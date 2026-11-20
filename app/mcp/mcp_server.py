"""MCP 服务入口：把现有能力包装为工具，提供最小可运行的注册 / 调用骨架。

- 工具：ask_question / summarize_documents / extract_reminders / validate_output，
  内部只调用 QAAgent / SummarizerAgent / ReminderAgent / ValidatorAgent，不复制业务逻辑；
- 无 MCP SDK 时：用标准库实现 JSON-RPC over stdio（initialize / tools/list / tools/call），
  mock 模式下离线可跑，无 API Key、无外部依赖；
- 真实 SDK 接入点：serve_stdio() 换成官方 mcp.server.Server 的 stdio_server 注册即可，
  工具定义（name / description / inputSchema / handler）可直接复用。
"""

import asyncio
import json
import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.config import get_config, is_mock_mode
from app.mcp.tools import qa_tool, reminder_tool, summary_tool, validator_tool

ToolHandler = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Dict[str, Any]]]

SERVER_NAME = "campus-assistant-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


class MCPServer:
    """最小 MCP 服务：工具注册表 + JSON-RPC 处理。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config if config is not None else get_config()
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.tools: Dict[str, Dict[str, Any]] = {}
        for tool in (qa_tool.TOOL, summary_tool.TOOL, reminder_tool.TOOL, validator_tool.TOOL):
            self.register_tool(tool)

    def register_tool(self, tool: Dict[str, Any]) -> None:
        name = tool.get("name")
        if not name or not callable(tool.get("handler")):
            raise ValueError("工具定义缺少 name 或 handler")
        self.tools[name] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": tool["name"], "description": tool["description"],
             "inputSchema": tool["inputSchema"]}
            for tool in self.tools.values()
        ]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError("未知工具: %s（可选 %s）" % (name, ", ".join(self.tools)))
        try:
            data = await tool["handler"](arguments or {}, self.config)
        except Exception as exc:
            return {"content": [{"type": "text", "text": "执行失败: %s" % exc}], "isError": True}
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "isError": False}

    async def handle_request(self, request: Any) -> Dict[str, Any]:
        request_id = request.get("id") if isinstance(request, dict) else None
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(request_id, -32600, "Invalid Request")
        method = request.get("method")
        if method == "initialize":
            return self._ok(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
        if method == "tools/list":
            return self._ok(request_id, {"tools": self.list_tools()})
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                result = await self.call_tool(params.get("name"), params.get("arguments") or {})
            except ValueError as exc:
                return self._error(request_id, -32602, str(exc))
            return self._ok(request_id, result)
        return self._error(request_id, -32601, "Method not found: %s" % method)

    def serve_stdio(self) -> None:
        """逐行读 JSON-RPC 请求并回写响应；真实 SDK 接入时替换此方法即可。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = self._error(None, -32700, "Parse error")
            else:
                response = asyncio.run(self.handle_request(request))
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def _ok(self, request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    MCPServer().serve_stdio()
