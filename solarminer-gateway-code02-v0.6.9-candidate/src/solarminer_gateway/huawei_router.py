"""Read-only Huawei HiLink client inventory for local MAC/IP association.

The router's HiLink WebUI API is not a stable public contract. This adapter
uses only the read-only ``wlan/host-list`` endpoint and fails closed when the
router firmware does not support the expected authenticated interface.
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import ipaddress
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
MAX_RESPONSE_BYTES = 256_000


class HuaweiRouterError(ValueError):
    """Sanitized error raised by the Huawei read-only adapter."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HuaweiRouterError("huawei_router_redirect_refused")


class HuaweiHiLinkClient:
    def __init__(self, config: dict[str, Any], timeout: float = 4.0):
        try:
            address = ipaddress.ip_address(str(config.get("host", "")))
        except ValueError as exc:
            raise HuaweiRouterError("huawei_router_private_ip_required") from exc
        if (address.version != 4 or not address.is_private or address.is_loopback
                or address.is_link_local or address.is_multicast or address.is_unspecified):
            raise HuaweiRouterError("huawei_router_private_ip_required")
        self.base = f"http://{address}/"
        self.username = str(config.get("username", "admin"))
        self.password = str(config.get("password", ""))
        if not self.username or len(self.username) > 128 or not self.password or len(self.password) > 512:
            raise HuaweiRouterError("huawei_router_credentials_required")
        self.timeout = max(1.0, min(float(timeout), 6.0))
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies), _NoRedirect())
        self.token = ""

    def _request(self, path: str, *, body: bytes | None = None, token: bool = False) -> tuple[bytes, Any]:
        headers = {"Accept": "application/xml,text/xml", "User-Agent": "SolarMiner-Gateway/0.6.86"}
        if body is not None:
            headers["Content-Type"] = "application/xml; charset=UTF-8"
        if token and self.token:
            headers["__RequestVerificationToken"] = self.token
        request = urllib.request.Request(self.base + path.lstrip("/"), data=body, headers=headers, method="POST" if body is not None else "GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise HuaweiRouterError("huawei_router_response_too_large")
                return raw, response.headers
        except HuaweiRouterError:
            raise
        except urllib.error.HTTPError as exc:
            raise HuaweiRouterError(f"huawei_router_http_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HuaweiRouterError("huawei_router_unreachable") from exc

    @staticmethod
    def _xml(raw: bytes) -> ET.Element:
        try:
            return ET.fromstring(raw)
        except ET.ParseError as exc:
            raise HuaweiRouterError("huawei_router_unexpected_response") from exc

    @staticmethod
    def _text(root: ET.Element, name: str, default: str = "") -> str:
        if root.tag.rsplit("}", 1)[-1] == name:
            return (root.text or "").strip() or default
        item = root.find(f".//{name}")
        return (item.text or "").strip() if item is not None else default

    def _load_token(self) -> None:
        raw, headers = self._request("api/webserver/SesTokInfo")
        root = self._xml(raw)
        self.token = self._text(root, "TokInfo") or headers.get("__RequestVerificationToken", "")
        if not self.token:
            raise HuaweiRouterError("huawei_router_session_token_missing")

    def _login(self) -> None:
        self._load_token()
        raw, headers = self._request("api/user/state-login", token=True)
        state = self._xml(raw)
        if self._text(state, "State") == "0":
            return
        # password_type=4 is the HiLink challenge hash. Older modes transmit
        # a base64-encoded plaintext password; refuse those on HTTP.
        if self._text(state, "password_type") != "4":
            raise HuaweiRouterError("huawei_router_secure_login_unsupported")
        password_hash = base64.b64encode(hashlib.sha256(self.password.encode("utf-8")).hexdigest().encode("ascii"))
        challenge = self.username.encode("utf-8") + password_hash + self.token.encode("utf-8")
        response_hash = base64.b64encode(hashlib.sha256(challenge).hexdigest().encode("ascii")).decode("ascii")
        request_root = ET.Element("request")
        # The 4G CPE 5 web UI asks only for a password. Keep the fixed admin
        # identity in the challenge hash, but omit Username from the XML body
        # to support the password-only login flow discussed for this firmware.
        ET.SubElement(request_root, "Password").text = response_hash
        ET.SubElement(request_root, "password_type").text = "4"
        payload = ET.tostring(request_root, encoding="utf-8", xml_declaration=True)
        raw, headers = self._request("api/user/login", body=payload, token=True)
        result = self._xml(raw)
        if self._text(result, "response") != "OK":
            raise HuaweiRouterError("huawei_router_login_rejected")
        self.token = headers.get("__RequestVerificationTokenone", "") or headers.get("__RequestVerificationToken", "") or self.token

    def clients(self) -> list[dict[str, str]]:
        self._login()
        raw, _ = self._request("api/wlan/host-list", token=True)
        root = self._xml(raw)
        result: list[dict[str, str]] = []
        for node in root.findall(".//Host"):
            mac = (self._text(node, "MacAddress") or self._text(node, "MACAddress")).upper()
            ip = self._text(node, "IpAddress") or self._text(node, "IPAddress")
            if not MAC_RE.fullmatch(mac):
                continue
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
                continue
            result.append({"mac": mac, "ip": str(address), "name": self._text(node, "HostName")[:120]})
        return result


def read_huawei_clients(config: dict[str, Any]) -> list[dict[str, str]]:
    return HuaweiHiLinkClient(config).clients()
