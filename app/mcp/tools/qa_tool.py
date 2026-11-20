"""MCP 工具：ask_question —— 基于校园资料知识库的问答（QAAgent）。"""

from typing import Any, Dict

from app.agents.qa_agent import QAAgent
from app.mcp.tools.common import build_task, unwrap


async def call(arguments: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ValueError("query 不能为空")
    params: Dict[str, Any] = {"query": query}
    if arguments.get("course"):
        params["course"] = arguments["course"]
    if arguments.get("top_k"):
        params["top_k"] = int(arguments["top_k"])
    agent = QAAgent(config=config)
    return unwrap(await agent.run(build_task("qa", params)))


TOOL = {
    "name": "ask_question",
    "description": "基于校园资料知识库回答问题，强制返回来源列表与置信度",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户问题"},
            "course": {"type": "string", "description": "可选，限定课程范围"},
            "top_k": {"type": "integer", "description": "检索条数，默认 5", "default": 5},
        },
        "required": ["query"],
    },
    "handler": call,
}
