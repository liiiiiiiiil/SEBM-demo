from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*allowed_roles):
    """角色权限装饰器"""
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

