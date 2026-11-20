"""提醒 Agent：从资料文本识别截止日期 / 考试安排 / 活动安排，并生成提醒。

- 事件识别：按关键词判定 event_type ∈ deadline / exam / activity；
- 时间解析：支持中文相对时间（明天、下周三、两周后、月底）与绝对日期（11月20日、2026-11-20）；
  解析失败不猜测，due_date 置 None，status="unparsed"，原始时间片段写入 unparsed_text；
- 推送渠道：站内通知 inapp / 邮件 email / Webhook webhook，取 task.params["channel"]，
  其次 config["notify_channel"]，缺省 inapp；mock 模式不真实推送，真实模式未注入 notification 时抛
  NotImplementedError 占位；
- 输出：{"reminders": [...], "count"}，单项含 title / event_type / due_date / priority / channel /
  status / unparsed_text。

时间解析基准：datetime.now()（本机时区），可用构造参数 now 注入固定基准便于测试与演示。
"""

import calendar
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.agents.base_agent import AgentResult, BaseAgent
from app.config import NOTIFY_CHANNEL, get_config, is_mock_mode

DEFAULT_CHANNEL = "inapp"
CHANNELS = ("inapp", "email", "webhook")
PRIORITY_ORDER = ("high", "medium", "low")

EVENT_KEYWORDS = {
    "deadline": ("截止", "提交", "deadline", "前完成"),
    "exam": ("考试", "测验", "期中", "期末", "exam", "考核"),
    "activity": ("讲座", "活动", "比赛", "宣讲", "会议", "班会", "报名参加"),
}

TIMESTAMP_PATTERN = re.compile(
    r"(下(?:个)?(?:周|星期|礼拜)[一二三四五六日天七]"
    r"|(?:本|这)(?:个)?(?:周|星期|礼拜)[一二三四五六日天七]"
    r"|(?:周|星期|礼拜)[一二三四五六日天七]"
    r"|[0-9一二三四五六七八九十两]+\s*(?:天|周|星期)后"
    r"|下?个?月(?:底|末)"
    r"|大后天|后天|明天|今天"
    r"|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"
    r"|\d{1,2}月\d{1,2}[日号])")

CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}
WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6, "七": 6}


def _cn_to_int(token: str) -> Optional[int]:
    """中文数字转整数（支持 两 / 十 / 十二 / 二十）。无法识别返回 None。"""
    token = token.strip()
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + CN_DIGITS.get(token[1:], 0)
    if token.endswith("十"):
        return CN_DIGITS.get(token[:-1], 0) * 10
    if "十" in token:
        head, tail = token.split("十", 1)
        return CN_DIGITS.get(head, 0) * 10 + CN_DIGITS.get(tail, 0)
    return CN_DIGITS.get(token)


