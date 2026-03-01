# 数值显示规则：有小数时最多精确到 4 位，整数不补零
from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def num(value, max_decimals=4):
    """
    格式化数值显示：
    - 若为整数或小数部分为 0：不补零（如 10、100）
    - 若有小数：最多显示 max_decimals 位，并去掉尾部多余的 0（如 1.5、3.25、0.1234）
    用法：{{ value|num }} 或 {{ value|num:2 }}（最多 2 位小数）
    """
    if value is None:
        return ''
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    try:
        max_d = int(max_decimals)
        if max_d < 0:
            max_d = 4
    except (TypeError, ValueError):
        max_d = 4
    d = round(d, max_d)
    if d == d.to_integral_value():
        return str(int(d))
    s = format(d, f'.{max_d}f').rstrip('0').rstrip('.')
    return s
