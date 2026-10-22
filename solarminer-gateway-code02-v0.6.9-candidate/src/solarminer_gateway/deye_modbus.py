"""Conservative read-only Modbus TCP transport for Deye-family devices.

This module intentionally ships without a register map. No register address,
scale, unit, or model compatibility is inferred from TCP reachability. A
model-specific, provenance-bearing register map must be reviewed and signed
before metric decoding can be enabled.
"""
from __future__ import annotations

import ipaddress
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any

MAX_REGISTERS = 125
DEFAULT_PORT = 502


class ModbusError(RuntimeError):
    """Base exception for protocol and communication failures."""


class ModbusTimeout(ModbusError):
    pass


class ModbusProtocolError(ModbusError):
    pass


class ModbusExceptionResponse(ModbusError):
    def __init__(self, function_code: int, exception_code: int):
        self.function_code = function_code
        self.exception_code = exception_code
        super().__init__(f"modbus_exception:function={function_code}:code={exception_code}")


def validate_target(host: str, port: int, unit_id: int, timeout: float) -> tuple[str, int, int, float]:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("ip_literal_required") from exc
    if not (ip.is_private or ip.is_link_local) or ip.is_loopback or ip.is_multicast or ip.is_unspecified:
        raise ValueError("private_or_link_local_target_required")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    if isinstance(unit_id, bool) or not isinstance(unit_id, int) or not 0 <= unit_id <= 247:
        raise ValueError("invalid_unit_id")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 5.0:
        raise ValueError("invalid_timeout")
    return str(ip), port, unit_id, float(timeout)


@dataclass(frozen=True)
class ModbusReadResult:
    host: str
    port: int
    unit_id: int
    function_code: int
    start_address: int
    register_count: int
    raw_registers: tuple[int, ...]
    read_at_epoch: float
    state: str = "RAW_READ_ONLY_UNMAPPED"
    units: str = "UNKNOWN"
    scaling: str = "UNKNOWN"
    model_compatibility: str = "NOT_VERIFIED"
    hardware_validation: str = "NOT_VALIDATED_ON_HARDWARE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host, "port": self.port, "unit_id": self.unit_id,
            "function_code": self.function_code, "start_address": self.start_address,
            "register_count": self.register_count, "raw_registers": list(self.raw_registers),
            "read_at_epoch": self.read_at_epoch, "state": self.state,
            "units": self.units, "scaling": self.scaling,
            "model_compatibility": self.model_compatibility,
            "hardware_validation": self.hardware_validation,
            "control_commands_sent": False,
        }


