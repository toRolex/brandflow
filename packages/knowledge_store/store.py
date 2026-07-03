from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from packages.knowledge_store.models import KnowledgeDocument, KnowledgeItem


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp_path.replace(path)


def _generate_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class KnowledgeStore:
    """File-based JSON persistence for knowledge documents and items.

    Stores data in <root_dir>/knowledge/ directory:
      - documents/<id>.json
      - items/<id>.json
    """

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._documents_dir = root_dir / "knowledge" / "documents"
        self._items_dir = root_dir / "knowledge" / "items"
        _ensure_dir(self._documents_dir)
        _ensure_dir(self._items_dir)

    def _document_path(self, doc_id: str) -> Path:
        return self._documents_dir / f"{doc_id}.json"

    def _item_path(self, item_id: str) -> Path:
        return self._items_dir / f"{item_id}.json"

    # ---- Documents ----

    def save_document(self, doc: KnowledgeDocument) -> None:
        _write_json(self._document_path(doc.id), doc.to_dict())

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        data = _read_json(self._document_path(doc_id))
        if data is None:
            return None
        return KnowledgeDocument.from_dict(data)

    def list_documents(self) -> list[KnowledgeDocument]:
        if not self._documents_dir.exists():
            return []
        docs: list[KnowledgeDocument] = []
        for f in sorted(self._documents_dir.iterdir()):
            if f.is_file() and f.suffix == ".json":
                data = _read_json(f)
                if data:
                    docs.append(KnowledgeDocument.from_dict(data))
        return docs

    def delete_document(self, doc_id: str) -> bool:
        path = self._document_path(doc_id)
        if not path.exists():
            return False
        path.unlink()
        # Cascade delete items for this document
        for item in self.list_items(document_id=doc_id):
            item_path = self._item_path(item.id)
            if item_path.exists():
                item_path.unlink()
        return True

    # ---- Items ----

    def save_items(self, items: list[KnowledgeItem]) -> None:
        for item in items:
            _write_json(self._item_path(item.id), item.to_dict())

    def list_items(
        self, document_id: str | None = None
    ) -> list[KnowledgeItem]:
        if not self._items_dir.exists():
            return []
        all_items: list[KnowledgeItem] = []
        for f in sorted(self._items_dir.iterdir()):
            if f.is_file() and f.suffix == ".json":
                data = _read_json(f)
                if data:
                    item = KnowledgeItem.from_dict(data)
                    if document_id is None or item.document_id == document_id:
                        all_items.append(item)
        return all_items

    def get_top_k_items(
        self, item_type: str, k: int = 5
    ) -> list[KnowledgeItem]:
        """Return top-K items of the given type, sorted by priority descending."""
        all_items: list[KnowledgeItem] = []
        for f in sorted(self._items_dir.iterdir()):
            if f.is_file() and f.suffix == ".json":
                data = _read_json(f)
                if data:
                    item = KnowledgeItem.from_dict(data)
                    if item.type.value == item_type or item.type == item_type:
                        all_items.append(item)
        all_items.sort(key=lambda x: x.priority, reverse=True)
        return all_items[:k]
