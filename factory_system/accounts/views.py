from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from .models import UserProfile


def login_view(request):
    """用户登录"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'欢迎回来，{user.username}！')
                return redirect('dashboard')
            else:
                messages.error(request, '用户名或密码错误')
        else:
            messages.error(request, '请检查输入信息')
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
