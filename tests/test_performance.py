"""TC07 / TC08 性能相关测试。

- TC07：mock 下只验证 100 文件并发调度不报错、全部成功，不断言耗时；
- TC08：10 万文档检索 <2s 属真实环境指标，mock 环境无法构造，标记 skip。
"""

import asyncio

import pytest

from app.agents.classifier_agent import ClassifierAgent


def make_task(agent_type, params):
    return {"task_id": "test-" + agent_type, "agent_type": agent_type, "params": params}


def test_tc07_high_concurrency():
    """TC07 高并发：100 份文件并发分类，全部完成且无失败。"""
    agent = ClassifierAgent()
    files = [{"document_id": "doc_%03d" % index,
              "original_filename": "资料%03d-第三章-课件.pdf" % index} for index in range(100)]

    async def gather_all():
        return await asyncio.gather(*[
            agent.run(make_task("classifier", {"files": [file]})) for file in files
        ])

    results = asyncio.run(gather_all())
    assert len(results) == 100
    assert all(result.success for result in results)
    assert agent.metrics["total"] == 100
    assert agent.metrics["fail"] == 0


@pytest.mark.skip(reason="10 万文档检索 <2s 为真实环境指标占位，mock 环境无法构造")
def test_tc08_retrieval_performance():
    """TC08 检索性能：真实环境要求端到端 <2 秒。"""
    assert False, "仅在真实 RAG / 向量库环境执行"
