"""
阿里云 OSS 文件下载和解析服务
"""

import oss2
from io import BytesIO
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import pandas as pd
from ..config import OSSSettings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class OSSService:
    """阿里云 OSS 文件下载服务"""

    def __init__(self, settings: OSSSettings):
        """
        初始化 OSS 客户端

        Args:
            settings: OSS 配置
        """
        self.settings = settings
        auth = oss2.Auth(
            settings.aliyun_oss_access_key_id, settings.aliyun_oss_access_key_secret
        )
        self.bucket = oss2.Bucket(
            auth, settings.aliyun_oss_endpoint, settings.aliyun_oss_bucket_name
        )
        logger.info(
            f"OSS Service initialized: bucket={settings.aliyun_oss_bucket_name}, "
            f"endpoint={settings.aliyun_oss_endpoint}"
        )

    def download_file(self, object_key: str) -> bytes:
        """
        从 OSS 下载文件

        Args:
            object_key: OSS 对象键（文件路径）

        Returns:
            文件二进制内容

        Raises:
            Exception: 下载失败
        """
        try:
            logger.info(f"Downloading file from OSS: {object_key}")
            result = self.bucket.get_object(object_key)
            content = result.read()
            logger.info(f"File downloaded successfully: {len(content)} bytes")
            return content
        except Exception as e:
            logger.error(f"Failed to download file {object_key}: {e}")
            raise

    def download_from_url(self, url: str) -> bytes:
        """
        从完整 OSS URL 下载文件

        Args:
            url: 完整的 OSS URL，如
                https://bucket-name.oss-cn-hangzhou.aliyuncs.com/path/to/file.xlsx

        Returns:
            文件二进制内容
        """
        object_key = self._extract_object_key(url)
        return self.download_file(object_key)

    def parse_attachment(self, url: str, mime_type: str) -> Dict[str, Any]:
        """
        解析 OSS 附件内容

        支持格式:
        - .xlsx, .xls (Excel)
        - .csv (CSV)
        - .txt (文本)

        Args:
            url: OSS 文件 URL
            mime_type: MIME 类型

        Returns:
            解析后的结构化数据
        """
        logger.info(f"Parsing attachment: {url} (type: {mime_type})")

        try:
            content = self.download_from_url(url)

            # 检查文件大小
            max_size_bytes = self.settings.oss_max_file_size * 1024 * 1024
            if len(content) > max_size_bytes:
                raise ValueError(
                    f"File size ({len(content)} bytes) exceeds max limit "
                    f"({max_size_bytes} bytes)"
                )

            # 根据 MIME 类型解析
            if mime_type.endswith("spreadsheetml.sheet") or mime_type.endswith(
                "ms-excel"
            ):
                return self._parse_excel(content)
            elif mime_type == "text/csv":
                return self._parse_csv(content)
            elif mime_type == "text/plain":
                return {"raw": content.decode("utf-8")}
            else:
                logger.warning(f"Unsupported MIME type: {mime_type}, treating as text")
                return {"raw": content.decode("utf-8", errors="ignore")}

        except Exception as e:
            logger.error(f"Failed to parse attachment {url}: {e}")
            raise

    def _extract_object_key(self, url: str) -> str:
        """
        从完整 OSS URL 提取 object_key

        示例:
        https://my-bucket.oss-cn-hangzhou.aliyuncs.com/uploads/2025/file.xlsx
        -> uploads/2025/file.xlsx

        Args:
            url: 完整的 OSS URL

        Returns:
            object_key
        """
        parsed = urlparse(url)
        # 去掉开头的 /
        object_key = parsed.path.lstrip("/")
        logger.debug(f"Extracted object_key: {object_key} from URL: {url}")
        return object_key

    def _parse_excel(self, content: bytes) -> Dict[str, Any]:
        """
        解析 Excel 文件

        Args:
            content: 文件二进制内容

        Returns:
            解析后的数据
        """
        try:
            bio = BytesIO(content)
            df = pd.read_excel(bio, engine="openpyxl")

            result = {
                "columns": df.columns.tolist(),
                "rows": df.values.tolist(),
                "row_count": len(df),
                "preview": df.head(10).to_dict(
                    orient="records"
                ),  # 预览前10行
            }

            logger.info(f"Parsed Excel: {result['row_count']} rows, {len(result['columns'])} columns")
            return result

        except Exception as e:
            logger.error(f"Failed to parse Excel: {e}")
            raise ValueError(f"Failed to parse Excel file: {e}")

    def _parse_csv(self, content: bytes) -> Dict[str, Any]:
        """
        解析 CSV 文件

        Args:
            content: 文件二进制内容

        Returns:
            解析后的数据
        """
        try:
            bio = BytesIO(content)
            df = pd.read_csv(bio)

            result = {
                "columns": df.columns.tolist(),
                "rows": df.values.tolist(),
                "row_count": len(df),
                "preview": df.head(10).to_dict(orient="records"),
            }

            logger.info(f"Parsed CSV: {result['row_count']} rows, {len(result['columns'])} columns")
            return result

        except Exception as e:
            logger.error(f"Failed to parse CSV: {e}")
            raise ValueError(f"Failed to parse CSV file: {e}")

    def check_file_exists(self, object_key: str) -> bool:
        """
        检查文件是否存在

        Args:
            object_key: OSS 对象键

        Returns:
            文件是否存在
        """
        try:
            exists = self.bucket.object_exists(object_key)
            logger.debug(f"File exists check: {object_key} -> {exists}")
            return exists
        except Exception as e:
            logger.error(f"Failed to check file existence {object_key}: {e}")
            return False

    def get_file_meta(self, object_key: str) -> Dict[str, Any]:
        """
        获取文件元信息

        Args:
            object_key: OSS 对象键

        Returns:
            文件元信息
        """
        try:
            meta = self.bucket.get_object_meta(object_key)
            result = {
                "content_length": meta.headers.get("Content-Length"),
                "content_type": meta.headers.get("Content-Type"),
                "etag": meta.headers.get("ETag"),
                "last_modified": meta.headers.get("Last-Modified"),
            }
            logger.debug(f"File meta retrieved: {object_key} -> {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to get file meta {object_key}: {e}")
            raise
