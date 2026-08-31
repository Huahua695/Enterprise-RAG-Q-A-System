# -*- coding: utf-8 -*-
"""登录限流：失败计数持久化到 SQLite（login_failures 表）。

重启不丢、多 worker 共享；窗口起点为首次失败时间，达到阈值后锁定至窗口
结束，到期记录在下次访问时惰性清理。SQLite 自身锁保证写串行，极端并发下
最坏多记一次失败，不影响防线；横向扩容到多机时再替换为 Redis 等共享存储。
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import LoginFailure

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """当前 UTC 时间（naive），与 login_failures 的 naive UTC 存储约定一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _load_fresh(self, db: Session, key: str) -> LoginFailure | None:
        """取该 key 的记录；窗口或锁定已过期则删除并视为无记录。"""
        record = db.get(LoginFailure, key)
        if record is None:
            return None
        now = _utcnow_naive()
        if record.locked_until is not None:
            expired = now >= record.locked_until
        else:
            expired = now - record.first_failure_at >= timedelta(seconds=self.window_seconds)
        if expired:
            db.delete(record)
            db.commit()
            return None
        return record

    def is_blocked(self, db: Session, key: str) -> bool:
        record = self._load_fresh(db, key)
        if record is None:
            return False
        if record.locked_until is not None:
            return True
        return record.failure_count >= self.max_attempts

    def record_failure(self, db: Session, key: str) -> None:
        record = self._load_fresh(db, key)
        if record is None:
            record = LoginFailure(key=key, failure_count=1, first_failure_at=_utcnow_naive())
            db.add(record)
        else:
            record.failure_count += 1
        if record.failure_count >= self.max_attempts:
            record.locked_until = record.first_failure_at + timedelta(seconds=self.window_seconds)
            logger.warning(
                "登录限流已触发：key=%s（%ss 窗口内第 %s 次失败，锁定至 %s）",
                key, self.window_seconds, record.failure_count, record.locked_until,
            )
        db.commit()

    def reset(self, db: Session, key: str) -> None:
        record = db.get(LoginFailure, key)
        if record is not None:
            db.delete(record)
            db.commit()


login_limiter = LoginRateLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60,
)
