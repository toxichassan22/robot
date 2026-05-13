"""Deprecated launcher shim for the relocated Pi web UI backend."""

from importlib import import_module as _import_module
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "pi5.web_ui.backend.main is deprecated; use pi_5.web_ui_backend.main instead.",
    DeprecationWarning,
    stacklevel=2,
)

_sys.modules[__name__] = _import_module("pi_5.web_ui_backend.main")
