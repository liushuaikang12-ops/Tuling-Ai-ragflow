from __future__ import annotations

import json
from typing import Any

import httpx

from config.settings import Settings
from core.ragflow_client import RAGFlowClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RAGFlowBackend:
    """仅通过 RAGFlow HTTP API 完成解析、索引和检索。"""

    def __init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("RAGFLOW_API_KEY", Settings.RAGFLOW_API_KEY),
                ("RAGFLOW_DATASET_ID", Settings.RAGFLOW_DATASET_ID),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"RAGFlow 后端缺少配置: {', '.join(missing)}")

        self.client = RAGFlowClient(
            base_url=Settings.RAGFLOW_BASE_URL,
            api_key=Settings.RAGFLOW_API_KEY or "",
            dataset_id=Settings.RAGFLOW_DATASET_ID or "",
            timeout=Settings.RAGFLOW_TIMEOUT_SECONDS,
        )

    async def upload_files(
        self,
        files: list[tuple[str, bytes]],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> dict[str, Any]:
        if not files:
            return {
                "status": "error",
                "message": "请上传至少一个文件",
                "processed_files": [],
            }
        if chunk_size is not None:
            await self.client.update_chunk_size(chunk_size)
        documents = await self.client.upload_documents(files)
        document_ids = [str(doc.get("id")) for doc in documents if doc.get("id")]
        if not document_ids:
            raise RuntimeError("RAGFlow 接受了上传请求，但没有返回文档 ID")
        await self.client.start_parsing(document_ids)
        return {
            "status": "success",
            "message": f"已上传 {len(documents)} 个文档，RAGFlow 正在异步解析",
            "processed_files": [name for name, _ in files],
            "document_ids": document_ids,
            "parsing": True,
        }

    @staticmethod
    def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
        name = str(document.get("name") or document.get("docnm_kwd") or "")
        return {
            "file_name": name,
            "doc_id": str(document.get("id") or ""),
            "file_path": "",
            "upload_time": str(
                document.get("create_date") or document.get("create_time") or ""
            ),
            "file_type": str(document.get("type") or document.get("suffix") or ""),
            "file_size": int(document.get("size") or 0),
            "status": document.get("run"),
            "progress": document.get("progress"),
            "progress_msg": document.get("progress_msg") or "",
            "chunk_count": document.get("chunk_count") or 0,
        }

    async def list_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        while True:
            data = await self.client.list_documents(page=page, page_size=page_size)
            batch = data.get("docs") or data.get("documents") or []
            documents.extend(item for item in batch if isinstance(item, dict))
            total = int(data.get("total") or len(documents))
            if len(batch) < page_size or len(documents) >= total:
                break
            page += 1
        return [
            self._normalize_document(document)
            for document in documents
        ]

    async def get_document_chunks(
        self, doc_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        data = await self.client.list_chunks(doc_id, page=page, page_size=page_size)
        raw_chunks = data.get("chunks") or []
        chunks = []
        for chunk in raw_chunks:
            if not isinstance(chunk, dict):
                continue
            content = str(chunk.get("content") or "")
            chunks.append(
                {
                    "chunk_id": str(chunk.get("id") or ""),
                    "text": content,
                    "metadata": {
                        "file_name": str(chunk.get("docnm_kwd") or ""),
                        "doc_id": doc_id,
                        "content_type": "text",
                        "chunk_size": len(content),
                        "image_id": chunk.get("image_id") or "",
                        "positions": chunk.get("positions") or [],
                        "keywords": chunk.get("important_keywords") or [],
                    },
                }
            )
        return {
            "chunks": chunks,
            "total": int(data.get("total") or len(chunks)),
            "page": page,
            "page_size": page_size,
        }

    async def delete_document(self, doc_id: str) -> dict[str, Any]:
        await self.client.delete_documents([doc_id])
        return {"status": "success", "message": f"已删除文档 {doc_id}"}

    async def reset_system(self) -> dict[str, str]:
        await self.client.delete_all_documents()
        return {"status": "success", "message": "RAGFlow 数据集已清空"}

    async def get_chunk_config(self) -> dict[str, int]:
        dataset = await self.client.get_dataset()
        parser_config = dataset.get("parser_config") or {}
        return {
            "chunk_size": int(
                parser_config.get("chunk_token_num") or Settings.CHUNK_SIZE
            ),
            "chunk_overlap": 0,
        }

    async def update_chunk_config(
        self, chunk_size: int, chunk_overlap: int
    ) -> dict[str, Any]:
        if chunk_size > 2048:
            raise ValueError("RAGFlow 内置解析器的 chunk_size 最大为 2048")
        await self.client.update_chunk_size(chunk_size)
        Settings.CHUNK_SIZE = chunk_size
        Settings.CHUNK_OVERLAP = chunk_overlap
        return {
            "status": "success",
            "chunk_size": chunk_size,
            "chunk_overlap": 0,
        }

    @staticmethod
    def _source_text(chunk: dict[str, Any]) -> str:
        name = str(
            chunk.get("document_name") or chunk.get("docnm_kwd") or "未知文档"
        )
        content = str(chunk.get("content") or "")
        score = chunk.get("similarity")
        score_text = (
            f" (相似度: {float(score) * 100:.1f}%)"
            if isinstance(score, (int, float))
            else ""
        )
        return f"📄 **{name}**{score_text}\n\n> {content}"

    async def _generate_answer(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> str:
        if not chunks:
            return "不知道：知识库中没有检索到足够相关的内容。"
        if not Settings.API_KEY or not Settings.API_BASE_URL:
            excerpts = []
            for index, chunk in enumerate(chunks[:3], 1):
                content = str(chunk.get("content") or "").strip()
                if content:
                    excerpts.append(f"[{index}] {content}")
            return (
                "已检索到以下相关资料（当前未配置文本生成模型，因此返回原始召回内容）：\n\n"
                + "\n\n".join(excerpts)
            )

        context_parts = []
        used_chars = 0
        for index, chunk in enumerate(chunks, 1):
            name = str(
                chunk.get("document_name")
                or chunk.get("docnm_kwd")
                or "未知文档"
            )
            content = str(chunk.get("content") or "")
            part = f"[{index}] 来源：{name}\n{content}"
            if used_chars + len(part) > Settings.RAGFLOW_GENERATION_MAX_CONTEXT_CHARS:
                break
            context_parts.append(part)
            used_chars += len(part)

        prompt = (
            "你是企业知识库问答助手。请仅依据给定资料回答问题，不要编造。"
            "如果资料不足，请明确说明。回答中可使用 [1]、[2] 标注依据。\n\n"
            f"问题：{query}\n\n资料：\n" + "\n\n".join(context_parts)
        )
        base_url = Settings.API_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(
            timeout=Settings.RAGFLOW_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {Settings.API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": Settings.MODEL,
                    "temperature": Settings.TEMPERATURE,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"无法解析模型响应: {json.dumps(payload, ensure_ascii=False)}"
            ) from exc

    async def query(self, query: str) -> dict[str, Any]:
        try:
            result = await self.client.retrieve(
                query,
                similarity_threshold=Settings.RAGFLOW_SIMILARITY_THRESHOLD,
                vector_similarity_weight=Settings.RAGFLOW_VECTOR_SIMILARITY_WEIGHT,
                top_k=Settings.RAGFLOW_TOP_K,
                rerank_id=Settings.RAGFLOW_RERANK_ID,
            )
            raw_chunks = result.get("chunks") or []
            chunks = [chunk for chunk in raw_chunks if isinstance(chunk, dict)]
            answer = await self._generate_answer(query, chunks)
            return {
                "answer": answer,
                "sources": [self._source_text(chunk) for chunk in chunks],
                "retrieval": {
                    "backend": "ragflow",
                    "total": result.get("total") or len(chunks),
                },
            }
        except Exception as exc:
            logger.exception("RAGFlow 查询失败")
            return {
                "answer": f"查询失败: {exc}",
                "sources": [],
                "retrieval": {"backend": "ragflow", "total": 0},
            }
