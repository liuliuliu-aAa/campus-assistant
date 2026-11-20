"""通知服务：实现提醒 Agent 的推送接入点 notification.send(reminder)。

- 渠道：inapp（站内通知）/ email（邮件）/ webhook，默认取 config 的 notify_channel，
  单次调用可用 channel=... 覆盖，其次取 reminder["channel"]；
- 未知渠道不静默：抛 ValueError；
- mock 模式只写内存记录并返回成功结果，不发网络请求、不依赖外部服务；
- 真实发送分支抛 NotImplementedError 占位（邮件 / Webhook / 站内通知的具体实现后续接入）。

reminder_agent 的调用方式是 await notification.send(reminder)，不使用返回值，
因此返回值结构仅为附加信息，不影响既有链路。
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import NOTIFY_CHANNEL, get_config, is_mock_mode

CHANNELS = ("inapp", "email", "webhook")


class NotificationService:
    """按渠道推送提醒；mock 模式内存记录。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, channel: Optional[str] = None) -> None:
        self.config = config if config is not None else get_config()
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.default_channel = channel or self.config.get("notify_channel") or NOTIFY_CHANNEL
        if self.default_channel not in CHANNELS:
            raise ValueError("未知推送渠道: %s（可选 %s）" % (self.default_channel, ", ".join(CHANNELS)))
        self.sent: List[Dict[str, Any]] = []

    async def send(self, reminder: Dict[str, Any], channel: Optional[str] = None) -> Dict[str, Any]:
        """发送单条提醒；channel 优先级：调用参数 > reminder["channel"] > 配置默认。"""
        target_channel = channel or reminder.get("channel") or self.default_channel
        if target_channel not in CHANNELS:
            raise ValueError("未知推送渠道: %s（可选 %s）" % (target_channel, ", ".join(CHANNELS)))
        if self.mock_mode:
            return self._record(reminder, target_channel)
        await self._send_via_channel(reminder, target_channel)
        return self._result(reminder, target_channel, mode="real")

    async def _send_via_channel(self, reminder: Dict[str, Any], channel: str) -> None:
        # 预留：真实模式按 channel 接入站内信 / SMTP / Webhook，当前统一占位。
        raise NotImplementedError("真实模式的 %s 推送待接入" % channel)

    def _record(self, reminder: Dict[str, Any], channel: str) -> Dict[str, Any]:
        record = self._result(reminder, channel, mode="mock")
        self.sent.append(record)
        return record

    def _result(self, reminder: Dict[str, Any], channel: str, mode: str) -> Dict[str, Any]:
        return {
            "success": True,
            "channel": channel,
            "message_id": "NTF-" + uuid.uuid4().hex[:8].upper(),
            "mode": mode,
            "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reminder_title": reminder.get("title") or "",
        }
