"""Read-only Huawei HiLink client inventory for local MAC/IP association.

The router's HiLink WebUI API is not a stable public contract. This adapter
uses read-only LAN, WLAN, and DHCP inventory endpoints, with bounded timeouts
and per-endpoint diagnostics because support varies by router firmware.
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import ipaddress
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
SESSION_RE = re.compile(r"^SessionID=([A-Za-z0-9+/=_-]{1,512})$")
MAX_RESPONSE_BYTES = 256_000
MIN_API_REQUEST_GAP_SECONDS = 2.5

# Read-only inventory variants verified/maintained per Huawei model. Keep an
# explicit generic fallback; do not infer firmware behavior from version
# number formatting alone. New exact firmware profiles can be added here as
# they are observed and validated.
HUAWEI_INVENTORY_PROFILES: dict[str, tuple[str, ...]] = {
    "B636-336": (
        "api/system/HostInfo",
    ),
}
HUAWEI_STATIC_DHCP_PROFILES: dict[str, str] = {
    "B636-336": "api/dhcp/static-addr-info",
}
GENERIC_INVENTORY_ENDPOINTS = (
    "api/lan/HostInfo",
    "api/system/HostInfo",
    "api/wlan/host-list",
    "api/dhcp/dhcp-host-info",
)


class HuaweiRouterError(ValueError):
    """Sanitized error raised by the Huawei read-only adapter."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HuaweiRouterError("huawei_router_redirect_refused")


