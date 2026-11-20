"""Agent 间消息总线：统一 JSON 消息格式 + send / subscribe。

消息字段严格为：task_id、from_agent、to_agent、action、payload、context、timestamp，
其中 context 严格为：course、priority、retry_count。

mock 模式（默认，取自 app.config 的 MOCK_MODE）为纯内存 asyncio 实现，
不依赖真实 Redis 或消息队列即可跑通；真实模式预留 Redis 接入位置。
"""

import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.config import MOCK_MODE, REDIS_URL

MESSAGE_FIELDS = ("task_id", "from_agent", "to_agent", "action", "payload", "context", "timestamp")
CONTEXT_FIELDS = ("course", "priority", "retry_count")


def _now() -> str:
    """UTC 时间戳，格式与申报书消息示例一致：2026-11-20T14:00:00Z。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_message(task_id: str, from_agent: str, to_agent: str, action: str,
                  payload: Optional[Dict[str, Any]] = None,
                  context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造严格符合约定格式的消息，context 缺失字段补默认值。"""
    ctx = dict(context or {})
    ctx.setdefault("course", None)
    ctx.setdefault("priority", None)
    ctx.setdefault("retry_count", 0)
    return {
        "task_id": task_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "action": action,
        "payload": {} if payload is None else payload,
        "context": ctx,
        "timestamp": _now(),
    }


def validate_message(message: Dict[str, Any]) -> None:
    """校验消息字段，不符合约定格式时抛 ValueError。"""
    if not isinstance(message, dict):
        raise TypeError("消息必须是 dict")
    if set(message.keys()) != set(MESSAGE_FIELDS):
        raise ValueError("消息字段必须严格为 %s，实际为 %s"
                         % (list(MESSAGE_FIELDS), sorted(message.keys())))
    if not isinstance(message["context"], dict) or set(message["context"].keys()) != set(CONTEXT_FIELDS):
        raise ValueError("context 字段必须严格为 %s" % (list(CONTEXT_FIELDS),))


class MessageBus:
    """内存消息总线：subscribe 注册消费者，send 按 to_agent 路由。"""

    def __init__(self, mock_mode: Optional[bool] = None, redis_url: Optional[str] = None):
        self.mock_mode = MOCK_MODE if mock_mode is None else mock_mode
        self.redis_url = REDIS_URL if redis_url is None else redis_url
        self.logger = logging.getLogger("orchestrator.message_bus")
        self._subscribers: Dict[str, List[Callable]] = {}
        self._redis = None

    def subscribe(self, agent_name: str, handler: Callable) -> None:
        """注册消费者；agent_name 为 "*" 时接收全部消息。新增 Agent 无需改总线代码。"""
        self._subscribers.setdefault(agent_name, []).append(handler)

    def unsubscribe(self, agent_name: str, handler: Callable) -> None:
        handlers = self._subscribers.get(agent_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def send(self, message: Dict[str, Any]) -> None:
        """发送消息：先校验格式，再按模式路由（mock 走内存，真实模式走 Redis）。"""
        validate_message(message)
        if not self.mock_mode:
            await self._send_via_redis(message)
            return
        await self._dispatch(message)

    async def _dispatch(self, message: Dict[str, Any]) -> None:
        handlers = list(self._subscribers.get(message["to_agent"], []))
        handlers += list(self._subscribers.get("*", []))
        for handler in handlers:
            outcome = handler(message)
            if inspect.isawaitable(outcome):
                await outcome

    async def _send_via_redis(self, message: Dict[str, Any]) -> None:
        # 预留：真实模式在此接入 Redis pub/sub（publish 到 to_agent 对应频道）。
        # 当前未实现，显式报错而不是静默丢消息。
        raise NotImplementedError("真实模式消息队列尚未接入：请在 _send_via_redis 中实现 Redis 发布")
