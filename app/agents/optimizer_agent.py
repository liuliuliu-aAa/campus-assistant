"""优化 Agent：消费降级消息与人工复核工单，输出策略优化建议。

- 消息驱动：构造时注入 message_bus 会自动 subscribe("optimizer_agent", handler)，handler 只入队；
  也可显式 bind(message_bus)；未注入总线时仍可用 execute(task) 直接分析；
- 分析输入：message_bus 收到的 action="degrade" 消息、validator 的 review 项与工单；
- 输出 {"suggestions": [...], "summary": {...}}，单条建议含 target（分析对象）/ dimension（分析维度）/
  issue（问题定性）/ action（建议动作）/ priority（high|medium|low）；
- mock 模式用规则分析，不调用真实 LLM，无需 API Key；真实模式 _analyze_with_llm 抛 NotImplementedError 占位。
"""

from typing import Any, Dict, List, Optional, Tuple

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode

OPTIMIZER_AGENT_NAME = "optimizer_agent"
DEGRADE_ACTION = "degrade"
REVIEW_CONFIDENCE_THRESHOLD = 0.7
CONSECUTIVE_FAILURE_THRESHOLD = 3
HIGH_PRIORITY_FAILURE_THRESHOLD = 2
RETRY_ATTEMPT_THRESHOLD = 2

DEFAULT_PRIORITY_WEIGHTS = {
    "urgency": 0.4,
    "user_priority": 0.3,
    "freshness": 0.2,
    "dependency_depth": 0.1,
}


