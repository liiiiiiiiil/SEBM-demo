import traceback
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.db import models
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
    from django.utils import timezone
    from datetime import timedelta, date
    from decimal import Decimal
    from sales.models import SalesOrder, ShippingNotice
    from inventory.models import Inventory, Material, Product, BOM, StockTransaction
    from production.models import ProductionTask, MaterialRequisition
    from logistics.models import Shipment
    
    try:
        profile = request.user.profile
        role = profile.role
    except UserProfile.DoesNotExist:
        role = None
    
    context = {
        'role': role,
        'user': request.user,
    }
    
    today = timezone.now().date()
    # 临近交期天数配置（默认7天）
    near_delivery_days = 7
    # 呆滞库存天数配置（默认90天）
    idle_inventory_days = 90
    # 长时间未推进天数配置（默认48小时，转换为天数）
    no_progress_days = 2
    
    # 检查权限
    try:
        profile = request.user.profile
        has_sales_permission = (role in ['sales', 'sales_mgr', 'ceo'] or 
                               profile.has_permission('sales.order.view'))
        has_production_permission = (role in ['production', 'ceo'] or 
                                    profile.has_permission('production.task.view'))
        has_inventory_permission = (role in ['warehouse', 'ceo'] or 
                                   profile.has_permission('inventory.view'))
        has_logistics_permission = (role in ['logistics', 'ceo'] or 
                                   profile.has_permission('logistics.shipment.view'))
    except:
        has_sales_permission = (role in ['sales', 'sales_mgr', 'ceo'])
        has_production_permission = (role in ['production', 'ceo'])
        has_inventory_permission = (role in ['warehouse', 'ceo'])
        has_logistics_permission = (role in ['logistics', 'ceo'])
    
    has_ceo_permission = (role == 'ceo')
    
    # 获取时间范围参数（用于订单和采购态势）
    date_from = request.GET.get('date_from', None)
    date_to = request.GET.get('date_to', None)
    salesperson_filter = request.GET.get('salesperson', None)
    customer_filter = request.GET.get('customer', None)
    
    # 一、订单态势
    if has_sales_permission:
        orders = SalesOrder.objects.all()
        
        # 应用筛选
        if date_from:
            orders = orders.filter(created_at__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__lte=date_to)
        if salesperson_filter:
            orders = orders.filter(salesperson_id=salesperson_filter)
        if customer_filter:
            orders = orders.filter(customer_id=customer_filter)
        
        # 1. 订单总数（不包括已终结订单）
        total_orders = orders.exclude(status='terminated').count()
        
        # 2. 订单总金额（不包括已终结订单）
        total_order_amount = orders.exclude(status='terminated').aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')
        
        # 3. 待审批订单数
        pending_approval_orders = orders.filter(status='pending').count()
        
        # 4. 本期新增订单数（默认本月）
        if not date_from:
            month_start = today.replace(day=1)
            new_orders = orders.filter(created_at__gte=month_start).count()
        else:
            new_orders = orders.filter(created_at__gte=date_from).count()
        
        # 5. 临近交期订单数（未来N天内）
        near_delivery_date = today + timedelta(days=near_delivery_days)
        near_delivery_orders = orders.filter(
            delivery_date__gte=today,
            delivery_date__lte=near_delivery_date,
            status__in=['in_production', 'ready_to_ship']
        ).count()
        
        # 6. 已逾期未交付订单数
        overdue_orders = orders.filter(
            delivery_date__lt=today,
            status__in=['pending', 'approved', 'ceo_pending', 'ceo_approved', 'in_production', 'ready_to_ship']
        ).count()
        
        context['order_status'] = {
            'total_orders': total_orders,
            'total_order_amount': total_order_amount,
            'pending_approval_orders': pending_approval_orders,
            'new_orders': new_orders,
            'near_delivery_orders': near_delivery_orders,
            'overdue_orders': overdue_orders,
        }
    
    # 二、生产态势
    if has_production_permission:
        # 1. 生产任务总数
        total_tasks = ProductionTask.objects.count()
        
        # 2. 进行中生产任务数
        active_tasks = ProductionTask.objects.filter(
            status__in=['received', 'material_preparing', 'in_production', 'qc_checking']
        ).count()
        
        # 3. 已延期生产任务数
        overdue_tasks = ProductionTask.objects.filter(
            planned_completion_date__lt=today,
            status__in=['received', 'material_preparing', 'in_production', 'qc_checking']
        ).count()
        
        context['production_status'] = {
            'total_tasks': total_tasks,
            'active_tasks': active_tasks,
            'overdue_tasks': overdue_tasks,
        }
    
    # 三、库存态势
    if has_inventory_permission:
        # 1. 库存物料总数
        total_materials = Inventory.objects.filter(inventory_type='material').count()
        
        # 2. 库存总数量
        total_quantity = Inventory.objects.aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')
        
        # 3. 库存总金额（需要计算，这里简化处理）
        total_inventory_value = Decimal('0')
        for inv in Inventory.objects.all():
            if inv.inventory_type == 'material' and inv.material:
                total_inventory_value += inv.quantity * inv.material.unit_price
            elif inv.inventory_type == 'product' and inv.product:
                # 成品库存价值可以用售价或成本价计算，这里用售价
                total_inventory_value += inv.quantity * inv.product.sale_price
        
        # 4. 低于安全库存物料数
        low_stock_materials = 0
        for inv in Inventory.objects.filter(inventory_type='material'):
            if inv.check_safety_stock():
                low_stock_materials += 1
        
        # 5. 缺料物料数（需要检查已排产任务的需求）
        shortage_materials = set()
        active_requisitions = MaterialRequisition.objects.filter(
            status__in=['pending', 'approved']
        )
        for req in active_requisitions:
            for item in req.items.all():
                try:
                    inv = Inventory.objects.get(
                        inventory_type='material',
                        material=item.material
                    )
                    if inv.quantity < item.required_quantity:
                        shortage_materials.add(item.material.id)
                except Inventory.DoesNotExist:
                    shortage_materials.add(item.material.id)
        
        # 6. 呆滞库存物料数（90天无出入库记录）
        idle_date = today - timedelta(days=idle_inventory_days)
        idle_materials = []
        idle_value = Decimal('0')
        for inv in Inventory.objects.filter(inventory_type='material'):
            last_transaction = StockTransaction.objects.filter(
                inventory=inv
            ).order_by('-created_at').first()
            if not last_transaction or last_transaction.created_at.date() < idle_date:
                idle_materials.append(inv.id)
                if inv.material:
                    idle_value += inv.quantity * inv.material.unit_price
        
        context['inventory_status'] = {
            'total_materials': total_materials,
            'total_quantity': total_quantity,
            'total_inventory_value': total_inventory_value,
            'low_stock_materials': low_stock_materials,
            'shortage_materials': len(shortage_materials),
            'idle_materials': len(idle_materials),
            'idle_value': idle_value,
        }
    
    # 四、采购态势（库存管理员和总经理）
    has_purchase_permission = (role in ['warehouse', 'ceo'])
    if has_purchase_permission:
        try:
            from purchase.models import PurchaseTask
            
            # 1. 采购任务数量
            total_purchase_tasks = PurchaseTask.objects.count()
            
            # 2. 采购总金额
            total_purchase_amount = PurchaseTask.objects.aggregate(
                total=models.Sum('total_amount')
            )['total'] or Decimal('0')
            
            # 3. 本期采购金额（默认本月）
            if not date_from:
                from datetime import date
                month_start = date.today().replace(day=1)
                current_month_purchases = PurchaseTask.objects.filter(created_at__date__gte=month_start)
            else:
                current_month_purchases = PurchaseTask.objects.filter(created_at__gte=date_from)
            current_month_amount = current_month_purchases.aggregate(
                total=models.Sum('total_amount')
            )['total'] or Decimal('0')
            
            context['purchase_status'] = {
                'total_tasks': total_purchase_tasks,
                'total_amount': total_purchase_amount,
                'current_month_amount': current_month_amount,
            }
        except ImportError:
            # 如果purchase应用还未迁移，跳过
            pass
    
    # 五、物流态势
    if has_logistics_permission:
        # 1. 待发货订单数
        pending_ship_orders = SalesOrder.objects.filter(
            status='ready_to_ship'
        ).count()
        
        # 2. 今日待发货订单数（简化处理，使用ready_to_ship状态）
        today_pending_ship = pending_ship_orders  # 简化：实际应该根据计划发货日期
        
        # 3. 已发货未签收订单数
        shipped_not_delivered = Shipment.objects.filter(
            status='shipped'
        ).count()
        
        # 4. 逾期未发货订单数
        overdue_ship_orders = SalesOrder.objects.filter(
            delivery_date__lt=today,
            status__in=['ready_to_ship']
        ).count()
        
        context['logistics_status'] = {
            'pending_ship_orders': pending_ship_orders,
            'today_pending_ship': today_pending_ship,
            'shipped_not_delivered': shipped_not_delivered,
            'overdue_ship_orders': overdue_ship_orders,
        }
    
    # 六、异常预警（仅总经理）
    if has_ceo_permission:
        alerts = []
        
        # 1. 订单交期冲突预警（简化：检查临近交期但未完成生产的订单）
        conflict_orders = SalesOrder.objects.filter(
            delivery_date__lte=today + timedelta(days=near_delivery_days),
            delivery_date__gte=today,
            status__in=['in_production']
        )
        for order in conflict_orders:
            tasks = order.production_tasks.filter(
                status__in=['pending', 'received', 'material_preparing', 'in_production', 'qc_checking']
            )
            if tasks.exists():
                alerts.append({
                    'type': 'order_delivery_conflict',
                    'message': f'订单 {order.order_no} 交期临近但生产未完成',
                    'level': 'warning',
                })
        
        # 2. 临期未排产订单数
        near_unplanned = SalesOrder.objects.filter(
            delivery_date__lte=today + timedelta(days=near_delivery_days),
            delivery_date__gte=today,
            production_tasks__isnull=True,
            status__in=['ceo_approved']
        ).distinct().count()
        if near_unplanned > 0:
            alerts.append({
                'type': 'near_unplanned_orders',
                'count': near_unplanned,
                'message': f'有 {near_unplanned} 个临期订单未排产',
                'level': 'danger',
            })
        
        # 3. 已逾期未交付订单数（已在订单态势中计算）
        if context.get('order_status', {}).get('overdue_orders', 0) > 0:
            alerts.append({
                'type': 'overdue_orders',
                'count': context['order_status']['overdue_orders'],
                'message': f'有 {context["order_status"]["overdue_orders"]} 个订单已逾期未交付',
                'level': 'danger',
            })
        
        # 5. 生产任务延期预警
        if context.get('production_status', {}).get('overdue_tasks', 0) > 0:
            alerts.append({
                'type': 'overdue_tasks',
                'count': context['production_status']['overdue_tasks'],
                'message': f'有 {context["production_status"]["overdue_tasks"]} 个生产任务已延期',
                'level': 'warning',
            })
        
        # 6. 生产任务长时间未推进
        no_progress_date = today - timedelta(days=no_progress_days)
        no_progress_tasks = ProductionTask.objects.filter(
            status__in=['received', 'material_preparing', 'in_production', 'qc_checking'],
            updated_at__lt=no_progress_date
        ).count()
        if no_progress_tasks > 0:
            alerts.append({
                'type': 'no_progress_tasks',
                'count': no_progress_tasks,
                'message': f'有 {no_progress_tasks} 个生产任务长时间未推进',
                'level': 'warning',
            })
        
        # 9. 关键物料缺料预警
        if context.get('inventory_status', {}).get('shortage_materials', 0) > 0:
            alerts.append({
                'type': 'material_shortage',
                'count': context['inventory_status']['shortage_materials'],
                'message': f'有 {context["inventory_status"]["shortage_materials"]} 种物料缺料',
                'level': 'danger',
            })
        
        # 10. 安全库存跌破预警
        if context.get('inventory_status', {}).get('low_stock_materials', 0) > 0:
            alerts.append({
                'type': 'low_stock',
                'count': context['inventory_status']['low_stock_materials'],
                'message': f'有 {context["inventory_status"]["low_stock_materials"]} 种物料低于安全库存',
                'level': 'warning',
            })
        
        # 13. 逾期未发货预警
        if context.get('logistics_status', {}).get('overdue_ship_orders', 0) > 0:
            alerts.append({
                'type': 'overdue_shipment',
                'count': context['logistics_status']['overdue_ship_orders'],
                'message': f'有 {context["logistics_status"]["overdue_ship_orders"]} 个订单逾期未发货',
                'level': 'warning',
            })
        
        context['alerts'] = alerts
    
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
