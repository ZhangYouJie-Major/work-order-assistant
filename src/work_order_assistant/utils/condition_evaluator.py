"""
条件表达式求值器

支持在 mutation steps 中使用条件表达式进行分支判断
"""

import re
from typing import Dict, Any, Optional
from .logger import get_logger

logger = get_logger(__name__)


class ConditionEvaluator:
    """条件表达式求值器"""

    @staticmethod
    def evaluate(expression: str, context: Dict[str, Any]) -> bool:
        """
        求值条件表达式

        支持的运算符：
        - 比较: ==, !=, >, <, >=, <=
        - 成员: in, not in
        - 逻辑: and, or, not
        - 特殊值: null, true, false

        示例：
        - {status} == '10'
        - {marine_order_id} != null
        - {status} in ['10', '11', '12']
        - {amount} > 100 and {status} == 'active'

        Args:
            expression: 条件表达式
            context: 变量上下文

        Returns:
            布尔值结果
        """
        if not expression or expression.strip() == "":
            logger.warning("空的条件表达式，默认返回 True")
            return True

        try:
            # 替换变量
            replaced_expr = ConditionEvaluator._replace_variables(expression, context)
            logger.debug(f"条件表达式: {expression} -> {replaced_expr}")

            # 求值
            result = ConditionEvaluator._safe_eval(replaced_expr)
            logger.debug(f"条件求值结果: {result}")

            return bool(result)

        except Exception as e:
            logger.error(f"条件表达式求值失败: {expression}, 错误: {e}")
            return False

    @staticmethod
    def _replace_variables(expression: str, context: Dict[str, Any]) -> str:
        """
        替换表达式中的变量

        Args:
            expression: 表达式字符串
            context: 变量上下文

        Returns:
            替换后的表达式
        """
        def replace_fn(match):
            var_name = match.group(1)
            value = context.get(var_name)

            if value is None:
                # 返回 None 字面量
                return "None"

            # 根据类型转换
            if isinstance(value, str):
                # 转义单引号
                escaped = value.replace("'", "\\'")
                return f"'{escaped}'"
            elif isinstance(value, bool):
                return str(value)
            elif isinstance(value, (int, float)):
                return str(value)
            else:
                # 其他类型转为字符串
                return f"'{str(value)}'"

        # 匹配 {variable_name} 格式
        result = re.sub(r'\{(\w+)\}', replace_fn, expression)

        # 替换特殊关键字
        result = result.replace("null", "None")
        result = result.replace("true", "True")
        result = result.replace("false", "False")

        return result

    @staticmethod
    def _safe_eval(expression: str) -> Any:
        """
        安全地求值表达式

        使用受限的命名空间，防止执行危险代码

        Args:
            expression: 表达式字符串

        Returns:
            求值结果
        """
        # 定义安全的命名空间
        safe_dict = {
            "__builtins__": {},
            "True": True,
            "False": False,
            "None": None,
        }

        # 检查表达式是否包含危险关键字
        dangerous_keywords = [
            "import", "exec", "eval", "compile", "open", "file",
            "__", "lambda", "def", "class", "yield", "del"
        ]

        for keyword in dangerous_keywords:
            if keyword in expression:
                raise ValueError(f"表达式包含不允许的关键字: {keyword}")

        # 求值
        try:
            result = eval(expression, safe_dict, {})
            return result
        except Exception as e:
            logger.error(f"表达式求值失败: {expression}, 错误: {e}")
            raise


def evaluate_condition(expression: str, context: Dict[str, Any]) -> bool:
    """
    便捷函数：求值条件表达式

    Args:
        expression: 条件表达式
        context: 变量上下文

    Returns:
        布尔值结果
    """
    return ConditionEvaluator.evaluate(expression, context)
