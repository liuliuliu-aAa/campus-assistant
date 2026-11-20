"""应用装配层：FastAPI 接口 + Agent / services 注入 + 整理流水线。

- Agent 内部逻辑不在本文件重写，只做实例装配与调用；
- FastAPI 不可用时自动退化为标准库 ASGI 应用（FallbackASGIApp），mock 下 import 不会崩；
- 流水线 collect→classify→summarize→validate 由 TaskGraph 定依赖、scheduler.select_agent 选 Agent、
  TaskExecutor 执行（含超时 / 重试 / 降级）；
- 统一响应包装：{"code": 0, "message": "ok", "mock": bool, "data": ...}，HTTP 状态码与 code 对齐。
"""

import json
import logging
import uuid
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from app.agents.classifier_agent import ClassifierAgent
from app.agents.collector_agent import CollectorAgent
from app.agents.optimizer_agent import OptimizerAgent
from app.agents.qa_agent import QAAgent
from app.agents.reminder_agent import ReminderAgent
from app.agents.summarizer_agent import SummarizerAgent
from app.agents.validator_agent import ValidatorAgent
from app.config import get_config, is_mock_mode
from app.mcp.mcp_server import MCPServer
from app.models.api_models import ApiResponse
from app.orchestrator.executor import TaskExecutor
from app.orchestrator.message_bus import MessageBus
from app.orchestrator.scheduler import select_agent
from app.orchestrator.task_graph import TaskGraph
from app.services.file_parser import FileParser
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.notification import NotificationService

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except Exception:  # 缺 fastapi / pydantic 时降级为纯标准库 ASGI
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("app.main")


