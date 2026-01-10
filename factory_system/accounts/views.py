import traceback
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from .models import UserProfile, Permission


def login_view(request):
    """用户登录（调试模式：允许空密码）"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # 初始化 form 变量，确保在所有代码路径中都有定义
    form = AuthenticationForm()
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        if not username:
            messages.error(request, '请输入用户名')
            return render(request, 'accounts/login.html', {'form': form})
        
        # 先检查用户名是否存在，避免后续处理中的异常
        try:
            user_exists = User.objects.filter(username=username).exists()
        except Exception as e:
            messages.error(request, f'系统错误：无法验证用户名 - {str(e)}')
            return render(request, 'accounts/login.html', {'form': form})
        
        # 调试模式：如果密码为空，直接验证用户名
        if not password:
            try:
                if not user_exists:
                    messages.error(request, '用户名不存在，请检查用户名是否正确')
                    return render(request, 'accounts/login.html', {'form': form})
                else:
                    user = User.objects.get(username=username)
                    # 空密码直接登录（仅用于调试）
                    login(request, user)
                    messages.success(request, f'欢迎回来，{user.username}！（调试模式：空密码登录）')
                    return redirect('dashboard')
            except User.DoesNotExist:
                messages.error(request, '用户名不存在，请检查用户名是否正确')
                return render(request, 'accounts/login.html', {'form': form})
            except Exception as e:
                messages.error(request, f'登录失败：{str(e)}')
                return render(request, 'accounts/login.html', {'form': form})
        else:
            # 正常密码验证
            try:
                # 如果用户名不存在，直接提示，避免 AuthenticationForm 可能的异常
                if not user_exists:
                    messages.error(request, '用户名不存在，请检查用户名是否正确')
                    return render(request, 'accounts/login.html', {'form': form})
                else:
                    # 用户名存在，使用 AuthenticationForm 进行验证
                    form = AuthenticationForm(request, data=request.POST)
                    if form.is_valid():
                        user = authenticate(username=username, password=password)
                        if user is not None:
                            login(request, user)
                            messages.success(request, f'欢迎回来，{user.username}！')
                            return redirect('dashboard')
                        else:
                            messages.error(request, '密码错误，请检查密码是否正确')
                    else:
                        # 表单验证失败，可能是密码错误或其他原因
                        # 由于我们已经检查了用户名存在，这里主要是密码错误
                        messages.error(request, '密码错误，请检查密码是否正确')
            except Exception as e:
                # 捕获所有可能的异常，避免程序崩溃
                messages.error(request, f'登录失败：{str(e)}')
                # 在调试模式下，可以记录详细错误信息
                if settings.DEBUG:
                    print(f"登录错误详情: {traceback.format_exc()}")
                # 重新创建 form，避免使用可能出错的 form
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
        from sales.models import SalesOrder, ShippingNotice
        from inventory.models import Inventory
        from production.models import ProductionTask
        from logistics.models import Shipment
        
        context.update({
            'total_orders': SalesOrder.objects.count(),
            # 待审批订单：总经理应该看到待总经理审批的订单
            'pending_orders': SalesOrder.objects.filter(status='ceo_pending').count(),
            'total_inventory_value': 0,  # 可以计算库存总价值
            # 生产中的任务：包括已接收、备料中、生产中、质检中等状态
            'active_production_tasks': ProductionTask.objects.filter(
                status__in=['received', 'material_preparing', 'in_production', 'qc_checking']
            ).count(),
            # 待发货：包括待发货状态的发货单和发货通知单
            'pending_shipments': Shipment.objects.filter(status='pending').count() + 
                                 ShippingNotice.objects.filter(status='pending').count(),
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
