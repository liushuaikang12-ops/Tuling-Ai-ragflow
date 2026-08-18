from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel

from core.backends import create_backend
from utils.logger import setup_logger


class QueryRequest(BaseModel):
    query: str


class ChunkConfigRequest(BaseModel):
    chunk_size: int
    chunk_overlap: int


class FormulaNormalizeRequest(BaseModel):
    dry_run: bool = False


logger = setup_logger(__name__)

router = APIRouter()

svc: Any = None


def init_rag_service():
    global svc
    if svc is not None:
        return
    svc = create_backend()


@router.post("/upload")
async def upload_docs(
    files: list[UploadFile] = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
):
    init_rag_service()
    try:
        payload = [(file.filename or "unnamed", await file.read()) for file in files]
        result = await svc.upload_files(
            payload,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return result
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_docs():
    init_rag_service()
    try:
        documents = await svc.list_documents()
        return {"documents": documents}
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chunks/{doc_id:path}")
async def get_document_chunks(
    doc_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    init_rag_service()
    try:
        return await svc.get_document_chunks(doc_id, page=page, page_size=page_size)
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id:path}")
async def delete_document(doc_id: str):
    init_rag_service()
    try:
        return await svc.delete_document(doc_id)
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id:path}/normalize-formulas")
async def normalize_document_formulas(
    doc_id: str,
    req: FormulaNormalizeRequest,
):
    init_rag_service()
    try:
        return await svc.normalize_document_formulas(doc_id, dry_run=req.dry_run)
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/chunk")
async def get_chunk_config():
    init_rag_service()
    return await svc.get_chunk_config()


@router.put("/config/chunk")
async def update_chunk_config(req: ChunkConfigRequest):
    if req.chunk_size < 50 or req.chunk_size > 4000:
        raise HTTPException(status_code=400, detail="chunk_size 范围: 50-4000")
    if req.chunk_overlap < 0 or req.chunk_overlap >= req.chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap 必须 >= 0 且 < chunk_size")
    init_rag_service()
    return await svc.update_chunk_config(req.chunk_size, req.chunk_overlap)


@router.post("/reset")
async def reset_system():
    init_rag_service()
    try:
        return await svc.reset_system()
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def query_docs(req: QueryRequest):
    init_rag_service()
    try:
        return await svc.query(
            query=req.query,
        )
    except Exception as e:
        logger.error(str(e))
        raise HTTPException(status_code=500, detail=str(e))
