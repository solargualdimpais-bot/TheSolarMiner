"""SolarMiner's local-only TinyTuya surface (upstream version 1.20.0).

The upstream package initializer imports its optional Cloud client and emits a
warning when the unrelated ``requests`` package is absent. SolarMiner uses
only the LAN Device class, so this minimal initializer keeps the vendored
runtime strictly on the local-device API.
"""
from .core.Device import Device
from .core import __version__

__all__ = ["Device", "__version__"]
