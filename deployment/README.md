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
