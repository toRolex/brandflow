"""Guards for the WorkspaceLayout project-tree seam.

The deletion check for issue #361 is represented as a source-level invariant:
project-tree paths must not be rebuilt by unrelated production modules. The
layout module is the one intentional exception because it defines the layout.
Global workspace paths such as ``shared_assets`` remain outside this seam.
"""

from __future__ import annotations

import ast
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAYOUT_PATH = _REPO_ROOT / "packages" / "file_store" / "layout.py"

# These are the project-tree path fragments owned by WorkspaceLayout. A static
# scan is deliberately limited to these fragments so global workspace paths
# (shared_assets, music_library, materials) remain valid outside the seam.
_PATH_SEQUENCES: tuple[tuple[str, ...], ...] = (
    ("workspace", "projects"),
    ("control", "jobs"),
    ("control", "batches"),
    ("runtime", "jobs"),
    ("runtime", "source_assets"),
    ("runtime", "indexed_clips"),
    ("runtime", "exports"),
    ("runtime", "schedule", "exports"),
)


def _production_python_files() -> list[Path]:
    return sorted(
        path
        for root_name in ("apps", "packages")
        for path in (_REPO_ROOT / root_name).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _contains_sequence(tokens: list[str | None], sequence: tuple[str, ...]) -> bool:
    size = len(sequence)
    return any(
        tokens[index : index + size] == list(sequence)
        for index in range(len(tokens) - size + 1)
    )


def _slash_tokens(node: ast.AST) -> list[str | None] | None:
    """Flatten a ``Path / "literal" / ...`` expression into static tokens."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _slash_tokens(node.left)
        right = _slash_tokens(node.right)
        if left is None or right is None:
            return None
        return left + right
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value.replace("\\", "/").strip("/")]
    # A dynamic Path expression is retained as a placeholder, allowing static
    # fragments on either side to be matched (e.g. project_dir / "runtime" /
    # "jobs" / job_id).
    return [None]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    nodes: set[int] = set()

    def mark(body: list[ast.stmt]) -> None:
        if body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                nodes.add(id(value))

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            mark(node.body)
    return nodes


class _ProjectTreeVisitor(ast.NodeVisitor):
    def __init__(self, docstrings: set[int]) -> None:
        self.docstrings = docstrings
        self.violations: list[tuple[int, str]] = []

    def _record(self, node: ast.AST, source: str) -> None:
        self.violations.append((node.lineno, source))

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            tokens = _slash_tokens(node)
            if tokens is not None and any(
                _contains_sequence(tokens, sequence) for sequence in _PATH_SEQUENCES
            ):
                self._record(node, ast.unparse(node))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if id(node) in self.docstrings or not isinstance(node.value, str):
            return
        normalized = node.value.replace("\\", "/")
        if any("/".join(sequence) in normalized for sequence in _PATH_SEQUENCES):
            self._record(node, repr(node.value))

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        static_text = "/".join(
            value.value.replace("\\", "/")
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
        if any("/".join(sequence) in static_text for sequence in _PATH_SEQUENCES):
            self._record(node, ast.unparse(node))
        self.generic_visit(node)


def test_project_tree_paths_are_constructed_only_by_workspace_layout() -> None:
    """Deleting a former caller cannot expose a second path-construction seam."""
    violations: list[str] = []
    for path in _production_python_files():
        if path == _LAYOUT_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _ProjectTreeVisitor(_docstring_nodes(tree))
        visitor.visit(tree)
        violations.extend(
            f"{path.relative_to(_REPO_ROOT)}:{line}: {source}"
            for line, source in visitor.violations
        )

    assert not violations, (
        "project-tree paths must be constructed through WorkspaceLayout; "
        "manual path fragments found in production code:\n"
        + "\n".join(f"- {violation}" for violation in violations)
    )
