"""
LangGraph CLI 入口文件

这个文件导出工作流图供 LangGraph CLI 和 LangSmith Studio 使用
运行方式: langgraph dev
"""

from .workflows.work_order_workflow import create_work_order_workflow
from .utils.logger import setup_logging, get_logger
from .config import settings

# 设置日志
setup_logging(
    log_level=settings.log.log_level,
    log_file=settings.log.log_file,
    log_format=settings.log.log_format,
)

logger = get_logger(__name__)

# 创建并导出工作流图
# LangGraph CLI 会查找名为 'graph' 的变量
graph = create_work_order_workflow()

logger.info("工作流图已创建并导出供 LangGraph CLI 使用")
