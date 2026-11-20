"""MCP 工具：summarize_documents —— 分类型文档摘要（SummarizerAgent）。"""

from typing import Any, Dict

from app.agents.summarizer_agent import SummarizerAgent
from app.mcp.tools.common import build_task, unwrap


async def call(arguments: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    files = arguments.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("files 必须为非空数组")
    agent = SummarizerAgent(config=config)
    return unwrap(await agent.run(build_task("summarizer", {"files": files})))


TOOL = {
    "name": "summarize_documents",
    "description": "对文档生成一句话摘要、知识点、关键词与适用场景（PPT 逐页 / PDF 分章节 / 图片 OCR）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "文档列表，单项至少含 document_id 或 original_filename",
                "items": {"type": "object"},
            },
        },
        "required": ["files"],
    },
    "handler": call,
}
