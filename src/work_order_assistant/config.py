"""
配置管理模块

使用 Pydantic Settings 管理环境变量配置
"""

import os
from typing import List, Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 在所有配置类之前加载 .env 到 os.environ
# 这样 LangSmith 等第三方库可以直接从 os.environ 读取配置
load_dotenv()


class AppSettings(BaseSettings):
    """应用基础配置"""

    app_name: str = Field(default="work-order-assistant", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    app_env: Literal["development", "staging", "production"] = Field(
        default="production", alias="APP_ENV"
    )
    api_key: Optional[str] = Field(default=None, alias="API_KEY")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class LLMSettings(BaseSettings):
    """LLM 配置"""

    llm_provider: Literal["openai", "azure", "anthropic"] = Field(
        default="openai", alias="LLM_PROVIDER"
    )
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    openai_model: str = Field(default="gpt-4", alias="OPENAI_MODEL")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class MySQLSettings(BaseSettings):
    """MySQL 数据库配置"""

    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(..., alias="MYSQL_USER")
    mysql_password: str = Field(..., alias="MYSQL_PASSWORD")
    mysql_database: str = Field(..., alias="MYSQL_DATABASE")
    mysql_charset: str = Field(default="utf8mb4", alias="MYSQL_CHARSET")
    mysql_connection_timeout: int = Field(default=30, alias="MYSQL_CONNECTION_TIMEOUT")
    mysql_max_retries: int = Field(default=3, alias="MYSQL_MAX_RETRIES")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class OSSSettings(BaseSettings):
    """阿里云 OSS 配置"""

    aliyun_oss_access_key_id: str = Field(..., alias="ALIYUN_OSS_ACCESS_KEY_ID")
    aliyun_oss_access_key_secret: str = Field(..., alias="ALIYUN_OSS_ACCESS_KEY_SECRET")
    aliyun_oss_endpoint: str = Field(..., alias="ALIYUN_OSS_ENDPOINT")
    aliyun_oss_bucket_name: str = Field(..., alias="ALIYUN_OSS_BUCKET_NAME")
    oss_download_timeout: int = Field(default=30, alias="OSS_DOWNLOAD_TIMEOUT")
    oss_max_file_size: int = Field(default=50, alias="OSS_MAX_FILE_SIZE")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class EmailSettings(BaseSettings):
    """邮件配置"""

    smtp_host: str = Field(..., alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_user: str = Field(..., alias="SMTP_USER")
    smtp_password: str = Field(..., alias="SMTP_PASSWORD")
    smtp_from: str = Field(..., alias="SMTP_FROM")
    email_ops_team: str = Field(..., alias="EMAIL_OPS_TEAM")
    email_dev_team: Optional[str] = Field(default=None, alias="EMAIL_DEV_TEAM")

    @field_validator("email_ops_team")
    @classmethod
    def parse_ops_team_emails(cls, v: str) -> List[str]:
        """解析运维团队邮箱列表"""
        return [email.strip() for email in v.split(",") if email.strip()]

    @field_validator("email_dev_team")
    @classmethod
    def parse_dev_team_emails(cls, v: Optional[str]) -> List[str]:
        """解析开发团队邮箱列表"""
        if not v:
            return []
        return [email.strip() for email in v.split(",") if email.strip()]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class AsyncTaskSettings(BaseSettings):
    """异步任务配置"""

    use_celery: bool = Field(default=False, alias="USE_CELERY")
    celery_broker_url: Optional[str] = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: Optional[str] = Field(
        default=None, alias="CELERY_RESULT_BACKEND"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class LogSettings(BaseSettings):
    """日志配置"""

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", alias="LOG_FILE")
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class WorkflowSettings(BaseSettings):
    """工作流配置"""

    langgraph_checkpointer: Literal["memory", "sqlite", "postgres"] = Field(
        default="memory", alias="LANGGRAPH_CHECKPOINTER"
    )
    langgraph_db_path: str = Field(
        default="data/checkpoints.db", alias="LANGGRAPH_DB_PATH"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class ResourceSettings(BaseSettings):
    """资源路径配置"""

    prompts_dir: str = Field(
        default="resources/prompts", alias="PROMPTS_DIR"
    )
    mutation_steps_dir: str = Field(
        default="resources/configs/mutation_steps", alias="MUTATION_STEPS_DIR"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class Settings:
    """全局配置管理器"""

    def __init__(self):
        self.app = AppSettings()
        self.llm = LLMSettings()
        self.mysql = MySQLSettings()
        self.oss = OSSSettings()
        self.email = EmailSettings()
        self.async_task = AsyncTaskSettings()
        self.log = LogSettings()
        self.workflow = WorkflowSettings()
        self.resource = ResourceSettings()


# 全局配置实例
settings = Settings()
