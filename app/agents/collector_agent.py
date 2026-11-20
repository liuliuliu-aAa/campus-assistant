"""采集 Agent：按订阅清单从多源渠道增量拉取原始文件与元数据，按内容哈希去重。

- 订阅清单：task["params"]["subscriptions"] = [{"channel": "course_group", "since": "2026-11-20T00:00:00Z"}, ...]
  since 可省略，省略时使用本进程内该渠道的游标（self.cursors）。
- 文件元数据：file_id / channel（来源渠道）/ source / uploader / original_filename /
  collected_at（采集时间）/ content_hash / size / content。
- 去重：sha256(content) 命中 self._seen_hashes 即跳过，计入 duplicates。
- mock 模式返回内置模拟文件列表，不调用任何真实接口；真实模式在 _fetch_from_channel 留接入点。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import get_config, is_mock_mode
from app.utils.hash_utils import sha256_hex

DEFAULT_SUBSCRIPTIONS = (
    {"channel": "course_group"},
    {"channel": "lms"},
    {"channel": "mail"},
)

MOCK_FILES = {
    "course_group": {
        "source": "高等数学课程群",
        "uploader": "张老师",
        "original_filename": "第三章-课件.pdf",
        "content": "高等数学 第三章 导数与微分 课件要点（模拟）",
    },
    "lms": {
        "source": "教务系统 LMS",
        "uploader": "教务秘书",
        "original_filename": "2026-11-20-作业提交通知.pdf",
        "content": "本周五前提交第三章作业（模拟）",
    },
    "mail": {
        "source": "校园邮箱",
        "uploader": "辅导员",
        "original_filename": "奖学金评审通知.docx",
        "content": "学院奖学金评审材料提交说明（模拟）",
    },
}


class CollectorAgent(BaseAgent):
    """多源增量采集，继承 BaseAgent，只实现 execute。"""

    def __init__(self, config=None, name="collector_agent"):
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        # TODO: 进程内增量游标，后续需持久化到元数据库（重启后需从库中恢复，避免重复全量采集）
        self.cursors: Dict[str, str] = {}
        # TODO: 进程内内容哈希去重集合，后续需持久化到元数据库（重启后仍需跨进程去重）
        self._seen_hashes = set()
        self._mock_collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        subscriptions = params.get("subscriptions") or list(DEFAULT_SUBSCRIPTIONS)
        files: List[Dict[str, Any]] = []
        duplicates = 0
        try:
            for subscription in subscriptions:
                channel = subscription.get("channel")
                cursor = subscription.get("since") or self.cursors.get(channel)
                for item in await self._fetch(channel, subscription):
                    if cursor and item["collected_at"] <= cursor:
                        continue
                    if item["content_hash"] in self._seen_hashes:
                        duplicates += 1
                        continue
                    self._seen_hashes.add(item["content_hash"])
                    files.append(item)
                    if item["collected_at"] > self.cursors.get(channel, ""):
                        self.cursors[channel] = item["collected_at"]
        except NotImplementedError as exc:
            return AgentResult(False, None, error=str(exc))
        return AgentResult(True, {
            "files": files,
            "new_count": len(files),
            "duplicates": duplicates,
            "subscriptions": subscriptions,
        })

    async def _fetch(self, channel: str, subscription: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return self._fetch_mock(channel)
        return await self._fetch_from_channel(channel, subscription)

    def _fetch_mock(self, channel: str) -> List[Dict[str, Any]]:
        template = MOCK_FILES.get(channel)
        if template is None:
            return []
        content = template["content"]
        return [{
            "file_id": "%s_%s" % (channel, sha256_hex(content)[:12]),
            "channel": channel,
            "source": template["source"],
            "uploader": template["uploader"],
            "original_filename": template["original_filename"],
            "collected_at": self._mock_collected_at,
            "content_hash": sha256_hex(content),
            "size": len(content.encode("utf-8")),
            "content": content,
        }]

    async def _fetch_from_channel(self, channel: str, subscription: Dict[str, Any]) -> List[Dict[str, Any]]:
        # 预留：真实模式在此接入各渠道（课程群 / LMS / 邮箱）的拉取接口。
        raise NotImplementedError("真实模式的渠道接入待实现: %s" % channel)
