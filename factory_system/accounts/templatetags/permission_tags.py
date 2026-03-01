# 数值显示规则：有小数时最多精确到 4 位，整数不补零
from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def num(value, max_decimals=4):
    """
    格式化数值显示：整数不补零，有小数时最多 max_decimals 位并去掉尾零。
    用法：{{ value|num }} 或 {{ value|num:1 }}
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
    return format(d, f'.{max_d}f').rstrip('0').rstrip('.')


@register.filter
def has_permission(user, permission_code):
    """检查用户是否有指定权限"""
    if not user or not user.is_authenticated:
        return False
    
    try:
        profile = user.profile
        return profile.has_permission(permission_code)
    except AttributeError:
        return False


@register.simple_tag
def check_permission(user, permission_code):
    """检查用户是否有指定权限（标签形式）"""
    if not user or not user.is_authenticated:
        return False
    
    try:
        profile = user.profile
        return profile.has_permission(permission_code)
    except AttributeError:
        return False


@register.simple_tag
def has_any_permission(user, *permission_codes):
    """检查用户是否有任意一个权限"""
    if not user or not user.is_authenticated:
        return False
    
    try:
        profile = user.profile
        for code in permission_codes:
            if profile.has_permission(code):
                return True
        return False
    except AttributeError:
        return False


@register.filter
def get_item(dictionary, key):
    """从字典中获取值"""
    if dictionary is None:
        return None
    return dictionary.get(key)

