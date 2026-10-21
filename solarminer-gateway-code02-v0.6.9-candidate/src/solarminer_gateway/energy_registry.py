"""Additive canonical equipment registry and supervised validation workflow.

No hardware operation is performed by this module. Test approval records operator
intent only; physical work remains manual and must follow manufacturer procedures.
"""
from __future__ import annotations
import json, re, sqlite3, uuid
from datetime import datetime, timezone
from typing import Any

TRUST = {"DOCUMENTED", "CANDIDATE", "INFERRED", "SIMULATED", "LIVE_UNVERIFIED", "PHYSICALLY_CORROBORATED", "BLOCKED", "UNKNOWN"}
CATEGORIES = {
    "inversores": "Inversores", "baterias": "Baterias", "mineradoras": "Mineradoras",
    "ev": "EV", "aqs": "AQS", "soalho-radiante": "Soalho Radiante",
}
TEST_STATES = {"PROPOSED", "APPROVED", "IN_PROGRESS", "PASS", "FAIL", "INCONCLUSIVE", "BLOCKED"}
DANGEROUS = re.compile(r"(desligar|desconectar|abrir|manipular|retirar|isolar)\s+(pain[eé]is?|strings?|cabos?|condutores?|baterias?|quadro|conectores?)|sob\s+carga|condutor(?:es)?\s+energizado|desativar\s+(?:bms|prote[cç][aã]o|alarme)", re.I)


