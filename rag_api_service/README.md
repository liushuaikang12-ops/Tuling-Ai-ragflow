# rag_api_service 说明文档

## 1. 服务定位

`rag_api_service` 是系统中的知识库适配服务，负责：

- 文件上传与文档摄取
- 文档管理（文档列表）
- 系统重置
- RAG 知识库问答（检索 → 生成）

服务支持两个可切换后端：

- `legacy`：项目原有 LlamaIndex + ChromaDB + BM25 实现。
- `ragflow`：通过官方 HTTP API 使用独立部署的 RAGFlow，由 RAGFlow 负责文档解析、分块、索引和检索。

对外仍维持原来的 `/api/docs/*` 协议，因此 `main_service`、`mcp_service` 和前端无需同步切换。

---

## 2. 目录结构

```text
rag_api_service/
├── core/
│   ├── application.py      # RAGApplication 主类
│   ├── backend.py          # legacy/RAGFlow 后端适配与统一契约
│   ├── ragflow_client.py   # RAGFlow HTTP API 客户端
│   ├── ingestion.py        # 文档摄取管道
│   ├── workflow.py         # RAGWorkflow 混合检索工作流
│   ├── pdf_parser.py       # PDF 处理器 (pymupdf4llm)
│   ├── pdfProcessor.py     # PDF 处理器 (unstructured，旧版)
│   ├── documentManager.py  # ChromaDB 文档管理器
│   └── events.py           # 工作流事件定义
├── utils/
│   └── logger.py           # 日志工具
├── config/
│   └── settings.py         # 服务配置
├── file/                   # 数据目录
│   ├── chroma_db/          # ChromaDB 向量数据库
│   ├── storage_bm25/       # BM25 索引
│   ├── documents/          # 文档文件
│   ├── image/              # PDF 提取的图片
│   ├── storage/            # 通用存储
│   └── logs/               # 日志文件
├── rest_api.py             # REST API 路由
├── run.py                  # 启动入口
├── pyproject.toml          # 依赖清单（uv 管理）
└── uv.lock                 # 依赖锁定文件
```

---

## 3. REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/docs/upload` | 上传文件（multipart），触发文档摄取 |
| GET  | `/api/docs/documents` | 返回已入库文档列表 |
| GET  | `/api/docs/chunks/{doc_id}` | 获取文档分块详情（支持分页） |
| DELETE | `/api/docs/documents/{doc_id}` | 删除单个文档 |
| GET  | `/api/docs/config/chunk` | 获取当前分块配置 |
| PUT  | `/api/docs/config/chunk` | 更新分块配置（chunk_size/chunk_overlap） |
| POST | `/api/docs/reset` | 重置系统 |
| POST | `/api/docs/query` | 知识库问答 |

### `/api/docs/query` 请求格式

```json
{
    "query": "用户问题"
}
```

返回格式：

```json
{
    "answer": "回答内容",
    "sources": ["来源1", "来源2"]
}
```

---

## 4. RAGFlow 接入

在 RAGFlow Cloud 或自托管 RAGFlow 中创建 Dataset 并获取 API Key，然后在项目根目录 `.env` 中配置。使用 Cloud 时无需本地 Docker：

```env
RAG_BACKEND=ragflow
RAGFLOW_BASE_URL=https://cloud.ragflow.io
RAGFLOW_API_KEY=ragflow-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAGFLOW_DATASET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

自托管时只需把 `RAGFLOW_BASE_URL` 改为实际地址，例如 `http://127.0.0.1:9380`。

RAGFlow 模式下的调用关系：

```text
上传：/api/docs/upload -> RAGFlow upload -> RAGFlow parse
查询：/api/docs/query  -> RAGFlow retrieval -> DashScope 生成答案
管理：文档列表/分块/删除/重置 -> RAGFlow dataset API
```

