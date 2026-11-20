"""MCP 工具：validate_output —— 五级校验与人工复核工单（ValidatorAgent）。"""

from typing import Any, Dict

from app.agents.validator_agent import ValidatorAgent
from app.mcp.tools.common import build_task, unwrap


async def call(arguments: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    output = arguments.get("output")
    if not isinstance(output, dict) or not output:
        raise ValueError("output 必须为待校验的非空对象")
    agent = ValidatorAgent(config=config)
    return unwrap(await agent.run(build_task("validator", {"outputs": [{"data": output}]})))


TOOL = {
    "name": "validate_output",
    "description": "对 classifier / summarizer / qa / reminder 的输出做 L1-L5 校验并生成人工复核工单",
    "inputSchema": {
        "type": "object",
        "properties": {
            "output": {
                "type": "object",
                "description": "待校验输出，如 {answer, sources, confidence} 或 {classified: [...]}",
            },
        },
        "required": ["output"],
    },
    "handler": call,
}
