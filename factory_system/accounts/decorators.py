from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*allowed_roles):
    """角色权限装饰器（兼容旧代码）"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, '请先登录')
                return redirect('login')
            
            try:
                user_role = request.user.profile.role
            except:
                messages.error(request, '用户角色未设置')
                return redirect('login')
            
            if user_role not in allowed_roles and 'ceo' not in allowed_roles:
                # CEO可以访问所有页面
                if user_role != 'ceo':
                    messages.error(request, '您没有权限访问此页面')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def permission_required(permission_code):
    """权限装饰器 - 检查用户是否有指定权限"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, '请先登录')
                return redirect('login')
            
            try:
                profile = request.user.profile
                if not profile.has_permission(permission_code):
                    messages.error(request, '您没有权限访问此页面')
                    return redirect('dashboard')
            except AttributeError:
                messages.error(request, '用户角色未设置')
                return redirect('login')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def role_or_permission_required(*allowed_roles, permission_code=None):
    """角色或权限装饰器 - 满足角色要求或拥有指定权限即可访问"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, '请先登录')
                return redirect('login')
            
            try:
                profile = request.user.profile
                user_role = profile.role
                
                # 检查角色
                if user_role in allowed_roles or user_role == 'ceo':
                    return view_func(request, *args, **kwargs)
                
                # 检查权限
                if permission_code and profile.has_permission(permission_code):
                    return view_func(request, *args, **kwargs)
                
                messages.error(request, '您没有权限访问此页面')
                return redirect('dashboard')
            except AttributeError:
                messages.error(request, '用户角色未设置')
                return redirect('login')
            
        return wrapped_view
    return decorator

