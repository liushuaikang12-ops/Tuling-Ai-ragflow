from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from config.settings import Settings
from core.ragflow_client import RAGFlowClient
from core.text_normalization import (
    normalize_pdf_symbol_text,
    standardize_formula_markdown,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)

_FORMULA_INTENT_RE = re.compile(r"公式|表达式|方程.*(?:什么|多少|给出|写出|列出)|解析解")
_FORMULA_REFERENCE_RE = re.compile(
    r"(?:方程|式)\s*[（(]\s*(\d+(?:\.\d+)+)\s*[）)]"
)
_LATEX_COMMAND_RE = re.compile(
    r"\\(?:sum|frac|exp|ln|partial|prod|sqrt|begin|cos|sin|tau|mu|gamma)\b"
)


class RAGFlowBackend:
    """仅通过 RAGFlow HTTP API 完成解析、索引和检索。"""

    def __init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("RAGFLOW_API_KEY", Settings.RAGFLOW_API_KEY),
                ("RAGFLOW_DATASET_ID", Settings.RAGFLOW_DATASET_ID),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"RAGFlow 后端缺少配置: {', '.join(missing)}")

        self.client = RAGFlowClient(
            base_url=Settings.RAGFLOW_BASE_URL,
            api_key=Settings.RAGFLOW_API_KEY or "",
            dataset_id=Settings.RAGFLOW_DATASET_ID or "",
            timeout=Settings.RAGFLOW_TIMEOUT_SECONDS,
        )
        self._formula_jobs: dict[str, asyncio.Task[None]] = {}
        self._formula_audited: set[str] = set()
        self._formula_reports: dict[str, dict[str, Any]] = {}

    async def upload_files(
        self,
        files: list[tuple[str, bytes]],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> dict[str, Any]:
        if not files:
            return {
                "status": "error",
                "message": "请上传至少一个文件",
                "processed_files": [],
            }
        if chunk_size is not None:
            await self.client.update_chunk_size(chunk_size)
        documents = await self.client.upload_documents(files)
        document_ids = [str(doc.get("id")) for doc in documents if doc.get("id")]
        if not document_ids:
            raise RuntimeError("RAGFlow 接受了上传请求，但没有返回文档 ID")
        await self.client.start_parsing(document_ids)
        for document_id in document_ids:
            self._schedule_formula_job(document_id)
        return {
            "status": "success",
            "message": f"已上传 {len(documents)} 个文档，RAGFlow 正在异步解析",
            "processed_files": [name for name, _ in files],
            "document_ids": document_ids,
            "parsing": True,
        }

    @staticmethod
    def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
        name = str(document.get("name") or document.get("docnm_kwd") or "")
        return {
            "file_name": name,
            "doc_id": str(document.get("id") or ""),
            "file_path": "",
            "upload_time": str(
                document.get("create_date") or document.get("create_time") or ""
            ),
            "file_type": str(document.get("type") or document.get("suffix") or ""),
            "file_size": int(document.get("size") or 0),
            "status": document.get("run"),
            "progress": document.get("progress"),
            "progress_msg": document.get("progress_msg") or "",
            "chunk_count": document.get("chunk_count") or 0,
        }

    async def list_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        while True:
            data = await self.client.list_documents(page=page, page_size=page_size)
            batch = data.get("docs") or data.get("documents") or []
            documents.extend(item for item in batch if isinstance(item, dict))
            total = int(data.get("total") or len(documents))
            if len(batch) < page_size or len(documents) >= total:
                break
            page += 1
        normalized_documents = []
        for document in documents:
            normalized = self._normalize_document(document)
            document_id = normalized["doc_id"]
            if str(normalized.get("status") or "").upper() == "DONE":
                self._schedule_formula_job(document_id)
            report = self._formula_reports.get(document_id)
            if report:
                normalized["formula_audit"] = report
            normalized_documents.append(normalized)
        return normalized_documents

    def _schedule_formula_job(self, document_id: str) -> None:
        if (
            not document_id
            or document_id in self._formula_audited
            or document_id in self._formula_jobs
        ):
            return
        task = asyncio.create_task(self._wait_and_normalize_formulas(document_id))
        self._formula_jobs[document_id] = task

    async def _wait_and_normalize_formulas(self, document_id: str) -> None:
        try:
            # Parsing is asynchronous in RAGFlow.  Keep upload responsive while
            # waiting for the final chunk set, then normalize before users rely
            # on the new document for formula retrieval.
            for _ in range(360):
                data = await self.client.list_documents(page=1, page_size=100)
                documents = data.get("docs") or data.get("documents") or []
                current = next(
                    (
                        item
                        for item in documents
                        if isinstance(item, dict)
                        and str(item.get("id") or "") == document_id
                    ),
                    None,
                )
                status = str((current or {}).get("run") or "").upper()
                if status == "DONE":
                    await self.normalize_document_formulas(document_id)
                    return
                if status in {"FAIL", "CANCEL"} or current is None:
                    return
                await asyncio.sleep(5)
        except Exception:
            logger.exception("文档 %s 的公式标准化任务失败", document_id)
        finally:
            self._formula_jobs.pop(document_id, None)

    async def _all_document_chunks(self, document_id: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.client.list_chunks(document_id, page=page, page_size=100)
            batch = [
                item for item in (data.get("chunks") or []) if isinstance(item, dict)
            ]
            chunks.extend(batch)
            total = int(data.get("total") or len(chunks))
            if len(batch) < 100 or len(chunks) >= total:
                return chunks
            page += 1

    @staticmethod
    def _formula_questions(
        labels: tuple[str, ...], chunks: list[dict[str, Any]]
    ) -> list[str]:
        questions: list[str] = []
        for label in labels:
            questions.append(f"方程({label})的完整 LaTeX 公式是什么？")
            label_re = re.compile(rf"[（(]\s*{re.escape(label)}\s*[）)]")
            for chunk in chunks:
                text = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
                for match in label_re.finditer(text):
                    # Only use the local explanation around the equation label.
                    # A RAGFlow chunk can contain several later sections whose
                    # equations are unrelated to this formula.
                    window = text[max(0, match.start() - 260) : match.end() + 80]
                    for sentence in re.split(r"[。\n]", window):
                        sentence = re.sub(r"\s+", " ", sentence).strip(" ：:，,")
                        sentence = re.sub(r"\[\d+(?:-\d+)?\]", "", sentence).strip()
                        sentence = re.sub(r"(?:如下|为)$", "", sentence).strip()
                        if (
                            8 <= len(sentence) <= 140
                            and "方程" in sentence
                            and "图像" not in sentence
                            and (
                                "解" in sentence
                                or "表达式" in sentence
                                or "公式" in sentence
                            )
                        ):
                            questions.append(sentence.rstrip("？?") + "是什么？")
        return list(dict.fromkeys(questions))[:5]

    @staticmethod
    def _formula_context(
        label: str, target_chunk: dict[str, Any], chunks: list[dict[str, Any]]
    ) -> str:
        contexts: list[str] = []
        label_re = re.compile(
            rf"(?:[（(]\s*{re.escape(label)}\s*[）)]|"
            rf"\\tag\{{\s*{re.escape(label)}\s*\}})"
        )
        for chunk in chunks:
            text = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
            for match in label_re.finditer(text):
                if str(chunk.get("id") or "") == str(target_chunk.get("id") or ""):
                    continue
                contexts.append(
                    re.sub(
                        r"\s+",
                        " ",
                        text[max(0, match.start() - 420) : match.end() + 160],
                    ).strip()
                )

        target_positions = target_chunk.get("positions") or []
        try:
            target_page = int(target_positions[0][0])
            target_top = float(target_positions[0][3])
        except (IndexError, TypeError, ValueError):
            target_page = -1
            target_top = 0
        page_neighbors: list[tuple[float, str]] = []
        for chunk in chunks:
            if str(chunk.get("id") or "") == str(target_chunk.get("id") or ""):
                continue
            text = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
            if len(re.findall(r"[\u3400-\u9fff]", text)) < 8:
                continue
            matching_positions = [
                position
                for position in (chunk.get("positions") or [])
                if position and int(position[0]) == target_page
            ]
            if not matching_positions:
                continue
            distance = min(abs(float(position[3]) - target_top) for position in matching_positions)
            page_neighbors.append((distance, re.sub(r"\s+", " ", text).strip()))
        for _, text in sorted(page_neighbors, key=lambda item: item[0])[:3]:
            contexts.append(text[:700])

        return "\n".join(dict.fromkeys(item for item in contexts if item))[:1800]

    @staticmethod
    def _formula_page(chunk: dict[str, Any]) -> int | None:
        positions = chunk.get("positions") or []
        try:
            # RAGFlow stores a zero-based PDF page index as the first value.
            return int(positions[0][0]) + 1
        except (IndexError, TypeError, ValueError):
            return None

    @staticmethod
    def _parse_formula_vision(text: str, expected_label: str) -> dict[str, Any]:
        candidate = text.strip().strip("`").strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
        starts = [index for index in (candidate.find("{"), candidate.find("[")) if index >= 0]
        if not starts:
            raise ValueError("视觉模型没有返回 JSON 公式结果")
        start = min(starts)
        closing = "]" if candidate[start] == "[" else "}"
        end = candidate.rfind(closing)
        if end < start:
            raise ValueError("视觉模型返回的 JSON 没有闭合")
        raw_json = candidate[start : end + 1]

        def encode_latex(match: re.Match[str]) -> str:
            latex_value = match.group("latex")
            latex_value = latex_value.replace("\\\\", "\\").replace('\\"', '"')
            latex_value = latex_value.replace("<BS>", "\\")
            return match.group("prefix") + json.dumps(latex_value, ensure_ascii=False)

        # Normalize both JSON strings and the Python-style r"..." strings that
        # some vision models emit for LaTeX. Re-encoding the value prevents
        # \beta / \tau / \frac from becoming JSON control escapes.
        repaired_json = re.sub(
            r'(?P<prefix>"latex"\s*:\s*)r?"(?P<latex>(?:\\.|[^"\\])*)"',
            encode_latex,
            raw_json,
        )
        payload: Any = json.loads(repaired_json)
        if isinstance(payload, list):
            payload = next(
                (
                    item
                    for item in payload
                    if isinstance(item, dict)
                    and str(item.get("equation_number") or "").strip("()（） ")
                    == expected_label
                ),
                None,
            )
            if payload is None:
                raise ValueError(f"视觉结果中没有公式 ({expected_label})")
        if not isinstance(payload, dict):
            raise ValueError("视觉模型返回的公式结果不是 JSON 对象")
        latex = str(payload.get("latex") or "")
        latex = latex.strip()
        latex = re.sub(r"^\\\[|\\\]$", "", latex).strip()
        latex = re.sub(r"^\$\$|\$\$$", "", latex).strip()
        latex = re.sub(r"\\tag\{[^{}]+\}", "", latex).strip()
        # A model may use "\\D" as a visual line separator before an
        # uppercase variable. Unknown one-letter commands do not render in
        # KaTeX, so restore them to ordinary variables without changing known
        # commands such as \Lambda.
        latex = re.sub(r"\\([A-Z])(?=\s|_|=)", r"\1", latex)
        relation_re = re.compile(
            r"=|[<>≤≥]|\\(?:sim|approx|propto|equiv|leq?|geq?|neq)\b"
        )
        if not latex or not relation_re.search(latex):
            raise ValueError("视觉模型返回的 LaTeX 不包含完整数学关系")
        label = str(payload.get("equation_number") or expected_label).strip("()（） ")
        if label != expected_label:
            raise ValueError(
                f"视觉模型返回编号 {label}，与 Chunk 编号 {expected_label} 不一致"
            )
        return {
            "latex": latex,
            "equation_number": label,
            "formula_name": str(payload.get("formula_name") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "confidence": float(payload.get("confidence") or 0),
        }

    @staticmethod
    def _formula_name_from_context(label: str, context: str) -> str:
        compact = re.sub(r"\s+", "", context)
        ito_match = re.search(
            r"((?:[（(]?\d+\+\d+[）)]?维)?[A-Za-z]+方程的N-孤子解)"
            r"的方程表达式如下",
            compact,
            re.IGNORECASE,
        )
        if ito_match:
            subject = ito_match.group(1)
            if label == "1.1":
                return f"{subject}的方程表达式"
            if "其中色散关系如下" in compact:
                return f"{subject}的色散关系"

        direct_solution = re.search(
            r"(方程[（(]?\d+[）)]?的N-孤子解)", compact, re.IGNORECASE
        )
        if direct_solution:
            return direct_solution.group(1)
        if label == "1.3" and ("D算子" in compact or "双线性算子" in compact):
            return "Hirota D 算子定义"
        patterns = [
            r"(呼吸子解|孤子解|Lump解|态转换解)",
        ]
        for pattern in patterns:
            found = re.search(pattern, compact, re.IGNORECASE)
            if found:
                name = found.group(1)
                return name
        return f"原文公式（式 {label}）"

    @staticmethod
    def _formula_context_summary(context: str) -> str:
        normalized = re.sub(r"\s+", " ", context).strip()
        if not normalized:
            return "原文未提供可独立提取的公式名称说明"
        sentences = [
            item.strip()
            for item in re.split(r"[。\n]", normalized)
            if item.strip()
        ]
        relevant = [
            sentence
            for sentence in sentences
            if any(
                marker in sentence
                for marker in ("方程", "公式", "表达式", "色散关系", "算子", "解")
            )
        ]
        return (relevant or sentences)[0][:320]

    def _annotate_standard_formula(
        self,
        chunk: dict[str, Any],
        content: str,
        label: str,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if content.lstrip().startswith("# 原文公式："):
            name_match = re.search(r"^# 原文公式：(.+)$", content, re.MULTILINE)
            name = (
                name_match.group(1).strip()
                if name_match
                else f"原文公式（式 {label}）"
            )
            return content, name
        display_match = re.search(r"\\\[([\s\S]*?)\\\]", content)
        if not display_match:
            return content, f"原文公式（式 {label}）"
        latex = re.sub(
            rf"\\tag\{{\s*{re.escape(label)}\s*\}}",
            "",
            display_match.group(1),
        ).strip()
        context = self._formula_context(label, chunk, chunks)
        name = self._formula_name_from_context(label, context)
        annotated = self._formula_chunk_content(
            latex=latex,
            label=label,
            name=name,
            description=self._formula_context_summary(context),
            document_name=str(chunk.get("docnm_kwd") or "未知文档"),
            page=self._formula_page(chunk),
        )
        return annotated, name

    def _formula_vision_prompt(
        self,
        *,
        label: str,
        ocr_text: str,
        context: str,
        document_name: str,
    ) -> str:
        return (
            "你是数学论文公式转写器。请逐符号读取图片中的公式，输出严格 JSON，"
            "不要输出 Markdown 代码围栏。字段必须为：equation_number、latex、"
            "confidence。latex 中每个反斜杠必须写成 <BS>，例如 <BS>alpha；"
            "latex 只放公式主体，不放 $$、"
            "\\[\\] 或 \\tag；必须保留下标、上标、分式、求和范围、偏导和大括号。"
            "不要解释或猜测公式名称，图片内容是唯一的公式转写依据。"
            f"\n预期编号：({label})"
            f"\n文档：{document_name}"
            f"\n现有 OCR（仅供校对，图片优先）：{ocr_text[:700]}"
            f"\n原文邻近上下文：{context or '未找到，名称使用“原文公式”'}"
        )

    @staticmethod
    def _formula_chunk_content(
        *,
        latex: str,
        label: str,
        name: str,
        description: str,
        document_name: str,
        page: int | None,
    ) -> str:
        formula_name = name or f"原文公式（式 {label}）"
        metadata = [
            f"# 原文公式：{formula_name}",
            f"- 公式编号：({label})",
            f"- 来源文档：{document_name}",
        ]
        if page is not None:
            metadata.append(f"- 原文 PDF 页码：{page}")
        if description:
            metadata.append(f"- 原文上下文：{description}")
        metadata.extend(
            [
                "",
                "\\[",
                latex,
                f"\\tag{{{label}}}",
                "\\]",
            ]
        )
        return "\n".join(metadata)

    async def _recognize_formula_chunk(
        self,
        chunk: dict[str, Any],
        label: str,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], list[str], list[str]]:
        image_id = str(chunk.get("image_id") or "")
        if not image_id:
            raise ValueError("公式 Chunk 没有页面裁剪图")
        document_name = str(chunk.get("docnm_kwd") or "未知文档")
        context = self._formula_context(label, chunk, chunks)
        prompt = self._formula_vision_prompt(
            label=label,
            ocr_text=normalize_pdf_symbol_text(str(chunk.get("content") or "")),
            context=context,
            document_name=document_name,
        )
        response = await self.client.recognize_formula(image_id, prompt)
        parsed = self._parse_formula_vision(str(response.get("text") or ""), label)
        name = self._formula_name_from_context(label, context)
        description = self._formula_context_summary(context)
        content = self._formula_chunk_content(
            latex=parsed["latex"],
            label=label,
            name=name,
            description=description,
            document_name=document_name,
            page=self._formula_page(chunk),
        )
        questions = list(
            dict.fromkeys(
                [
                    f"{name}的具体公式是什么？",
                    f"方程({label})的完整 LaTeX 公式是什么？",
                    *self._formula_questions((label,), chunks),
                ]
            )
        )[:6]
        keywords = list(
            dict.fromkeys(["LaTeX", "数学公式", name, f"公式({label})", f"方程({label})"])
        )
        return content, parsed, questions, keywords

    async def normalize_document_formulas(
        self, doc_id: str, dry_run: bool = False
    ) -> dict[str, Any]:
        chunks = await self._all_document_chunks(doc_id)
        standardized = []
        standard_chunks = []
        visual_review = []
        already_standard = 0
        for chunk in chunks:
            chunk_id = str(chunk.get("id") or "")
            result = standardize_formula_markdown(str(chunk.get("content") or ""))
            if result.changed:
                standardized.append((chunk, result))
            elif result.needs_visual_review:
                visual_review.append(chunk_id)
            elif "\\[" in result.content or "$$" in result.content:
                already_standard += 1
                if result.equation_labels:
                    standard_chunks.append((chunk, result))

        metadata_refreshed = 0
        vision_standardized: list[str] = []
        vision_failed: list[dict[str, str]] = []
        if not dry_run:
            for chunk, result in [*standardized, *standard_chunks]:
                chunk_id = str(chunk.get("id") or "")
                labels = result.equation_labels
                content = result.content
                if content.lstrip().startswith("# 原文公式：") and not result.changed:
                    # This chunk already passed formula annotation and its
                    # embedding was rebuilt. Avoid re-embedding it on every
                    # audit/list request.
                    continue
                names: list[str] = []
                if labels:
                    content, name = self._annotate_standard_formula(
                        chunk, content, labels[0], chunks
                    )
                    names.append(name)
                questions = list(
                    dict.fromkeys(
                        [
                            *[f"{name}的具体公式是什么？" for name in names],
                            *self._formula_questions(labels, chunks),
                        ]
                    )
                )[:6]
                keywords = ["LaTeX"]
                for label in labels:
                    keywords.extend([f"公式({label})", f"方程({label})"])
                keywords.extend(names)
                keywords = list(dict.fromkeys(keywords))
                old_questions = [str(item) for item in chunk.get("questions") or []]
                old_keywords = [
                    str(item) for item in chunk.get("important_keywords") or []
                ]
                if (
                    not result.changed
                    and str(chunk.get("content") or "") == content
                    and old_questions == questions
                    and old_keywords == keywords
                ):
                    continue
                await self.client.update_chunk(
                    doc_id,
                    chunk_id,
                    content=content,
                    questions=questions,
                    important_keywords=keywords,
                )
                if not result.changed:
                    metadata_refreshed += 1

            if Settings.RAGFLOW_FORMULA_VISION_ENABLED:
                chunks_by_id = {
                    str(item.get("id") or ""): item for item in chunks
                }
                for chunk_id in visual_review:
                    chunk = chunks_by_id[chunk_id]
                    result = standardize_formula_markdown(
                        str(chunk.get("content") or "")
                    )
                    if not result.equation_labels:
                        continue
                    label = result.equation_labels[0]
                    try:
                        content, parsed, questions, keywords = (
                            await self._recognize_formula_chunk(
                                chunk, label, chunks
                            )
                        )
                        await self.client.update_chunk(
                            doc_id,
                            chunk_id,
                            content=content,
                            questions=questions,
                            important_keywords=keywords,
                        )
                        vision_standardized.append(chunk_id)
                        logger.info(
                            "公式 (%s) 已由视觉模型转为 LaTeX，confidence=%s",
                            label,
                            parsed["confidence"],
                        )
                    except Exception as exc:
                        logger.warning("公式 Chunk %s 视觉转写失败: %s", chunk_id, exc)
                        vision_failed.append(
                            {"chunk_id": chunk_id, "error": str(exc)}
                        )
                    await asyncio.sleep(
                        max(0, Settings.RAGFLOW_FORMULA_VISION_DELAY_SECONDS)
                    )
            else:
                vision_failed = [
                    {"chunk_id": chunk_id, "error": "公式视觉转写未启用"}
                    for chunk_id in visual_review
                ]

        pending_visual_ids = (
            visual_review
            if dry_run
            else [item["chunk_id"] for item in vision_failed]
        )
        report: dict[str, Any] = {
            "status": "preview" if dry_run else "success",
            "message": (
                f"扫描 {len(chunks)} 个 Chunk，标准化 {len(standardized)} 个；"
                f"视觉转写 {len(vision_standardized)} 个；"
                f"{len(vision_failed) if not dry_run else len(visual_review)} 个待处理"
            ),
            "document_id": doc_id,
            "dry_run": dry_run,
            "scanned": len(chunks),
            "standardized": len(standardized),
            "metadata_refreshed": metadata_refreshed,
            "already_standard": already_standard,
            "needs_visual_review": len(pending_visual_ids),
            "vision_enabled": Settings.RAGFLOW_FORMULA_VISION_ENABLED,
            "vision_standardized": len(vision_standardized),
            "vision_standardized_chunk_ids": vision_standardized,
            "vision_failed": vision_failed,
            "standardized_chunk_ids": [
                str(item[0].get("id") or "") for item in standardized
            ],
            "visual_review_chunk_ids": pending_visual_ids,
        }
        if not dry_run:
            self._formula_audited.add(doc_id)
            self._formula_reports[doc_id] = report
            logger.info(report["message"])
        return report

    async def get_document_chunks(
        self, doc_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        data = await self.client.list_chunks(doc_id, page=page, page_size=page_size)
        raw_chunks = data.get("chunks") or []
        chunks = []
        for chunk in raw_chunks:
            if not isinstance(chunk, dict):
                continue
            content = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
            formula_result = standardize_formula_markdown(content)
            formula_name_match = re.search(
                r"^# 原文公式：(.+)$", content, re.MULTILINE
            )
            chunks.append(
                {
                    "chunk_id": str(chunk.get("id") or ""),
                    "text": content,
                    "metadata": {
                        "file_name": str(chunk.get("docnm_kwd") or ""),
                        "doc_id": doc_id,
                        "content_type": "text",
                        "chunk_size": len(content),
                        "image_id": chunk.get("image_id") or "",
                        "positions": chunk.get("positions") or [],
                        "keywords": chunk.get("important_keywords") or [],
                        "formula_format": (
                            "latex"
                            if "\\[" in content or "$$" in content
                            else (
                                "needs_vision"
                                if formula_result.needs_visual_review
                                else "none"
                            )
                        ),
                        "formula_name": (
                            formula_name_match.group(1).strip()
                            if formula_name_match
                            else ""
                        ),
                        "equation_numbers": list(formula_result.equation_labels),
                    },
                }
            )
        return {
            "chunks": chunks,
            "total": int(data.get("total") or len(chunks)),
            "page": page,
            "page_size": page_size,
        }

    async def delete_document(self, doc_id: str) -> dict[str, Any]:
        await self.client.delete_documents([doc_id])
        return {"status": "success", "message": f"已删除文档 {doc_id}"}

    async def reset_system(self) -> dict[str, str]:
        await self.client.delete_all_documents()
        return {"status": "success", "message": "RAGFlow 数据集已清空"}

    async def get_chunk_config(self) -> dict[str, int]:
        dataset = await self.client.get_dataset()
        parser_config = dataset.get("parser_config") or {}
        return {
            "chunk_size": int(
                parser_config.get("chunk_token_num") or Settings.CHUNK_SIZE
            ),
            "chunk_overlap": 0,
        }

    async def update_chunk_config(
        self, chunk_size: int, chunk_overlap: int
    ) -> dict[str, Any]:
        if chunk_size > 2048:
            raise ValueError("RAGFlow 内置解析器的 chunk_size 最大为 2048")
        await self.client.update_chunk_size(chunk_size)
        Settings.CHUNK_SIZE = chunk_size
        Settings.CHUNK_OVERLAP = chunk_overlap
        return {
            "status": "success",
            "chunk_size": chunk_size,
            "chunk_overlap": 0,
        }

    @staticmethod
    def _source_text(chunk: dict[str, Any]) -> str:
        name = str(
            chunk.get("document_name") or chunk.get("docnm_kwd") or "未知文档"
        )
        content = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
        score = chunk.get("similarity")
        score_text = (
            f" (相似度: {float(score) * 100:.1f}%)"
            if isinstance(score, (int, float))
            else ""
        )
        return f"📄 **{name}**{score_text}\n\n> {content}"

    @staticmethod
    def _formula_references(chunks: list[dict[str, Any]]) -> list[str]:
        def collect(items: list[dict[str, Any]]) -> list[str]:
            references: list[str] = []
            for chunk in items:
                content = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
                for reference in _FORMULA_REFERENCE_RE.findall(content):
                    if reference not in references:
                        references.append(reference)
            return references

        # An equation explanation normally ranks near the top. Restricting the
        # first pass avoids pulling unrelated equation numbers from lower-ranked
        # chunks of the same paper; fall back to all Top-K only when necessary.
        references = collect(chunks[:3]) or collect(chunks)
        return references[:2]

    @staticmethod
    def _formula_score(chunk: dict[str, Any], references: list[str]) -> int:
        content = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
        tag_hits = sum(
            bool(re.search(rf"\\tag\{{\s*{re.escape(reference)}\s*\}}", content))
            for reference in references
        )
        reference_hits = sum(content.count(f"({reference})") for reference in references)
        latex_hits = len(_LATEX_COMMAND_RE.findall(content))
        operator_hits = len(re.findall(r"[=∑∂]|_\{|\^\{", content))
        # An authoritative LaTeX tag must outrank chunks that merely mention
        # the same equation number in explanatory source context.
        return tag_hits * 1000 + reference_hits * 8 + latex_hits * 3 + min(operator_hits, 12)

    async def _expand_formula_chunks(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Retrieve formula bodies referenced by explanatory text chunks.

        DeepDoc may put “equation (1.1) is as follows” and the equation image in
        separate chunks.  A second, reference-focused retrieval prevents the
        explanatory chunk from entering Top-K without its formula body.
        """

        if not _FORMULA_INTENT_RE.search(query):
            return chunks, []
        references = self._formula_references(chunks)
        if not references:
            return chunks, []

        expanded_queries: list[str] = []
        candidates: list[dict[str, Any]] = []
        for reference in references:
            expansion_query = f"方程({reference})的完整公式和表达式"
            expanded_queries.append(expansion_query)
            result = await self.client.retrieve(
                expansion_query,
                similarity_threshold=0.0,
                vector_similarity_weight=Settings.RAGFLOW_VECTOR_SIMILARITY_WEIGHT,
                top_k=max(Settings.RAGFLOW_TOP_K, 16),
                rerank_id=Settings.RAGFLOW_RERANK_ID,
            )
            candidates.extend(
                item
                for item in (result.get("chunks") or [])
                if isinstance(item, dict)
            )

        # Formula-rich exact-reference chunks go before the original Top-K.
        candidates.sort(
            key=lambda item: self._formula_score(item, references),
            reverse=True,
        )
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in [*candidates[:4], *chunks]:
            chunk_id = str(item.get("id") or "")
            if chunk_id and chunk_id in seen_ids:
                continue
            if chunk_id:
                seen_ids.add(chunk_id)
            merged.append(item)
        return merged, expanded_queries

    async def _generate_answer(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> str:
        if not chunks:
            return "不知道：知识库中没有检索到足够相关的内容。"
        if not Settings.API_KEY or not Settings.API_BASE_URL:
            excerpts = []
            for index, chunk in enumerate(chunks[:3], 1):
                content = normalize_pdf_symbol_text(
                    str(chunk.get("content") or "")
                ).strip()
                if content:
                    excerpts.append(f"[{index}] {content}")
            return (
                "已检索到以下相关资料（当前未配置文本生成模型，因此返回原始召回内容）：\n\n"
                + "\n\n".join(excerpts)
            )

        context_parts = []
        used_chars = 0
        for index, chunk in enumerate(chunks, 1):
            name = str(
                chunk.get("document_name")
                or chunk.get("docnm_kwd")
                or "未知文档"
            )
            content = normalize_pdf_symbol_text(str(chunk.get("content") or ""))
            part = f"[{index}] 来源：{name}\n{content}"
            if used_chars + len(part) > Settings.RAGFLOW_GENERATION_MAX_CONTEXT_CHARS:
                break
            context_parts.append(part)
            used_chars += len(part)

        prompt = (
            "你是企业知识库问答助手。请仅依据给定资料回答问题，不要编造。"
            "如果资料不足，请明确说明。回答中可使用 [1]、[2] 标注依据。"
            "当用户询问公式或表达式时，若资料中存在 LaTeX、等号或数学符号，"
            "必须先给出原文公式名称、编号和完整 LaTeX 公式，再解释各符号；"
            "不得只复述‘表达式如下’或只返回公式说明。带有‘# 原文公式’标记的"
            "Chunk 是公式本体，应优先逐项抄录；不要仅因原文换行或格式不整齐就判断公式缺失，"
            "无法确认的单个符号应标注为 OCR 不确定。\n\n"
            f"问题：{query}\n\n资料：\n" + "\n\n".join(context_parts)
        )
        base_url = Settings.API_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(
            timeout=Settings.RAGFLOW_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {Settings.API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": Settings.MODEL,
                    "temperature": Settings.TEMPERATURE,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"无法解析模型响应: {json.dumps(payload, ensure_ascii=False)}"
            ) from exc

    async def query(self, query: str) -> dict[str, Any]:
        try:
            result = await self.client.retrieve(
                query,
                similarity_threshold=Settings.RAGFLOW_SIMILARITY_THRESHOLD,
                vector_similarity_weight=Settings.RAGFLOW_VECTOR_SIMILARITY_WEIGHT,
                top_k=Settings.RAGFLOW_TOP_K,
                rerank_id=Settings.RAGFLOW_RERANK_ID,
            )
            raw_chunks = result.get("chunks") or []
            chunks = [chunk for chunk in raw_chunks if isinstance(chunk, dict)]
            chunks, expanded_queries = await self._expand_formula_chunks(query, chunks)
            answer = await self._generate_answer(query, chunks)
            return {
                "answer": answer,
                "sources": [self._source_text(chunk) for chunk in chunks],
                "retrieval": {
                    "backend": "ragflow",
                    "total": result.get("total") or len(chunks),
                    "formula_expansion": expanded_queries,
                },
            }
        except Exception as exc:
            logger.exception("RAGFlow 查询失败")
            return {
                "answer": f"查询失败: {exc}",
                "sources": [],
                "retrieval": {"backend": "ragflow", "total": 0},
            }
