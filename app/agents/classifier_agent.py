"""分类 Agent：三级分类策略。

1. LLM 零样本分类（首选）；
2. 向量相似度 + 已分类文档投票校验（注入了 vector_db / embedding_model 才启用）；
3. 规则引擎兜底（文件名关键词、扩展名、上传渠道）。

输出标签：course（课程归属）、chapter（章节/知识点）、doc_type（课件/习题/笔记/通知/试卷）、
importance（高/中/低），每个标签附带 confidence；任一标签置信度低于 CONFIDENCE_THRESHOLD
即标记 needs_review=True（待人工确认）。

mock 模式完全本地计算，不调用真实 LLM，也不需要 API Key；真实模式在 _llm_zero_shot 留接入点。
"""

import os
import re
from typing import Any, Dict, List, Optional

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode

COURSE_KEYWORDS = {
    "高等数学": ("高等数学", "高数", "微积分", "导数", "微分", "积分"),
    "线性代数": ("线性代数", "线代", "矩阵", "行列式"),
    "大学英语": ("英语", "english", "四六级", "cet"),
    "数据结构": ("数据结构", "算法", "algorithm", "二叉树"),
}

DOC_TYPE_KEYWORDS = {
    "课件": ("课件", "讲义", "lecture", "slides", "ppt"),
    "习题": ("习题", "作业", "练习", "homework", "exercise"),
    "笔记": ("笔记", "note"),
    "通知": ("通知", "公告", "notice", "提醒"),
    "试卷": ("试卷", "试题", "exam", "期中", "期末", "测验"),
}

EXTENSION_DOC_TYPE = {
    ".pdf": "课件",
    ".ppt": "课件",
    ".pptx": "课件",
    ".doc": "笔记",
    ".docx": "笔记",
    ".md": "笔记",
    ".txt": "笔记",
}

CHANNEL_DOC_TYPE = {
    "course_group": "课件",
    "lms": "习题",
    "mail": "通知",
}

URGENT_KEYWORDS = ("紧急", "截止", "考试", "deadline", "报名")

CHAPTER_PATTERN = re.compile(r"第([一二三四五六七八九十0-9]+)章")


