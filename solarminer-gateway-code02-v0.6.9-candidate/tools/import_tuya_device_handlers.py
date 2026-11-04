#!/usr/bin/env python3
"""Compile the MIT-licensed Tuya Device Handlers quirks into safe JSON data.

This tool parses handler syntax with Python's AST. It never imports or executes
upstream Python modules. Output is a pinned, offline catalog for the Gateway.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys


def literal(node: ast.AST | None):
    try:
        return ast.literal_eval(node) if node is not None else None
    except (ValueError, TypeError):
        return None


def calls_in_chain(node: ast.AST) -> list[ast.Call]:
    if not isinstance(node, ast.Call):
        return []
    result = calls_in_chain(node.func.value) if isinstance(node.func, ast.Attribute) else []
    result.append(node)
    return result


def kw(call: ast.Call, name: str):
    return next((item.value for item in call.keywords if item.arg == name), None)


def dpmode(node: ast.AST | None) -> tuple[bool, bool]:
    names = {part.attr for part in ast.walk(node) if isinstance(part, ast.Attribute)} if node else set()
    return "READ" in names, "WRITE" in names


def condition_for(name: str | None, helpers: dict[str, ast.FunctionDef]):
    if not name or name not in helpers:
        return {"id": name, "supported": False}
    fn = helpers[name]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        left = node.left
        if not isinstance(left, ast.Call) or not isinstance(left.func, ast.Attribute) or left.func.attr != "get":
            continue
        field = literal(left.args[0]) if left.args else None
        value = literal(node.comparators[0])
        op = type(node.ops[0]).__name__
        if isinstance(field, str) and isinstance(value, (int, float)) and op in {"GtE", "Gt", "LtE", "Lt", "Eq", "NotEq"}:
            return {"id": name, "supported": True, "status_code": field, "operator": op, "value": value}
    if any(isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) for node in ast.walk(fn)):
        return {"id": name, "supported": True, "negates": name.removeprefix("_is_")}
    return {"id": name, "supported": False}


def compile_file(path: pathlib.Path, root: pathlib.Path) -> dict | None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helpers = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    expr = next((n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                 and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "DeviceQuirk"
                         for c in ast.walk(n.value))), None)
    if expr is None:
        return None
    chain = calls_in_chain(expr)
    methods = [(call.func.attr, call) for call in chain if isinstance(call.func, ast.Attribute)]
    product_call = next((call for name, call in methods if name == "applies_to"), None)
    product_id = literal(kw(product_call, "product_id")) if product_call else None
    if not isinstance(product_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id):
        return None
    profile = {"product_id": product_id, "category": path.parent.name,
               "source_file": path.relative_to(root).as_posix(), "dps": [], "operations": []}
    for key in ("manufacturer", "model", "model_id"):
        value = literal(kw(product_call, key)) if product_call else None
        if isinstance(value, str):
            profile[key] = value[:120]
    doc = ast.get_docstring(tree)
    if doc:
        profile["description"] = doc.splitlines()[0][:200]
    dps: dict[tuple[int, str], dict] = {}
    for name, call in methods:
        args = {item.arg: literal(item.value) for item in call.keywords if item.arg}
        if name == "override_category" and isinstance(args.get("category"), str):
            profile["operations"].append({"op": name, "category": args["category"]})
            profile["category_override"] = args["category"]
        elif name.startswith("add_dpid_"):
            dp_id, code = args.get("dpid"), args.get("dpcode")
            if isinstance(dp_id, int) and isinstance(code, str):
                read, write = dpmode(kw(call, "dpmode"))
                kind = name.removeprefix("add_dpid_")
                value_range = {k: args[k] for k in ("unit", "min", "max", "scale", "step", "enum_range", "label_range") if k in args}
                if kind == "integer":
                    value_range = {k: args.get(k) for k in ("unit", "min", "max", "scale", "step")}
                if kind == "enum": value_range = {"range": args.get("enum_range", [])}
                if kind == "bitmap": value_range = {"label": args.get("label_range", [])}
                cond_node = kw(call, "apply_when")
                cond_name = ast.unparse(cond_node) if cond_node else None
                condition = condition_for(cond_name, helpers) if cond_name else None
                item = {"id": dp_id, "code": code, "type": {"integer":"Integer", "boolean":"Boolean", "enum":"Enum", "bitmap":"Bitmap"}.get(kind, kind.title()),
                        "read_supported": read, "write_supported": write,
                        "range": value_range, "source": "home-assistant-libs/tuya-device-handlers"}
                if condition: item["condition"] = condition
                dps[(dp_id, code)] = item
                profile["operations"].append({"op": name, **item})
        elif name == "remove_dpid":
            dp_id, code = args.get("dpid"), args.get("dpcode")
            if isinstance(dp_id, int) and isinstance(code, str):
                dps.pop((dp_id, code), None)
                profile["operations"].append({"op": name, "id": dp_id, "code": code})
        elif name in {"set_dpid_strategy_to_enum", "map_dpid_initial_status_values"}:
            entry = {"op": name}
            for key in ("dpid", "dpcode", "enum_mapping_map", "status_mapping"):
                if args.get(key) is not None: entry[key] = args[key]
            profile["operations"].append(entry)
        elif name == "override_dpid_type_information_cls":
            dp_id, code = args.get("dpid"), args.get("dpcode")
            type_node = kw(call, "type_information_cls")
            if isinstance(dp_id, int) and isinstance(code, str):
                class_name = ast.unparse(type_node) if type_node else "unknown"
                profile["operations"].append({"op": name, "id": dp_id, "code": code, "type_information": class_name})
        elif name not in {"applies_to", "register"}:
            # Preserve framework-specific declarative operations for the
            # Gateway catalog even where they have no native card equivalent.
            profile["operations"].append({"op": name, "source_expression": ast.unparse(call)[:600]})
    profile["dps"] = list(dps.values())
    return profile


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: import_tuya_device_handlers.py <tuya-device-handlers-checkout>", file=sys.stderr)
        return 2
    checkout = pathlib.Path(sys.argv[1]).resolve()
    source_dir = checkout / "src" / "tuya_device_handlers" / "devices"
    output = pathlib.Path(__file__).resolve().parents[1] / "src" / "solarminer_gateway" / "tuya_device_handlers_catalog.json"
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    profiles = [row for file in sorted(source_dir.rglob("*.py")) if file.name != "__init__.py"
                if (row := compile_file(file, source_dir)) is not None]
    catalog = {"schema_version": 1, "source": {"repository": "home-assistant-libs/tuya-device-handlers",
               "url": "https://github.com/home-assistant-libs/tuya-device-handlers", "commit": commit,
               "license": "MIT", "license_file": "LICENSE.md",
               "notice": "Declarative handler metadata compiled from upstream AST. Upstream code is not executed."},
               "profiles": profiles}
    output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"compiled {len(profiles)} exact-product handlers; {sum(len(p['dps']) for p in profiles)} DPS definitions; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
