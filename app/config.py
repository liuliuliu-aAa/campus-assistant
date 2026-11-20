"""全局配置：mock 模式 / 真实大模型（通义千问 qwen-max）双模式。

切换方式
--------
1. 环境变量：MOCK_MODE=true|false
2. 或在部署/测试入口处直接改写模块级常量 MOCK_MODE

真实模式（MOCK_MODE=False）下必须提供 LLM_API_KEY，否则 validate_config() 会直接报错；
mock 模式（MOCK_MODE=True）不依赖任何外部服务与 API Key，可直接演示。
"""

import os

_TRUE_VALUES = ("1", "true", "yes", "on")


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量，未设置时返回 default。"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE_VALUES


# ---------------------------------------------------------------------------
# 模式开关
# MOCK_MODE = True  : 模拟大模型，不需要 API Key，演示用
# MOCK_MODE = False : 调用真实通义千问 qwen-max
# ---------------------------------------------------------------------------
MOCK_MODE = _env_bool("MOCK_MODE", True)

# ---------------------------------------------------------------------------
# 大模型配置
# ---------------------------------------------------------------------------
# 真实模式必填；也兼容 DashScope 官方的 DASHSCOPE_API_KEY
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))

# 真实模式默认 qwen-max；mock 模式使用占位模型名，不发起网络请求
LLM_MODEL = os.getenv("LLM_MODEL", "mock-qwen-max" if MOCK_MODE else "qwen-max")

# ---------------------------------------------------------------------------
# 依赖服务
# ---------------------------------------------------------------------------
# 向量数据库地址（host:port）：按申报书以 Milvus 为默认口径，Milvus 默认端口 19530。
# MVP 为 mock，不接真实向量库；生产可替换 Milvus / Qdrant 等实现。
VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "localhost:19530")

# Redis 连接串（任务队列 / 消息总线）
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ---------------------------------------------------------------------------
# 提醒推送
# ---------------------------------------------------------------------------
# 推送渠道：inapp（站内通知）/ email（邮件）/ webhook
NOTIFY_CHANNEL = os.getenv("NOTIFY_CHANNEL", "inapp")

# ---------------------------------------------------------------------------
# 运行参数
# ---------------------------------------------------------------------------
# 单任务最大重试次数
MAX_RETRY = int(os.getenv("MAX_RETRY", "3"))

# 单任务超时时间（秒）
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "30"))


def is_mock_mode() -> bool:
    """当前是否处于 mock（模拟大模型）模式。"""
    return MOCK_MODE


def validate_config() -> None:
    """校验当前模式下的必填配置，不合法时抛出 ValueError。"""
    if MOCK_MODE:
        return
    if not LLM_API_KEY:
        raise ValueError("MOCK_MODE=False 时必须配置 LLM_API_KEY（或 DASHSCOPE_API_KEY）")
    if not LLM_MODEL:
        raise ValueError("MOCK_MODE=False 时 LLM_MODEL 不能为空，默认应为 qwen-max")
    if MAX_RETRY < 0:
        raise ValueError("MAX_RETRY 不能为负数")
    if TASK_TIMEOUT <= 0:
        raise ValueError("TASK_TIMEOUT 必须大于 0")


def get_config() -> dict:
    """返回配置字典，供 BaseAgent 等后续模块以 config 参数注入。"""
    return {
        "mock_mode": MOCK_MODE,
        "llm_api_key": LLM_API_KEY,
        "llm_model": LLM_MODEL,
        "vector_db_host": VECTOR_DB_HOST,
        "redis_url": REDIS_URL,
        "notify_channel": NOTIFY_CHANNEL,
        "max_retry": MAX_RETRY,
        "task_timeout": TASK_TIMEOUT,
    }
