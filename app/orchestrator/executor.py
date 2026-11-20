"""任务执行器（状态机）：按 TaskGraph 的批次计划并行执行 Agent 任务。

状态流转：
    pending -> running -> succeeded
                       -> retrying -> succeeded
                       -> degraded        （重试耗尽）
    pending -> skipped                       （上游任务降级，依赖链被阻塞）

实现约定：
- 每个批次内的任务用 asyncio.gather 并行执行，批次之间串行；
- 单任务超时取 config 的 TASK_TIMEOUT（默认 30 秒）；
- 首次失败后指数退避 1s、2s、4s ... 重试，最多 MAX_RETRY 次（默认 3 次，即总尝试 4 次）；
- 重试耗尽即降级：任务标记 degraded，不抛异常中断后续批次，并通过 message_bus
  向优化 Agent 发送 action="degrade" 的消息（不直接 import / 实例化 optimizer_agent）；
- 依赖已降级任务的下游任务不再执行，标记 skipped。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import MAX_RETRY, TASK_TIMEOUT, get_config
from app.orchestrator.message_bus import MessageBus, build_message
from app.orchestrator.task_graph import TaskGraph, TaskNode
from app.utils.logging_utils import log_event

OPTIMIZER_AGENT = "optimizer_agent"
EXECUTOR_AGENT = "executor"


@dataclass
class TaskRecord:
    """单个任务的执行记录，回传给调用方。"""
    task_id: str
    agent_type: str
    state: str = "pending"
    attempts: int = 0
    success: bool = False
    result: Any = None
    execution_time: float = 0.0
    confidence: float = 0.0
    error: Optional[str] = None


class TaskExecutor:
    """状态机执行器：agent_pool 为 {agent_type: agent 实例} 映射。"""

    graph: Optional[TaskGraph]
    agent_pool: Dict[str, Any]
    message_bus: Optional[MessageBus]
    config: Dict[str, Any]
    max_retry: int
    timeout: float
    logger: logging.Logger
    consecutive_failures: int

    def __init__(self, graph: Optional[TaskGraph] = None,
                 agent_pool: Optional[Dict[str, Any]] = None,
                 message_bus: Optional[MessageBus] = None,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self.graph = graph
        self.agent_pool = agent_pool if agent_pool is not None else {}
        self.message_bus = message_bus
        self.config = config if config is not None else get_config()
        self.max_retry = int(self.config.get("max_retry", MAX_RETRY))
        self.timeout = float(self.config.get("task_timeout", TASK_TIMEOUT))
        self.logger = logging.getLogger("orchestrator.executor")
        self.consecutive_failures = 0

    async def run(self, graph: Optional[TaskGraph] = None) -> Dict[str, TaskRecord]:
        """按 get_execution_plan() 的批次执行，返回 {task_id: TaskRecord}。"""
        graph = graph if graph is not None else self.graph
        if graph is None:
            raise ValueError("TaskExecutor 需要 TaskGraph 实例")
        records: Dict[str, TaskRecord] = {}
        blocked = set()
        for batch in graph.get_execution_plan():
            runnable: list = []
            for task_id in batch:
                depends_on = [dep for dep, target in graph.edges if target == task_id]
                if any(dep in blocked for dep in depends_on):
                    record = TaskRecord(
                        task_id=task_id,
                        agent_type=graph.nodes[task_id].agent_type,
                        state="skipped",
                        error="upstream task degraded",
                    )
                    records[task_id] = record
                    blocked.add(task_id)
                    self._log_event("task_skipped", record, logging.WARNING)
                else:
                    runnable.append(task_id)
            if not runnable:
                continue
            batch_records = await asyncio.gather(
                *(self._run_task(task_id, graph.nodes[task_id]) for task_id in runnable))
            for record in batch_records:
                records[record.task_id] = record
                if record.state == "degraded":
                    blocked.add(record.task_id)
        return records

    async def _run_task(self, task_id: str, node: TaskNode) -> TaskRecord:
        record = TaskRecord(task_id=task_id, agent_type=node.agent_type)
        agent = self.agent_pool.get(node.agent_type)
        if agent is None:
            record.state = "degraded"
            record.error = "no agent registered for agent_type=%s" % node.agent_type
            await self._degrade(record, node)
            return record
        task = {"task_id": task_id, "agent_type": node.agent_type, "params": node.params}
        while True:
            record.attempts += 1
            record.state = "running" if record.attempts == 1 else "retrying"
            try:
                result = await asyncio.wait_for(agent.run(task), timeout=self.timeout)
            except asyncio.TimeoutError:
                record.error = "task timeout after %ss" % self.timeout
            except Exception as exc:
                record.error = str(exc)
            else:
                record.result = result
                record.execution_time = getattr(result, "execution_time", 0.0)
                record.confidence = getattr(result, "confidence", 0.0)
                if getattr(result, "success", False):
                    record.success = True
                    record.state = "succeeded"
                    self.consecutive_failures = 0
                    return record
                record.error = getattr(result, "error", None) or "agent returned success=False"
            if record.attempts > self.max_retry:
                break
            backoff = 2 ** (record.attempts - 1)
            self._log_event("task_retry", record, logging.WARNING)
            await asyncio.sleep(backoff)
        record.state = "degraded"
        await self._degrade(record, node)
        return record

    async def _degrade(self, record: TaskRecord, node: TaskNode) -> None:
        """降级策略：记录 degraded + 结构化日志 + 通知优化 Agent。"""
        self.consecutive_failures += 1
        self._log_event("task_degraded", record)
        if self.message_bus is None:
            self.logger.error("message_bus not injected, skip notifying %s" % OPTIMIZER_AGENT)
            return
        params = node.params if isinstance(node.params, dict) else {}
        message = build_message(
            task_id=record.task_id,
            from_agent=EXECUTOR_AGENT,
            to_agent=OPTIMIZER_AGENT,
            action="degrade",
            payload={
                "agent_type": record.agent_type,
                "state": record.state,
                "attempts": record.attempts,
                "error": record.error,
                "consecutive_failures": self.consecutive_failures,
            },
            context={
                "course": params.get("course"),
                "priority": params.get("priority"),
                "retry_count": max(record.attempts - 1, 0),
            },
        )
        await self.message_bus.send(message)

    def _log_event(self, event: str, record: TaskRecord, level: int = logging.ERROR) -> None:
        """结构化日志：单行 JSON，便于采集与检索。"""
        log_event(self.logger, event, level=level, task_id=record.task_id,
                  agent_type=record.agent_type, state=record.state,
                  attempts=record.attempts, execution_time=record.execution_time,
                  confidence=record.confidence, error=record.error)
