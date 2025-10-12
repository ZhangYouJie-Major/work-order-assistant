"""
FastAPI 应用入口

工单智能处理助手主应用
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from .api.routes import work_order_router
from .api.schemas.response import HealthCheckResponse, ServiceStatus
from .config import settings
from .utils.logger import setup_logging, get_logger

# 设置日志
setup_logging(
    log_level=settings.log.log_level,
    log_file=settings.log.log_file,
    log_format=settings.log.log_format,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info(
        f"启动 {settings.app.app_name} v{settings.app.app_version} "
        f"(环境: {settings.app.app_env})"
    )
    logger.info(f"LLM 提供商: {settings.llm.llm_provider}")

    yield

    # 关闭时执行
    logger.info(f"关闭 {settings.app.app_name}")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app.app_name,
    version=settings.app.app_version,
    description="基于 LangGraph 和 MCP 的智能工单处理系统",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "内部服务器错误",
            "data": {"error": str(exc)},
        },
    )


# 健康检查接口
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    健康检查接口

    检查各个服务的连接状态
    """
    # 简化处理，服务假设已连接
    # 实际应该分别测试 LLM、OSS、Email 服务
    llm_status = "connected"
    mcp_status = "connected"
    oss_status = "connected"
    email_status = "connected"

    return HealthCheckResponse(
        status="healthy",
        version=settings.app.app_version,
        timestamp=datetime.utcnow(),
        services=ServiceStatus(
            llm=llm_status, mcp=mcp_status, oss=oss_status, email=email_status
        ),
    )


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app.app_name,
        "version": settings.app.app_version,
        "status": "running",
        "docs": "/docs",
    }


# 注册路由
app.include_router(work_order_router)

# 如果直接运行此文件
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "work_order_assistant.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.app_env == "development",
    )
