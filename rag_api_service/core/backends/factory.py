from __future__ import annotations

from config.settings import Settings
from core.backends.base import RAGBackend
from utils.logger import setup_logger

logger = setup_logger(__name__)


def create_backend() -> RAGBackend:
    """只导入被明确选中的后端，防止解析实现交叉加载。"""
    if Settings.RAG_BACKEND == "ragflow":
        from core.backends.ragflow import RAGFlowBackend

        logger.info("使用 RAGFlow 知识库后端: %s", Settings.RAGFLOW_BASE_URL)
        return RAGFlowBackend()

    if Settings.RAG_BACKEND == "legacy":
        if not Settings.ENABLE_LEGACY_RAG:
            raise RuntimeError(
                "legacy RAG 已被安全开关禁用；如确需启用，请安装独立 legacy 依赖并设置 "
                "ENABLE_LEGACY_RAG=true"
            )

        from core.backends.legacy import LegacyRAGBackend

        logger.warning("显式启用 legacy LlamaIndex/Chroma/BM25 知识库后端")
        return LegacyRAGBackend()

    raise RuntimeError("RAG_BACKEND 仅支持 'ragflow' 或 'legacy'")
