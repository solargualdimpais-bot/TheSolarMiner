"""Run the Intelligence bridge logic tests on Windows without emulating fcntl.

The Gateway uses POSIX-only fcntl in unrelated modules imported by the app.
This focused test does not exercise file locks or interface ioctls, so provide
an import-only stub that raises if any such operation is reached.
This is a Windows logic-test harness, not Debian/runtime validation.
"""
from __future__ import annotations

import os
import sys
import types


def _install_import_only_fcntl_stub() -> None:
    if os.name != "nt":
        return

    module = types.ModuleType("fcntl")
    module.LOCK_EX = 2
    module.LOCK_UN = 8
    module.LOCK_NB = 4

    def unsupported_operation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fcntl operation is outside the Intelligence bridge test scope")

    module.flock = unsupported_operation
    module.ioctl = unsupported_operation
    sys.modules["fcntl"] = module


def main() -> int:
    _install_import_only_fcntl_stub()
    import pytest

    targets = sys.argv[1:] or ["tests/test_intelligence_bridge.py"]
    return int(pytest.main(["-q", *targets]))


if __name__ == "__main__":
    raise SystemExit(main())
