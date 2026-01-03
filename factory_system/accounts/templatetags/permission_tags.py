from django import template

register = template.Library()


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

