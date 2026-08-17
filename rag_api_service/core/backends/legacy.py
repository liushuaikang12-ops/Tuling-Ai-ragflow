from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any

from config.settings import Settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class LegacyRAGBackend:
    """项目原有 LlamaIndex/Chroma/BM25 后端，仅允许显式启用。"""

    def __init__(self) -> None:
        from core.application import RAGApplication
        from core.documentManager import DocumentManager

        self.app = RAGApplication()
        self.doc_manager = DocumentManager()

    async def upload_files(
        self,
        files: list[tuple[str, bytes]],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> dict[str, Any]:
        tmpdir = tempfile.mkdtemp(prefix="rag_api_upload_")
        paths: list[str] = []
        filenames: list[str] = []
        try:
            for name, content in files:
                path = os.path.join(tmpdir, name)
                with open(path, "wb") as file_obj:
                    file_obj.write(content)
                paths.append(path)
                filenames.append(name)

            status, status_text = self.app.upload_and_process_files(
                paths,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            return {
                "status": status,
                "message": status_text,
                "processed_files": filenames,
            }
        except Exception as exc:
            logger.error("Legacy 文件上传失败: %s", exc)
            return {"status": "error", "message": str(exc), "processed_files": []}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def list_documents(self) -> list[dict[str, Any]]:
        return self.doc_manager.get_all_document_names()

    async def get_document_chunks(
        self, doc_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        return self.doc_manager.get_document_chunks(doc_id, page, page_size)

    async def delete_document(self, doc_id: str) -> dict[str, Any]:
        result = self.doc_manager.delete_document(doc_id)
        if result.get("status") == "success":
            try:
                self.app.delete_document_from_redis(doc_id)
            except Exception as exc:
                logger.warning("删除 Redis 存储失败: %s", exc)
            try:
                self.app.rebuild_bm25_index()
            except Exception as exc:
                logger.warning("重建 BM25 索引失败: %s", exc)
        return result

    async def reset_system(self) -> dict[str, str]:
        self.app.reset()
        return {"status": "success", "message": "系统已重置"}

    async def get_chunk_config(self) -> dict[str, int]:
        return {
            "chunk_size": Settings.CHUNK_SIZE,
            "chunk_overlap": Settings.CHUNK_OVERLAP,
        }

    async def update_chunk_config(
        self, chunk_size: int, chunk_overlap: int
    ) -> dict[str, Any]:
        Settings.CHUNK_SIZE = chunk_size
        Settings.CHUNK_OVERLAP = chunk_overlap
        return {
            "status": "success",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

    async def query(self, query: str) -> dict[str, Any]:
        answer, sources = await self.app.query_documents(
            query=query,
            knowledge_bool=True,
        )
        return {
            "answer": answer,
            "sources": [str(source) for source in sources or []],
        }
