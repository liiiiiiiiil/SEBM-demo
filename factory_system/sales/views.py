from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from accounts.decorators import role_required
from .models import SalesOrder, SalesOrderItem, ShippingNotice
from inventory.models import Customer, Product, Inventory
from production.models import ProductionTask


@login_required
@role_required('sales', 'sales_mgr', 'ceo')
def order_list(request):
    """订单列表"""
    orders = SalesOrder.objects.select_related('customer', 'salesperson').all()
    
    # 销售员只能看自己的订单
    if request.user.profile.role == 'sales':
        orders = orders.filter(salesperson=request.user)
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    context = {
        'orders': orders,
        'status_filter': status_filter,
    }
    return render(request, 'sales/order_list.html', context)


@login_required
@role_required('sales', 'ceo')
def order_create(request):
    """创建订单"""
    from .forms import SalesOrderForm, SalesOrderItemFormSet
    
    if request.method == 'POST':
        form = SalesOrderForm(request.POST)
        formset = SalesOrderItemFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.salesperson = request.user
                order.order_no = f"SO{timezone.now().strftime('%Y%m%d%H%M%S')}"
                order.save()
                
                # 保存订单明细并计算总额
                total = 0
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                        item = item_form.save(commit=False)
                        item.order = order
                        item.subtotal = item.quantity * item.unit_price
                        item.save()
                        total += item.subtotal
                
                order.total_amount = total
                order.save()
                
                messages.success(request, f'订单 {order.order_no} 创建成功，等待审批')
                return redirect('sales:order_detail', pk=order.pk)
    else:
        form = SalesOrderForm()
        formset = SalesOrderItemFormSet()
    
    return render(request, 'sales/order_form.html', {'form': form, 'formset': formset, 'title': '创建订单'})


@login_required
@role_required('sales', 'sales_mgr', 'ceo')
def order_detail(request, pk):
    """订单详情"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product'), pk=pk)
    
    # 权限检查
    if request.user.profile.role == 'sales' and order.salesperson != request.user:
        messages.error(request, '您没有权限查看此订单')
        return redirect('sales:order_list')
    
    context = {
        'order': order,
    }
    return render(request, 'sales/order_detail.html', context)


@login_required
@role_required('sales_mgr', 'ceo')
def order_approve(request, pk):
    """审批订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'pending':
        messages.error(request, '订单状态不正确')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            order.status = 'approved'
            order.approved_by = request.user
            order.approved_at = timezone.now()
            order.save()
            
            # 智能库存研判
            check_inventory_and_create_tasks(order)
            
            messages.success(request, f'订单 {order.order_no} 审批通过')
            return redirect('sales:order_detail', pk=pk)
    
    return render(request, 'sales/order_approve.html', {'order': order})


def check_inventory_and_create_tasks(order):
    """智能库存研判 - 检查库存并创建生产任务或发货通知"""
    from django.db import transaction
    
    with transaction.atomic():
        all_sufficient = True
        
        for item in order.items.all():
            # 获取成品库存
            try:
                inventory = Inventory.objects.get(inventory_type='product', product=item.product)
                available_qty = inventory.quantity
            except Inventory.DoesNotExist:
                available_qty = 0
            
            if available_qty >= item.quantity:
                # 库存充足 - 锁定库存
                inventory.quantity -= item.quantity
                inventory.save()
            else:
                # 库存不足 - 需要生产
                all_sufficient = False
                shortage = item.quantity - available_qty
                
                # 创建生产任务
                task = ProductionTask.objects.create(
                    task_no=f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}{order.pk}",
                    order=order,
                    product=item.product,
                    required_quantity=shortage,
                    status='pending',
                )
        
        if all_sufficient:
            # 所有产品库存充足，创建发货通知单
            ShippingNotice.objects.create(
                notice_no=f"SN{timezone.now().strftime('%Y%m%d%H%M%S')}",
                order=order,
                status='pending',
            )
            order.status = 'ready_to_ship'
        else:
            order.status = 'in_production'
        
        order.save()