def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def dumps(value: Any) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS energy_equipment(
      id TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL, manufacturer TEXT,
      model TEXT, firmware TEXT, logical_location TEXT, connector_id TEXT, protocol TEXT,
      connection_state TEXT NOT NULL DEFAULT 'UNKNOWN', last_communication_at TEXT,
      declared_capabilities_json TEXT NOT NULL DEFAULT '[]', implemented_capabilities_json TEXT NOT NULL DEFAULT '[]',
      verified_capabilities_json TEXT NOT NULL DEFAULT '[]', config_json TEXT NOT NULL DEFAULT '{}',
      limitations_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'CONFIGURED'
    );
    CREATE TABLE IF NOT EXISTS energy_readings(
      id TEXT PRIMARY KEY, equipment_id TEXT NOT NULL REFERENCES energy_equipment(id) ON DELETE CASCADE,
      field TEXT NOT NULL, value_json TEXT NOT NULL, unit TEXT, observed_at TEXT NOT NULL,
      source TEXT NOT NULL, trust TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '{}',
      UNIQUE(equipment_id,field,observed_at,source)
    );
    CREATE INDEX IF NOT EXISTS idx_energy_readings_latest ON energy_readings(equipment_id,field,observed_at);
    CREATE TABLE IF NOT EXISTS energy_physical_tests(
      id TEXT PRIMARY KEY, equipment_id TEXT NOT NULL REFERENCES energy_equipment(id) ON DELETE CASCADE,
      title TEXT NOT NULL, hypothesis TEXT NOT NULL, affected_fields_json TEXT NOT NULL,
      source_reference TEXT NOT NULL, initial_confidence TEXT NOT NULL, expected_result TEXT NOT NULL,
      preconditions_json TEXT NOT NULL, risks_json TEXT NOT NULL, instrumentation_json TEXT NOT NULL,
      manual_steps_json TEXT NOT NULL, stop_conditions_json TEXT NOT NULL, state TEXT NOT NULL,
      created_by TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL, approved_at TEXT,
      started_at TEXT, completed_at TEXT, result_json TEXT NOT NULL DEFAULT '{}',
      profile_version TEXT NOT NULL DEFAULT '1'
    );
    CREATE TABLE IF NOT EXISTS energy_test_evidence(
      id TEXT PRIMARY KEY, test_id TEXT NOT NULL REFERENCES energy_physical_tests(id) ON DELETE CASCADE,
      operator_id TEXT NOT NULL, observed_at TEXT NOT NULL, phase TEXT NOT NULL,
      observations_json TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', evidence_hash TEXT
    );
    """)


def equipment_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for source, target in (("declared_capabilities_json","declared_capabilities"),("implemented_capabilities_json","implemented_capabilities"),("verified_capabilities_json","verified_capabilities"),("config_json","config"),("limitations_json","limitations")):
        item[target] = json.loads(item.pop(source))
    return item


def upsert_equipment(conn: sqlite3.Connection, payload: dict[str, Any], equipment_id: str | None = None) -> dict[str, Any]:
    ensure_schema(conn)
    category = payload.get("category")
    if category not in CATEGORIES: raise ValueError("invalid_energy_category")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 160: raise ValueError("invalid_equipment_name")
    def strings(key: str, maximum: int = 4000) -> str:
        value = payload.get(key, [])
        if not isinstance(value, list) or len(dumps(value)) > maximum or any(not isinstance(x, str) for x in value): raise ValueError("invalid_" + key)
        return dumps(value)
    config = payload.get("config", {})
    if not isinstance(config, dict) or len(dumps(config)) > 8000: raise ValueError("invalid_config")
    identifier = equipment_id or str(uuid.uuid4()); stamp = now()
    fields = ("manufacturer", "model", "firmware", "logical_location", "connector_id", "protocol")
    vals = [payload.get(k) for k in fields]
    if any(v is not None and (not isinstance(v, str) or len(v) > 256) for v in vals): raise ValueError("invalid_equipment_metadata")
    conn.execute("""INSERT INTO energy_equipment(id,category,name,manufacturer,model,firmware,logical_location,connector_id,protocol,connection_state,declared_capabilities_json,implemented_capabilities_json,verified_capabilities_json,config_json,limitations_json,created_at,updated_at,status)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET category=excluded.category,name=excluded.name,manufacturer=excluded.manufacturer,model=excluded.model,firmware=excluded.firmware,logical_location=excluded.logical_location,connector_id=excluded.connector_id,protocol=excluded.protocol,declared_capabilities_json=excluded.declared_capabilities_json,implemented_capabilities_json=excluded.implemented_capabilities_json,config_json=excluded.config_json,limitations_json=excluded.limitations_json,updated_at=excluded.updated_at,status=excluded.status""",
      (identifier,category,name.strip(),*vals,payload.get("connection_state","UNKNOWN"),strings("declared_capabilities"),strings("implemented_capabilities"),strings("verified_capabilities"),dumps(config),strings("limitations"),stamp,stamp,payload.get("status","CONFIGURED")))
    row = conn.execute("SELECT * FROM energy_equipment WHERE id=?", (identifier,)).fetchone()
    return equipment_dict(row)


def list_equipment(conn: sqlite3.Connection, category: str | None = None) -> list[dict[str, Any]]:
    ensure_schema(conn)
    if category is not None and category not in CATEGORIES: raise ValueError("invalid_energy_category")
    rows = conn.execute("SELECT * FROM energy_equipment WHERE category=? ORDER BY name,id" if category else "SELECT * FROM energy_equipment ORDER BY category,name,id", (category,) if category else ()).fetchall()
    result = []
    for row in rows:
        item = equipment_dict(row)
        item["readings"] = latest_readings(conn, item["id"])
        item["trust_summary"] = summarize_trust(item["readings"])
        result.append(item)
    return result


def get_equipment(conn: sqlite3.Connection, equipment_id: str) -> dict[str, Any] | None:
    ensure_schema(conn); row = conn.execute("SELECT * FROM energy_equipment WHERE id=?", (equipment_id,)).fetchone()
    if not row: return None
    item = equipment_dict(row); item["readings"] = latest_readings(conn, equipment_id)
    item["tests"] = [dict(r) for r in conn.execute("SELECT id,title,state,created_at,completed_at FROM energy_physical_tests WHERE equipment_id=? ORDER BY created_at DESC", (equipment_id,)).fetchall()]
    item["trust_summary"] = summarize_trust(item["readings"]); return item


def add_reading(conn: sqlite3.Connection, equipment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_schema(conn)
    if not conn.execute("SELECT 1 FROM energy_equipment WHERE id=?", (equipment_id,)).fetchone(): raise LookupError("equipment_not_found")
    field, trust, source = payload.get("field"), payload.get("trust"), payload.get("source")
    if not isinstance(field,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}",field): raise ValueError("invalid_reading_field")
    if trust not in TRUST: raise ValueError("invalid_trust_class")
    if not isinstance(source,str) or not source or len(source)>256: raise ValueError("invalid_reading_source")
    if trust == "PHYSICALLY_CORROBORATED": raise ValueError("physical_corroboration_requires_test_evidence")
    observed = payload.get("observed_at") or now()
    if not isinstance(observed,str) or len(observed)>64: raise ValueError("invalid_observed_at")
    evidence = payload.get("evidence", {})
    if not isinstance(evidence,dict) or len(dumps(evidence))>8000: raise ValueError("invalid_evidence")
    rid = str(uuid.uuid4()); conn.execute("INSERT INTO energy_readings VALUES(?,?,?,?,?,?,?,?,?)", (rid,equipment_id,field,dumps(payload.get("value")),payload.get("unit"),observed,source,trust,dumps(evidence)))
    conn.execute("UPDATE energy_equipment SET connection_state=?,last_communication_at=?,updated_at=? WHERE id=?", ("CONNECTED" if trust in {"LIVE_UNVERIFIED","PHYSICALLY_CORROBORATED"} else "UNKNOWN", observed, now(), equipment_id))
    return dict(conn.execute("SELECT * FROM energy_readings WHERE id=?",(rid,)).fetchone())


def latest_readings(conn: sqlite3.Connection, equipment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT r.* FROM energy_readings r JOIN (SELECT field,MAX(observed_at) observed_at FROM energy_readings WHERE equipment_id=? GROUP BY field) x ON x.field=r.field AND x.observed_at=r.observed_at WHERE r.equipment_id=? ORDER BY r.field", (equipment_id,equipment_id)).fetchall()
    result=[]
    for row in rows:
        item=dict(row); item["value"] = json.loads(item.pop("value_json")); item["evidence"] = json.loads(item.pop("evidence_json")); result.append(item)
    return result


def summarize_trust(readings: list[dict[str, Any]]) -> dict[str, int]:
    summary={t:0 for t in sorted(TRUST)}
    for r in readings:
        if r.get("trust") in summary: summary[r["trust"]]+=1
    return summary


def propose_test(conn: sqlite3.Connection, equipment_id: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_schema(conn)
    if not conn.execute("SELECT 1 FROM energy_equipment WHERE id=?",(equipment_id,)).fetchone(): raise LookupError("equipment_not_found")
    required=("title","hypothesis","affected_fields","source_reference","initial_confidence","expected_result","preconditions","risks","instrumentation","manual_steps","stop_conditions")
    if any(k not in payload for k in required): raise ValueError("physical_test_fields_required")
    if any(not isinstance(payload[k],str) or not payload[k].strip() or len(payload[k])>2000 for k in ("title","hypothesis","source_reference","initial_confidence","expected_result")): raise ValueError("invalid_physical_test_text")
    for k in ("affected_fields","preconditions","risks","instrumentation","manual_steps","stop_conditions"):
        if not isinstance(payload[k],list) or not payload[k] or any(not isinstance(v,str) or not v.strip() or len(v)>1000 for v in payload[k]): raise ValueError("invalid_"+k)
    steps=" ".join(payload["manual_steps"]+payload["risks"])
    if DANGEROUS.search(steps):
        state="BLOCKED"
    else: state="PROPOSED"
    test_id=str(uuid.uuid4()); stamp=now()
    conn.execute("INSERT INTO energy_physical_tests(id,equipment_id,title,hypothesis,affected_fields_json,source_reference,initial_confidence,expected_result,preconditions_json,risks_json,instrumentation_json,manual_steps_json,stop_conditions_json,state,created_by,created_at,result_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (test_id,equipment_id,payload["title"],payload["hypothesis"],dumps(payload["affected_fields"]),payload["source_reference"],payload["initial_confidence"],payload["expected_result"],dumps(payload["preconditions"]),dumps(payload["risks"]),dumps(payload["instrumentation"]),dumps(payload["manual_steps"]),dumps(payload["stop_conditions"]),state,actor,stamp,dumps({"hardware_commands_executed":False,"reason":"dangerous_manual_step_requires_qualified_professional_or_blocked" if state=="BLOCKED" else "proposal_only_no_hardware_action"})))
    return get_test(conn,test_id)


def get_test(conn: sqlite3.Connection, test_id: str) -> dict[str, Any] | None:
    row=conn.execute("SELECT * FROM energy_physical_tests WHERE id=?",(test_id,)).fetchone()
    if not row:return None
    item=dict(row)
    for k in ("affected_fields_json","preconditions_json","risks_json","instrumentation_json","manual_steps_json","stop_conditions_json","result_json"):
        item[k[:-5] if k.endswith("_json") else k]=json.loads(item.pop(k))
    item["evidence"]=[dict(r) for r in conn.execute("SELECT id,operator_id,observed_at,phase,observations_json,notes,evidence_hash FROM energy_test_evidence WHERE test_id=? ORDER BY observed_at",(test_id,)).fetchall()]
    for ev in item["evidence"]: ev["observations"] = json.loads(ev.pop("observations_json"))
    return item


def approve_test(conn: sqlite3.Connection, test_id: str, actor: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed: raise PermissionError("explicit_physical_test_confirmation_required")
    row=conn.execute("SELECT state FROM energy_physical_tests WHERE id=?",(test_id,)).fetchone()
    if not row: raise LookupError("physical_test_not_found")
    if row["state"]!="PROPOSED": raise ValueError("physical_test_not_approvable")
    stamp=now(); conn.execute("UPDATE energy_physical_tests SET state='APPROVED',approved_by=?,approved_at=? WHERE id=?",(actor,stamp,test_id)); return get_test(conn,test_id)


def record_test_event(conn: sqlite3.Connection, test_id: str, actor: str, phase: str, observations: dict[str, Any], notes: str="", result: str | None=None) -> dict[str, Any]:
    if phase not in {"BEFORE","DURING","AFTER","OPERATOR_NOTE"}: raise ValueError("invalid_evidence_phase")
    if result is not None and result not in {"PASS","FAIL","INCONCLUSIVE"}: raise ValueError("invalid_physical_test_result")
    if result is not None and phase != "AFTER": raise ValueError("test_result_requires_after_phase")
    if not isinstance(observations,dict) or len(dumps(observations))>16000 or not isinstance(notes,str) or len(notes)>4000: raise ValueError("invalid_test_evidence")
    row=conn.execute("SELECT * FROM energy_physical_tests WHERE id=?",(test_id,)).fetchone()
    if not row: raise LookupError("physical_test_not_found")
    if row["state"] not in {"APPROVED","IN_PROGRESS"}: raise ValueError("physical_test_not_recordable")
    stamp=now(); conn.execute("INSERT INTO energy_test_evidence VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),test_id,actor,stamp,phase,dumps(observations),notes,None))
    if row["state"]=="APPROVED": conn.execute("UPDATE energy_physical_tests SET state='IN_PROGRESS',started_at=? WHERE id=?",(stamp,test_id))
    if result is not None:
        corroborated_fields=[]
        if result=="PASS" and phase=="AFTER":
            # Corroborate only a LIVE_UNVERIFIED reading whose exact value was
            # observed in the recorded AFTER evidence. Never promote SIMULATED.
            for field in json.loads(row["affected_fields_json"]):
                if field not in observations: continue
                reading=conn.execute("SELECT id,value_json FROM energy_readings WHERE equipment_id=? AND field=? AND trust='LIVE_UNVERIFIED' ORDER BY observed_at DESC LIMIT 1",(row["equipment_id"],field)).fetchone()
                if reading is None: continue
                try: matches=json.loads(reading["value_json"]) == observations[field]
                except (ValueError,TypeError): matches=False
                if matches:
                    conn.execute("UPDATE energy_readings SET trust='PHYSICALLY_CORROBORATED',evidence_json=json_set(evidence_json,'$.physical_test_id',?,'$.corroborated_at',?,'$.operator_id',?,'$.corroborated_condition','AFTER observation exact-value match') WHERE id=?",(test_id,stamp,actor,reading["id"]))
                    corroborated_fields.append(field)
        conn.execute("UPDATE energy_physical_tests SET state=?,completed_at=?,result_json=? WHERE id=?",(result,stamp,dumps({"result":result,"hardware_commands_executed":False,"operator_recorded":True,"corroborated_fields":corroborated_fields,"limitations":"A PASS applies only to fields explicitly observed after the procedure and matched to LIVE_UNVERIFIED readings; future readings are not automatically validated."}),test_id))
    return get_test(conn,test_id)