class HuaweiHiLinkClient:
    # Huawei firmwares vary considerably. Bound each HTTP call, and also the
    # whole inventory request, so trying alternate read-only APIs cannot hang
    # a Gateway worker indefinitely.
    def __init__(self, config: dict[str, Any], timeout: float = 15.0, total_timeout: float = 150.0):
        try:
            address = ipaddress.ip_address(str(config.get("host", "")))
        except ValueError as exc:
            raise HuaweiRouterError("huawei_router_private_ip_required") from exc
        if (address.version != 4 or not address.is_private or address.is_loopback
                or address.is_link_local or address.is_multicast or address.is_unspecified):
            raise HuaweiRouterError("huawei_router_private_ip_required")
        self.base = f"http://{address}/"
        discovered = config.get("discovered_device", {})
        self.discovered_device = discovered if isinstance(discovered, dict) else {}
        self.username = str(config.get("username", "admin"))
        self.password = str(config.get("password", ""))
        if not self.username or len(self.username) > 128 or not self.password or len(self.password) > 512:
            raise HuaweiRouterError("huawei_router_credentials_required")
        self.timeout = max(1.0, min(float(timeout), 20.0))
        self.deadline = time.monotonic() + max(self.timeout, min(float(total_timeout), 150.0))
        self.last_diagnostics: dict[str, Any] = {}
        self.last_request_completed_at: float | None = None
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies), _NoRedirect())
        self.token = ""
        self.session_id = ""
        self.login_state = "unknown"

    def _refresh_session_headers(self, headers: Any) -> None:
        """Keep HiLink's rotating session cookie and verification token in sync.

        Some Huawei WebUIs issue a new verification token (and occasionally a
        new SessionID) after every request. Reusing the token from SesTokInfo
        for all inventory calls can produce 100003/125003 despite reaching
        the router successfully.
        """
        if headers is None:
            return
        get = getattr(headers, "get", lambda *_args, **_kwargs: "")
        next_token = (get("__RequestVerificationTokenone", "")
                      or get("__RequestVerificationTokentwo", "")
                      or get("__RequestVerificationToken", ""))
        if next_token:
            self.token = str(next_token).split("#", 1)[0].strip()
        cookie_header = get("Set-Cookie", "")
        match = re.search(r"(?:^|[,; ]+)SessionID=([^;, ]+)", str(cookie_header), re.I)
        if match:
            self.session_id = match.group(1)
        try:
            for cookie in self.cookies:
                if cookie.name.lower() == "sessionid" and cookie.value:
                    self.session_id = cookie.value
                    break
        except TypeError:
            pass

    def _request(self, path: str, *, body: bytes | None = None, token: bool = False) -> tuple[bytes, Any]:
        self._wait_for_request_slot()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HuaweiRouterError("huawei_router_total_timeout")
        headers = {"Accept": "application/xml,text/xml", "User-Agent": "SolarMiner-Gateway/0.6.152"}
        headers["X-Requested-With"] = "XMLHttpRequest"
        if self.session_id:
            headers["Cookie"] = f"SessionID={self.session_id}"
        if body is not None:
            headers["Content-Type"] = "application/xml; charset=UTF-8"
        if token and self.token:
            headers["__RequestVerificationToken"] = self.token
        request = urllib.request.Request(self.base + path.lstrip("/"), data=body, headers=headers, method="POST" if body is not None else "GET")
        try:
            with self.opener.open(request, timeout=min(self.timeout, remaining)) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise HuaweiRouterError("huawei_router_response_too_large")
                self._refresh_session_headers(response.headers)
                return raw, response.headers
        except HuaweiRouterError:
            raise
        except urllib.error.HTTPError as exc:
            raise HuaweiRouterError(f"huawei_router_http_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HuaweiRouterError("huawei_router_unreachable") from exc
        finally:
            self.last_request_completed_at = time.monotonic()

    def _wait_for_request_slot(self) -> None:
        """Leave a firmware-friendly gap between all HiLink HTTP requests."""
        if self.last_request_completed_at is None:
            return
        wait_seconds = (self.last_request_completed_at + MIN_API_REQUEST_GAP_SECONDS
                        - time.monotonic())
        if wait_seconds <= 0:
            return
        if time.monotonic() + wait_seconds >= self.deadline:
            raise HuaweiRouterError("huawei_router_total_timeout")
        time.sleep(wait_seconds)

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
        wanted = name.lower()
        item = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == wanted), None)
        return (item.text or "").strip() if item is not None else default

    def _load_token(self) -> None:
        raw, headers = self._request("api/webserver/SesTokInfo")
        root = self._xml(raw)
        self.token = self._text(root, "TokInfo") or headers.get("__RequestVerificationToken", "")
        session_info = self._text(root, "SesInfo")
        match = SESSION_RE.fullmatch(session_info)
        self.session_id = match.group(1) if match else ""
        if not self.token:
            raise HuaweiRouterError("huawei_router_session_token_missing")
        self._refresh_session_headers(headers)

    def _login(self) -> None:
        self._load_token()
        raw, headers = self._request("api/user/state-login", token=True)
        state = self._xml(raw)
        state_value = self._text(state, "State", "unknown")
        self.login_state = "authenticated_or_login_disabled" if state_value == "0" else "login_required"
        if state_value == "0":
            return
        # password_type=4 is the HiLink challenge hash. Older modes transmit
        # a base64-encoded plaintext password; refuse those on HTTP.
        if self._text(state, "password_type") != "4":
            raise HuaweiRouterError("huawei_router_secure_login_unsupported")
        password_hash = base64.b64encode(hashlib.sha256(self.password.encode("utf-8")).hexdigest().encode("ascii"))
        challenge = self.username.encode("utf-8") + password_hash + self.token.encode("utf-8")
        response_hash = base64.b64encode(hashlib.sha256(challenge).hexdigest().encode("ascii")).decode("ascii")
        # Password-only CPE firmware still uses the fixed admin identity in
        # the challenge hash. Try its browser-shaped body first, then the
        # compatible legacy body with Username if the modem rejects that XML.
        # Both attempts use the same challenge and never send the password in
        # clear text.
        for include_username in (False, True):
            request_root = ET.Element("request")
            if include_username:
                ET.SubElement(request_root, "Username").text = self.username
            ET.SubElement(request_root, "Password").text = response_hash
            ET.SubElement(request_root, "password_type").text = "4"
            payload = ET.tostring(request_root, encoding="utf-8", xml_declaration=True)
            raw, headers = self._request("api/user/login", body=payload, token=True)
            result = self._xml(raw)
            if self._text(result, "response").upper() == "OK":
                self.token = (headers.get("__RequestVerificationTokenone", "")
                              or headers.get("__RequestVerificationToken", "") or self.token)
                self.login_state = "authenticated"
                return
        raise HuaweiRouterError("huawei_router_login_rejected")

    def device_information(self, reference_values: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read non-secret identity/version fields using known HiLink variants.

        Firmware-specific APIs differ, so this is best-effort and read-only.
        We deliberately omit serial numbers, IMEI/IMSI, MAC addresses and
        credentials from the returned profile.
        """
        endpoints = ("api/device/information", "api/device/basic_information")
        fields = {
            "model": ("Model", "model", "ProductFamily", "ProductName", "DeviceName"),
            "hardware_version": ("HardwareVersion", "hardwareversion", "Hardware", "HWVersion", "HWVer", "hw_version"),
            "software_version": ("SoftwareVersion", "softwareversion", "FirmwareVersion", "Firmware", "SWVersion", "FWVersion", "sw_version"),
            "webui_version": ("WebUIVersion", "WebUIversion", "webuiversion", "WebUI", "WebVersion", "web_ui_version"),
            "harmony_version": ("HarmonyVersion", "HarmonyOSVersion", "harmonyversion", "HarmonyOS", "harmony_version"),
            "product_family": ("ProductFamily", "productfamily"),
        }
        reference_keys = ("model", "hardware_version", "software_version", "harmony_version", "webui_version")
        references = {key: str(reference_values.get(key) or "").strip()[:128]
                      for key in reference_keys
                      if isinstance(reference_values, dict) and str(reference_values.get(key) or "").strip()}
        found: dict[str, str] = {}
        found_at: dict[str, dict[str, str]] = {}
        reference_matches: dict[str, list[dict[str, str]]] = {key: [] for key in references}
        errors: dict[str, str] = {}
        authenticated = False

        def comparable(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", value.casefold())

        def values_match(expected: str, actual: str) -> bool:
            # Firmware strings often wrap a dotted version in a WebUI prefix
            # or carrier suffix, so compare the version token when available.
            version = re.search(r"\d+(?:\.\d+){2,}", expected)
            if version:
                return version.group(0) in actual
            return bool(comparable(expected)) and comparable(expected) == comparable(actual)

        def xml_path(root: ET.Element, target: ET.Element) -> str:
            parents = {child: parent for parent in root.iter() for child in parent}
            nodes = [target]
            while nodes[-1] in parents:
                nodes.append(parents[nodes[-1]])
            return "/".join(node.tag.rsplit("}", 1)[-1] for node in reversed(nodes))

        def read_endpoint(path: str) -> bool:
            try:
                raw, _headers = self._request(path, token=True)
                root = self._xml(raw)
                error = next((node for node in root.iter()
                              if node.tag.rsplit("}", 1)[-1].lower() == "error"), None)
                if error is not None:
                    code = self._text(error, "code", "unknown")
                    if code in {"100003", "125001", "125002", "125003"}:
                        raise HuaweiRouterError(f"huawei_router_api_error_{code}")
                    errors[path] = f"api_error_{code}"
                    return False
                for ref_key, expected in references.items():
                    for node in root.iter():
                        actual = (node.text or "").strip()
                        if not actual or not values_match(expected, actual):
                            continue
                        match = {"endpoint": path, "xml_path": xml_path(root, node), "value": actual[:128]}
                        if match not in reference_matches[ref_key]:
                            reference_matches[ref_key].append(match)
                for key, aliases in fields.items():
                    if key in found and not authenticated:
                        continue
                    for alias in aliases:
                        value = self._text(root, alias)
                        if value and len(value) <= 128 and not any(ord(ch) < 32 for ch in value):
                            found[key] = value.strip()
                            found_at[key] = {"endpoint": path, "xml_path": next(
                                (xml_path(root, node) for node in root.iter()
                                 if node.tag.rsplit("}", 1)[-1].lower() == alias.lower()
                                 and (node.text or "").strip() == value), "")}
                            break
                return True
            except HuaweiRouterError as exc:
                errors[path] = str(exc)[:80]
                return False

        # Try firmware information endpoints without authentication first;
        # a successful response avoids any login attempt at all.
        for path in endpoints:
            read_endpoint(path)
        needs_auth = any(any(code in error for code in ("100003", "12500"))
                         for error in errors.values())
        missing_version_fields = any(key not in found for key in
                                     ("hardware_version", "software_version", "webui_version"))
        missing_reference_values = any(not reference_matches.get(key) for key in references)
        # A sparse unauthenticated response (for example model only) is not a
        # complete identification. Re-read after establishing the normal
        # HiLink session so version fields are not silently left undiscovered.
        if needs_auth or missing_version_fields or missing_reference_values:
            try:
                self._login()
                authenticated = True
                errors.clear()
                for path in endpoints:
                    read_endpoint(path)
            except HuaweiRouterError as exc:
                errors["login"] = str(exc)[:80]
        return {
            **found,
            "field_sources": found_at,
            "reference_matches": reference_matches,
            "missing_fields": [key for key in fields if key not in found],
            "model": found.get("model") or "",
            "probe_status": "identified" if found else "unavailable",
            "authenticated": authenticated,
            "endpoints": [path for path in endpoints if path not in errors],
            "endpoint_errors": errors,
            "source": "huawei_local_read_only_api",
        }

    def clients(self) -> list[dict[str, str]]:
        started = time.monotonic()
        self._login()
        # HostInfo is the LAN-wide table (Ethernet + Wi-Fi) on supported CPEs.
        # host-list is explicitly WLAN-only, so it is a fallback, not the only
        # source. DHCP host-info exists on some older HiLink firmwares.
        discovered_model = str(self.discovered_device.get("model") or "").upper()
        profile_model = next((model for model in HUAWEI_INVENTORY_PROFILES if model.upper() == discovered_model), "")
        endpoints = HUAWEI_INVENTORY_PROFILES.get(profile_model, GENERIC_INVENTORY_ENDPOINTS)
        static_dhcp_endpoint = next((path for model, path in HUAWEI_STATIC_DHCP_PROFILES.items()
                                     if model.upper() == discovered_model), "")
        combined: dict[tuple[str, str], dict[str, str]] = {}
        succeeded: list[str] = []
        errors: dict[str, str] = {}
        dhcp_reservations: list[dict[str, str]] = []
        dhcp_reservation_error = ""
        refreshed_after_no_right = False
        for path in endpoints:
            try:
                raw, response_headers = self._request(path, token=True)
                root = self._xml(raw)
                error_node = next((node for node in root.iter()
                                   if node.tag.rsplit("}", 1)[-1].lower() == "error"), None)
                if error_node is not None:
                    code = self._text(error_node, "code", "unknown")
                    if code == "100003" and not refreshed_after_no_right:
                        # A fresh HiLink session/token can recover routers that
                        # rotate authentication state between setup and reads.
                        refreshed_after_no_right = True
                        self._load_token()
                        self._login()
                        raw, response_headers = self._request(path, token=True)
                        root = self._xml(raw)
                        error_node = next((node for node in root.iter()
                                           if node.tag.rsplit("}", 1)[-1].lower() == "error"), None)
                        if error_node is None:
                            code = ""
                        else:
                            code = self._text(error_node, "code", "unknown")
                    if error_node is not None:
                        raise HuaweiRouterError(f"huawei_router_api_error_{code}")
                succeeded.append(path)
                for item in self._parse_hosts(root):
                    item["source"] = path
                    combined[(item["mac"], item["ip"])] = item
            except HuaweiRouterError as exc:
                errors[path] = str(exc)[:80]
                # Continue to other read-only inventory endpoints when a
                # firmware does not implement one of them.
                continue
        if static_dhcp_endpoint:
            try:
                raw, _headers = self._request(static_dhcp_endpoint, token=True)
                root = self._xml(raw)
                error_node = next((node for node in root.iter()
                                   if node.tag.rsplit("}", 1)[-1].lower() == "error"), None)
                if error_node is not None:
                    code = self._text(error_node, "code", "unknown")
                    raise HuaweiRouterError(f"huawei_router_api_error_{code}")
                dhcp_reservations = self._parse_hosts(root)
                for item in dhcp_reservations:
                    item["source"] = "huawei_dhcp_reservation"
            except HuaweiRouterError as exc:
                dhcp_reservation_error = str(exc)[:80]
        self.last_diagnostics = {
            "device_profile": profile_model or "generic_hilink",
            "software_version": str(self.discovered_device.get("software_version") or "")[:128],
            "endpoints_succeeded": succeeded,
            "endpoint_errors": errors,
            "login_state": self.login_state,
            "auth_session_id_present": bool(self.session_id),
            "verification_token_refreshed": bool(self.token),
            "dhcp_reservation_endpoint": static_dhcp_endpoint,
            "dhcp_reservation_count": len(dhcp_reservations),
            "dhcp_reservations": dhcp_reservations,
            "dhcp_reservation_error": dhcp_reservation_error,
            "failure_class": ("authorization_or_session" if errors and all("100003" in value or "12500" in value for value in errors.values()) else "endpoint_or_firmware" if errors and not succeeded else None),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        if not succeeded:
            raise HuaweiRouterError("huawei_router_hosts_unavailable:" + ",".join(errors.values())[:120],
                                    diagnostics=dict(self.last_diagnostics))
        return list(combined.values())

    @staticmethod
    def _parse_hosts(root: ET.Element) -> list[dict[str, str]]:
        """Parse host rows from the differing XML shapes used by HiLink APIs."""
        aliases = {
            "mac": {"mac", "macaddress", "macaddr", "hostmac", "clientmac", "devicemac"},
            "ip": {"ip", "ipaddress", "hostip", "clientip", "assignedip", "ipaddr"},
            "name": {"hostname", "host_name", "name", "devicename", "clientname"},
        }

        def normalized(tag: str) -> str:
            return re.sub(r"[^a-z]", "", tag.rsplit("}", 1)[-1].lower())

        rows: dict[tuple[str, str], dict[str, str]] = {}
        # Huawei responses commonly wrap records in Host/Hosts, but tags and
        # casing vary by firmware. Consider each element as a possible record.
        for node in root.iter():
            values: dict[str, str] = {}
            for raw_key, raw_value in node.attrib.items():
                key = normalized(raw_key)
                value = str(raw_value).strip()
                for field, names in aliases.items():
                    if key in {normalized(alias) for alias in names} and value:
                        values.setdefault(field, value)
            for child in node.iter():
                if child is node or len(child):
                    continue
                key = normalized(child.tag)
                value = (child.text or "").strip()
                if not value:
                    continue
                for field, names in aliases.items():
                    if key in {normalized(alias) for alias in names} and field not in values:
                        values[field] = value
            mac = values.get("mac", "").upper().replace("-", ":")
            ip = values.get("ip", "")
            if not MAC_RE.fullmatch(mac) and not ip:
                continue
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
                continue
            if not MAC_RE.fullmatch(mac):
                mac = ""
            item = {"mac": mac, "ip": str(address), "name": values.get("name", "")[:120]}
            rows[(mac, str(address))] = item
        return list(rows.values())


def read_huawei_clients(config: dict[str, Any]) -> list[dict[str, str]]:
    return HuaweiHiLinkClient(config).clients()


def read_huawei_clients_with_diagnostics(config: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    client = HuaweiHiLinkClient(config)
    hosts = client.clients()
    return hosts, dict(client.last_diagnostics)


def read_huawei_device_information(config: dict[str, Any],
                                   reference_values: dict[str, Any] | None = None) -> dict[str, Any]:
    client = HuaweiHiLinkClient(config, timeout=8.0, total_timeout=90.0)
    return client.device_information(reference_values)


def merge_gateway_neighbor_hosts(
    router_hosts: list[dict[str, str]], neighbors_by_mac: dict[str, str],
    *, source: str = "gateway_neighbour_cache",
) -> tuple[list[dict[str, str]], int]:
    """Add private LAN IP/MAC pairs already learned by this Gateway's ARP table."""
    merged = {(str(item.get("mac") or "").upper(), str(item.get("ip") or "")): dict(item)
              for item in router_hosts if isinstance(item, dict)}
    before = len(merged)
    for raw_mac, raw_ip in neighbors_by_mac.items():
        mac = str(raw_mac or "").upper()
        ip = str(raw_ip or "")
        if not MAC_RE.fullmatch(mac):
            continue
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
            continue
        merged.setdefault((mac, str(address)), {
            "mac": mac, "ip": str(address), "name": "", "source": source})
    return list(merged.values()), len(merged) - before

