"""Tests for tools/sync_version.py."""

import json
from pathlib import Path

from tools.sync_version import get_version, update_package_json, update_context_md, main

PYPROJECT_TOML = """[project]
name = "test"
version = "0.7.14"
"""

PACKAGE_JSON = """{
  "name": "test",
  "version": "0.7.13",
  "private": true
}
"""

CONTEXT_MD = """# Title

## 架构状态（v0.7.0）

v0.7.0 已完成测试。
"""

CONTEXT_MD_UPDATED = """# Title

## 架构状态（v0.7.14）

v0.7.14 已完成测试。
"""


def test_read_version_from_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_TOML)
    assert get_version(pyproject) == "0.7.14"


def test_update_package_json(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text(PACKAGE_JSON)
    update_package_json(pkg, "0.7.14")
    data = json.loads(pkg.read_text())
    assert data["version"] == "0.7.14"
    # Preserve other fields
    assert data["name"] == "test"
    assert data["private"] is True


def test_update_context_md_references(tmp_path: Path) -> None:
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(CONTEXT_MD)
    update_context_md(ctx, "0.7.14")
    text = ctx.read_text()
    assert "v0.7.14" in text
    assert "v0.7.0" not in text


def test_main_end_to_end(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pkg = tmp_path / "package.json"
    ctx = tmp_path / "CONTEXT.md"
    pyproject.write_text(PYPROJECT_TOML)
    pkg.write_text(PACKAGE_JSON)
    ctx.write_text(CONTEXT_MD)

    main(
        pyproject_path=pyproject,
        package_json_path=pkg,
        context_md_path=ctx,
    )

    data = json.loads(pkg.read_text())
    assert data["version"] == "0.7.14"
    assert "v0.7.14" in ctx.read_text()
