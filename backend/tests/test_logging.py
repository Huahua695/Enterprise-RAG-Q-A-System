# -*- coding: utf-8 -*-
"""日志体系测试：setup_logging 幂等、滚动文件落盘、级别配置可读。"""
import logging
import os

import pytest

from app.core.config import settings
from app.core.logging_config import setup_logging


@pytest.fixture(scope="module", autouse=True)
def _logging_env(tmp_path_factory):
    """模块内只初始化一次日志（setup_logging 有全局幂等守卫），统一指向临时目录。"""
    log_dir = tmp_path_factory.mktemp("logs")
    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "LOG_DIR", str(log_dir))
    setup_logging()
    yield log_dir
    mp.undo()


def test_setup_logging_idempotent():
    root = logging.getLogger()
    count_first = len(root.handlers)
    assert count_first >= 2  # 控制台 + 滚动文件

    setup_logging()
    assert len(root.handlers) == count_first  # 重复调用不叠加 handler


def test_log_file_created(_logging_env):
    logging.getLogger("test.probe").info("写入探测日志")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert os.path.exists(os.path.join(str(_logging_env), "app.log"))


def test_log_level_default_readable():
    level = getattr(logging, settings.LOG_LEVEL.upper(), None)
    assert isinstance(level, int)  # 默认 INFO 可被 logging 模块解析
