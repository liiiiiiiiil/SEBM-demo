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
@role_required('sales', 'sales_mgr', 'warehouse', 'ceo')
def order_list(request):
    """订单列表"""
    orders = SalesOrder.objects.select_related('customer', 'salesperson').all()
    
    # 销售员只能看自己的订单
    if request.user.profile.role == 'sales':
        orders = orders.filter(salesperson=request.user)
    
    status_filter = request.GET.get('status', '')
    # 库存管理员默认显示待库存审批的订单
    if not status_filter and request.user.profile.role == 'warehouse':
        status_filter = 'warehouse_pending'
        orders = orders.filter(status='warehouse_pending')
    elif status_filter:
        orders = orders.filter(status=status_filter)
    
    context = {
        'orders': orders,
        'status_filter': status_filter,
    }
    return render(request, 'sales/order_list.html', context)


@login_required
@role_required('sales', 'ceo')
def order_create(request, order_pk=None):
    """创建订单或编辑被退回的订单"""
    from .forms import SalesOrderForm, SalesOrderItemFormSet
    
    # 如果是编辑被退回的订单
    order = None
    if order_pk:
        order = get_object_or_404(SalesOrder, pk=order_pk)
        # 只能编辑被退回的订单
        if order.status != 'rejected':
            messages.error(request, '只能编辑被退回的订单')
            return redirect('sales:order_list')
        # 销售员只能编辑自己创建的订单
        if request.user.profile.role == 'sales' and order.salesperson != request.user:
            messages.error(request, '您只能编辑自己创建的订单')
            return redirect('sales:order_list')
    
    if request.method == 'POST':
        form = SalesOrderForm(request.POST, instance=order)
        # 编辑时使用不同的formset
        from .forms import SalesOrderItemFormSet, SalesOrderItemFormSetEdit
        if order_pk:
            formset = SalesOrderItemFormSetEdit(request.POST, instance=order)
        else:
            formset = SalesOrderItemFormSet(request.POST, instance=order)
        
        if form.is_valid() and formset.is_valid():
            # 验证至少有一个订单明细
            valid_items = [f for f in formset if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]
            if not valid_items:
                messages.error(request, '至少需要添加一个产品明细')
                return render(request, 'sales/order_form.html', {
                    'form': form, 
                    'formset': formset, 
                    'title': '编辑订单' if order_pk else '创建订单', 
                    'order': order
                })
            
            with transaction.atomic():
                order = form.save(commit=False)
                if not order_pk:  # 新建订单
                    order.salesperson = request.user
                    order.order_no = f"SO{timezone.now().strftime('%Y%m%d%H%M%S')}"
                else:  # 编辑被退回的订单，重置状态为待审批
                    order.status = 'pending'
                    order.rejected_by = None
                    order.rejected_at = None
                    order.reject_reason = ''
                
                order.save()
                
                # 使用formset保存订单明细（会自动处理删除和更新）
                instances = formset.save(commit=False)
                
                # 计算总额并保存明细
                total = 0
                for item in instances:
                    item.order = order  # 确保订单关联正确
                    item.subtotal = item.quantity * item.unit_price
                    item.save()
                    total += item.subtotal
                
                # 删除标记为删除的明细
                for item in formset.deleted_objects:
                    item.delete()
                
                order.total_amount = total
                order.save()
                
                if order_pk:
                    messages.success(request, f'订单 {order.order_no} 已重新提交，等待审批')
                else:
                    messages.success(request, f'订单 {order.order_no} 创建成功，等待审批')
                return redirect('sales:order_detail', pk=order.pk)
        else:
            # 显示表单错误
            if not form.is_valid():
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
            if not formset.is_valid():
                for form_item in formset:
                    if form_item.errors:
                        for field, errors in form_item.errors.items():
                            for error in errors:
                                messages.error(request, f'订单明细错误 ({form_item.prefix}-{field}): {error}')
                if formset.non_form_errors():
                    for error in formset.non_form_errors():
                        messages.error(request, f'订单明细错误: {error}')
    else:
        form = SalesOrderForm(instance=order)
        # 编辑时，extra=0，不显示空行；新建时，extra=1，显示一个空行
        from .forms import SalesOrderItemFormSet, SalesOrderItemFormSetEdit
        if order_pk:
            formset = SalesOrderItemFormSetEdit(instance=order, queryset=order.items.all())
        else:
            # 新建订单时，instance=None，只显示一个空行
            formset = SalesOrderItemFormSet(instance=None)
    
    title = '编辑订单' if order_pk else '创建订单'
    return render(request, 'sales/order_form.html', {'form': form, 'formset': formset, 'title': title, 'order': order})


