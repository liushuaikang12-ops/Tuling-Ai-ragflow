import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


PROJECT_ROOT = Path(__file__).parent.parent


class Settings:
    PROJECT_ROOT: Path = PROJECT_ROOT
    LOG_DIR: Path = PROJECT_ROOT / "file"

    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DASHSCOPE_API_KEY: Optional[str] = os.getenv("DASHSCOPE_API_KEY")

    # 与 LangGraph 服务保持一致：优先使用通用 OpenAI 兼容配置，其次
    # 自动选择 DeepSeek，最后回退到 DashScope。
    API_KEY: Optional[str] = (
        os.getenv("TEXT_MODEL_API_KEY")
        or DEEPSEEK_API_KEY
        or DASHSCOPE_API_KEY
    )
    API_BASE_URL: Optional[str] = os.getenv("TEXT_MODEL_BASE_URL") or (
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if DEEPSEEK_API_KEY
        else os.getenv("DASHSCOPE_BASE_URL")
    )
    MODEL: str = os.getenv("TEXT_MODEL_MODEL") or (
        os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        if DEEPSEEK_API_KEY
        else os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    )
    TEMPERATURE: float = float(os.getenv("MODEL_TEMPERATURE", "0.1"))
    EMBEDDING_MODEL_PATH: str = os.getenv(
        "EMBEDDING_MODEL_PATH",
        r"D:\llm\Local_model\BAAI\bge-small-zh-v1___5",
    )

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    TITLE_EXTRACTOR_NODES: int = int(os.getenv("TITLE_EXTRACTOR_NODES", "5"))

    SIMILARITY_TOP_K: int = int(os.getenv("SIMILARITY_TOP_K", "5"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "3"))
    RERANK_MODEL_PATH: str = os.getenv(
        "RERANK_MODEL_PATH",
        r"D:\llm\Local_model\BAAI\bge-reranker-large",
    )

    # RAG 后端。legacy 使用项目原有 LlamaIndex/Chroma/BM25 实现；
    # ragflow 通过官方 HTTP API 使用独立部署的 RAGFlow 服务。
    RAG_BACKEND: str = os.getenv("RAG_BACKEND", "ragflow").strip().lower()
    ENABLE_LEGACY_RAG: bool = os.getenv("ENABLE_LEGACY_RAG", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    RAGFLOW_BASE_URL: str = os.getenv("RAGFLOW_BASE_URL", "http://127.0.0.1:9380").rstrip("/")
    RAGFLOW_API_KEY: Optional[str] = os.getenv("RAGFLOW_API_KEY")
    RAGFLOW_FORMULA_VISION_ENABLED: bool = (
        os.getenv("RAGFLOW_FORMULA_VISION_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    RAGFLOW_FORMULA_VISION_DELAY_SECONDS: float = float(
        os.getenv("RAGFLOW_FORMULA_VISION_DELAY_SECONDS", "1.5")
    )
    RAGFLOW_DATASET_ID: Optional[str] = os.getenv("RAGFLOW_DATASET_ID")
    RAGFLOW_TIMEOUT_SECONDS: float = float(os.getenv("RAGFLOW_TIMEOUT_SECONDS", "120"))
    RAGFLOW_SIMILARITY_THRESHOLD: float = float(
        os.getenv("RAGFLOW_SIMILARITY_THRESHOLD", "0.2")
    )
    RAGFLOW_VECTOR_SIMILARITY_WEIGHT: float = float(
        os.getenv("RAGFLOW_VECTOR_SIMILARITY_WEIGHT", "0.3")
    )
    RAGFLOW_TOP_K: int = int(os.getenv("RAGFLOW_TOP_K", "8"))
    RAGFLOW_RERANK_ID: Optional[str] = os.getenv("RAGFLOW_RERANK_ID")
    RAGFLOW_GENERATION_MAX_CONTEXT_CHARS: int = int(
        os.getenv("RAGFLOW_GENERATION_MAX_CONTEXT_CHARS", "24000")
    )

    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "file/chroma_db")
    BM25_PERSIST_DIR: str = str(PROJECT_ROOT / "file/storage_bm25")
    DOCUMENTS_DIR: str = str(PROJECT_ROOT / "file/documents")
    DEFAULT_PERSIST_DIR: str = str(PROJECT_ROOT / "file/storage")
    PDF_IMAGE_DIR: str = str(PROJECT_ROOT / "file/image")

    HOST: str = os.getenv("RAG_API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("RAG_API_PORT", "8011"))
