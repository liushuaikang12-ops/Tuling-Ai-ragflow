import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """langgraph_service 配置。"""

    PROJECT_ROOT: Path = Path(__file__).parent.parent

    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DASHSCOPE_API_KEY: Optional[str] = os.getenv("DASHSCOPE_API_KEY")

    # 通用文本模型配置优先；未显式设置时自动选择 DeepSeek 或 DashScope。
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
    TAVILY_API_KEY: Optional[str] = os.getenv("TAVILY_API_KEY")

    POSTGRES_URL: str = os.getenv(
        "POSTGRES_URL",
        "postgresql+psycopg://postgres:123456@127.0.0.1:5432/langgraph_agents",
    )
    LANGGRAPH_POSTGRES_DSN: str = os.getenv(
        "LANGGRAPH_POSTGRES_DSN",
        "postgresql://postgres:123456@127.0.0.1:5432/langgraph_agents?sslmode=disable",
    )
    MCP_SERVICE_URL: str = os.getenv("MCP_SERVICE_URL", "http://127.0.0.1:8010/mcp")
