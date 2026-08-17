from __future__ import annotations

from typing import Any, Protocol


class RAGBackend(Protocol):
    async def upload_files(
        self,
        files: list[tuple[str, bytes]],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> dict[str, Any]: ...

    async def list_documents(self) -> list[dict[str, Any]]: ...

    async def get_document_chunks(
        self, doc_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]: ...

    async def delete_document(self, doc_id: str) -> dict[str, Any]: ...

    async def reset_system(self) -> dict[str, str]: ...

    async def get_chunk_config(self) -> dict[str, int]: ...

    async def update_chunk_config(
        self, chunk_size: int, chunk_overlap: int
    ) -> dict[str, Any]: ...

    async def query(self, query: str) -> dict[str, Any]: ...