@login_required
@role_required('sales', 'sales_mgr', 'warehouse', 'ceo')
def order_detail(request, pk):
    """订单详情"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product'), pk=pk)
    
    # 权限检查：销售员只能看自己的订单，库存管理员和销售经理可以看所有订单
    if request.user.profile.role == 'sales' and order.salesperson != request.user:
        messages.error(request, '您没有权限查看此订单')
        return redirect('sales:order_list')
    
    context = {
        'order': order,
    }
    return render(request, 'sales/order_detail.html', context)


@login_required
@role_required('sales', 'ceo')
def order_cancel(request, pk):
    """取消订单（销售员只能取消自己创建的、待审批的订单）"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    # 权限检查：只能取消自己创建的订单
    if request.user.profile.role == 'sales' and order.salesperson != request.user:
        messages.error(request, '您只能取消自己创建的订单')
        return redirect('sales:order_list')
    
    # 只能取消待审批状态的订单
    if order.status != 'pending':
        messages.error(request, '只能取消待审批状态的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        cancel_reason = request.POST.get('cancel_reason', '').strip()
        
        with transaction.atomic():
            order.status = 'cancelled'
            if cancel_reason:
                order.remark = f"{order.remark}\n[取消原因：{cancel_reason}]" if order.remark else f"[取消原因：{cancel_reason}]"
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 已取消')
            return redirect('sales:order_list')
    
    return render(request, 'sales/order_cancel.html', {'order': order})


@login_required
@role_required('sales_mgr', 'ceo')
def order_approve(request, pk):
    """销售审批订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'pending':
        messages.error(request, '订单状态不正确')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            order.status = 'warehouse_pending'  # 销售审批后进入库存审批
            order.approved_by = request.user
            order.approved_at = timezone.now()
            # 清除退回信息（如果之前被退回过）
            order.rejected_by = None
            order.rejected_at = None
            order.reject_reason = ''
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 销售审批通过，已提交至库存审批')
            return redirect('sales:order_detail', pk=pk)
    
    return render(request, 'sales/order_approve.html', {'order': order})


@login_required
@role_required('sales_mgr', 'ceo')
def order_reject(request, pk):
    """退回订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    # 只能退回待审批状态的订单
    if order.status != 'pending':
        messages.error(request, '只能退回待审批状态的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请输入退回原因')
            return render(request, 'sales/order_reject.html', {'order': order})
        
        with transaction.atomic():
            order.status = 'rejected'
            order.rejected_by = request.user
            order.rejected_at = timezone.now()
            order.reject_reason = reject_reason
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 已退回给销售员 {order.salesperson.username}')
            return redirect('sales:order_detail', pk=pk)
    
    return render(request, 'sales/order_reject.html', {'order': order})


@login_required
@role_required('warehouse', 'ceo')
def warehouse_approve(request, pk):
    """库存审批订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'warehouse_pending':
        messages.error(request, '订单状态不正确，只能审批待库存审批的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            order.status = 'warehouse_approved'
            order.warehouse_approved_by = request.user
            order.warehouse_approved_at = timezone.now()
            order.save()
            
            # 库存审批完成后，进入智能库存研判
            check_inventory_and_create_tasks(order)
            
            messages.success(request, f'订单 {order.order_no} 库存审批通过，已进入生产/物流环节')
            return redirect('sales:order_detail', pk=pk)
    
    # 审批前进行库存判断（不实际创建任务）
    inventory_check_result = check_inventory_status(order)
    
    context = {
        'order': order,
        'inventory_check': inventory_check_result,
    }
    return render(request, 'sales/warehouse_approve.html', context)


@login_required
@role_required('warehouse', 'ceo')
def warehouse_reject(request, pk):
    """库存退回订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'warehouse_pending':
        messages.error(request, '只能退回待库存审批状态的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请输入退回原因')
            return render(request, 'sales/warehouse_reject.html', {'order': order})
        
        with transaction.atomic():
            order.status = 'rejected'
            order.rejected_by = request.user
            order.rejected_at = timezone.now()
            order.reject_reason = reject_reason
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 已退回给销售员 {order.salesperson.username}')
            return redirect('sales:order_detail', pk=pk)
    
    return render(request, 'sales/warehouse_reject.html', {'order': order})


def check_inventory_status(order):
    """检查库存状态（不实际创建任务，仅用于显示判断结果）"""
    result = {
        'all_sufficient': True,
        'items': [],
        'next_step': None,
        'next_step_display': None,
    }
    
    for item in order.items.all():
        # 获取成品库存
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=item.product)
            available_qty = inventory.quantity
        except Inventory.DoesNotExist:
            available_qty = 0
        
        item_result = {
            'product': item.product,
            'required_quantity': item.quantity,
            'available_quantity': available_qty,
            'sufficient': available_qty >= item.quantity,
            'shortage': max(0, item.quantity - available_qty),
        }
        
        result['items'].append(item_result)
        
        if not item_result['sufficient']:
            result['all_sufficient'] = False
    
    # 判断下一步流程
    if result['all_sufficient']:
        result['next_step'] = 'logistics'
        result['next_step_display'] = '物流发货'
    else:
        result['next_step'] = 'production'
        result['next_step_display'] = '生产环节'
    
    return result


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
