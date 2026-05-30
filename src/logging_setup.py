"""统一日志系统

替换全项目中的 print() 调用, 提供:
  - 彩色控制台输出 (INFO/WARNING/ERROR)
  - 文件持久化 (DEBUG 级别, 自动轮转)
  - 模块级 logger 获取

用法:
  from src.logging_setup import get_logger
  logger = get_logger(__name__)
  logger.info("Processing event %s", event_id)
  logger.debug("Edge count: %d", count)
  logger.warning("No images found for post %s", post_id)
  logger.error("Failed to download: %s", url)
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════

_initialized = False
_LOG_DIR = None
_LOG_FILE = None


def setup_logging(log_dir: str = "data/logs",
                  level: int = logging.INFO,
                  file_level: int = logging.DEBUG):
    """初始化日志系统 (幂等, 仅首次调用生效)。

    Parameters
    ----------
    log_dir: 日志文件目录
    level: 控制台日志级别
    file_level: 文件日志级别
    """
    global _initialized, _LOG_DIR, _LOG_FILE
    if _initialized:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    _LOG_DIR = str(log_path)
    _LOG_FILE = str(log_path / f"pipeline_{datetime.now():%Y%m%d}.log")

    # ── Root logger ──────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # 允许所有级别通过, handler 各自过滤

    # ── Console handler (INFO+) ──────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    # ── File handler (DEBUG+) ────────────────────────────────
    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    _initialized = True

    # 首条日志
    logger = logging.getLogger("bdma")
    logger.info("Logging initialized — console=%s, file=%s",
                logging.getLevelName(level),
                logging.getLevelName(file_level))


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger (首次调用自动初始化日志系统)"""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)


class _ConsoleFormatter(logging.Formatter):
    """彩色控制台格式化器"""

    COLORS = {
        "DEBUG":    "\033[90m",   # grey
        "INFO":     "\033[36m",   # cyan
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        # 简化的单行格式
        prefix = f"{color}[{record.name}]{self.RESET}" if record.name != "root" else ""
        msg = super().format(record)
        return f"{prefix} {color}{record.levelname:<7}{self.RESET} {record.getMessage()}"