class OptimizerAgent(BaseAgent):
    """降级消息 + 复核工单 → 规则化优化建议。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = OPTIMIZER_AGENT_NAME,
                 message_bus: Any = None, llm: Any = None) -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.llm = llm
        self.message_bus = None
        self.inbox: List[Dict[str, Any]] = []
        if message_bus is not None:
            self.bind(message_bus)

    def bind(self, message_bus: Any) -> None:
        """注册消息消费；新增 Agent 只需 unsubscribe 即可摘除，不改总线代码。"""
        self.message_bus = message_bus
        message_bus.subscribe(OPTIMIZER_AGENT_NAME, self.handle_message)

    def handle_message(self, message: Dict[str, Any]) -> None:
        """总线回调：只入队，避免在消息线程里做重分析。"""
        if isinstance(message, dict):
            self.inbox.append(message)

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        messages, reviews = self._collect_inputs(params)
        if not messages and not reviews and self.mock_mode:
            messages, reviews = self._mock_inputs()
        try:
            if self.mock_mode:
                suggestions = self._analyze_by_rules(messages, reviews)
            else:
                suggestions = await self._analyze_with_llm(messages, reviews)
        except NotImplementedError as exc:
            return AgentResult(False, None, error=str(exc))
        return AgentResult(True, {
            "suggestions": suggestions,
            "summary": {
                "analyzed_messages": len(messages),
                "analyzed_reviews": len(reviews),
                "suggestion_count": len(suggestions),
                "high_priority": sum(1 for item in suggestions if item["priority"] == "high"),
                "weights": dict(DEFAULT_PRIORITY_WEIGHTS),
            },
        })

    def _collect_inputs(self, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        messages = list(self.inbox)
        messages += [item for item in params.get("messages") or [] if isinstance(item, dict)]
        messages += [item for item in params.get("degrade_messages") or [] if isinstance(item, dict)]
        reviews = [item for item in params.get("validated") or [] if isinstance(item, dict)]
        reviews += [item for item in params.get("tickets") or [] if isinstance(item, dict)]
        self.inbox.clear()
        return messages, reviews

    async def _analyze_with_llm(self, messages: List[Dict[str, Any]],
                                reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 预留：真实模式在此把降级/工单数据组织成 prompt，交给 self.llm.generate(...)。
        raise NotImplementedError("真实模式的策略优化建议生成待接入")

    def _analyze_by_rules(self, messages: List[Dict[str, Any]],
                          reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        failures = self._group_failures(messages)
        for agent_type, entry in failures.items():
            error_sample = entry["errors"][0] if entry["errors"] else "未知错误"
            suggestions.append({
                "target": agent_type,
                "dimension": "failure_pattern",
                "issue": "近 %d 次任务重试耗尽后降级，典型错误：%s" % (entry["count"], error_sample),
                "action": "排查该 Agent 的输入与下游依赖；连续失败时提高重试上限并降低调度权重",
                "priority": "high" if entry["count"] >= HIGH_PRIORITY_FAILURE_THRESHOLD else "medium",
            })
            if entry["max_consecutive"] >= CONSECUTIVE_FAILURE_THRESHOLD:
                suggestions.append({
                    "target": agent_type,
                    "dimension": "agent_performance",
                    "issue": "连续失败 %d 次，已超过熔断阈值 %d" %
                             (entry["max_consecutive"], CONSECUTIVE_FAILURE_THRESHOLD),
                    "action": "为该 Agent 启用熔断与限流，失败期间任务改派同类 Agent 或延后重试",
                    "priority": "high",
                })

        if any(entry["max_attempts"] > RETRY_ATTEMPT_THRESHOLD for entry in failures.values()):
            suggestions.append({
                "target": "executor",
                "dimension": "retry_policy",
                "issue": "存在用满 %d 次尝试才降级的任务，重试成本偏高" % (RETRY_ATTEMPT_THRESHOLD + 2),
                "action": "指数退避基数 1s→2s，并对同类错误启用熔断（连续失败 3 次停止重试）",
                "priority": "medium",
            })

        high_priority_failures = sum(entry["high_priority"] for entry in failures.values())
        if high_priority_failures >= HIGH_PRIORITY_FAILURE_THRESHOLD:
            suggestions.append({
                "target": "scheduler",
                "dimension": "priority_weight",
                "issue": "高优先级任务多次降级，现有优先级权重未能保障关键任务",
                "action": "urgency 权重 0.4→0.5、freshness 0.2→0.1，优先消化高优先级积压",
                "priority": "high",
            })

        ticket_counts = self._group_tickets(reviews)
        for kind, count in ticket_counts.items():
            suggestions.append({
                "target": kind,
                "dimension": "review_ticket",
                "issue": "人工复核工单集中在 %s，共 %d 条" % (kind, count),
                "action": "为该类输出补充规则与标注样本；复核阈值可在 %s±0.05 范围内微调"
                          % REVIEW_CONFIDENCE_THRESHOLD,
                "priority": "high" if count >= 3 else "medium",
            })

        classification_reviews = ticket_counts.get("classification", 0)
        if classification_reviews:
            suggestions.append({
                "target": "classifier_agent",
                "dimension": "classification_weight",
                "issue": "分类结果人工复核工单 %d 条，规则兜底覆盖不足" % classification_reviews,
                "action": "提高规则引擎权重（LLM:vector:rule 由 0.6:0.3:0.1 调整为 0.5:0.3:0.2），"
                          "低置信标签阈值 0.7→0.65",
                "priority": "high" if classification_reviews >= 3 else "medium",
            })

        if self._needs_chunk_tuning(messages):
            suggestions.append({
                "target": "summarizer_agent",
                "dimension": "chunk_strategy",
                "issue": "摘要/解析类任务多次因长文档或超时失败，分块粒度过粗",
                "action": "PDF 由整章改为 2000 字滑窗（重叠 200 字），PPT 按页合并后再压缩",
                "priority": "medium",
            })

        if any(len(entry["errors"]) >= 2 for entry in failures.values()):
            suggestions.append({
                "target": "agent_pool",
                "dimension": "prompt",
                "issue": "同类错误在不同任务中重复出现，提示词约束不足",
                "action": "为失败 Agent 的提示词补充输出格式示例、few-shot 样例与失败重试指令",
                "priority": "medium",
            })
        return suggestions

    def _needs_chunk_tuning(self, messages: List[Dict[str, Any]]) -> bool:
        keywords = ("chunk", "分块", "过长", "too long", "token", "超时", "timeout")
        for message in messages:
            if message.get("action") != DEGRADE_ACTION:
                continue
            payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
            error = str(payload.get("error") or "").lower()
            if any(word in error for word in keywords):
                return True
            if payload.get("agent_type") in ("summarizer_agent", "collector_agent") \
                    and self._int(payload.get("attempts")) >= 2:
                return True
        return False

    def _group_failures(self, messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        failures: Dict[str, Dict[str, Any]] = {}
        for message in messages:
            if message.get("action") != DEGRADE_ACTION:
                continue
            payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
            agent_type = payload.get("agent_type") or message.get("from_agent") or "unknown"
            entry = failures.setdefault(agent_type, {
                "count": 0, "errors": [], "max_attempts": 0,
                "max_consecutive": 0, "high_priority": 0,
            })
            entry["count"] += 1
            if payload.get("error"):
                entry["errors"].append(str(payload["error"]))
            entry["max_attempts"] = max(entry["max_attempts"], self._int(payload.get("attempts")))
            entry["max_consecutive"] = max(entry["max_consecutive"],
                                            self._int(payload.get("consecutive_failures")))
            context = message.get("context") if isinstance(message.get("context"), dict) else {}
            if context.get("priority") == "high":
                entry["high_priority"] += 1
        return failures

    def _group_tickets(self, reviews: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in reviews:
            ticket = item.get("ticket") if isinstance(item.get("ticket"), dict) else item
            if item.get("result") not in (None, "review") and "ticket_id" not in ticket:
                continue
            kind = ticket.get("kind") or item.get("kind") or "unknown"
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def _int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _mock_inputs(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        messages = [
            {
                "task_id": "mock_task_1",
                "from_agent": "executor",
                "to_agent": OPTIMIZER_AGENT_NAME,
                "action": DEGRADE_ACTION,
                "payload": {"agent_type": "collector_agent", "attempts": 4,
                            "error": "渠道拉取超时", "consecutive_failures": 2},
                "context": {"course": "高等数学", "priority": "high", "retry_count": 3},
                "timestamp": "2026-11-20T06:00:00Z",
            },
            {
                "task_id": "mock_task_2",
                "from_agent": "executor",
                "to_agent": OPTIMIZER_AGENT_NAME,
                "action": DEGRADE_ACTION,
                "payload": {"agent_type": "collector_agent", "attempts": 4,
                            "error": "渠道拉取超时", "consecutive_failures": 4},
                "context": {"course": "高等数学", "priority": "high", "retry_count": 3},
                "timestamp": "2026-11-20T06:05:00Z",
            },
            {
                "task_id": "mock_task_3",
                "from_agent": "executor",
                "to_agent": OPTIMIZER_AGENT_NAME,
                "action": DEGRADE_ACTION,
                "payload": {"agent_type": "summarizer_agent", "attempts": 3,
                            "error": "OCR 服务不可用", "consecutive_failures": 1},
                "context": {"course": "高等数学", "priority": "medium", "retry_count": 2},
                "timestamp": "2026-11-20T06:10:00Z",
            },
        ]
        reviews = [
            {"level": "L5", "kind": "qa", "target": "mock_qa_1", "result": "review",
             "issue": "confidence=0.62 低于阈值 0.7", "confidence": 0.62,
             "ticket": {"ticket_id": "RV-0000MOCK", "level": "L5", "kind": "qa",
                        "target": "mock_qa_1", "issue": "confidence=0.62 低于阈值 0.7",
                        "created_at": "2026-11-20T06:15:00Z", "status": "open"}},
            {"level": "L5", "kind": "qa", "target": "mock_qa_2", "result": "review",
             "issue": "confidence=0.58 低于阈值 0.7", "confidence": 0.58,
             "ticket": {"ticket_id": "RV-0000MOC2", "level": "L5", "kind": "qa",
                        "target": "mock_qa_2", "issue": "confidence=0.58 低于阈值 0.7",
                        "created_at": "2026-11-20T06:16:00Z", "status": "open"}},
            {"level": "L5", "kind": "classification", "target": "mock_doc_1", "result": "review",
             "issue": "chapter 标签置信度 0.3 低于阈值 0.7", "confidence": 0.3,
             "ticket": {"ticket_id": "RV-0000MOC3", "level": "L5", "kind": "classification",
                        "target": "mock_doc_1", "issue": "chapter 标签置信度 0.3 低于阈值 0.7",
                        "created_at": "2026-11-20T06:17:00Z", "status": "open"}},
        ]
        return messages, reviews
