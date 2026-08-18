# 帅康 AI：基于 RAGFlow 与 LangGraph 的多模式知识助手

帅康 AI 是一个面向知识库问答、通用智能体和长文写作场景的本地微服务项目。本分支在原 Tuling-Ai 项目基础上，引入独立部署的 RAGFlow 作为默认文档解析与检索后端，并使用 LangGraph 组织三种交互模式。

项目当前支持：

- 智能体模式：自动识别普通对话、知识检索和写作意图。
- 知识库模式：强制走 RAGFlow 检索，返回答案和可展开来源。
- 写作模式：需求理解、资料收集、大纲、草稿、审核、修订和人工确认。
- 文档管理：上传、解析状态、分块查看和文档删除。
- 交互式使用说明：可视化展示 LlamaIndex、LangGraph 和 RAGFlow 的处理流程。

> 当前默认 RAG 后端是 RAGFlow。原有 LlamaIndex + ChromaDB + BM25 实现作为可选 Legacy 后端保留，但不会在 RAGFlow 模式下导入或安装。

## 一、项目基于哪些开源项目

本项目不是从零实现所有基础能力，而是在以下开源项目之上进行集成和工程化改造：

| 开源项目 | 本项目中的用途 |
|---|---|
| [Tuling-Ai](https://github.com/chujian66688/Tuling-Ai) | 上游项目；提供原始微服务、LangGraph、MCP、LlamaIndex RAG 和 Vue 前端基础 |
| [RAGFlow](https://github.com/infiniflow/ragflow) | 当前默认的文档解析、版面理解、分块、索引和检索后端 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 多智能体状态图、条件路由、线程状态和中断恢复 |
| [LangMem](https://github.com/langchain-ai/langmem) | 长对话摘要和短期记忆压缩 |
| [LlamaIndex](https://github.com/run-llama/llama_index) | 可选 Legacy 数据接入、分块和检索工作流 |
| [Model Context Protocol](https://github.com/modelcontextprotocol) / FastMCP | 将知识检索封装为 `query_rag` 工具 |
| [FastAPI](https://github.com/fastapi/fastapi) | 主服务和 RAG REST API |
| [Vue](https://github.com/vuejs/core) + Vite | 登录、聊天、文档管理和使用说明页面 |

各上游项目仍遵循其各自的许可证和商标规则。本仓库的独立许可证尚待补充。

## 二、原架构的核心问题

本次改造主要解决以下工程问题。

### 1. 文档解析和应用服务耦合过重

原有实现把 PDF 解析、LlamaIndex 摄取、ChromaDB、BM25、重排和回答生成集中在 `rag_api_service` 内部：

- Python 依赖数量多，安装和启动成本高。
- 解析、索引和查询共享同一套实现，难以单独替换。
- MCP 服务容易承担超出“工具代理”职责的 RAG 代码。
- 文档解析质量和复杂版面能力受本地实现限制。

### 2. RAG 后端无法真正独立切换

如果在模块导入阶段加载 Legacy 代码，即使配置了 RAGFlow，仍可能安装或加载 LlamaIndex、ChromaDB、Sentence-Transformers 等依赖，不能算完全解耦。

### 3. 复杂文档缺少统一理解链路

普通文本切分无法充分处理：

- 扫描 PDF 的 OCR 文本。
- 多栏版面与阅读顺序。
- 图片区域及其语义。
- 表格的行列结构。
- 公式区域和上下标符号。

### 4. 三种用户模式不够明确

原前端只有一个不明显的知识库开关，写作工作流主要依赖模型自动识别，用户无法明确选择“智能体 / 知识库 / 写作”。

### 5. 本地部署缺少完整闭环

首次部署还存在数据库初始化顺序、日志目录、系统代理访问 localhost、模型提供商写死、文档入口隐藏等问题。

## 三、本分支完成了哪些改造

### 1. RAGFlow 成为默认 RAG 后端

`rag_api_service` 通过后端工厂按配置加载实现：

```text
RAG_BACKEND=ragflow  → 只导入 RAGFlowBackend
RAG_BACKEND=legacy   → 需要同时设置 ENABLE_LEGACY_RAG=true
```

主要变化：

- 新增 `core/backends/base.py`、`factory.py`、`ragflow.py`、`legacy.py`。
- 新增独立的 `RAGFlowClient`，封装上传、列表、分块、删除、解析和检索 API。
- RAGFlow 模式默认不安装 LlamaIndex、ChromaDB 和本地重排模型。
- Legacy 重依赖移动到 `rag_api_service/requirements-legacy.txt`。
- RAGFlow 与 Legacy 不在模块导入阶段互相引用。
- RAGFlow 检索结果适配为项目统一的 `answer / sources` 响应。

### 2. 文档解析转交给独立 RAGFlow

当前本地 RAGFlow 配置使用：

- DeepDoc：OCR、版面区域识别和阅读顺序恢复。
- GLM Vision：仅用于图片等视觉内容理解，不用于普通文本聊天。
- Qwen3-Embedding-0.6B + TEI：本地生成 1024 维文本向量。
- Elasticsearch：RAGFlow 检索索引。
- RAGFlow Dataset：统一管理上传文档、解析任务和 Chunk。

复杂文档处理关注点：

| 内容类型 | 处理方式 |
|---|---|
| 正文与扫描文本 | 页面渲染、文字检测、OCR 和阅读顺序恢复 |
| 公式 | 检测公式区域并尽量保留表达；扫描质量会影响符号和上下标准确率 |
| 图片 | 提取图片区域，使用视觉模型生成可检索语义描述 |
| 表格 | 检测表格区域和单元格关系，组织为结构化文本进入分块 |
| 标题与段落 | 根据版面和语义边界形成 Chunk，而不是只按固定字符盲切 |

部分由 Word/MathType 生成的论文 PDF 会把 SymbolMT 字体暴露为 `U+F0xx`
私有区字符。`rag_api_service` 会在展示 Chunk、拼接来源和生成回答前，将
这些编码还原为标准的希腊字母与数学符号；前端使用 KaTeX 渲染模型返回的
LaTeX。公式类问题还会从高相关 Chunk 中识别“方程 (1.1)”等编号，执行一次
编号定向召回，避免“表达式如下”和公式本体被分到不同 Chunk 后只召回前者。
这个兼容层不能凭空恢复解析阶段已经丢失的公式结构：如果 RAGFlow
解析日志中出现视觉模型 `429`，应先处理模型配额或限流，再重新解析原文档。

### 3. MCP 变为纯查询代理

`mcp_service` 只公开一个工具：

```text
query_rag(query)
```

调用链：

```text
LangGraph knowledge_agent
  → MCP streamable-http
  → mcp_service.query_rag
  → HTTP POST rag_api_service/api/docs/query
  → RAGFlow retrieval
```

上传、列表、分块和删除等文档管理操作不经过 MCP，由 `main_service` 直接通过 REST 调用 `rag_api_service`。

### 4. LangGraph 新增显式三模式路由

前端请求包含：

```json
{
  "query": "用户输入",
  "mode": "agent | knowledge | writing"
}
```

- `agent`：由 `intent_router` 自动选择 chat、knowledge 或 writing。
- `knowledge`：直接进入 `knowledge_agent`，不再额外做意图识别。
- `writing`：直接进入写作子图。

知识回答质量较差时，`knowledge_guard` 可以进入 Tavily 搜索兜底；未配置 Tavily 时会给出明确提示，不阻塞图加载。

### 5. 文本模型支持 DeepSeek 与 DashScope

文本模型配置不再写死单一提供商，优先级如下：

```text
TEXT_MODEL_* 通用 OpenAI 兼容配置
  → DEEPSEEK_*
  → DASHSCOPE_*
```

当前本地验证使用 DeepSeek OpenAI 兼容接口。视觉模型密钥与文本模型密钥保持职责分离。

### 6. 前端功能完善

- 品牌更新为“帅康 AI”。
- 增加清晰的智能体、知识库和写作模式选择器。
- 聊天页右上角和侧边栏提供文档上传入口。
- 新增交互式“使用说明”页面。
- 使用说明包含 LlamaIndex 接入、LangGraph 三模式、RAGFlow 多模态解析流程。
- 文档来源、写作进度、人工审阅和会话管理保留流式交互。

### 7. 本地部署稳定性修复

- localhost 微服务请求显式禁用系统/VPN HTTP 代理。
- 修复主服务首次启动时先迁移、后建表的顺序问题。
- 日志目录改为递归创建。
- 后台运行时默认关闭 Uvicorn 热重载。
- 未配置 JWT 密钥时生成进程级临时强密钥；生产和多实例必须显式配置。
- 新增 PostgreSQL 本地基础设施 Compose 文件。

## 四、整体架构

```text
┌──────────────────────────────────────────────────────────────┐
│                 chat-ai-ui-main · Vue 3 :5173                │
│ 登录 / 会话 / 三种模式 / 文档管理 / 交互式使用说明              │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP + SSE
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   main_service · FastAPI :8000               │
│ JWT / 用户 / 会话 / 路由聚合 / LangGraph SDK                  │
└───────────────┬───────────────────────────────┬──────────────┘
                │                               │
                │ langgraph-sdk                 │ REST 文档管理
                ▼                               ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│ langgraph_service :2024      │    │ rag_api_service :8011        │
│ 摘要 / 意图 / Agent / 写作子图 │    │ RAG 后端工厂 / 统一 REST API    │
└───────────────┬──────────────┘    └───────────────▲──────────────┘
                │ MCP streamable-http              │ HTTP query
                ▼                                  │
┌──────────────────────────────┐                    │
│ mcp_service :8010/mcp        │────────────────────┘
│ 仅公开 query_rag              │
└──────────────────────────────┘
                                                     │
                         RAG_BACKEND=ragflow         ▼
                                ┌──────────────────────────────┐
                                │ 独立 RAGFlow 服务 :9380       │
                                │ DeepDoc / Vision / TEI / ES  │
                                └──────────────────────────────┘

PostgreSQL :5432
  ├─ main_service 用户与会话
  └─ LangGraph checkpoint / 线程恢复
```

## 五、服务职责与端口

| 服务 | 端口 | 职责 |
|---|---:|---|
| `chat-ai-ui-main` | 5173 | Vue 前端、SSE 聊天、文档管理和说明页面 |
| `main_service` | 8000 | JWT 鉴权、用户/会话管理、统一对外入口 |
| `langgraph_service` | 2024 | 多智能体编排、记忆、路由、写作子图 |
| `mcp_service` | 8010 | `query_rag` MCP 纯代理 |
| `rag_api_service` | 8011 | 文档管理与 RAG 查询适配层 |
| PostgreSQL | 5432 | 用户、会话和 LangGraph 状态持久化 |
| RAGFlow | 9380 | 独立文档解析、索引和检索服务 |

推荐启动顺序：

```text
RAGFlow / PostgreSQL
  → rag_api_service
  → mcp_service
  → langgraph_service
  → main_service
  → chat-ai-ui-main
```

## 六、LangGraph 工作流

### 主图

```text
START
  → summarize
  → intent_router
      ├─ knowledge_agent
      │    → knowledge_guard
      │         ├─ finalize
      │         └─ fallback_search → finalize
      ├─ writing_workflow → finalize
      └─ chat_agent → finalize
  → END
```

### 三种模式

#### 智能体模式

```text
用户输入
  → 对话摘要
  → 意图识别
  → 自动选择 chat / knowledge / writing
  → 返回流式结果
```

#### 知识库模式

```text
用户问题
  → knowledge_agent
  → MCP query_rag
  → rag_api_service
  → RAGFlow 混合召回
  → answer + sources
  → quality guard
  → finalize
```

#### 写作模式

```text
understand
  ├─ 需求不清晰 → ask_clarification → understand
  └─ 需求清晰 → research → outline → draft → review
                                         ▲         │
                                         └─ revise ┘
                                                   │
                                             human_review
                                         ┌─────────┼──────────┐
                                      approve     edit      rewrite
                                         └─────────┴──────────┘
                                                   ↓
                                             format_output
```

## 七、文档处理与检索流程

### 当前默认：RAGFlow

```text
文件上传
  → RAGFlow Dataset
  → 异步解析任务
  → 页面渲染与版面分析
  → OCR / 公式区域 / 图片理解 / 表格结构
  → 结构化 Chunk
  → 本地 TEI Embedding
  → Elasticsearch 索引
  → 混合检索
  → answer + sources
```

### 可选：LlamaIndex Legacy

只有同时满足以下条件才允许启动：

```env
RAG_BACKEND=legacy
ENABLE_LEGACY_RAG=true
```

处理流程：

```text
SimpleDirectoryReader / MultimodalPDFProcessor
  → LlamaIndex Document
  → SentenceSplitter
  → Chroma Vector Index + BM25 Index
  → Hybrid Retrieval
  → SentenceTransformerRerank
  → answer + sources
```

## 八、目录结构

```text
Tuling-Ai-ragflow/
├─ chat-ai-ui-main/chat-ai-ui-main/
│  ├─ src/components/          # 聊天输入、侧边栏、消息组件
│  ├─ src/stores/              # Pinia 用户与会话状态
│  ├─ src/views/               # 登录、聊天、文档管理、使用说明
│  └─ src/assets/              # 帅康 AI 图标
├─ main_service/
│  ├─ app/routers/             # chat / documents / users
│  ├─ app/services/            # LangGraph 与 RAG API 客户端
│  └─ models.py                # 用户与会话模型
├─ langgraph_service/
│  ├─ my_agent/agent.py        # 主图定义
│  ├─ my_agent/utils/          # 状态、节点、MCP 与搜索工具
│  └─ my_agent/writing_subgraph/
├─ mcp_service/
│  └─ mcp_server.py            # query_rag 纯代理
├─ rag_api_service/
│  ├─ core/backends/           # RAGFlow / Legacy 后端隔离
│  ├─ core/ragflow_client.py   # RAGFlow HTTP 客户端
│  ├─ core/ingestion.py        # Legacy LlamaIndex 摄取
│  ├─ core/workflow.py         # Legacy 混合检索
│  └─ requirements-legacy.txt
├─ docker-compose.infrastructure.yml
├─ .env.example
└─ AGENTS.md
```

## 九、快速开始

### 1. 环境要求

- Windows 10/11 或 Linux。
- Python 3.11。
- Node.js 18+。
- [uv](https://github.com/astral-sh/uv)。
- Docker Desktop / Docker Engine。
- 独立部署并可访问的 RAGFlow。

### 2. 克隆与配置

```powershell
git clone https://github.com/liushuaikang12-ops/Tuling-Ai-ragflow.git
cd Tuling-Ai-ragflow
Copy-Item .env.example .env
```

最小配置示例：

```env
RAG_BACKEND=ragflow
ENABLE_LEGACY_RAG=false

RAGFLOW_BASE_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=ragflow-your-key
RAGFLOW_DATASET_ID=your-dataset-id

POSTGRES_URL=postgresql+psycopg://postgres:123456@127.0.0.1:5432/langgraph_agents
LANGGRAPH_POSTGRES_DSN=postgresql://postgres:123456@127.0.0.1:5432/langgraph_agents?sslmode=disable

# 文本模型任选一种
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 或使用 DashScope
# DASHSCOPE_API_KEY=sk-your-key
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# DASHSCOPE_MODEL=qwen-plus

JWT_SECRET_KEY=replace-with-a-random-secret
NO_PROXY=127.0.0.1,localhost
no_proxy=127.0.0.1,localhost
```

不要提交 `.env`。仓库中的 `.env.example` 只包含占位符。

如果使用 RAGFlow v0.26.4 的 CPU TEI，文档 Chunk 数超过默认客户端批量上限，或本地 Qwen3 Embedding 单批处理超过 30 秒时，解析会在向量化阶段失败。本仓库提供了可复现的 [CPU TEI 稳定性补丁](deployment/README.md)，将请求拆成小批次并延长单批超时。

### 3. 启动 PostgreSQL

```powershell
docker compose -f docker-compose.infrastructure.yml up -d
```

### 4. 安装依赖

```powershell
uv sync --project rag_api_service --python 3.11
uv sync --project mcp_service --python 3.11
uv sync --project langgraph_service --python 3.11
uv sync --project main_service --python 3.11

cd chat-ai-ui-main/chat-ai-ui-main
npm install
cd ../..
```

Legacy 后端额外安装：

```powershell
uv pip install --python rag_api_service/.venv -r rag_api_service/requirements-legacy.txt
```

### 5. 启动五个服务

在项目根目录分别打开终端：

```powershell
uv run --project rag_api_service python rag_api_service/run.py
uv run --project mcp_service python mcp_service/run.py
uv run --project langgraph_service langgraph dev --config langgraph_service/langgraph.json --no-reload --no-browser
uv run --project main_service python main_service/run.py

cd chat-ai-ui-main/chat-ai-ui-main
npm run dev
```

### 6. 访问

- 帅康 AI：http://127.0.0.1:5173
- 交互式使用说明：http://127.0.0.1:5173/guide
- main_service API：http://127.0.0.1:8000/docs
- LangGraph API：http://127.0.0.1:2024/docs
- RAGFlow API：http://127.0.0.1:9380

默认本地管理员：

```text
用户名：root
密码：admin123
```

对外展示前务必修改默认密码并固定 `JWT_SECRET_KEY`。

## 十、主要配置项

| 变量 | 说明 | 默认值 |
|---|---|---|
| `RAG_BACKEND` | `ragflow` 或 `legacy` | `ragflow` |
| `ENABLE_LEGACY_RAG` | Legacy 二次安全开关 | `false` |
| `RAGFLOW_BASE_URL` | RAGFlow API 地址 | - |
| `RAGFLOW_API_KEY` | RAGFlow API Key | - |
| `RAGFLOW_DATASET_ID` | 项目 Dataset ID | - |
| `RAGFLOW_TOP_K` | 检索候选数量 | `8` |
| `RAGFLOW_SIMILARITY_THRESHOLD` | 相似度阈值 | `0.2` |
| `DEEPSEEK_API_KEY` | DeepSeek 文本模型密钥 | - |
| `DEEPSEEK_MODEL` | DeepSeek 模型 | `deepseek-v4-flash` |
| `TEXT_MODEL_*` | 通用 OpenAI 兼容文本模型配置 | - |
| `TAVILY_API_KEY` | 联网搜索兜底 | 可选 |
| `POSTGRES_URL` | SQLAlchemy PostgreSQL URL | - |
| `LANGGRAPH_POSTGRES_DSN` | LangGraph PostgreSQL DSN | - |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 本地缺省时临时生成 |

## 十一、验证状态

本分支已完成以下本地端到端验证：

- RAGFlow 文档上传和异步解析成功。
- DeepDoc 解析状态为 DONE。
- 本地 TEI Embedding 工作正常。
- `rag_api_service` 文档列表、分块和查询成功。
- MCP 仅公开 `query_rag`，调用成功。
- LangGraph 知识模式召回测试文档并返回来源。
- DeepSeek 智能体模式返回正常文本。
- 写作模式完成草稿、人工审阅和确认后的最终输出。
- 主服务登录、会话和重启恢复成功。
- Vue TypeScript 检查和生产构建成功。

## 十二、安全说明

- `.env` 包含真实 API Key，已被 Git 忽略。
- 不要把 `root / admin123` 暴露到公网。
- 不要直接公开 PostgreSQL、Redis、Elasticsearch、MinIO 或 RAGFlow 内部端口。
- 面试演示建议使用临时 HTTPS Tunnel，并创建权限受限的演示账号。
- Quick Tunnel 仅适合临时演示，不等同于生产部署。

## 十三、后续计划

- 增加自动化测试、Lint、TypeScript Check 和 CI。
- 为面试演示增加只读账号、同源 API 网关和临时公网 Tunnel。
- 增加解析任务进度展示和失败重试。
- 增加公式、图片和表格识别质量评测集。
- 增加检索 Recall、MRR、NDCG 和回答忠实度评估。
- 对前端大包进行路由级代码拆分。
