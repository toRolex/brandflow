"""Phase 1 regression: production code must be free of legacy brand references."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BANNED_PATTERNS = [
    "滋元堂",
    "ziyuantang",
    "Ziyuantang",
    "荔枝菌",
    "充分烹熟",
]

EXCLUDE_DIRS = [
    "node_modules",
    ".git",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
]

EXCLUDE_FILES = [
    "uv.lock",
    "pnpm-lock.yaml",
]

ALLOWLIST_PATHS = [
    # asset_library keyword_map is out of scope for Phase 1
    "packages/pipeline_services/asset_library/keyword_map.json",
    # CONTEXT.md domain vocabulary — uses brand name as an example
    "CONTEXT.md",
]

ALLOWLIST_DIRS = [
    # historical planning documents — snapshots, not living references
    "docs/superpowers/plans/",
    "docs/prd/",  # Phase 2+ PRDs reference legacy brand for context
]


def _is_allowed(file_path: str) -> bool:
    for allowed in ALLOWLIST_PATHS:
        if file_path.endswith(allowed):
            return True
    for allowed_dir in ALLOWLIST_DIRS:
        if allowed_dir in file_path:
            return True
    return False


def test_production_code_has_no_legacy_brand_references() -> None:
    """US16: grep-based regression — production sources must not contain legacy brand strings."""
    args = (
        ["grep", "-rn"]
        + BANNED_PATTERNS
        + [
            "--include=*.py",
            "--include=*.ts",
            "--include=*.tsx",
            "--include=*.json",
            "--include=*.yaml",
            "--include=*.md",
            "--include=*.txt",
            "--include=*.html",
            "--include=*.bat",
            "--include=*.toml",
            "--include=*.css",
        ]
    )

    for d in EXCLUDE_DIRS:
        args.extend([f"--exclude-dir={d}"])
    for f in EXCLUDE_FILES:
        args.extend([f"--exclude={f}"])

    args.append(str(REPO_ROOT))

    result = subprocess.run(args, capture_output=True, text=True)
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

    # Filter out test files and allowed paths
    violations = [
        line
        for line in lines
        if "/tests/" not in line and not _is_allowed(line.split(":")[0])
    ]

    assert len(violations) == 0, (
        f"Found {len(violations)} legacy brand reference(s) in production code:\n"
        + "\n".join(violations)
    )
