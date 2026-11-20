"""TC09 异常处理：损坏文件优雅报错并跳过，不影响其他任务。

- 单任务异常由 TaskExecutor 包成 degraded 记录，不中断整批；
- 同批次无依赖任务继续成功，依赖降级任务的下游标 skipped。
"""

import asyncio

import pytest

from app.agents.base_agent import AgentResult
from app.agents.classifier_agent import ClassifierAgent
from app.orchestrator.executor import TaskExecutor
from app.orchestrator.message_bus import MessageBus
from app.orchestrator.task_graph import TaskGraph
from app.services.file_parser import FileParser


def run(coro):
    return asyncio.run(coro)


def test_tc09_corrupted_file():
    """TC09：损坏 PDF 不抛未捕获异常；不支持类型明确报错；其他任务继续成功。"""
    parser = FileParser()
    parsed = parser.parse({"original_filename": "损坏.pdf", "file_type": "pdf", "content": ""})
    assert parsed["file_type"] == "pdf"
    assert parsed["segments"] == []

    with pytest.raises(ValueError):
        parser.parse({"original_filename": "bad.exe", "file_type": "exe", "content": "x"})

    result = run(ClassifierAgent().run({
        "task_id": "test-classifier", "agent_type": "classifier",
        "params": {"files": [{"document_id": "doc_ok",
                              "original_filename": "第三章-课件.pdf"}]},
    }))
    assert result.success
    assert result.data["classified"]


class _BrokenAgent:
    """模拟损坏文件导致 Agent 直接抛异常（异常来自真实 FileParser 的非法类型校验）。"""

    async def run(self, task):
        FileParser().parse({"original_filename": "bad.exe", "file_type": "exe", "content": "x"})


class _GoodAgent:
    async def run(self, task):
        return AgentResult(True, {"ok": True}, confidence=0.9)


def test_tc09_executor_isolates_failed_task():
    """TC09：executor 将异常包成降级记录，同批正常任务继续，下游 skipped。"""
    graph = TaskGraph()
    graph.add_task("bad", "broken", {})
    graph.add_task("good", "good", {})
    graph.add_task("downstream", "good", {}, depends_on=("bad",))

    executor = TaskExecutor(
        graph=graph,
        agent_pool={"broken": _BrokenAgent(), "good": _GoodAgent()},
        message_bus=MessageBus(),
        config={"max_retry": 0, "task_timeout": 5},
    )
    records = run(executor.run())

    assert records["bad"].success is False
    assert records["bad"].state == "degraded"
    assert records["bad"].error
    assert records["good"].success is True
    assert records["good"].state == "succeeded"
    assert records["downstream"].state == "skipped"
