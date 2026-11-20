"""摘要 Agent：按文档类型分处理并生成结构化摘要。

- PPT：按页提取文本后合并（按 page 顺序拼接）；
- PDF：按章节分段（chapters / sections），保留分段数；
- 图片型内容：先 OCR 再进入摘要（OCR 接入点 _ocr_image，可注入 self.ocr）；
- 输出：一句话摘要 summary、知识点 knowledge_points、关键词 keywords、适用场景 scenario；
- 摘要超过 MAX_SUMMARY_CHARS 时截断并追加 TRUNCATED_MARK（内容不完整），同时置 truncated=True。

mock 模式本地生成模拟摘要，不调用真实 LLM；真实模式在 _summarize_with_llm 抛 NotImplementedError 占位，
由 execute 捕获成失败结果，不影响 mock 跑通。
"""

import os
import re
from typing import Any, Callable, Dict, List, Optional

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode

MAX_SUMMARY_CHARS = 500
TRUNCATED_MARK = "（内容不完整）"
MAX_KNOWLEDGE_POINTS = 5
MAX_KEYWORDS = 5

PPT_EXTENSIONS = (".ppt", ".pptx")
PDF_EXTENSIONS = (".pdf",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff")

SCENARIO_BY_TYPE = {
    "ppt": "课前预习与课堂复习",
    "pdf": "章节复习与考试备考",
    "image": "碎片资料归档与检索",
    "text": "日常资料整理",
}


class SummarizerAgent(BaseAgent):
    """分类型摘要：PPT 逐页合并 / PDF 分章节 / 图片先 OCR。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "summarizer_agent",
                 llm: Any = None, ocr: Optional[Callable] = None) -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.llm = llm
        self.ocr = ocr

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        documents = self._extract_documents(params)
        summaries: List[Dict[str, Any]] = []
        try:
            for document in documents:
                prepared = self._prepare(document)
                if self.mock_mode:
                    summary = self._summarize_mock(prepared)
                else:
                    summary = await self._summarize_with_llm(prepared)
                summaries.append(self._finalize(document, prepared, summary))
        except NotImplementedError as exc:
            return AgentResult(False, None, error=str(exc))
        return AgentResult(True, {"summaries": summaries, "count": len(summaries)})

    def _extract_documents(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        documents = params.get("files") or params.get("documents")
        if documents:
            return list(documents)
        if params.get("document_id") or params.get("original_filename"):
            return [params]
        return []

    def _detect_file_type(self, filename: str) -> str:
        extension = os.path.splitext(filename)[1].lower()
        if extension in PPT_EXTENSIONS:
            return "ppt"
        if extension in PDF_EXTENSIONS:
            return "pdf"
        if extension in IMAGE_EXTENSIONS:
            return "image"
        return "text"

    def _prepare(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """按文档类型抽取可摘要的文本分段。"""
        filename = document.get("original_filename") or document.get("filename") or ""
        file_type = (document.get("file_type") or self._detect_file_type(filename)).lower()
        text = document.get("content") or document.get("text_content") or ""
        ocr_applied = False
        segments: List[str] = []
        if file_type == "ppt":
            segments = self._merge_ppt_pages(document.get("pages"))
        elif file_type == "pdf":
            segments = self._split_pdf_sections(document.get("chapters") or document.get("sections"))
        elif file_type == "image":
            text = self._ocr_image(document, text)
            ocr_applied = True
            segments = [text]
        if not segments:
            segments = [text]
        segments = [segment for segment in segments if segment and segment.strip()] or [text or ""]
        return {"file_type": file_type, "segments": segments, "ocr_applied": ocr_applied}

    def _merge_ppt_pages(self, pages: Optional[List[Any]]) -> List[str]:
        if not pages:
            return []
        merged = []
        for index, page in enumerate(pages, start=1):
            if isinstance(page, dict):
                page_no = page.get("page") or index
                merged.append("第%s页 %s" % (page_no, page.get("text", "")))
            else:
                merged.append("第%s页 %s" % (index, page))
        return merged

    def _split_pdf_sections(self, sections: Optional[List[Any]]) -> List[str]:
        if not sections:
            return []
        segments = []
        for index, section in enumerate(sections, start=1):
            if isinstance(section, dict):
                title = section.get("title") or "第%s节" % index
                segments.append("%s %s" % (title, section.get("text", "")))
            else:
                segments.append(str(section))
        return segments

    def _ocr_image(self, document: Dict[str, Any], text: str) -> str:
        if self.ocr is not None:
            result = self.ocr(document)
            return result if isinstance(result, str) else (text or "")
        if self.mock_mode:
            return document.get("ocr_text") or "OCR 模拟识别：%s" % (
                document.get("original_filename") or "图片资料")
        # 预留：真实模式在此接入 OCR 服务（PaddleOCR / 云 OCR 等）。
        raise NotImplementedError("真实模式的 OCR 接入待实现")

    async def _summarize_with_llm(self, prepared: Dict[str, Any]) -> Dict[str, Any]:
        # 预留：真实模式在此组织摘要 prompt 并调用 self.llm.generate(...)。
        raise NotImplementedError("真实模式的 LLM 摘要待接入")

    def _summarize_mock(self, prepared: Dict[str, Any]) -> Dict[str, Any]:
        # 限制说明：mock 摘要仅按标点切词后拼装，不是真实语义摘要，仅用于演示与联调。
        segments = prepared["segments"]
        joined = " ".join(segments)
        keywords = self._extract_keywords(joined)
        knowledge_points = [segment[:40] for segment in segments][:MAX_KNOWLEDGE_POINTS]
        sentence = "该%s资料共 %s 段，主要内容围绕%s展开（模拟摘要）。" % (
            prepared["file_type"],
            len(segments),
            "、".join(keywords[:3]) if keywords else "校园资料",
        )
        return {
            "summary": sentence,
            "knowledge_points": knowledge_points,
            "keywords": keywords,
            "scenario": SCENARIO_BY_TYPE.get(prepared["file_type"], "日常资料整理"),
        }

    def _extract_keywords(self, text: str) -> List[str]:
        tokens = re.split(r"[\s,，。;；、:：!！?？()（）\[\]【】/\\|]+", text)
        keywords: List[str] = []
        for token in tokens:
            token = token.strip()
            if len(token) >= 2 and token not in keywords:
                keywords.append(token)
            if len(keywords) >= MAX_KEYWORDS:
                break
        return keywords

    def _finalize(self, document: Dict[str, Any], prepared: Dict[str, Any],
                  summary: Dict[str, Any]) -> Dict[str, Any]:
        one_sentence = summary.get("summary") or ""
        truncated = len(one_sentence) > MAX_SUMMARY_CHARS
        if truncated:
            one_sentence = one_sentence[:MAX_SUMMARY_CHARS] + TRUNCATED_MARK
        return {
            "document_id": document.get("document_id") or document.get("file_id"),
            "original_filename": document.get("original_filename") or document.get("filename"),
            "file_type": prepared["file_type"],
            "segment_count": len(prepared["segments"]),
            "ocr_applied": prepared["ocr_applied"],
            "summary": one_sentence,
            "knowledge_points": summary.get("knowledge_points") or [],
            "keywords": summary.get("keywords") or [],
            "scenario": summary.get("scenario") or "",
            "truncated": truncated,
        }
