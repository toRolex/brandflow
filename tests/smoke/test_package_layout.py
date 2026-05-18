import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PACKAGE_NAMES = [
    "apps.control_plane",
    "apps.runtime_worker",
    "packages.domain_core",
    "packages.file_store",
    "packages.runtime_adapters",
    "packages.pipeline_services",
]

ENTRY_MODULES = [
    "apps.control_plane.__main__",
    "apps.runtime_worker.__main__",
]


def test_phase1_package_layout_imports_exist() -> None:
    for package_name in PACKAGE_NAMES:
        importlib.import_module(package_name)


def test_phase1_entry_modules_are_importable() -> None:
    for module_name in ENTRY_MODULES:
        module = importlib.import_module(module_name)
        assert hasattr(module, "main")
        assert callable(module.main)
