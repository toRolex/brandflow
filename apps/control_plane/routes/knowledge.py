from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from packages.knowledge_store.extractor import KnowledgeExtractor
from packages.knowledge_store.models import KnowledgeDocument
from packages.knowledge_store.store import KnowledgeStore
from packages.pipeline_services.llm_client import LLMClient
from packages.provider_config.app_config import AppConfigManager

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".txt"}


def _get_store(request: Request) -> KnowledgeStore:
    return KnowledgeStore(request.app.state.root_dir)


def _make_extractor() -> KnowledgeExtractor | None:
    """Create a KnowledgeExtractor with LLM client from app config."""
    try:
        cfg = AppConfigManager()
        llm_config = cfg.get_llm_config()
        api_key = cfg.get_llm_api_key()
        if not api_key:
            return None
        client = LLMClient(
            api_key=api_key,
            base_url=llm_config.get("base_url", cfg.get_llm_endpoint()),
            model=llm_config.get("model", ""),
            timeout=120,
        )
        return KnowledgeExtractor(llm_client=client)
    except Exception:
        return None


@router.post("/upload")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload a TXT file, extract knowledge via LLM, store results.

    Returns document ID, filename, item count, and extraction summary.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only TXT files are allowed.",
        )

    content_bytes = await file.read()
    text = content_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        raise HTTPException(status_code=400, detail="File is empty")

    store = _get_store(request)

    # Create document record
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc = KnowledgeDocument(
        id=doc_id,
        filename=file.filename,
        source_type="txt",
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
