# -*- coding: utf-8 -*-
"""登录限流：进程内滑动窗口。

适用前提：本应用按单进程部署（uvicorn 单 worker / 容器单实例）。
状态存内存——重启清零、多 worker 不共享；横向扩容前需替换为 Redis 等共享存储。
"""
import logging
import threading
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        return [t for t in stamps if now - t < self.window_seconds]

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            stamps = self._prune(self._attempts.get(key, []), now)
            self._attempts[key] = stamps
            return len(stamps) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            stamps = self._prune(self._attempts.get(key, []), now) + [now]
            self._attempts[key] = stamps
            if len(stamps) >= self.max_attempts:
                logger.warning(
                    "登录限流已触发：key=%s（%ss 窗口内第 %s 次失败）",
                    key, self.window_seconds, len(stamps),
                )

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


login_limiter = LoginRateLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60,
)