文档解析是异步任务。上传成功只表示 RAGFlow 已接受任务，可通过文档列表中的 `status`、`progress` 和 `progress_msg` 查看进度。

RAGFlow 内置解析器用 `chunk_token_num` 控制分块大小，没有与 legacy `chunk_overlap` 完全等价的参数；RAGFlow 模式下接口会返回 `chunk_overlap=0`。

### 编号公式转写

自托管 RAGFlow 可加载 `deployment/docker-compose.ragflow-formula.yml`。解析完成后，
适配层会审计带编号的公式 Chunk：已有可信 LaTeX 时直接规范化；只有扁平 OCR 时，
通过受 Dataset 权限保护的 `/api/v1/datasets/{dataset_id}/formula-vision` 读取公式
裁剪图，并调用 RAGFlow 中配置的默认 `IMAGE2TEXT` 模型转写。结果以
`名称 + 编号 + 文档 + PDF 页码 + 原文上下文 + LaTeX` 写回原 Chunk，并重新建立
检索向量。`GET /api/docs/chunks/{doc_id}` 会返回 `formula_format`、
`formula_name` 和 `equation_numbers` 元数据。

## 5. 启动方式

在项目根目录执行：

```bash
uv run --project rag_api_service python rag_api_service/run.py
```

默认监听：

- `http://127.0.0.1:8011`

---

## 6. 关键配置

配置文件：`rag_api_service/config/settings.py`

重点环境变量：

- `DASHSCOPE_API_KEY`：模型调用密钥
- `DASHSCOPE_BASE_URL`：模型接口地址
- `DASHSCOPE_MODEL`：默认模型
- `MODEL_TEMPERATURE`：默认温度
- `EMBEDDING_MODEL_PATH`：Embedding 模型路径
- `CHUNK_SIZE`：文本切块大小
- `RERANK_MODEL_PATH`：重排模型路径
- `SIMILARITY_TOP_K`：检索召回数量
- `RERANK_TOP_K`：重排保留数量

RAGFlow 模式配置：

- `RAG_BACKEND`：`ragflow`（默认）或 `legacy`
- `ENABLE_LEGACY_RAG`：默认 `false`；只有明确允许旧后端时才能设为 `true`
- `RAGFLOW_BASE_URL`：RAGFlow HTTP 地址
- `RAGFLOW_API_KEY`：RAGFlow API Key
- `RAGFLOW_DATASET_ID`：目标 Dataset ID
- `RAGFLOW_SIMILARITY_THRESHOLD`：最低相似度
- `RAGFLOW_VECTOR_SIMILARITY_WEIGHT`：向量相似度权重
- `RAGFLOW_TOP_K`：最大召回数量
- `RAGFLOW_RERANK_ID`：可选 Rerank 模型 ID

路径类配置：

- `CHROMA_PERSIST_DIR`、`BM25_PERSIST_DIR`、`DOCUMENTS_DIR`、`PDF_IMAGE_DIR` 自动基于 `rag_api_service/file/` 生成

---

## 7. 运行依赖

- RAGFlow 模式：独立运行的 RAGFlow 服务，以及可用的 Dataset/API Key。
- RAGFlow 模式执行 `uv sync --python 3.11` 即可，只安装轻量 HTTP 服务依赖。
- legacy 模式：先执行 `uv sync --python 3.11`，再执行 `uv pip install --python .venv -r requirements-legacy.txt`，并准备 Redis、ChromaDB、本地 Embedding/Reranker 模型和可写数据目录。
- legacy 模式还必须同时配置 `RAG_BACKEND=legacy` 和 `ENABLE_LEGACY_RAG=true`，否则服务会拒绝启动旧解析链路。
- 两种模式都需要可用的答案生成模型配置。

---

## 8. 被调用关系

```text
main_service  → HTTP REST → rag_api_service  (文件上传/文档列表/重置)
mcp_service   → HTTP REST → rag_api_service  (RAG 查询 /api/docs/query)
```
