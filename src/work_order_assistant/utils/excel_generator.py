"""
Excel 生成工具
"""

from io import BytesIO
from typing import List, Dict, Any
import pandas as pd
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ExcelGenerator:
    """Excel 文件生成器"""

    @staticmethod
    def generate_from_query_result(
        columns: List[str], rows: List[List[Any]]
    ) -> bytes:
        """
        从查询结果生成 Excel 文件

        Args:
            columns: 列名列表
            rows: 数据行列表

        Returns:
            Excel 文件二进制内容
        """
        try:
            # 创建 DataFrame
            df = pd.DataFrame(rows, columns=columns)

            # 写入到 BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="查询结果")

            output.seek(0)
            excel_bytes = output.read()

            logger.info(
                f"生成 Excel: {len(rows)} 行, {len(columns)} 列"
            )

            return excel_bytes

        except Exception as e:
            logger.error(f"生成 Excel 失败: {e}")
            raise
