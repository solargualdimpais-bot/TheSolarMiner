"""Daily signed release check and safe automatic application when preflight passes."""
from __future__ import annotations

import json
import sys
import uuid

from . import app as gateway
from . import update_helper_client
from . import updates


def _previous_apply_failed(version: str, operation_id: str) -> bool:
    """Do not retry the same failed release every day without an Owner review."""
    with gateway.db() as conn:
        row = conn.execute(
            "SELECT 1 FROM update_operations WHERE target_version=? AND id<>? "
            "AND state IN ('FAILED','ROLLED_BACK','RECOVERY_BLOCKED') LIMIT 1",
            (version, operation_id),
        ).fetchone()
    return row is not None


def main() -> int:
    with gateway.db() as conn:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key='update_repository_url'"
        ).fetchone()
    try:
        if row and row["value"]:
            source = updates.load_update_source(row["value"])
        else:
            # The installer provisions the root-owned allowlist before the
            # first Owner session exists; its first approved entry is the initial source.
            source = updates.list_update_sources()[0]
    except updates.UpdateValidationError as exc:
        print(json.dumps({"status": "not_configured", "reason": str(exc)}, separators=(",", ":")))
        return 0
    try:
        result = gateway._check_system_update_manifest(
            source["manifest_url"],
            {"user_id": None},
            manifest_origins=source["manifest_origins"],
            package_origins=source["package_origins"],
            repository_url=source["repository_url"],
        )
        if result.get("status") == "verified_staged":
            if _previous_apply_failed(str(result.get("available_version") or ""), str(result.get("operation_id") or "")):
                print(json.dumps({"status": "auto_apply_blocked_after_previous_failure",
                                  "reason": "owner_review_required", "target_version": result.get("available_version")}, separators=(",", ":")))
                return 0
            if result.get("activation_available") is not True:
                print(json.dumps({"status": "verified_staged", "activation": "blocked",
                                  "reason": "update_pipeline_preflight_failed",
                                  "target_version": result.get("available_version")}, separators=(",", ":")))
                return 1
            operation_id = result.get("operation_id")
            try:
                normalized_id = str(uuid.UUID(str(operation_id)))
            except (ValueError, AttributeError, TypeError):
                print(json.dumps({"status": "failed", "reason": "update_operation_id_invalid"}, separators=(",", ":")))
                return 1
            try:
                confirmation = update_helper_client.request("enqueue", normalized_id)
            except (OSError, RuntimeError, TimeoutError, ValueError):
                print(json.dumps({"status": "failed", "reason": "update_helper_unavailable_or_timed_out"}, separators=(",", ":")))
                return 1
            if (not isinstance(confirmation, dict)
                    or confirmation.get("operation_id") != normalized_id
                    or confirmation.get("status") != "APPLY_QUEUED"):
                print(json.dumps({"status": "failed", "reason": "update_helper_did_not_confirm_queue"}, separators=(",", ":")))
                return 1
            print(json.dumps({"status": "apply_queued", "operation_id": normalized_id,
                              "target_version": result.get("available_version")}, separators=(",", ":")))
            return 0
        print(json.dumps(result, separators=(",", ":")))
        return 0 if result.get("status") == "current" else 1
    except Exception as exc:
        # Do not emit manifest content, URLs with query strings, or credentials.
        print(json.dumps({"status": "failed", "reason": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
