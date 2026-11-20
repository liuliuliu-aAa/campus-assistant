"""MCP 工具公共辅助：统一构造 task 并解包 AgentResult。"""

import uuid
from typing import Any, Dict

from app.agents.base_agent import AgentResult


def build_task(agent_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """按编排层约定构造 {"task_id", "agent_type", "params"}。"""
    return {
        "task_id": "mcp-" + uuid.uuid4().hex[:8],
        "agent_type": agent_type,
        "params": params,
    }


def unwrap(result: AgentResult) -> Dict[str, Any]:
    """Agent 失败时抛出异常，由 MCPServer 统一转 isError 响应。"""
    if not result.success:
        raise RuntimeError(result.error or "agent 执行失败")
    return result.data if isinstance(result.data, dict) else {"data": result.data}
