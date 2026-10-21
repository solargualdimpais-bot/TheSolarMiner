"""Daily, non-applying check of the Owner-selected, administratively allowed release source."""
from __future__ import annotations

import json
import sys

from . import app as gateway
from . import updates


def main() -> int:
    with gateway.db() as conn:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key='update_repository_url'"
        ).fetchone()
    if not row or not row["value"]:
        print(json.dumps({"status": "not_configured"}, separators=(",", ":")))
        return 0
    try:
        source = updates.load_update_source(row["value"])
        result = gateway._check_system_update_manifest(
            source["manifest_url"],
            {"user_id": None},
            manifest_origins=source["manifest_origins"],
            package_origins=source["package_origins"],
            repository_url=source["repository_url"],
        )
        print(json.dumps(result, separators=(",", ":")))
        return 0 if result.get("status") in {"current", "update_available", "verified"} else 1
    except Exception as exc:
        # Do not emit manifest content, URLs with query strings, or credentials.
        print(json.dumps({"status": "failed", "reason": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
