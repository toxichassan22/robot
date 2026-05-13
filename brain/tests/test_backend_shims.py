import importlib
import sys
import warnings


def _reload_module(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_canonical_backend_import_smoke():
    package = importlib.import_module("pi_5.web_ui_backend")
    module = importlib.import_module("pi_5.web_ui_backend.main")

    assert package is not None
    assert hasattr(module, "app")


def test_pi5_launcher_shim_warns_and_forwards():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        module = _reload_module("pi5.web_ui.backend.main")

    assert hasattr(module, "app")
    assert any("deprecated" in str(item.message).lower() for item in captured)


def test_web_ui_import_shim_warns_and_forwards():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        module = _reload_module("web_ui.backend.main")

    assert hasattr(module, "app")
    assert any("deprecated" in str(item.message).lower() for item in captured)
