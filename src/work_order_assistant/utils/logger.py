"""
日志工具模块

支持 JSON 和文本格式输出
"""

import logging
import sys
from pathlib import Path
from typing import Optional
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器（简化版）"""

    def format(self, record: logging.LogRecord) -> str:
        # 简化时间戳：只保留时分秒
        timestamp = datetime.utcnow().strftime("%H:%M:%S")

        # 简化日志级别
        level_short = {
            "DEBUG": "DBG",
            "INFO": "INF",
            "WARNING": "WRN",
            "ERROR": "ERR",
            "CRITICAL": "CRT"
        }.get(record.levelname, record.levelname[:3])

        # 简化模块名（只保留最后一段）
        module_short = record.name.split('.')[-1]

        log_data = {
            "time": timestamp,
            "lvl": level_short,
            "msg": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, "task_id"):
            log_data["task"] = record.task_id

        # 添加异常信息（简化）
        if record.exc_info:
            log_data["error"] = str(record.exc_info[1])

        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """文本格式日志格式化器"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: str = "json",
) -> None:
    """
    配置全局日志系统

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，如果为 None 则只输出到控制台
        log_format: 日志格式 (json | text)
    """
    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 选择格式化器
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 设置第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器

    Args:
        name: 日志记录器名称，通常使用 __name__

    Returns:
        Logger 实例
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    日志适配器，用于添加上下文信息

    使用示例:
        logger = get_logger(__name__)
        context_logger = LoggerAdapter(logger, {"task_id": "task-123", "user": "user@example.com"})
        context_logger.info("Processing work order", extra={"operation": "query"})
    """

    def process(self, msg, kwargs):
        # 合并上下文和额外参数
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs
