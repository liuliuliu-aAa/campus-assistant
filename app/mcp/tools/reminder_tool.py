"""MCP 工具：extract_reminders —— 截止 / 考试 / 活动识别（ReminderAgent）。"""

from typing import Any, Dict

from app.agents.reminder_agent import ReminderAgent
from app.mcp.tools.common import build_task, unwrap


async def call(arguments: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if isinstance(arguments.get("files"), list) and arguments["files"]:
        params["files"] = arguments["files"]
    elif str(arguments.get("text") or "").strip():
        params["text"] = arguments["text"]
    else:
        raise ValueError("files 或 text 至少提供一个")
    if arguments.get("channel"):
        params["channel"] = arguments["channel"]
    agent = ReminderAgent(config=config)
    return unwrap(await agent.run(build_task("reminder", params)))


TOOL = {
    "name": "extract_reminders",
    "description": "从资料文本识别截止日期、考试安排与活动安排，输出结构化提醒",
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "原始文本"},
            "files": {"type": "array", "description": "文档列表（含 content）", "items": {"type": "object"}},
            "channel": {"type": "string", "enum": ["inapp", "email", "webhook"]},
        },
        "required": [],
    },
    "handler": call,
}
