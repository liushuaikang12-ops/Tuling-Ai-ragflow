import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """main_service 配置。"""

    PROJECT_ROOT: Path = Path(__file__).parent.parent
    LOG_DIR: Path = PROJECT_ROOT / "file"

    POSTGRES_URL: str = os.getenv(
        "POSTGRES_URL",
        "postgresql+psycopg://postgres:123456@127.0.0.1:5432/langgraph_agents",
    )
    # 本地开发未配置时生成进程级临时密钥，避免使用公开的固定默认值。
    # 多实例或生产部署必须显式配置 JWT_SECRET_KEY。
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
    DASHSCOPE_API_KEY: str | None = os.getenv("DASHSCOPE_API_KEY")
    TEXT_MODEL_API_KEY: str | None = (
        os.getenv("TEXT_MODEL_API_KEY")
        or DEEPSEEK_API_KEY
        or DASHSCOPE_API_KEY
    )
    MODEL: str = os.getenv("TEXT_MODEL_MODEL") or (
        os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        if DEEPSEEK_API_KEY
        else os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    )
    TEXT_MODEL_CONFIGURED: bool = bool(
        TEXT_MODEL_API_KEY
    )
    LANGGRAPH_API_URL: str = os.getenv("LANGGRAPH_API_URL", "http://127.0.0.1:2024")
    LANGGRAPH_ASSISTANT_ID: str = os.getenv("LANGGRAPH_ASSISTANT_ID", "multi_agent")
    MCP_SERVICE_URL: str = os.getenv("MCP_SERVICE_URL", "http://127.0.0.1:8010/mcp")
    RAG_API_URL: str = os.getenv("RAG_API_URL", "http://127.0.0.1:8011/api/docs")
