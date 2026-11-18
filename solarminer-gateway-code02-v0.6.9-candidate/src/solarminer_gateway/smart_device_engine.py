"""Per-device scheduler primitives for the Gateway's Tuya/Shelly LAN engine.

This module deliberately contains no PWA or energy-device logic. The Gateway
owns the schedule and availability decision; callers provide transport I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any


MIN_POLL_DELAY_SECONDS = 0.01
MAX_POLL_DELAY_SECONDS = 60.0
OFFLINE_LATENCY_MULTIPLIER = 5.0
ENGINE_RETRY_BASE_SECONDS = 0.25
ENGINE_RETRY_MAX_SECONDS = 30.0


def cycle_retry_delay(failure_count: int) -> float:
    """Bounded exponential retry delay for faults in the scheduler loop itself."""
    count = max(1, int(failure_count))
    return min(ENGINE_RETRY_MAX_SECONDS, ENGINE_RETRY_BASE_SECONDS * (2 ** min(count - 1, 7)))


def configured_device_for_cycle(cycle: "DeviceCycle", configured: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve a due scheduler entry without assuming inventory/config coherence."""
    return configured.get(f"{cycle.provider}:{cycle.device_id}")


@dataclass
class DeviceCycle:
    provider: str
    device_id: str
    latency_seconds: float = 0.5
    last_success_monotonic: float | None = None
    first_attempt_monotonic: float | None = None
    next_poll_monotonic: float = 0.0
    in_flight: bool = False
    cloud_check_in_flight: bool = False
    cloud_checked_for_outage: bool = False
    urgent_poll_requested: bool = False

    @property
    def offline_after_seconds(self) -> float:
        return max(0.01, self.latency_seconds * OFFLINE_LATENCY_MULTIPLIER)

    def is_online(self, now: float) -> bool:
        # A configured device is not online until the Gateway has actually
        # received at least one LAN response. A recent first attempt is not
        # evidence of availability.
        return (self.last_success_monotonic is not None
                and 0 <= now - self.last_success_monotonic <= self.offline_after_seconds)


class SmartDeviceScheduler:
    """A small deterministic schedule state machine, keyed by provider/id."""

    def __init__(self) -> None:
        self.devices: dict[tuple[str, str], DeviceCycle] = {}

    def reconcile(self, configured: list[tuple[str, str]], now: float) -> None:
        allowed = {(provider, device_id) for provider, device_id in configured if provider in {"tuya", "shelly"} and device_id}
        for key in tuple(self.devices):
            if key not in allowed:
                del self.devices[key]
        for provider, device_id in allowed:
            self.devices.setdefault((provider, device_id), DeviceCycle(provider, device_id, next_poll_monotonic=now))

    def restore(self, provider: str, device_id: str, *, latency_seconds: float,
                last_success_age_seconds: float | None, now: float) -> DeviceCycle:
        """Restore persisted timing without treating process restart as a fresh read."""
        item = self.devices.setdefault((provider, device_id), DeviceCycle(provider, device_id))
        item.latency_seconds = max(0.01, min(float(latency_seconds), MAX_POLL_DELAY_SECONDS))
        if last_success_age_seconds is not None:
            age = max(0.0, float(last_success_age_seconds))
            item.last_success_monotonic = now - age
            item.first_attempt_monotonic = None
            item.next_poll_monotonic = min(item.next_poll_monotonic, now)
        return item

    def due(self, now: float, limit: int) -> list[DeviceCycle]:
        ready = sorted((item for item in self.devices.values()
                        if not item.in_flight and item.next_poll_monotonic <= now),
                       key=lambda item: item.next_poll_monotonic)
        selected = ready[:max(0, limit)]
        for item in selected:
            item.in_flight = True
        return selected

    def complete(self, item: DeviceCycle, now: float, latency_seconds: float, success: bool) -> None:
        item.in_flight = False
        if item.first_attempt_monotonic is None:
            item.first_attempt_monotonic = now
        measured = max(0.01, min(float(latency_seconds), MAX_POLL_DELAY_SECONDS))
        if success:
            # Use this device's latest observed LAN round-trip. The schedule
            # and offline threshold are explicitly per-device and must not be
            # blurred by fleet averages or an EMA that hides a changed link.
            item.latency_seconds = measured
            item.last_success_monotonic = now
            item.cloud_checked_for_outage = False
        # Never poll this device again before twice its own measured response
        # time. A fleet-wide ceiling would violate this contract for slow links.
        delay = (MIN_POLL_DELAY_SECONDS if item.urgent_poll_requested
                 else max(MIN_POLL_DELAY_SECONDS, item.latency_seconds * 2.0))
        item.urgent_poll_requested = False
        item.next_poll_monotonic = now + delay

    def request_now(self, provider: str, device_id: str, now: float) -> bool:
        """Schedule a confirmation sample after a command, without overlapping I/O."""
        item = self.devices.get((provider, device_id))
        if item is None:
            return False
        if item.in_flight:
            item.urgent_poll_requested = True
        else:
            item.next_poll_monotonic = min(item.next_poll_monotonic, now)
        return True

    def needs_cloud_check(self, item: DeviceCycle, now: float) -> bool:
        reference = item.last_success_monotonic if item.last_success_monotonic is not None else item.first_attempt_monotonic
        if item.provider != "tuya" or reference is None or item.is_online(now):
            return False
        # Cloud availability is only a fallback after the same per-device
        # five-latency timeout used to mark the LAN sample unavailable.
        if now - reference < item.offline_after_seconds:
            return False
        if item.cloud_checked_for_outage or item.cloud_check_in_flight:
            return False
        item.cloud_check_in_flight = True
        return True

    def complete_cloud_check(self, item: DeviceCycle) -> None:
        item.cloud_check_in_flight = False
        item.cloud_checked_for_outage = True


class SmartDeviceCommandRouter:
    """Gateway-owned command lane for Tuya/Shelly, serialized per device.

    This serializes writes for one device without waiting for its next scheduled
    poll. A LAN transaction already in progress may still serialize at the
    protocol adapter; the router never performs a verification read itself.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple[str, str], threading.Lock] = {}

    def execute(self, provider: str, device_id: str, operation: Any) -> Any:
        if provider not in {"tuya", "shelly"} or not device_id or not callable(operation):
            raise ValueError("unsupported_smart_device_command")
        key = (provider, device_id)
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            return operation()