class ClassifierAgent(BaseAgent):
    """三级分类：LLM → 向量校验 → 规则兜底。"""

    CONFIDENCE_THRESHOLD: float = 0.7
    VECTOR_TOP_K: int = 5
    LABEL_FIELDS = ("course", "chapter", "doc_type", "importance")

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "classifier_agent",
                 llm: Any = None, vector_db: Any = None, embedding_model: Any = None) -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.llm = llm
        self.vector_db = vector_db
        self.embedding_model = embedding_model

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        documents = self._extract_documents(params)
        classified: List[Dict[str, Any]] = []
        for document in documents:
            classified.append(await self._classify_document(document))
        return AgentResult(True, {
            "classified": classified,
            "count": len(classified),
            "threshold": self.CONFIDENCE_THRESHOLD,
        })

    def _extract_documents(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        documents = params.get("documents") or params.get("files")
        if documents:
            return list(documents)
        if params.get("document_id") or params.get("original_filename"):
            return [params]
        return []

    async def _classify_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        filename = document.get("original_filename") or document.get("filename") or ""
        text = document.get("content") or document.get("text_content") or ""
        channel = document.get("channel") or ""

        labels: Optional[Dict[str, Any]] = None
        method = "llm"
        try:
            labels = await self._classify_by_llm(filename, text, channel)
        except Exception:
            labels = None
        if labels is None:
            method = "vector"
            labels = await self._classify_by_vector(text or filename, channel)
        if labels is None:
            method = "rule"
            labels = self._classify_by_rules(filename, text, channel)

        review_labels = [
            field for field in self.LABEL_FIELDS
            if labels[field]["confidence"] < self.CONFIDENCE_THRESHOLD
        ]
        return {
            "document_id": document.get("document_id") or document.get("file_id"),
            "original_filename": filename,
            "labels": labels,
            "method": method,
            "needs_review": bool(review_labels),
            "review_labels": review_labels,
        }

    async def _classify_by_llm(self, filename: str, text: str, channel: str) -> Optional[Dict[str, Any]]:
        """一级：LLM 零样本分类。mock 模式本地模拟，不发起任何请求。"""
        if self.mock_mode:
            labels = self._classify_by_rules(filename, text, channel)
            for field in ("course", "chapter", "doc_type"):
                if labels[field]["confidence"] >= self.CONFIDENCE_THRESHOLD:
                    labels[field]["confidence"] = 0.92
            if labels["importance"]["confidence"] >= self.CONFIDENCE_THRESHOLD:
                labels["importance"]["confidence"] = 0.88
            return labels
        if self.llm is None:
            raise RuntimeError("真实模式未注入 llm")
        return await self._llm_zero_shot(filename, text, channel)

    async def _llm_zero_shot(self, filename: str, text: str, channel: str) -> Optional[Dict[str, Any]]:
        # 预留：真实模式在此组织零样本分类 prompt 并调用 self.llm.generate(...)。
        raise NotImplementedError("真实模式的 LLM 零样本分类待接入")

    async def _classify_by_vector(self, query: str, channel: str) -> Optional[Dict[str, Any]]:
        """二级：用向量检索已分类文档投票；置信不足返回 None 交给规则引擎。"""
        if not query or self.vector_db is None or self.embedding_model is None:
            return None
        try:
            vec = self.embedding_model.encode(query)
            results = self.vector_db.search(vec, top_k=self.VECTOR_TOP_K, filter=None)
        except Exception:
            return None
        if not results:
            return None
        scores: Dict[str, Dict[str, float]] = {field: {} for field in ("course", "chapter", "doc_type")}
        for item in results:
            metadata = getattr(item, "metadata", None) or {}
            score = float(getattr(item, "score", 0.0) or 0.0)
            for field in scores:
                label = metadata.get(field) or metadata.get("category")
                if not label:
                    continue
                scores[field].setdefault(label, 0.0)
                scores[field][label] += score
        labels: Dict[str, Any] = {}
        for field, bucket in scores.items():
            if not bucket:
                labels[field] = {"label": "未识别", "confidence": 0.0}
                continue
            best_label = max(bucket, key=bucket.get)
            labels[field] = {"label": best_label, "confidence": min(bucket[best_label], 0.95)}
        if max(labels[field]["confidence"] for field in scores) < self.CONFIDENCE_THRESHOLD:
            return None
        labels["importance"] = self._rule_importance(
            labels["doc_type"]["label"], query, channel)
        return labels

    def _classify_by_rules(self, filename: str, text: str, channel: str) -> Dict[str, Any]:
        """三级：规则引擎兜底（文件名关键词 + 扩展名 + 上传渠道）。"""
        haystack = ("%s %s" % (filename, text)).lower()
        extension = os.path.splitext(filename)[1].lower()

        course_label, course_conf = self._match_keywords(haystack, COURSE_KEYWORDS)
        chapter_label, chapter_conf = self._match_chapter("%s %s" % (filename, text))
        doc_type_label, doc_type_conf = self._match_keywords(haystack, DOC_TYPE_KEYWORDS)
        if doc_type_conf < self.CONFIDENCE_THRESHOLD and extension in EXTENSION_DOC_TYPE:
            doc_type_label, doc_type_conf = EXTENSION_DOC_TYPE[extension], 0.55
        if doc_type_conf < self.CONFIDENCE_THRESHOLD and channel in CHANNEL_DOC_TYPE:
            doc_type_label, doc_type_conf = CHANNEL_DOC_TYPE[channel], 0.6

        return {
            "course": {"label": course_label, "confidence": course_conf},
            "chapter": {"label": chapter_label, "confidence": chapter_conf},
            "doc_type": {"label": doc_type_label, "confidence": doc_type_conf},
            "importance": self._rule_importance(doc_type_label, haystack, channel),
        }

    def _match_keywords(self, haystack: str, keywords: Dict[str, tuple]) -> tuple:
        for label, words in keywords.items():
            if any(word.lower() in haystack for word in words):
                return label, 0.8
        return "未识别", 0.3

    def _match_chapter(self, raw: str) -> tuple:
        match = CHAPTER_PATTERN.search(raw)
        if match:
            return "第%s章" % match.group(1), 0.75
        return "未识别", 0.3

    def _rule_importance(self, doc_type: str, haystack: str, channel: str) -> Dict[str, Any]:
        lowered = haystack.lower()
        if any(word in lowered for word in URGENT_KEYWORDS):
            return {"label": "高", "confidence": 0.85}
        if doc_type in ("试卷", "通知"):
            return {"label": "高", "confidence": 0.8}
        if doc_type in ("课件", "习题"):
            return {"label": "中", "confidence": 0.7}
        if doc_type == "笔记":
            return {"label": "低", "confidence": 0.6}
        return {"label": "中", "confidence": 0.3}