def read_holding_registers(host: str, start_address: int, count: int, port: int = DEFAULT_PORT,
                           unit_id: int = 1, timeout: float = 1.5,
                           socket_factory=socket.create_connection) -> ModbusReadResult:
    """Read holding registers using FC03 only; this function has no write path."""
    address, port, unit_id, timeout = validate_target(host, port, unit_id, timeout)
    if isinstance(start_address, bool) or not isinstance(start_address, int) or not 0 <= start_address <= 65535:
        raise ValueError("invalid_start_address")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_REGISTERS:
        raise ValueError("invalid_register_count")
    if start_address + count > 65536:
        raise ValueError("register_range_overflow")

    transaction_id = 1  # Single request per socket; deterministic and easy to validate.
    pdu = struct.pack(">BHH", 0x03, start_address, count)
    request = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu
    try:
        with socket_factory((address, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            header = _recv_exact(sock, 7)
            rx_tid, protocol_id, length, rx_unit = struct.unpack(">HHHB", header)
            if rx_tid != transaction_id or protocol_id != 0 or rx_unit != unit_id or not 2 <= length <= 254:
                raise ModbusProtocolError("invalid_mbap_header")
            pdu_response = _recv_exact(sock, length - 1)
    except socket.timeout as exc:
        raise ModbusTimeout("modbus_timeout") from exc
    except OSError as exc:
        raise ModbusError(f"modbus_connection_error:{type(exc).__name__}") from exc

    function_code = pdu_response[0]
    if function_code == 0x83:
        if len(pdu_response) != 2:
            raise ModbusProtocolError("invalid_exception_response")
        raise ModbusExceptionResponse(0x03, pdu_response[1])
    if function_code != 0x03 or len(pdu_response) < 2:
        raise ModbusProtocolError("unexpected_function_or_short_response")
    byte_count = pdu_response[1]
    if byte_count != count * 2 or len(pdu_response) != 2 + byte_count:
        raise ModbusProtocolError("invalid_register_payload_length")
    registers = struct.unpack(f">{count}H", pdu_response[2:])
    return ModbusReadResult(address, port, unit_id, 0x03, start_address, count,
                            tuple(registers), time.time())


def read_device_identification(host: str, port: int = DEFAULT_PORT, unit_id: int = 1,
                               timeout: float = 1.5,
                               socket_factory=socket.create_connection) -> dict[str, Any]:
    """Probe Modbus with the standard Read Device Identification request.

    Unlike FC03 this does not guess a vendor register address. Some devices do
    not implement FC43/MEI 14; an exception response still proves Modbus was
    reached, while a timeout remains distinguishable from a closed TCP port.
    """
    address, port, unit_id, timeout = validate_target(host, port, unit_id, timeout)
    transaction_id = 1
    # FC43 / MEI 14 / Read Device ID / Basic identification / object 0.
    pdu = bytes((0x2B, 0x0E, 0x01, 0x00))
    request = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu
    try:
        with socket_factory((address, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            header = _recv_exact(sock, 7)
            rx_tid, protocol_id, length, rx_unit = struct.unpack(">HHHB", header)
            if rx_tid != transaction_id or protocol_id != 0 or rx_unit != unit_id or not 2 <= length <= 254:
                raise ModbusProtocolError("invalid_mbap_header")
            response = _recv_exact(sock, length - 1)
    except socket.timeout as exc:
        raise ModbusTimeout("modbus_identification_timeout") from exc
    except OSError as exc:
        raise ModbusError(f"modbus_connection_error:{type(exc).__name__}") from exc

    function_code = response[0]
    if function_code == 0xAB:
        if len(response) != 2:
            raise ModbusProtocolError("invalid_device_identification_exception")
        raise ModbusExceptionResponse(0x2B, response[1])
    if function_code != 0x2B or len(response) < 7 or response[1] != 0x0E:
        raise ModbusProtocolError("invalid_device_identification_response")
    read_code, conformity, more_follows, next_object, object_count = response[2:7]
    if read_code not in (0x01, 0x02, 0x03) or more_follows not in (0x00, 0xFF):
        raise ModbusProtocolError("invalid_device_identification_fields")
    offset = 7
    objects = []
    for _ in range(object_count):
        if offset + 2 > len(response):
            raise ModbusProtocolError("truncated_device_identification_object")
        object_id, value_length = response[offset], response[offset + 1]
        offset += 2
        if offset + value_length > len(response):
            raise ModbusProtocolError("truncated_device_identification_value")
        value = response[offset:offset + value_length].decode("utf-8", "replace")
        objects.append({"id": object_id, "value": value})
        offset += value_length
    if offset != len(response):
        raise ModbusProtocolError("trailing_device_identification_data")
    return {"state": "modbus_identity_response", "read_device_id_code": read_code,
            "conformity_level": conformity, "more_follows": more_follows == 0xFF,
            "next_object_id": next_object, "objects": objects}


def _recv_exact(sock, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ModbusProtocolError("connection_closed_mid_response")
        data.extend(chunk)
    return bytes(data)


def documented_metrics(*_args, **_kwargs) -> dict[str, Any]:
    """Fail closed until an applicable, provenance-verified register map exists."""
    raise RuntimeError("model_specific_register_map_not_verified; raw reads only")
