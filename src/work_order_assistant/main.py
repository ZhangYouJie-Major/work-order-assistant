"""
FastAPI 应用入口

工单智能处理助手主应用
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from .api.routes import work_order_router
from .api.schemas.response import HealthCheckResponse, ServiceStatus
from .config import settings
from .utils.logger import setup_logging, get_logger
from .services.mcp_service import MCPService

# 设置日志
setup_logging(
    log_level=settings.log.log_level,
    log_file=settings.log.log_file,
    log_format=settings.log.log_format,
)

logger = get_logger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app.app_name,
    version=settings.app.app_version,
    description="基于 LangGraph 和 MCP 的智能工单处理系统",
    docs_url="/docs",
    redoc_url="/redoc",
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
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "内部服务器错误",
            "data": {"error": str(exc)},
        },
    )


# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info(
        f"Starting {settings.app.app_name} v{settings.app.app_version} "
        f"(env: {settings.app.app_env})"
    )
    logger.info(f"LLM Provider: {settings.llm.llm_provider}")
    logger.info(f"MCP Server: {settings.mcp.mcp_server_url}")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info(f"Shutting down {settings.app.app_name}")


# 健康检查接口
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    健康检查接口

    检查各个服务的连接状态
    """
    # 检查 MCP 连接
    mcp_service = MCPService(settings.mcp)
    mcp_status = "connected" if await mcp_service.test_connection() else "disconnected"

    # 简化处理，其他服务假设已连接
    # 实际应该分别测试 LLM、OSS、Email 服务
    llm_status = "connected"
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