class ReminderAgent(BaseAgent):
    """事件识别 + 中文时间解析 + 多渠道推送（mock 优先）。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "reminder_agent",
                 notification: Any = None, now: Optional[datetime] = None) -> None:
        super().__init__(name, config if config is not None else get_config())
        self.mock_mode = bool(self.config.get("mock_mode", is_mock_mode()))
        self.notify_channel = self.config.get("notify_channel") or NOTIFY_CHANNEL
        self.notification = notification
        # TODO: 后续复用 app/utils/time_utils 统一时区处理（当前保留本机时区语义）
        self.base_time = now or datetime.now()

    async def execute(self, task: Dict) -> AgentResult:
        params = (task or {}).get("params") or {}
        channel = params.get("channel") or self.notify_channel or DEFAULT_CHANNEL
        if channel not in CHANNELS:
            channel = DEFAULT_CHANNEL
        texts = self._extract_texts(params)
        try:
            if texts:
                reminders: List[Dict[str, Any]] = []
                for text, title_hint in texts:
                    reminders.extend(self._extract_reminders(text, title_hint, channel))
            elif self.mock_mode:
                reminders = self._mock_reminders(channel)
            else:
                reminders = []
            for reminder in reminders:
                await self._push(reminder)
        except NotImplementedError as exc:
            return AgentResult(False, None, error=str(exc))
        return AgentResult(True, {"reminders": reminders, "count": len(reminders)})

    def _extract_texts(self, params: Dict[str, Any]) -> List[Tuple[str, str]]:
        documents = params.get("files") or params.get("documents")
        if documents:
            return [
                (doc.get("content") or doc.get("text_content") or "",
                 doc.get("original_filename") or doc.get("document_id") or "")
                for doc in documents
            ]
        text = params.get("text") or params.get("content") or params.get("text_content") or ""
        if text:
            return [(text, params.get("title") or params.get("original_filename") or "")]
        return []

    def _extract_reminders(self, text: str, title_hint: str, channel: str) -> List[Dict[str, Any]]:
        reminders: List[Dict[str, Any]] = []
        for sentence in re.split(r"[。！？\n;；]", text):
            sentence = sentence.strip()
            if not sentence:
                continue
            event_type = self._detect_event_type(sentence)
            if event_type is None:
                continue
            phrase_match = TIMESTAMP_PATTERN.search(sentence)
            phrase = phrase_match.group(0) if phrase_match else ""
            due = self._parse_due(phrase) if phrase else None
            title = (title_hint + " - " + sentence) if title_hint else sentence
            reminders.append({
                "title": title[:40],
                "event_type": event_type,
                "due_date": due.strftime("%Y-%m-%d") if due else None,
                "priority": self._priority(event_type, due),
                "channel": channel,
                "status": "pending" if due else "unparsed",
                "unparsed_text": "" if due else (phrase or sentence[:30]),
            })
        return reminders

    def _detect_event_type(self, sentence: str) -> Optional[str]:
        for event_type, keywords in EVENT_KEYWORDS.items():
            if any(keyword.lower() in sentence.lower() for keyword in keywords):
                return event_type
        return None

    def _parse_due(self, phrase: str) -> Optional[datetime]:
        """解析时间短语为日期；无法识别返回 None（不猜测）。"""
        phrase = phrase.strip()
        if not phrase:
            return None
        today = self.base_time.replace(hour=0, minute=0, second=0, microsecond=0)

        if phrase in ("今天", "明天", "后天", "大后天"):
            offsets = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
            return today + timedelta(days=offsets[phrase])

        match = re.fullmatch(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", phrase)
        if match:
            return self._safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        match = re.fullmatch(r"(\d{1,2})月(\d{1,2})[日号]", phrase)
        if match:
            return self._safe_date(today.year, int(match.group(1)), int(match.group(2)))

        match = re.fullmatch(r"([0-9一二三四五六七八九十两]+)\s*(天|周|星期)后", phrase)
        if match:
            amount = _cn_to_int(match.group(1))
            if amount is None:
                return None
            days = amount * 7 if match.group(2) in ("周", "星期") else amount
            return today + timedelta(days=days)

        match = re.fullmatch(r"下(?:个)?(?:周|星期|礼拜)([一二三四五六日天七])", phrase)
        if match:
            next_monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
            return next_monday + timedelta(days=WEEKDAY_MAP[match.group(1)])
        match = re.fullmatch(r"(?:本|这)(?:个)?(?:周|星期|礼拜)([一二三四五六日天七])", phrase)
        if match:
            this_monday = today - timedelta(days=today.weekday())
            return this_monday + timedelta(days=WEEKDAY_MAP[match.group(1)])
        match = re.fullmatch(r"(?:周|星期|礼拜)([一二三四五六日天七])", phrase)
        if match:
            this_monday = today - timedelta(days=today.weekday())
            return this_monday + timedelta(days=WEEKDAY_MAP[match.group(1)])

        match = re.fullmatch(r"(下)?个?月(?:底|末)", phrase)
        if match:
            month_offset = 1 if match.group(1) else 0
            year = today.year + (today.month - 1 + month_offset) // 12
            month = (today.month - 1 + month_offset) % 12 + 1
            return datetime(year, month, calendar.monthrange(year, month)[1])
        return None

    def _safe_date(self, year: int, month: int, day: int) -> Optional[datetime]:
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    def _priority(self, event_type: str, due: Optional[datetime]) -> str:
        fallback = {"deadline": "high", "exam": "high", "activity": "medium"}
        if due is None:
            return fallback.get(event_type, "medium")
        if event_type == "exam":
            return "high"
        days = (due.date() - self.base_time.date()).days
        if days <= 3:
            return "high"
        if days <= 7:
            return "medium"
        return "low"

    def _mock_reminders(self, channel: str) -> List[Dict[str, Any]]:
        today = self.base_time.replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            {
                "title": "第三章作业提交截止（模拟）",
                "event_type": "deadline",
                "due_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
                "priority": "high",
                "channel": channel,
                "status": "pending",
                "unparsed_text": "",
            },
            {
                "title": "高等数学期中考试（模拟）",
                "event_type": "exam",
                "due_date": (today + timedelta(days=9)).strftime("%Y-%m-%d"),
                "priority": "high",
                "channel": channel,
                "status": "pending",
                "unparsed_text": "",
            },
            {
                "title": "学院学术讲座（模拟）",
                "event_type": "activity",
                "due_date": None,
                "priority": "medium",
                "channel": channel,
                "status": "unparsed",
                "unparsed_text": "时间待定",
            },
        ]

    async def _push(self, reminder: Dict[str, Any]) -> None:
        """mock 不真实推送；真实模式需注入 notification，否则占位报错。"""
        if self.mock_mode:
            return
        if self.notification is None:
            raise NotImplementedError("真实模式的推送渠道待接入: %s" % reminder["channel"])
        await self.notification.send(reminder)
        reminder["status"] = "pushed"
