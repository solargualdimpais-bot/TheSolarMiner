"""Strict JSON IPC primitives for an isolated connector worker.

Peer identity is checked with SO_PEERCRED on Linux. Socket permissions and a
separate Unix UID are mandatory for operational use; tests using one UID prove
protocol behavior only, not isolation enforcement.
"""
from __future__ import annotations
import json, os, socket, struct
from typing import Any

PROTOCOL_VERSION = 1
MAX_MESSAGE = 65536
ALLOWED_OPERATIONS = {"health", "tcp_probe", "deye_fc03_read"}

class IPCError(RuntimeError): pass

def _peer_uid(sock: socket.socket) -> int:
    if not hasattr(socket, "SO_PEERCRED"):
        raise IPCError("peer_credentials_unsupported")
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", raw)
    return uid

def encode_message(message: dict[str, Any]) -> bytes:
    if not isinstance(message, dict) or len(json.dumps(message, separators=(",", ":")).encode()) > MAX_MESSAGE:
        raise IPCError("ipc_message_invalid_or_too_large")
    return json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"

def recv_message(sock: socket.socket) -> dict[str, Any]:
    data=bytearray()
    while len(data)<=MAX_MESSAGE:
        chunk=sock.recv(min(4096,MAX_MESSAGE+1-len(data)))
        if not chunk: break
        data.extend(chunk)
        if b"\n" in chunk: break
    if not data or len(data)>MAX_MESSAGE or b"\n" not in data: raise IPCError("ipc_frame_invalid")
    line=bytes(data).split(b"\n",1)[0]
    try: msg=json.loads(line)
    except (json.JSONDecodeError,UnicodeDecodeError) as exc: raise IPCError("ipc_json_invalid") from exc
    if not isinstance(msg,dict): raise IPCError("ipc_message_must_be_object")
    return msg

def validate_request(msg: dict[str, Any]) -> dict[str, Any]:
    if set(msg) != {"protocol_version","request_id","operation","arguments"}: raise IPCError("ipc_schema_invalid")
    if msg.get("protocol_version") != PROTOCOL_VERSION: raise IPCError("ipc_version_invalid")
    rid=msg.get("request_id")
    if not isinstance(rid,str) or not 1<=len(rid)<=80: raise IPCError("ipc_request_id_invalid")
    op=msg.get("operation")
    if op not in ALLOWED_OPERATIONS: raise IPCError("ipc_operation_not_allowed")
    args=msg.get("arguments")
    if not isinstance(args,dict) or len(json.dumps(args))>16000: raise IPCError("ipc_arguments_invalid")
    if op=="deye_fc03_read":
        if set(args)-{"host","port","unit_id","start_address","count","timeout"}: raise IPCError("ipc_argument_not_allowed")
        if not isinstance(args.get("host"),str) or not args["host"]: raise IPCError("ipc_host_required")
    elif op=="tcp_probe":
        if set(args)-{"host","port","timeout"}: raise IPCError("ipc_argument_not_allowed")
    elif args: raise IPCError("ipc_arguments_not_allowed_for_operation")
    return msg

def verify_peer(sock: socket.socket, allowed_uid: int) -> None:
    if isinstance(allowed_uid,bool) or not isinstance(allowed_uid,int) or allowed_uid<0: raise IPCError("expected_peer_uid_required")
    if _peer_uid(sock) != allowed_uid: raise IPCError("ipc_peer_uid_denied")

def request(sock: socket.socket, operation: str, arguments: dict[str,Any], timeout: float=3.0) -> dict[str,Any]:
    if not 0.1<=timeout<=30: raise IPCError("ipc_timeout_invalid")
    import uuid
    sock.settimeout(timeout)
    msg={"protocol_version":PROTOCOL_VERSION,"request_id":str(uuid.uuid4()),"operation":operation,"arguments":arguments}
    validate_request(msg); sock.sendall(encode_message(msg)); response=recv_message(sock)
    if response.get("protocol_version")!=PROTOCOL_VERSION or response.get("request_id")!=msg["request_id"] or not isinstance(response.get("ok"),bool): raise IPCError("ipc_response_invalid")
    if not response["ok"]: raise IPCError("worker_operation_failed")
    result=response.get("result")
    if not isinstance(result,dict): raise IPCError("ipc_result_invalid")
    return result
