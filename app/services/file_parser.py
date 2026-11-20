"""文件解析服务：PPT / PDF / 图片 / 纯文本 → 统一 segments。

返回结构：
{"document_id": str, "file_type": "ppt|pdf|image|text",
 "segments": [{"seq": 1, "text": "...", "source": "page:1|chapter:1|ocr|paragraph:1|text"}]}

- 解析器与 OCR 以可选 callable 注入（ppt_parser / pdf_parser / ocr），注入优先；
- 未注入且 MOCK_MODE=True 时走本地 mock 分段，不 import PyMuPDF / python-pptx / PaddleOCR 等第三方库；
- 未注入且真实模式时抛 NotImplementedError，由调用方降级处理。
"""

import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.config import get_config, is_mock_mode
from app.utils.hash_utils import document_id as build_document_id

SUPPORTED_FILE_TYPES = ("ppt", "pdf", "image", "text")
PPT_EXTENSIONS = (".ppt", ".pptx")
PDF_EXTENSIONS = (".pdf",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff")


class FileParser:
    """按文件类型抽取文本分段，mock 离线可跑。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 ppt_parser: Optional[Callable] = None,
                 pdf_parser: Optional[Callable] = None,
                 ocr: Optional[Callable] = None) -> None:
        self.config = config if config is not None else get_config()
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.ppt_parser = ppt_parser
        self.pdf_parser = pdf_parser
        self.ocr = ocr

    def parse(self, document: Dict[str, Any]) -> Dict[str, Any]:
        filename = document.get("original_filename") or document.get("filename") or ""
        file_type = (document.get("file_type") or self._detect_file_type(filename)).lower()
        if file_type not in SUPPORTED_FILE_TYPES:
            raise ValueError("不支持的文件类型: %s（可选 %s）"
                             % (file_type, ", ".join(SUPPORTED_FILE_TYPES)))
        document_id = document.get("document_id") or self._make_document_id(document, filename)
        if file_type == "ppt" and callable(self.ppt_parser):
            segments = self._normalize(self.ppt_parser(document), "page")
        elif file_type == "pdf" and callable(self.pdf_parser):
            segments = self._normalize(self.pdf_parser(document), "chapter")
        elif file_type == "image" and callable(self.ocr):
            segments = self._normalize(self.ocr(document), "ocr")
        elif self.mock_mode:
            segments = self._mock_segments(document, file_type)
        else:
            raise NotImplementedError("真实模式的 %s 解析待接入（PyMuPDF / python-pptx / OCR）" % file_type)
        return {
            "document_id": document_id,
            "file_type": file_type,
            "segments": [{"seq": index, "text": text, "source": source}
                         for index, (text, source) in enumerate(segments, start=1)],
        }

    def _detect_file_type(self, filename: str) -> str:
        extension = os.path.splitext(filename)[1].lower()
        if extension in PPT_EXTENSIONS:
            return "ppt"
        if extension in PDF_EXTENSIONS:
            return "pdf"
        if extension in IMAGE_EXTENSIONS:
            return "image"
        return "text"

    def _make_document_id(self, document: Dict[str, Any], filename: str) -> str:
        content = document.get("content") or document.get("text_content") or ""
        if not filename and not content:
            return "doc_" + uuid.uuid4().hex[:10]
        return build_document_id(filename, str(content))

    def _normalize(self, raw: Any, default_source: str) -> List[tuple]:
        """把注入解析器的返回值统一成 [(text, source)]。"""
        if raw is None:
            return []
        if isinstance(raw, str):
            return [(raw, default_source)]
        segments = []
        for index, item in enumerate(raw if isinstance(raw, list) else [raw], start=1):
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if item.get("page"):
                    source = "page:%s" % item["page"]
                elif item.get("chapter"):
                    source = "chapter:%s" % item["chapter"]
                elif item.get("title"):
                    source = "chapter:%s" % item["title"]
                else:
                    source = "%s:%d" % (default_source, index)
                segments.append((text, source))
            else:
                text = str(item).strip()
                if text:
                    segments.append((text, "%s:%d" % (default_source, index)))
        return segments

    def _mock_segments(self, document: Dict[str, Any], file_type: str) -> List[tuple]:
        content = str(document.get("content") or document.get("text_content") or "")
        filename = document.get("original_filename") or document.get("filename") or "未命名文件"
        if file_type == "ppt":
            pages = document.get("pages")
            if isinstance(pages, list) and pages:
                return self._normalize(pages, "page")
            return [(text, "page:%d" % index)
                    for index, text in enumerate(self._paragraphs(content), start=1)]
        if file_type == "pdf":
            sections = document.get("chapters") or document.get("sections")
            if isinstance(sections, list) and sections:
                return self._normalize(sections, "chapter")
            return [(text, "chapter:%d" % index)
                    for index, text in enumerate(self._paragraphs(content), start=1)]
        if file_type == "image":
            ocr_text = document.get("ocr_text") or "OCR 模拟识别：%s" % filename
            return [(str(ocr_text), "ocr")]
        paragraphs = self._paragraphs(content)
        if not paragraphs:
            return []
        if len(paragraphs) == 1:
            return [(paragraphs[0], "text")]
        return [(text, "paragraph:%d" % index)
                for index, text in enumerate(paragraphs, start=1)]

    def _paragraphs(self, content: str) -> List[str]:
        content = content.strip()
        if not content:
            return []
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        return paragraphs or [content]
