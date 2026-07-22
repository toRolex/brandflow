"""Sync version from pyproject.toml to frontend/package.json and CONTEXT.md.

Usage:
    uv run python tools/sync_version.py
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_version(pyproject_path: Path) -> str:
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def update_package_json(package_json_path: Path, version: str) -> None:
    data = json.loads(package_json_path.read_text())
    data["version"] = version
    package_json_path.write_text(json.dumps(data, indent=2) + "\n")


def update_context_md(context_md_path: Path, version: str) -> None:
    text = context_md_path.read_text()
    text = re.sub(r"v(\d+\.\d+\.\d+)", f"v{version}", text)
    context_md_path.write_text(text)


def main(
    pyproject_path: Path | None = None,
    package_json_path: Path | None = None,
    context_md_path: Path | None = None,
) -> None:
    root = _PROJECT_ROOT
    pp = pyproject_path or root / "pyproject.toml"
    pj = package_json_path or root / "frontend" / "package.json"
    cm = context_md_path or root / "CONTEXT.md"
    version = get_version(pp)
    update_package_json(pj, version)
    update_context_md(cm, version)
    print(f"Synced version to {version}")


if __name__ == "__main__":
    main()
