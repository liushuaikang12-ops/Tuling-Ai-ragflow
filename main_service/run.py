from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=os.getenv("MAIN_SERVICE_RELOAD", "false").lower() == "true",
        log_level="info",
    )
