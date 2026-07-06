from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from packages.knowledge_store.models import KnowledgeDocument, KnowledgeItem


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return __import__("json").loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        __import__("json").dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _generate_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _load_documents(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    if isinstance(data, list):
        return data
    return []


def _load_items(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    if isinstance(data, list):
        return data
    return []


def _type_matches(item_type_value: str, target: str) -> bool:
    return item_type_value == target


class KnowledgeStore:
    """File-based JSON persistence for knowledge documents and items.

    Stores data in <root_dir>/knowledge/ directory:
      - documents.json
      - items.json
    """

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._knowledge_dir = root_dir / "knowledge"
        self._documents_path = self._knowledge_dir / "documents.json"
        self._items_path = self._knowledge_dir / "items.json"
        _ensure_dir(self._knowledge_dir)

    # ---- Documents ----

    def save_document(self, doc: KnowledgeDocument) -> None:
        docs = _load_documents(self._documents_path)
        payload = doc.to_dict()
        for idx, existing in enumerate(docs):
            if existing.get("id") == doc.id:
                docs[idx] = payload
                break
        else:
            docs.append(payload)
        _write_json(self._documents_path, docs)

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        for data in _load_documents(self._documents_path):
            if data.get("id") == doc_id:
                return KnowledgeDocument.from_dict(data)
        return None

    def list_documents(self) -> list[KnowledgeDocument]:
        return [
            KnowledgeDocument.from_dict(data)
            for data in _load_documents(self._documents_path)
        ]

    def delete_document(self, doc_id: str) -> bool:
        docs = _load_documents(self._documents_path)
        new_docs = [d for d in docs if d.get("id") != doc_id]
        removed = len(new_docs) != len(docs)
        if not removed:
            return False

        _write_json(self._documents_path, new_docs)

        # Cascade delete items for this document
        items = _load_items(self._items_path)
        new_items = [i for i in items if i.get("document_id") != doc_id]
        if len(new_items) != len(items):
            _write_json(self._items_path, new_items)
        return True

    # ---- Items ----

    def save_items(self, items: list[KnowledgeItem]) -> None:
        if not items:
            return
        existing = _load_items(self._items_path)
        existing_by_id = {item.get("id"): idx for idx, item in enumerate(existing)}
        for item in items:
            payload = item.to_dict()
            if item.id in existing_by_id:
                existing[existing_by_id[item.id]] = payload
            else:
                existing_by_id[item.id] = len(existing)
                existing.append(payload)
        _write_json(self._items_path, existing)

    def list_items(self, document_id: str | None = None) -> list[KnowledgeItem]:
        items = [
            KnowledgeItem.from_dict(data) for data in _load_items(self._items_path)
        ]
        if document_id is None:
            return items
        return [item for item in items if item.document_id == document_id]

    def get_top_k_items(self, item_type: str, k: int = 5) -> list[KnowledgeItem]:
        """Return top-K items of the given type, sorted by priority descending."""
        all_items = [
            KnowledgeItem.from_dict(data) for data in _load_items(self._items_path)
        ]
        filtered = [
            item for item in all_items if _type_matches(item.type.value, item_type)
        ]
        filtered.sort(key=lambda x: x.priority, reverse=True)
        return filtered[:k]

    # ---- Selling point management (Phase 4 Slice 3) ----

    def list_selling_points(
        self,
        priority_min: int | None = None,
        priority_max: int | None = None,
        tags: list[str] | None = None,
    ) -> list[KnowledgeItem]:
        """List all selling_point items with optional filters.

        Args:
            priority_min: Minimum priority (inclusive).
            priority_max: Maximum priority (inclusive).
            tags: If provided, return items matching ANY of these tags.

        Returns:
            Filtered list of KnowledgeItem with type selling_point.
        """
        all_items = [
            KnowledgeItem.from_dict(data) for data in _load_items(self._items_path)
        ]
        result: list[KnowledgeItem] = []
        for item in all_items:
            if item.type.value != "selling_point":
                continue
            if priority_min is not None and item.priority < priority_min:
                continue
            if priority_max is not None and item.priority > priority_max:
                continue
            if tags:
                item_tags_set = {tag.lower() for tag in item.tags}
                query_tags_set = {tag.lower() for tag in tags}
                if not item_tags_set.intersection(query_tags_set):
                    continue
            result.append(item)
        return result

    def get_top_selling_points(self, top_k: int = 5) -> list[KnowledgeItem]:
        """Return top-K selling points, sorted by priority descending.

        Convenience wrapper around get_top_k_items with selling_point type.
        """
        return self.get_top_k_items(item_type="selling_point", k=top_k)

    def update_item(self, item_id: str, **fields: Any) -> KnowledgeItem | None:
        """Update fields on an existing KnowledgeItem.

        Allowed fields: title, content, priority, tags.
        Returns the updated item, or None if not found.
        """
        items = _load_items(self._items_path)
        for data in items:
            if data.get("id") == item_id:
                allowed = {"title", "content", "priority", "tags"}
                for key, value in fields.items():
                    if key in allowed:
                        data[key] = value
                _write_json(self._items_path, items)
                return KnowledgeItem.from_dict(data)
        return None

    def refresh_all(self, extractor: Any) -> int:
        """Re-extract knowledge from all documents, replacing old items.

        Args:
            extractor: An object with an ``extract(text, source_document)`` method
                       that returns a list of KnowledgeItem.

        Returns:
            Number of items extracted across all documents.
        """
        if extractor is None:
            return 0

        docs = self.list_documents()
        if not docs:
            return 0

        # Delete all existing items
        _write_json(self._items_path, [])

        total = 0
        for doc in docs:
            text = doc.parsed_text.strip()
            if not text:
                continue
            try:
                items = extractor.extract(text, source_document=doc.filename)
                if items:
                    for item in items:
                        item.document_id = doc.id
                    self.save_items(items)
                    total += len(items)
            except Exception:
                continue

        return total
