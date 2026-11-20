"""日志工具：结构化单行 JSON 日志（可被日志采集直接解析）。"""

import json
import logging
from typing import Any

from app.utils.time_utils import utc_now_iso


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO,
              **fields: Any) -> None:
    payload = {"event": event, "timestamp": utc_now_iso()}
    payload.update(fields)
    logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
