"""Shared-workspace PDF ingestion and document-scoped question answering."""
from __future__ import annotations

import io
import asyncio
import base64
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf import PdfWriter
import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.core.config import get_settings
from app.db.mongodb import get_mongodb
from app.db.repositories.search_new import SearchRepository
from app.models.chunks import Chunk
from app.services.embedding import EmbeddingService
from app.services.rag import RAGService

logger = logging.getLogger(__name__)
router = APIRouter()
ask_router = APIRouter()
DOCUMENTS_COLLECTION = "manual_documents"
CHUNK_CHARS = 1800
CHUNK_OVERLAP = 250
OCR_PAGES_PER_REQUEST = 15


def _ocr_pdf_pages(payload: bytes, page_count: int, settings) -> list[str]:
    """OCR a PDF in Document AI's 15-page online request chunks."""
    if not settings.DOCUMENT_AI_PROCESSOR_NAME:
        raise HTTPException(status_code=503, detail="This PDF needs OCR. Configure DOCUMENT_AI_PROCESSOR_NAME and grant the service account Document AI access.")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    reader = PdfReader(io.BytesIO(payload), strict=False)
    page_texts: list[str] = []
    processor = settings.DOCUMENT_AI_PROCESSOR_NAME
    endpoint = f"https://{settings.DOCUMENT_AI_LOCATION}-documentai.googleapis.com/v1/{processor}:process"
    for start in range(0, page_count, OCR_PAGES_PER_REQUEST):
        writer = PdfWriter()
        end = min(start + OCR_PAGES_PER_REQUEST, page_count)
        for page_index in range(start, end):
            writer.add_page(reader.pages[page_index])
        buffer = io.BytesIO()
        writer.write(buffer)
        response = session.post(endpoint, json={"rawDocument": {
            "content": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "mimeType": "application/pdf"}}, timeout=120)
        response.raise_for_status()
        document = response.json().get("document", {})
        text = document.get("text", "")
        pages = document.get("pages", [])
        for page_offset in range(end - start):
            if page_offset >= len(pages):
                page_texts.append("")
                continue
            segments = pages[page_offset].get("layout", {}).get("textAnchor", {}).get("textSegments", [])
            page_texts.append(" ".join(text[int(seg.get("startIndex", 0)):int(seg.get("endIndex", 0))] for seg in segments).strip())
    return page_texts


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    document_ids: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=5, ge=1, le=10)


def _split_page(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + CHUNK_CHARS // 2, end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


@router.post("/upload", status_code=201)
async def upload_pdf(file: UploadFile = File(...)):
    settings = get_settings()
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".pdf") or file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Upload a PDF file.")
    payload = await file.read(settings.MAX_PDF_UPLOAD_MB * 1024 * 1024 + 1)
    if len(payload) > settings.MAX_PDF_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {settings.MAX_PDF_UPLOAD_MB} MB limit.")
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File is not a valid PDF.")

    try:
        reader = PdfReader(io.BytesIO(payload), strict=False)
        if reader.is_encrypted:
            raise HTTPException(status_code=422, detail="Encrypted PDFs are not supported.")
        if not reader.pages or len(reader.pages) > settings.MAX_PDF_PAGES:
            raise HTTPException(status_code=422, detail=f"PDF must contain 1 to {settings.MAX_PDF_PAGES} pages.")
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read this PDF.") from exc
    if any(not text.strip() for text in page_texts):
        try:
            page_texts = await asyncio.to_thread(_ocr_pdf_pages, payload, len(reader.pages), settings)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Document AI OCR failed")
            raise HTTPException(status_code=502, detail="OCR failed. Verify the Document AI processor, region, API, and service-account permissions.") from exc
    page_chunks = [(page_no, chunk) for page_no, text in enumerate(page_texts, 1)
                   for chunk in _split_page(text)]
    if not page_chunks:
        raise HTTPException(status_code=422, detail="PDF contains no readable text after OCR. Check that it is readable and not blank.")

    mongodb = get_mongodb()
    chunks_collection = mongodb.get_collection(settings.CHUNKS_COLLECTION)
    documents_collection = mongodb.get_collection(DOCUMENTS_COLLECTION)
    if chunks_collection is None or documents_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable.")

    document_id = str(uuid4())
    now = datetime.now(timezone.utc)
    documents_collection.insert_one({"document_id": document_id, "filename": filename,
        "page_count": len(reader.pages), "chunk_count": 0, "status": "processing", "created_at": now})
    write_started = False
    try:
        embedder = EmbeddingService()
        docs = []
        embeddings = await embedder.generate_embeddings([text for _, text in page_chunks])
        if len(embeddings) != len(page_chunks):
            raise ValueError("Embedding response count did not match the number of chunks.")
        for index, (page_no, text) in enumerate(page_chunks, 1):
            embedding = embeddings[index - 1]
            if len(embedding) != settings.VECTOR_DIMENSIONS:
                raise ValueError(f"Embedding dimension mismatch: expected {settings.VECTOR_DIMENSIONS}.")
            chunk_id = f"{document_id}:{index}"
            chunk = Chunk(id=chunk_id, document_id=document_id, source_filename=filename,
                          text=text, page_numbers=[page_no], content_type=["manual"],
                          metadata={"source_pages": str(page_no), "page_count": 1,
                                    "chunk_length": len(text), "document_id": document_id,
                                    "source_filename": filename})
            row = chunk.model_dump(exclude_none=True)
            row[settings.VECTOR_FIELD_NAME] = embedding
            docs.append(row)
        if docs:
            write_started = True
            result = chunks_collection.insert_many(docs, ordered=True)
        documents_collection.update_one({"document_id": document_id}, {"$set": {
            "status": "ready", "chunk_count": len(docs), "completed_at": datetime.now(timezone.utc)}})
        return {"document_id": document_id, "filename": filename, "status": "ready",
                "page_count": len(reader.pages), "chunk_count": len(docs)}
    except Exception as exc:
        if write_started:
            chunks_collection.delete_many({"document_id": document_id})
        documents_collection.update_one({"document_id": document_id}, {"$set": {
            "status": "failed", "error": "Ingestion failed", "failed_at": datetime.now(timezone.utc)}})
        logger.exception("PDF ingestion failed for document %s", document_id)
        detail = "PDF ingestion failed; the document was not marked ready."
        if isinstance(exc, RuntimeError) and "DOCUMENT_AI_PROCESSOR_NAME" in str(exc):
            detail = "This PDF needs OCR. Configure DOCUMENT_AI_PROCESSOR_NAME and grant the service account Document AI access."
        raise HTTPException(status_code=502, detail=detail) from exc


