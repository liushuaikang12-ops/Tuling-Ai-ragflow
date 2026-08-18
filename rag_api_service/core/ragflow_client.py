from __future__ import annotations

import mimetypes
from typing import Any

import httpx


class RAGFlowError(RuntimeError):
    """RAGFlow HTTP API 调用失败。"""


class RAGFlowClient:
    """RAGFlow 官方 HTTP API 的轻量异步客户端。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        dataset_id: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.dataset_id = dataset_id
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(self._headers)
        headers.update(kwargs.pop("headers", {}))
        # RAGFlow 通常部署在 localhost/内网。忽略系统代理，避免本地请求被
        # VPN/HTTP_PROXY 转发后产生 502；外部答案生成客户端不受此设置影响。
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                **kwargs,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RAGFlowError(
                f"RAGFlow 返回了非 JSON 响应: HTTP {response.status_code}"
            ) from exc

        if response.is_error:
            message = payload.get("message") if isinstance(payload, dict) else str(payload)
            raise RAGFlowError(f"RAGFlow HTTP {response.status_code}: {message}")

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise RAGFlowError(str(payload.get("message") or "RAGFlow 请求失败"))

        return payload.get("data") if isinstance(payload, dict) else payload

    async def upload_documents(self, files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        multipart = []
        for name, content in files:
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            multipart.append(("file", (name, content, content_type)))
        data = await self._request(
            "POST",
            f"/api/v1/datasets/{self.dataset_id}/documents",
            files=multipart,
        )
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            docs = data.get("docs") or data.get("documents") or []
            return [item for item in docs if isinstance(item, dict)]
        return []

    async def start_parsing(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        await self._request(
            "POST",
            f"/api/v1/datasets/{self.dataset_id}/chunks",
            json={"document_ids": document_ids},
        )

    async def list_documents(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        # RAGFlow v0.26.x 的 REST API 将单页上限固定为 100。
        page_size = max(1, min(page_size, 100))
        data = await self._request(
            "GET",
            f"/api/v1/datasets/{self.dataset_id}/documents",
            params={"page": page, "page_size": page_size},
        )
        if isinstance(data, list):
            return {"docs": data, "total": len(data)}
        return data if isinstance(data, dict) else {"docs": [], "total": 0}

    async def list_chunks(
        self,
        document_id: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/api/v1/datasets/{self.dataset_id}/documents/{document_id}/chunks",
            params={"page": page, "page_size": page_size},
        )
        if isinstance(data, list):
            return {"chunks": data, "total": len(data)}
        return data if isinstance(data, dict) else {"chunks": [], "total": 0}

    async def update_chunk(
        self,
        document_id: str,
        chunk_id: str,
        *,
        content: str,
        questions: list[str] | None = None,
        important_keywords: list[str] | None = None,
    ) -> None:
        body: dict[str, Any] = {"content": content}
        if questions:
            body["questions"] = questions
        if important_keywords:
            body["important_keywords"] = important_keywords
        await self._request(
            "PATCH",
            f"/api/v1/datasets/{self.dataset_id}/documents/"
            f"{document_id}/chunks/{chunk_id}",
            json=body,
        )

    async def delete_documents(self, document_ids: list[str]) -> None:
        await self._request(
            "DELETE",
            f"/api/v1/datasets/{self.dataset_id}/documents",
            json={"ids": document_ids, "delete_all": False},
        )

    async def delete_all_documents(self) -> None:
        await self._request(
            "DELETE",
            f"/api/v1/datasets/{self.dataset_id}/documents",
            json={"ids": [], "delete_all": True},
        )

    async def retrieve(
        self,
        question: str,
        *,
        similarity_threshold: float,
        vector_similarity_weight: float,
        top_k: int,
        rerank_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "dataset_ids": [self.dataset_id],
            "page": 1,
            "page_size": top_k,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "vector_similarity_weight": vector_similarity_weight,
            # keyword=true 会要求 RAGFlow 调用默认聊天模型做关键词扩展。
            # 检索层不应隐式依赖生成模型，因此默认关闭该扩展；RAGFlow 仍会
            # 按 vector_similarity_weight 执行向量与文本相关性检索。
            "keyword": False,
            "highlight": False,
        }
        if rerank_id:
            body["rerank_id"] = rerank_id
        data = await self._request("POST", "/api/v1/retrieval", json=body)
        return data if isinstance(data, dict) else {"chunks": [], "total": 0}

    async def get_dataset(self) -> dict[str, Any]:
        data = await self._request(
            "GET",
            "/api/v1/datasets",
            params={"id": self.dataset_id, "page": 1, "page_size": 1},
        )
        datasets = data if isinstance(data, list) else (data or {}).get("datasets", [])
        for dataset in datasets:
            if isinstance(dataset, dict) and dataset.get("id") == self.dataset_id:
                return dataset
        return datasets[0] if datasets else {}

    async def update_chunk_size(self, chunk_size: int) -> None:
        dataset = await self.get_dataset()
        parser_config = dict(dataset.get("parser_config") or {})
        parser_config["chunk_token_num"] = chunk_size
        await self._request(
            "PUT",
            f"/api/v1/datasets/{self.dataset_id}",
            json={"parser_config": parser_config},
        )
