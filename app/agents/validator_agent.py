"""校验 Agent：五级校验 + 人工复核工单。

L1 格式完整性：必填字段是否存在且非空；
L2 字段合法性与取值枚举：doc_type / importance / event_type / priority / status / channel / method 等；
L3 逻辑一致性与交叉验证：needs_review 与标签置信度是否一致、截断标记、时间与状态是否自洽、
   问答 confidence 是否约等于来源均分；
L4 引用一致性：答案必须有来源、来源必须有 title/url、空来源必须回答"未检索到"；
L5 置信度与人工复核阈值：低于 REVIEW_THRESHOLD 或不可信数据标记 review 并生成工单。

输出 {"validated": [...], "passed", "failed", "needs_review"}：
- validated 每项含 level / target / kind / result(pass|fail|review|skip) / issue / confidence，
  其中 result == "review" 的项额外带 ticket（转人工工单）；
- passed / failed / needs_review 为校验项计数。

mock 模式在未传入待校验输出时，用内置样例跑同一套规则（不依赖真实 LLM）。
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode

REVIEW_THRESHOLD = 0.7
LABEL_THRESHOLD = 0.7
QA_CONFIDENCE_TOLERANCE = 0.1
TRUNCATED_MARK = "（内容不完整）"
NO_RESULT_TEXT = "知识库中未检索到相关内容"

LABEL_FIELDS = ("course", "chapter", "doc_type", "importance")
DOC_TYPES = ("课件", "习题", "笔记", "通知", "试卷", "未识别")
IMPORTANCE_LEVELS = ("高", "中", "低", "未识别")
METHODS = ("llm", "vector", "rule")
FILE_TYPES = ("ppt", "pdf", "image", "text")
EVENT_TYPES = ("deadline", "exam", "activity")
PRIORITIES = ("high", "medium", "low")
STATUSES = ("pending", "unparsed", "pushed")
CHANNELS = ("inapp", "email", "webhook")


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class ValidatorAgent(BaseAgent):
    """对 classifier / summarizer / qa / reminder 的输出做五级校验。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "validator_agent") -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        targets = self._collect_targets(params)
        if not targets and self.mock_mode:
            targets = self._mock_targets()
        checks: List[Dict[str, Any]] = []
        for kind, item in targets:
            checks.extend(self._validate(kind, item))
        for check in checks:
            if check["result"] == "review":
                check["ticket"] = self._make_ticket(check)
        return AgentResult(True, {
            "validated": checks,
            "passed": sum(1 for check in checks if check["result"] == "pass"),
            "failed": sum(1 for check in checks if check["result"] == "fail"),
            "needs_review": sum(1 for check in checks if check["result"] == "review"),
        })

    # ------------------------------------------------------------------ 目标识别

    def _collect_targets(self, params: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        targets: List[Tuple[str, Dict[str, Any]]] = []
        if isinstance(params.get("classified"), list):
            targets += [("classification", item) for item in params["classified"]]
        if isinstance(params.get("summaries"), list):
            targets += [("summary", item) for item in params["summaries"]]
        if "answer" in params:
            targets.append(("qa", params))
        if isinstance(params.get("reminders"), list):
            targets += [("reminder", item) for item in params["reminders"]]
        for output in params.get("outputs") or []:
            if isinstance(output, dict) and isinstance(output.get("data"), dict):
                targets.extend(self._collect_targets(output["data"]))
        return [item for item in targets if isinstance(item[1], dict)]

    # ------------------------------------------------------------------ 分发

    def _validate(self, kind: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        if kind == "classification":
            return self._validate_classification(item)
        if kind == "summary":
            return self._validate_summary(item)
        if kind == "qa":
            return self._validate_qa(item)
        return self._validate_reminder(item)

    def _item(self, level: str, kind: str, target: str, result: str,
              issue: str = "", confidence: float = 1.0) -> Dict[str, Any]:
        return {"level": level, "kind": kind, "target": target, "result": result,
                "issue": issue, "confidence": round(float(confidence), 2)}

    def _skip(self, level: str, kind: str, target: str, reason: str) -> Dict[str, Any]:
        return self._item(level, kind, target, "skip", reason)

    # ------------------------------------------------------------------ 分类结果

    def _validate_classification(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        kind = "classification"
        target = item.get("document_id") or item.get("original_filename") or "classification"
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
        checks: List[Dict[str, Any]] = []

        missing = [field for field in LABEL_FIELDS
                   if not isinstance(labels.get(field), dict) or not labels[field].get("label")]
        checks.append(self._item("L1", kind, target, "fail" if missing else "pass",
                                 "缺少标签字段: %s" % ",".join(missing) if missing else ""))

        invalid = []
        doc_type = (labels.get("doc_type") or {}).get("label")
        if doc_type is not None and doc_type not in DOC_TYPES:
            invalid.append("doc_type=%s" % doc_type)
        importance = (labels.get("importance") or {}).get("label")
        if importance is not None and importance not in IMPORTANCE_LEVELS:
            invalid.append("importance=%s" % importance)
        if item.get("method") not in METHODS:
            invalid.append("method=%s" % item.get("method"))
        checks.append(self._item("L2", kind, target, "fail" if invalid else "pass",
                                 "非法取值: %s" % ",".join(invalid) if invalid else ""))

        confidences = [_number((labels.get(field) or {}).get("confidence"))
                       for field in LABEL_FIELDS if isinstance(labels.get(field), dict)]
        low_labels = [field for field in LABEL_FIELDS
                      if isinstance(labels.get(field), dict)
                      and _number(labels[field].get("confidence")) < LABEL_THRESHOLD]
        computed_review = bool(low_labels)
        inconsistent = bool(item.get("needs_review")) != computed_review
        checks.append(self._item(
            "L3", kind, target, "fail" if inconsistent else "pass",
            "needs_review=%s 与低置信标签 %s 不一致" % (item.get("needs_review"), low_labels)
            if inconsistent else ""))

        checks.append(self._skip("L4", kind, target, "分类结果无引用来源，跳过引用一致性"))

        min_conf = min(confidences) if confidences else 0.0
        checks.append(self._item(
            "L5", kind, target, "review" if computed_review else "pass",
            "标签置信度低于阈值 %s: %s" % (LABEL_THRESHOLD, low_labels) if computed_review else "",
            min_conf))
        return checks

    # ------------------------------------------------------------------ 摘要结果

    def _validate_summary(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        kind = "summary"
        target = item.get("document_id") or item.get("original_filename") or "summary"
        checks: List[Dict[str, Any]] = []

        missing = []
        if not str(item.get("summary") or "").strip():
            missing.append("summary")
        if not str(item.get("scenario") or "").strip():
            missing.append("scenario")
        if not isinstance(item.get("knowledge_points"), list):
            missing.append("knowledge_points")
        checks.append(self._item("L1", kind, target, "fail" if missing else "pass",
                                 "缺少字段: %s" % ",".join(missing) if missing else ""))

        invalid = []
        if item.get("file_type") not in FILE_TYPES:
            invalid.append("file_type=%s" % item.get("file_type"))
        if not isinstance(item.get("truncated"), bool):
            invalid.append("truncated 非布尔")
        checks.append(self._item("L2", kind, target, "fail" if invalid else "pass",
                                 "非法取值: %s" % ",".join(invalid) if invalid else ""))

        issues = []
        summary_text = str(item.get("summary") or "")
        if item.get("truncated") and not summary_text.endswith(TRUNCATED_MARK):
            issues.append("truncated=True 但摘要缺少 %s 标记" % TRUNCATED_MARK)
        if int(_number(item.get("segment_count"))) < 1:
            issues.append("segment_count 必须 >= 1")
        checks.append(self._item("L3", kind, target, "fail" if issues else "pass",
                                 "; ".join(issues)))

        checks.append(self._skip("L4", kind, target, "摘要无引用来源，跳过引用一致性"))

        truncated = bool(item.get("truncated"))
        checks.append(self._item(
            "L5", kind, target, "review" if truncated else "pass",
            "摘要被截断，内容不完整，建议人工复核" if truncated else "",
            0.6 if truncated else 1.0))
        return checks

    # ------------------------------------------------------------------ 问答结果

    def _validate_qa(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        kind = "qa"
        target = item.get("document_id") or "qa"
        answer = str(item.get("answer") or "")
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        confidence = _number(item.get("confidence"))
        checks: List[Dict[str, Any]] = []

        missing = []
        if not answer.strip():
            missing.append("answer")
        if not isinstance(item.get("sources"), list):
            missing.append("sources")
        if any(not str(source.get("title") or "").strip()
               for source in sources if isinstance(source, dict)):
            missing.append("sources[].title")
        checks.append(self._item("L1", kind, target, "fail" if missing else "pass",
                                 "缺少字段: %s" % ",".join(missing) if missing else ""))

        invalid = []
        if not 0.0 <= confidence <= 1.0:
            invalid.append("confidence=%s" % confidence)
        if any(not 0.0 <= _number(source.get("score")) <= 1.0
               for source in sources if isinstance(source, dict)):
            invalid.append("sources[].score 越界")
        checks.append(self._item("L2", kind, target, "fail" if invalid else "pass",
                                 "非法取值: %s" % ",".join(invalid) if invalid else ""))

        issues = []
        if sources:
            average = sum(_number(source.get("score")) for source in sources) / len(sources)
            if abs(average - confidence) > QA_CONFIDENCE_TOLERANCE:
                issues.append("confidence=%.2f 与来源均分 %.2f 偏差超过 %.2f"
                              % (confidence, average, QA_CONFIDENCE_TOLERANCE))
        if not sources and answer != NO_RESULT_TEXT:
            issues.append("无来源却给出答案，存在编造风险")
        if sources and answer == NO_RESULT_TEXT:
            issues.append("已有来源却回答未检索到相关内容")
        checks.append(self._item("L3", kind, target, "fail" if issues else "pass",
                                 "; ".join(issues)))

        citation_issues = [source.get("title") for source in sources
                           if isinstance(source, dict) and not str(source.get("url") or "").strip()]
        checks.append(self._item("L4", kind, target, "fail" if citation_issues else "pass",
                                 "来源缺少 url: %s" % citation_issues if citation_issues else ""))

        needs_review = confidence < REVIEW_THRESHOLD or not sources
        checks.append(self._item(
            "L5", kind, target, "review" if needs_review else "pass",
            "confidence=%.2f 低于阈值 %s 或缺少来源" % (confidence, REVIEW_THRESHOLD)
            if needs_review else "", confidence))
        return checks

    # ------------------------------------------------------------------ 提醒结果

    def _validate_reminder(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        kind = "reminder"
        target = item.get("title") or "reminder"
        checks: List[Dict[str, Any]] = []

        missing = [field for field in ("title", "event_type", "priority", "channel", "status")
                   if not str(item.get(field) or "").strip()]
        checks.append(self._item("L1", kind, target, "fail" if missing else "pass",
                                 "缺少字段: %s" % ",".join(missing) if missing else ""))

        invalid = []
        if item.get("event_type") not in EVENT_TYPES:
            invalid.append("event_type=%s" % item.get("event_type"))
        if item.get("priority") not in PRIORITIES:
            invalid.append("priority=%s" % item.get("priority"))
        if item.get("status") not in STATUSES:
            invalid.append("status=%s" % item.get("status"))
        if item.get("channel") not in CHANNELS:
            invalid.append("channel=%s" % item.get("channel"))
        checks.append(self._item("L2", kind, target, "fail" if invalid else "pass",
                                 "非法取值: %s" % ",".join(invalid) if invalid else ""))

        issues = []
        due_date = item.get("due_date")
        status = item.get("status")
        if status == "unparsed":
            if due_date is not None:
                issues.append("status=unparsed 但 due_date 非空")
            if not str(item.get("unparsed_text") or "").strip():
                issues.append("status=unparsed 但缺少 unparsed_text")
        elif status in ("pending", "pushed"):
            if not due_date:
                issues.append("status=%s 但缺少 due_date" % status)
            else:
                try:
                    datetime.strptime(str(due_date), "%Y-%m-%d")
                except ValueError:
                    issues.append("due_date 格式非 YYYY-MM-DD: %s" % due_date)
        checks.append(self._item("L3", kind, target, "fail" if issues else "pass",
                                 "; ".join(issues)))

        checks.append(self._skip("L4", kind, target, "提醒无引用来源，跳过引用一致性"))

        needs_review = status == "unparsed"
        checks.append(self._item(
            "L5", kind, target, "review" if needs_review else "pass",
            "时间未解析，需人工确认" if needs_review else "",
            0.4 if needs_review else 1.0))
        return checks

    # ------------------------------------------------------------------ 工单与 mock

    def _make_ticket(self, check: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ticket_id": "RV-" + uuid.uuid4().hex[:8].upper(),
            "level": check["level"],
            "kind": check["kind"],
            "target": check["target"],
            "issue": check["issue"],
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "open",
        }

    def _mock_targets(self) -> List[Tuple[str, Dict[str, Any]]]:
        return [
            ("qa", {
                "document_id": "mock_qa_1",
                "answer": "第三章重点是导数与微分。",
                "sources": [
                    {"title": "高等数学 第三章 课件", "url": "mock://course/gaoshu/ch03", "score": 0.88},
                    {"title": "高等数学 第三章 习题", "url": "mock://course/gaoshu/ch03-ex", "score": 0.76},
                ],
                "confidence": 0.82,
            }),
            ("classification", {
                "document_id": "mock_doc_1",
                "labels": {
                    "course": {"label": "高等数学", "confidence": 0.92},
                    "chapter": {"label": "未识别", "confidence": 0.3},
                    "doc_type": {"label": "课件", "confidence": 0.9},
                    "importance": {"label": "中", "confidence": 0.7},
                },
                "method": "llm",
                "needs_review": True,
                "review_labels": ["chapter"],
            }),
            ("summary", {
                "document_id": "mock_doc_2",
                "summary": "该 pdf 资料共 2 段，主要内容围绕导数、微分展开（模拟摘要）。",
                "knowledge_points": ["第三章 导数", "第三章 微分"],
                "keywords": ["导数", "微分"],
                "scenario": "章节复习与考试备考",
                "file_type": "pdf",
                "segment_count": 2,
                "truncated": False,
            }),
            ("reminder", {
                "title": "学院学术讲座（模拟）",
                "event_type": "activity",
                "due_date": None,
                "priority": "medium",
                "channel": "inapp",
                "status": "unparsed",
                "unparsed_text": "时间待定",
            }),
        ]
