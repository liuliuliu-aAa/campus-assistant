"""问答 Agent：优先调用 RAGService.answer 检索问答，知识图谱用于关联知识点扩展与来源补全。

输出固定为 {"answer", "sources", "confidence"}：
- sources 每项含 title / url / score，无检索结果时 answer 固定为 NO_RESULT_TEXT，sources 为空，绝不编造；
- confidence = 来源 score 的均值（保留两位小数），无来源时为 0.0。

mock 模式（或未注入 rag_service）走本地模拟问答，不调用真实 LLM；
真实模式未注入 rag_service 时抛 NotImplementedError 占位，由 execute 捕获成失败结果。
"""

from typing import Any, Dict, List, Optional

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode

NO_RESULT_TEXT = "知识库中未检索到相关内容"
DEFAULT_TOP_K = 5

MOCK_SOURCES = [
    {"title": "高等数学 第三章 课件", "url": "mock://course/gaoshu/ch03", "score": 0.88},
    {"title": "高等数学 第三章 习题与答案", "url": "mock://course/gaoshu/ch03-exercise", "score": 0.76},
]


class QAAgent(BaseAgent):
    """RAG 问答：强制带来源，低检索时明确说不知道。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "qa_agent",
                 rag_service: Any = None, knowledge_graph: Any = None) -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.rag_service = rag_service
        self.knowledge_graph = knowledge_graph

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        query = params.get("query") or params.get("question") or ""
        if not query:
            return AgentResult(False, None, error="query 不能为空")
        course = params.get("course")
        top_k = int(params.get("top_k", DEFAULT_TOP_K))
        try:
            if self.rag_service is not None:
                result = await self.rag_service.answer(query, course=course, top_k=top_k)
                answer = (result or {}).get("answer") or NO_RESULT_TEXT
                sources = self._normalize_sources((result or {}).get("sources"))
            elif self.mock_mode:
                answer = self._mock_answer(query, course)
                sources = self._normalize_sources(MOCK_SOURCES)
            else:
                answer, sources = await self._answer_with_llm(query, course)
            answer, sources = self._expand_with_knowledge_graph(query, answer, sources)
        except NotImplementedError as exc:
            return AgentResult(False, None, error=str(exc))
        if not sources:
            answer = NO_RESULT_TEXT
        return AgentResult(True, {
            "answer": answer,
            "sources": sources,
            "confidence": self._compute_confidence(sources),
        })

    def _mock_answer(self, query: str, course: Optional[str]) -> str:
        subject = course or "校园资料"
        return "（模拟问答）已基于%s检索到相关内容：关于“%s”的要点见来源列表（mock 模式，未调用真实 LLM）。" % (
            subject, query)

    async def _answer_with_llm(self, query: str, course: Optional[str]):
        # 预留：真实模式在未接入 RAGService 时的直连 LLM 兜底路径。
        raise NotImplementedError("真实模式未注入 rag_service，直连 LLM 问答待接入")

    def _normalize_sources(self, sources: Optional[List[Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for source in sources or []:
            if not isinstance(source, dict) or not source.get("title"):
                continue
            normalized.append({
                "title": source.get("title"),
                "url": source.get("url") or "",
                "score": float(source.get("score") or 0.0),
            })
        return normalized

    def _expand_with_knowledge_graph(self, query: str, answer: str,
                                     sources: List[Dict[str, Any]]):
        """知识图谱扩展：补充关联知识点与来源；接口缺失或异常时原样返回。"""
        graph = self.knowledge_graph
        if graph is None:
            return answer, sources
        try:
            expansion = graph.expand(query)
        except (AttributeError, NotImplementedError):
            return answer, sources
        except Exception:
            return answer, sources
        if not isinstance(expansion, dict):
            return answer, sources
        points = expansion.get("knowledge_points") or []
        if points:
            answer = "%s\n关联知识点：%s" % (answer, "、".join(str(point) for point in points))
        extra_sources = self._normalize_sources(expansion.get("sources"))
        merged = sources + [item for item in extra_sources
                            if item["title"] not in {s["title"] for s in sources}]
        return answer, merged

    def _compute_confidence(self, sources: List[Dict[str, Any]]) -> float:
        if not sources:
            return 0.0
        average = sum(source["score"] for source in sources) / len(sources)
        return round(min(max(average, 0.0), 1.0), 2)
