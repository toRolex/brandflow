"""Read current version from pyproject.toml."""

import tomllib
from pathlib import Path


def get_version() -> str:
    """Read version from pyproject.toml using tomllib (Python 3.11+ stdlib).

    Resolved relative to this file so it works regardless of cwd (tests
    that pass an arbitrary ``tmp_path`` as ``root_dir`` also work).
    """
    path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)["project"]["version"]