@router.get("")
async def list_documents():
    collection = get_mongodb().get_collection(DOCUMENTS_COLLECTION)
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable.")
    rows = collection.find({}, {"_id": 0}).sort("created_at", -1).limit(100)
    return [{**row, "created_at": row["created_at"].isoformat() if row.get("created_at") else None}
            for row in rows]


@ask_router.post("/ask")
async def ask_document(request: AskRequest):
    settings = get_settings()
    collection = get_mongodb().get_collection(settings.CHUNKS_COLLECTION)
    docs_collection = get_mongodb().get_collection(DOCUMENTS_COLLECTION)
    if collection is None or docs_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable.")
    ready_ids = [row["document_id"] for row in docs_collection.find(
        {"document_id": {"$in": request.document_ids}, "status": "ready"}, {"document_id": 1})]
    if not ready_ids:
        raise HTTPException(status_code=404, detail="No selected ready documents were found.")
    embedding = await EmbeddingService().generate_embedding(request.question)
    if len(embedding) != settings.VECTOR_DIMENSIONS:
        raise HTTPException(status_code=502, detail="Question embedding has an unexpected dimension.")
    try:
        matches = await SearchRepository().vector_search(
            query_embedding=embedding, limit=request.limit,
            num_candidates_multiplier=20, document_ids=ready_ids,
            index_name=settings.DOCUMENT_VECTOR_INDEX_NAME)
    except Exception as exc:
        logger.exception("Document vector retrieval failed")
        raise HTTPException(status_code=503, detail=("Document vector search is unavailable. Configure a separate Atlas vector index named "
            f"'{settings.DOCUMENT_VECTOR_INDEX_NAME}' with {settings.VECTOR_DIMENSIONS} dimensions and a filter field on 'document_id'.")) from exc
    if not matches:
        return {"question": request.question, "answer": "The selected document does not provide enough information to answer this question.", "citations": [], "sources": []}
    source_rows = [row.model_dump() for row in matches]
    answer = await RAGService().generate_answer(request.question, [Chunk(
        id=row.get("chunk_id"), document_id=row.get("document_id"),
        source_filename=row.get("source_filename"), text=row.get("text", ""),
        page_numbers=row.get("page_numbers") or [0], breadcrumb_trail=row.get("breadcrumb_trail"))
        for row in source_rows])
    citations = [{"filename": row.get("source_filename") or "Uploaded PDF",
                  "page_number": (row.get("page_numbers") or [None])[0], "chunk_id": row.get("chunk_id"),
                  "score": row.get("score")} for row in source_rows]
    return {"question": request.question, "answer": answer, "citations": citations, "sources": source_rows}
