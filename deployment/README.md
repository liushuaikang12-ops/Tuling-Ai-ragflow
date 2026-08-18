# RAGFlow 本地部署补丁

## RAGFlow v0.26.4 + CPU TEI

RAGFlow 将同一文档生成的多个 Chunk 一次性发送给 Hugging Face TEI。CPU 模式的默认客户端批量限制和 30 秒请求超时可能导致以下错误：

```text
batch size N > maximum allowed batch size 8
Read timed out. (read timeout=30)
```

本目录提供的 `ragflow-v0.26.4-cpu-tei.patch` 会：

- 将 TEI 客户端批量上限调整为 32。
- 在 RAGFlow 调用层按 4 条 Chunk 分批请求 TEI。
- 将单批请求超时调整为 60 秒。
- 通过只读 Docker volume 挂载修改后的调用层，避免容器重建后丢失。

在 RAGFlow v0.26.4 仓库根目录执行：

```powershell
git apply C:\path\to\Tuling-Ai-ragflow\deployment\ragflow-v0.26.4-cpu-tei.patch
cd docker
docker compose --profile cpu --profile tei-cpu up -d --force-recreate tei-cpu ragflow-cpu
```

GPU TEI 或较新版本 RAGFlow 应先验证是否仍存在该问题，不要直接套用此版本补丁。

## 编号公式视觉转写接口

RAGFlow 的公开 Chunk API 能返回公式裁剪图 ID，但没有直接用当前租户视觉模型
重读该裁剪图的接口。本目录用只读 Compose overlay 加载
`ragflow_formula_vision_api.py`，它会：

- 校验调用者是否拥有 Dataset，且公式图片确实属于该 Dataset。
- 从 RAGFlow 对象存储读取原始公式裁剪图。
- 调用租户当前默认的 `IMAGE2TEXT` 模型；无需把视觉 API Key 复制到本项目。
- 对模型繁忙和限流做有限重试，并在适配层串行处理，避免突发并发。

在 Tuling-Ai-ragflow 项目根目录执行（下面假设 RAGFlow 仓库位于相邻目录）：

```powershell
$env:FORMULA_VISION_API_FILE=(Resolve-Path 'deployment\ragflow_formula_vision_api.py').Path
docker compose `
  -f ..\ragflow\docker\docker-compose.yml `
  -f deployment\docker-compose.ragflow-formula.yml `
  --project-directory ..\ragflow\docker `
  --profile cpu --profile tei-cpu `
  up -d --force-recreate ragflow-cpu
```

然后在项目根目录 `.env` 中启用：

```env
RAGFLOW_FORMULA_VISION_ENABLED=true
RAGFLOW_FORMULA_VISION_DELAY_SECONDS=1.5
```

这是自托管 RAGFlow 的扩展；RAGFlow Cloud 无法挂载该 overlay，应保持开关关闭。
