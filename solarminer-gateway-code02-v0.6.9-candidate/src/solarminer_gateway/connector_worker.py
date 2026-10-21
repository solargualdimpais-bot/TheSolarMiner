"""Minimal allowlisted connector worker process. No shell, DB, or write protocol."""
from __future__ import annotations
import argparse, json, os, socket, stat, uuid
from pathlib import Path
from . import worker_ipc


def execute(msg):
    msg=worker_ipc.validate_request(msg); op=msg["operation"]; args=msg["arguments"]
    if op=="health": return {"worker":"ready","connector_id":os.environ.get("SOLARMINER_CONNECTOR_ID","unknown"),"hardware_commands_sent":False}
    if op=="tcp_probe":
        import ipaddress
        import socket as net
        host=args.get("host"); port=args.get("port",502); timeout=args.get("timeout",1.5)
        ip=ipaddress.ip_address(host)
        if not (ip.is_private or ip.is_link_local) or ip.is_loopback or ip.is_multicast or ip.is_unspecified: raise ValueError("private_device_target_required")
        if isinstance(port,bool) or not isinstance(port,int) or not 1<=port<=65535: raise ValueError("invalid_port")
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0.1<=timeout<=5: raise ValueError("invalid_timeout")
        try:
            with net.create_connection((str(ip),port),timeout=float(timeout)): pass
            reachable = True
            error_type = None
        except OSError as exc:
            reachable = False
            error_type = type(exc).__name__
        return {"reachable":reachable,"host":str(ip),"port":port,
                "error_type":error_type,"application_protocol_verified":False,
                "hardware_commands_sent":False,"payload_sent":False}
    if op=="deye_fc03_read":
        from .deye_modbus import read_holding_registers
        result=read_holding_registers(**args)
        return result.as_dict()
    raise ValueError("operation_not_allowed")


def serve(path: str, allowed_gateway_uid: int) -> None:
    socket_path=Path(path)
    if not socket_path.is_absolute() or len(str(socket_path))>100: raise ValueError("invalid_socket_path")
    socket_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if socket_path.exists():
        st=socket_path.lstat()
        if not stat.S_ISSOCK(st.st_mode): raise RuntimeError("refusing_to_replace_non_socket")
        socket_path.unlink()
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    server.bind(str(socket_path)); os.chmod(socket_path,0o660); server.listen(8); server.settimeout(1.0)
    try:
        while True:
            try: client,_=server.accept()
            except socket.timeout: continue
            with client:
                client.settimeout(2.0)
                msg = None
                try:
                    worker_ipc.verify_peer(client,allowed_gateway_uid)
                    msg=worker_ipc.recv_message(client); result=execute(msg)
                    response={"protocol_version":worker_ipc.PROTOCOL_VERSION,"request_id":msg.get("request_id"),"ok":True,"result":result}
                except Exception as exc:
                    # Error class only; no exception text that could leak paths, secrets or arguments.
                    response={"protocol_version":worker_ipc.PROTOCOL_VERSION,"request_id":(msg.get("request_id") if isinstance(msg,dict) else None),"ok":False,"error":type(exc).__name__}
                try: client.sendall(worker_ipc.encode_message(response))
                except (OSError,worker_ipc.IPCError): pass
    finally:
        server.close(); socket_path.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--socket",required=True); parser.add_argument("--gateway-uid",required=True,type=int)
    args=parser.parse_args(); serve(args.socket,args.gateway_uid)
if __name__=="__main__": main()
