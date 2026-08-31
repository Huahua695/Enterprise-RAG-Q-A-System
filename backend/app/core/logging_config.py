# -*- coding: utf-8 -*-
"""应用日志配置：控制台 + 滚动文件（db_data/logs/app.log），main.py 启动时初始化一次。"""
import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"

# 三方库默认日志很吵，统一压到 WARNING（jieba 会把自身 logger 设为 DEBUG）
_NOISY_LOGGERS = ("urllib3", "httpx", "httpcore", "openai", "langchain", "faiss", "charset_normalizer", "jieba")

_configured = False


def setup_logging() -> None:
    """初始化根 logger（幂等，可安全多次调用）。"""
    global _configured
    if _configured:
        return

    level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(settings.LOG_DIR, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
