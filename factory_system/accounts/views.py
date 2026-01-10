from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from .models import UserProfile, Permission


def login_view(request):
    """用户登录（调试模式：允许空密码）"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        if not username:
            messages.error(request, '请输入用户名')
            form = AuthenticationForm()
            return render(request, 'accounts/login.html', {'form': form})
        
        # 调试模式：如果密码为空，直接验证用户名
        if not password:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(username=username)
                # 空密码直接登录（仅用于调试）
                login(request, user)
                messages.success(request, f'欢迎回来，{user.username}！（调试模式：空密码登录）')
                return redirect('dashboard')
            except User.DoesNotExist:
                messages.error(request, '用户名不存在，请检查用户名是否正确')
            except Exception as e:
                messages.error(request, f'登录失败：{str(e)}')
        else:
            # 正常密码验证
            try:
                form = AuthenticationForm(request, data=request.POST)
                if form.is_valid():
                    user = authenticate(username=username, password=password)
                    if user is not None:
                        login(request, user)
                        messages.success(request, f'欢迎回来，{user.username}！')
                        return redirect('dashboard')
                    else:
                        messages.error(request, '用户名或密码错误')
                else:
                    # 检查是否是用户名不存在的问题
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    if not User.objects.filter(username=username).exists():
                        messages.error(request, '用户名不存在，请检查用户名是否正确')
                    else:
                        messages.error(request, '密码错误，请检查密码是否正确')
            except Exception as e:
                messages.error(request, f'登录失败：{str(e)}')
    else:
        form = AuthenticationForm()
    
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def dashboard(request):
    """仪表板 - 根据角色显示不同内容"""
    try:
        profile = request.user.profile
        role = profile.role
    except UserProfile.DoesNotExist:
        role = None
    
    context = {
        'role': role,
        'user': request.user,
    }
    
    # 根据角色加载不同的数据
    if role == 'ceo':
        # 总经理视图 - 数据驾驶舱
        from sales.models import SalesOrder
        from inventory.models import Inventory
        from production.models import ProductionTask
        from logistics.models import Shipment
        
        context.update({
            'total_orders': SalesOrder.objects.count(),
            'pending_orders': SalesOrder.objects.filter(status='pending').count(),
            'total_inventory_value': 0,  # 可以计算库存总价值
            'active_production_tasks': ProductionTask.objects.filter(status__in=['in_production', 'material_preparing']).count(),
            'pending_shipments': Shipment.objects.filter(status='pending').count(),
        })
    
    return render(request, 'accounts/dashboard.html', context)


def logout_view(request):
    """用户登出"""
    logout(request)
    messages.success(request, '您已成功退出登录')
    return redirect('login')


@login_required
def my_permissions(request):
    """查看我的权限"""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, '用户角色未设置')
        return redirect('dashboard')
    
    # 获取角色默认权限
    role_permissions = profile.get_role_default_permissions()
    role_permission_objs = Permission.objects.filter(code__in=role_permissions)
    
    # 获取额外配置的权限
    extra_permissions = profile.permissions.all()
    
    # 获取所有权限
    all_permissions = profile.get_all_permissions()
    
    context = {
        'profile': profile,
        'role_permissions': role_permission_objs,
        'extra_permissions': extra_permissions,
        'all_permissions': all_permissions,
    }
    
    return render(request, 'accounts/my_permissions.html', context)
