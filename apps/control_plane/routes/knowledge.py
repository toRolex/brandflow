from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from packages.knowledge_store.extractor import KnowledgeExtractor
from packages.knowledge_store.models import KnowledgeDocument, SourceType
from packages.knowledge_store.parsers import parse_file
from packages.knowledge_store.store import KnowledgeStore
from packages.pipeline_services.llm_client import LLMClient
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

_SOURCE_TYPE_BY_MIME = {
    "text/plain": SourceType.TXT,
    "application/pdf": SourceType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": SourceType.DOCX,
}

_SOURCE_TYPE_BY_EXT = {
    ".txt": SourceType.TXT,
    ".pdf": SourceType.PDF,
    ".docx": SourceType.DOCX,
}

_EXT_BY_SOURCE_TYPE = {
    SourceType.TXT: ".txt",
    SourceType.PDF: ".pdf",
    SourceType.DOCX: ".docx",
}


def _detect_source_type(filename: str, content_type: str | None) -> SourceType:
    """Detect document source type from MIME type, falling back to extension."""
    if content_type:
        source_type = _SOURCE_TYPE_BY_MIME.get(content_type.lower())
        if source_type is not None:
            return source_type
    ext = Path(filename).suffix.lower()
    source_type = _SOURCE_TYPE_BY_EXT.get(ext)
    if source_type is None:
        raise ValueError(f"Unsupported file type '{ext}'")
    return source_type


def _get_store(request: Request) -> KnowledgeStore:
    return KnowledgeStore(request.app.state.root_dir)


def _make_extractor() -> KnowledgeExtractor | None:
    """Create a KnowledgeExtractor with LLM client from app config."""
    try:
        reader = ConfigReader()
        secrets = SecretStore()
        llm_config = reader.get_llm_config()
        api_key = secrets.get_llm_api_key(reader)
        if not api_key:
            return None
        client = LLMClient(
            api_key=api_key,
            base_url=llm_config.get("base_url", secrets.get_llm_endpoint(reader)),
            model=llm_config.get("model", ""),
            timeout=120,
        )
        return KnowledgeExtractor(llm_client=client)
    except Exception:
        return None


def _bytes_to_tempfile(content: bytes, suffix: str) -> Path:
    """Write bytes to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, content)
    os.close(fd)
    return Path(path)


@router.post("/upload")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload a TXT/PDF/DOCX file, extract knowledge via LLM, store results.

    Returns document ID, filename, item count, and extraction summary.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        source_type = _detect_source_type(file.filename, file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ext = _EXT_BY_SOURCE_TYPE[source_type]

    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )
    if not content_bytes:
        raise HTTPException(status_code=400, detail="File is empty")

    # Parse text based on file type
    if source_type == SourceType.TXT:
        text = content_bytes.decode("utf-8", errors="replace").strip()
    else:
        # PDF or DOCX: write to temp file, parse, then clean up
        tmp_path = _bytes_to_tempfile(content_bytes, suffix=ext)
        try:
            text = parse_file(tmp_path).strip()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse {ext} file: {e}",
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    if not text:
        raise HTTPException(status_code=400, detail="Parsed text is empty")

    store = _get_store(request)

    # Create document record
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc = KnowledgeDocument(
        id=doc_id,
        filename=file.filename,
        source_type=source_type,
        parsed_text=text,
    )
    store.save_document(doc)

    # Extract knowledge via LLM
    items = []
    extractor = _make_extractor()
    if extractor is not None:
        try:
            extracted = extractor.extract(text, source_document=file.filename)
            # Assign document_id to each item
            for item in extracted:
                item.document_id = doc_id
            if extracted:
                store.save_items(extracted)
                items = extracted
        except Exception:
            pass

    # Build summary
    type_counts: dict[str, int] = {}
    for item in items:
        t = item.type.value if hasattr(item.type, "value") else str(item.type)
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "document_id": doc_id,
        "filename": file.filename,
        "item_count": len(items),
        "summary": type_counts,
    }


@router.get("/documents")
def list_documents(request: Request):
    """List all uploaded knowledge documents."""
    store = _get_store(request)
    docs = store.list_documents()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "source_type": d.source_type,
            "created_at": d.created_at,
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}/items")
def get_document_items(request: Request, doc_id: str):
    """Get extracted knowledge items for a document."""
    store = _get_store(request)
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    items = store.list_items(document_id=doc_id)
    return [item.to_dict() for item in items]


@router.get("/selling-points")
def list_selling_points(
    request: Request,
    priority_min: int | None = Query(None, ge=1, le=5),
    priority_max: int | None = Query(None, ge=1, le=5),
    tags: str | None = Query(None, description="Comma-separated tags"),
):
    """List all selling points with optional priority/tag filters."""
    store = _get_store(request)
    tag_list: list[str] | None = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    items = store.list_selling_points(
        priority_min=priority_min,
        priority_max=priority_max,
        tags=tag_list,
    )
    return [item.to_dict() for item in items]


@router.put("/selling-points/{item_id}")
def update_selling_point(
    request: Request,
    item_id: str,
    body: dict[str, Any],
):
    """Update a selling point's title, content, priority, or tags."""
    store = _get_store(request)
    allowed_keys = {"title", "content", "priority", "tags"}
    fields = {k: v for k, v in body.items() if k in allowed_keys}
    if not fields:
        raise HTTPException(
            status_code=400,
            detail="No valid fields to update. Allowed: title, content, priority, tags",
        )
    updated = store.update_item(item_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Selling point not found")
    return updated.to_dict()


@router.post("/refresh")
def refresh_knowledge(request: Request):
    """Re-parse all uploaded documents and re-extract knowledge items."""
    store = _get_store(request)
    extractor = _make_extractor()
    count = store.refresh_all(extractor)
    return {"refreshed_count": count}