class ApiError(Exception):
    """业务异常：status 与 code 一致，交由统一包装输出。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = status


class AgentAdapter:
    """编排层适配：给现有 Agent 补 supports / current_load / avg_response_time。"""

    def __init__(self, agent_type: str, agent: Any,
                 supported_types: Optional[List[str]] = None) -> None:
        self.agent_type = agent_type
        self.agent = agent
        self.supported_types = tuple(supported_types or (agent_type,))
        self.current_load = 0
        self._durations: List[float] = []

    def supports(self, task_type: str) -> bool:
        return task_type in self.supported_types

    @property
    def avg_response_time(self) -> float:
        if not self._durations:
            return 0.0
        return sum(self._durations) / len(self._durations)

    @property
    def metrics(self) -> Dict[str, int]:
        return dict(self.agent.metrics)

    async def run(self, task: Dict[str, Any]) -> Any:
        self.current_load += 1
        try:
            result = await self.agent.run(task)
        finally:
            self.current_load = max(0, self.current_load - 1)
        self._durations.append(float(result.execution_time or 0.0))
        self._durations = self._durations[-20:]
        return result


class AppContainer:
    """应用装配：mock 实例 + 适配器 + MCP 服务。"""

    PIPELINE = (("collect", "collector"), ("classify", "classifier"),
                ("summarize", "summarizer"), ("validate", "validator"))

    def __init__(self) -> None:
        self.config = get_config()
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.message_bus = MessageBus()
        self.notification = NotificationService(config=self.config)
        self.knowledge_graph = KnowledgeGraphService(config=self.config)
        self.file_parser = FileParser(config=self.config)
        self.adapters: Dict[str, AgentAdapter] = {
            "collector": AgentAdapter("collector", CollectorAgent(config=self.config)),
            "classifier": AgentAdapter("classifier", ClassifierAgent(config=self.config)),
            "summarizer": AgentAdapter("summarizer", SummarizerAgent(config=self.config)),
            "qa": AgentAdapter("qa", QAAgent(config=self.config,
                                            knowledge_graph=self.knowledge_graph)),
            "reminder": AgentAdapter("reminder", ReminderAgent(config=self.config,
                                                               notification=self.notification)),
            "validator": AgentAdapter("validator", ValidatorAgent(config=self.config)),
            "optimizer": AgentAdapter("optimizer", OptimizerAgent(config=self.config,
                                                                  message_bus=self.message_bus)),
        }
        self.mcp_server = MCPServer(config=self.config)

    # ------------------------------------------------------------------ 基础调用

    async def run_agent(self, agent_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = self.adapters.get(agent_type)
        if adapter is None:
            raise ApiError(500, "未装配 Agent: %s" % agent_type)
        task = {"task_id": "api-" + uuid.uuid4().hex[:8], "agent_type": agent_type,
                "params": params or {}}
        result = await adapter.run(task)
        if not result.success:
            raise ApiError(502, result.error or "%s 执行失败" % agent_type)
        return result.data if isinstance(result.data, dict) else {"data": result.data}

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": self.mock_mode,
            "fastapi_available": FASTAPI_AVAILABLE,
            "agents": sorted(self.adapters),
            "tools": [tool["name"] for tool in self.mcp_server.list_tools()],
        }

    def metrics(self) -> Dict[str, Any]:
        return {"agents": [
            {
                "agent": name,
                "total": adapter.metrics.get("total", 0),
                "success": adapter.metrics.get("success", 0),
                "fail": adapter.metrics.get("fail", 0),
                "current_load": adapter.current_load,
                "avg_response_time": round(adapter.avg_response_time, 3),
            }
            for name, adapter in self.adapters.items()
        ]}

    # ------------------------------------------------------------------ 流水线

    async def run_pipeline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        graph = TaskGraph()
        previous = None
        for stage, agent_type in self.PIPELINE:
            graph.add_task(stage, agent_type, {}, depends_on=(previous,) if previous else ())
            previous = stage

        context: Dict[str, Any] = {
            "subscriptions": payload.get("subscriptions") or payload.get("channels"),
        }
        steps: Dict[str, Any] = {}
        for batch in graph.get_execution_plan():
            for stage in batch:
                node = graph.nodes[stage]
                stage_params = self._pipeline_params(stage, context)
                if stage_params is None:
                    steps[stage] = {"state": "skipped", "success": False,
                                    "error": "上游任务未成功"}
                    context[stage] = None
                    continue
                selected = select_agent(list(self.adapters.values()),
                                        SimpleNamespace(type=node.agent_type))
                stage_graph = TaskGraph()
                stage_graph.add_task(stage, node.agent_type, stage_params)
                executor = TaskExecutor(graph=stage_graph,
                                        agent_pool={node.agent_type: selected},
                                        message_bus=self.message_bus, config=self.config)
                records = await executor.run()
                record = records[stage]
                steps[stage] = self._record_dict(record)
                context[stage] = record.result if record.success else None
        return {"steps": steps, "collect": context.get("collect"),
                "classify": context.get("classify"), "summarize": context.get("summarize"),
                "validate": context.get("validate")}

    def _pipeline_params(self, stage: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if stage == "collect":
            params: Dict[str, Any] = {}
            if context.get("subscriptions"):
                params["subscriptions"] = context["subscriptions"]
            return params
        collect = context.get("collect")
        if not isinstance(collect, dict):
            return None
        files = collect.get("files") or []
        if stage == "classify":
            return {"files": files}
        classify = context.get("classify")
        if stage == "summarize":
            if classify is None:
                return None
            labels = {item.get("document_id"): item.get("labels")
                      for item in (classify.get("classified") or [])}
            enriched = []
            for item in files:
                document = dict(item)
                document["category"] = labels.get(document.get("document_id")) or {}
                enriched.append(document)
            return {"files": enriched}
        summarize = context.get("summarize")
        if summarize is None:
            return None
        return {"outputs": [
            {"type": "classification", "data": {"classified": (classify or {}).get("classified") or []}},
            {"type": "summary", "data": {"summaries": (summarize or {}).get("summaries") or []}},
        ]}

    @staticmethod
    def _record_dict(record: Any) -> Dict[str, Any]:
        if is_dataclass(record):
            data = asdict(record)
        else:
            data = {field: getattr(record, field, None)
                    for field in ("task_id", "agent_type", "state", "attempts", "success",
                                  "result", "execution_time", "confidence", "error")}
        return data

    # ------------------------------------------------------------------ 复习提纲

    async def study_outline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise ApiError(400, "files 不能为空")
        summary = await self.run_agent("summarizer", {"files": files})
        query = str(payload.get("query") or "").strip()
        points: List[str] = []
        if query:
            params: Dict[str, Any] = {"query": query}
            if payload.get("course"):
                params["course"] = payload["course"]
            if payload.get("top_k"):
                params["top_k"] = int(payload["top_k"])
            qa = await self.run_agent("qa", params)
        else:
            for item in summary.get("summaries") or []:
                points.extend(item.get("knowledge_points") or [])
            qa = {
                "answer": "已根据摘要知识点生成复习提纲（占位，未调用检索问答）。"
                          if points else "知识库中未检索到相关内容",
                "sources": [],
                "confidence": 0.0,
            }
        return {"summary": summary, "qa": qa, "knowledge_points": points}


def ok(data: Any) -> Dict[str, Any]:
    return asdict(ApiResponse(data=data))


def fail(container: AppContainer, status: int, message: str) -> Any:
    return status, asdict(ApiResponse(code=status, message=message,
                                      mock=container.mock_mode, data=None))


async def dispatch(container: AppContainer, method: str, path: str,
                   payload: Dict[str, Any]) -> Any:
    """统一路由分发，FastAPI 与降级 ASGI 共用。"""
    payload = payload if isinstance(payload, dict) else {}
    try:
        if method == "GET" and path == "/api/health":
            body = ok(container.health())
        elif method == "GET" and path == "/api/agents/metrics":
            body = ok(container.metrics())
        elif method == "POST" and path == "/api/collect":
            body = ok(await container.run_agent("collector", payload))
        elif method == "POST" and path == "/api/classify":
            body = ok(await container.run_agent("classifier", payload))
        elif method == "POST" and path == "/api/summarize":
            body = ok(await container.run_agent("summarizer", payload))
        elif method == "POST" and path == "/api/qa":
            if not str(payload.get("query") or "").strip():
                raise ApiError(400, "query 不能为空")
            body = ok(await container.run_agent("qa", payload))
        elif method == "POST" and path == "/api/reminders":
            body = ok(await container.run_agent("reminder", payload))
        elif method == "POST" and path == "/api/validate":
            body = ok(await container.run_agent("validator", payload))
        elif method == "POST" and path == "/api/study-outline":
            body = ok(await container.study_outline(payload))
        elif method == "POST" and path == "/api/pipeline":
            body = ok(await container.run_pipeline(payload))
        else:
            return fail(container, 404, "Not Found: %s %s" % (method, path))
    except ApiError as exc:
        return fail(container, exc.status, str(exc))
    except Exception as exc:  # 兜底：不让单次请求拖垮进程
        logger.exception("api error")
        return fail(container, 500, str(exc))
    body["mock"] = container.mock_mode
    return 200, body


class FallbackASGIApp:
    """无 FastAPI 时的最小 ASGI 应用：标准库 JSON 请求 / 响应。"""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            return
        try:
            payload = await self._read_json(receive)
        except ApiError as exc:
            status, body = fail(self.container, exc.status, str(exc))
        else:
            status, body = await dispatch(self.container, scope.get("method", "GET").upper(),
                                          scope.get("path", "/"), payload)
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")]})
        await send({"type": "http.response.body", "body": raw})

    async def _read_json(self, receive: Any) -> Dict[str, Any]:
        chunks = b""
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunks += message.get("body", b"")
            if not message.get("more_body"):
                break
        if not chunks:
            return {}
        try:
            data = json.loads(chunks.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "请求体必须是合法 JSON")
        return data if isinstance(data, dict) else {}


def create_app() -> Any:
    container = AppContainer()
    if not FASTAPI_AVAILABLE:
        logger.warning("FastAPI 不可用，已降级为纯标准库 ASGI 应用")
        return FallbackASGIApp(container)

    app = FastAPI(title="校园资料智能整理助手", version="0.1.0")

    async def handle(request: Request, path: str) -> JSONResponse:
        payload: Dict[str, Any] = {}
        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                payload = {}
        status, body = await dispatch(container, request.method, path, payload)
        return JSONResponse(status_code=status, content=body)

    @app.get("/api/health")
    async def health(request: Request) -> JSONResponse:
        return await handle(request, "/api/health")

    @app.get("/api/agents/metrics")
    async def agents_metrics(request: Request) -> JSONResponse:
        return await handle(request, "/api/agents/metrics")

    @app.post("/api/collect")
    async def collect(request: Request) -> JSONResponse:
        return await handle(request, "/api/collect")

    @app.post("/api/classify")
    async def classify(request: Request) -> JSONResponse:
        return await handle(request, "/api/classify")

    @app.post("/api/summarize")
    async def summarize(request: Request) -> JSONResponse:
        return await handle(request, "/api/summarize")

    @app.post("/api/qa")
    async def qa(request: Request) -> JSONResponse:
        return await handle(request, "/api/qa")

    @app.post("/api/reminders")
    async def reminders(request: Request) -> JSONResponse:
        return await handle(request, "/api/reminders")

    @app.post("/api/validate")
    async def validate(request: Request) -> JSONResponse:
        return await handle(request, "/api/validate")

    @app.post("/api/study-outline")
    async def study_outline(request: Request) -> JSONResponse:
        return await handle(request, "/api/study-outline")

    @app.post("/api/pipeline")
    async def pipeline(request: Request) -> JSONResponse:
        return await handle(request, "/api/pipeline")

    return app


app = create_app()


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("未安装 uvicorn，请先 pip install fastapi uvicorn") from exc
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
