from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
import json
from decimal import Decimal, InvalidOperation
from accounts.decorators import role_required, role_or_permission_required
from django.db.models import Q
from .models import SalesOrder, SalesOrderItem, SalesOrderItemBatch, Customer, CustomerTransfer
from inventory.models import Product, Inventory, Batch
from production.models import ProductionTask, MaterialRequisition
from factory_system.utils import get_paginate_by


@login_required
@role_required('sales', 'sales_mgr', 'warehouse', 'ceo')
def order_list(request):
    """订单列表"""
    orders = SalesOrder.objects.select_related('customer', 'salesperson').all()
    
    # 销售员只能看自己的订单
    if request.user.profile.role == 'sales':
        orders = orders.filter(salesperson=request.user)
    
    status_filter = request.GET.get('status', '')
    # 根据筛选条件过滤订单
    if status_filter:
        orders = orders.filter(status=status_filter)
    # 注意：总经理默认显示所有订单，不再自动筛选为待审批订单
    
    # 分页处理
    paginate_by = get_paginate_by(request, desktop_count=20, mobile_count=10)
    paginator = Paginator(orders, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if status_filter:
        extra_params = f'status={status_filter}'
    
    context = {
        'orders': page_obj,
        'status_filter': status_filter,
        'extra_params': extra_params,
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
                # 表单输入为显示单位，需转为基础单位存储
                total = 0
                formset_forms = list(formset.forms)
                for idx, item in enumerate(instances):
                    item.order = order
                    # 用户输入为显示单位，转为基础单位
                    qty_display = item.quantity
                    item.quantity = item.product.from_display(qty_display)
                    item.subtotal = item.quantity * item.unit_price
                    item.save()
                    total += item.subtotal
                
                    # 保存批次分配信息
                    # 删除该订单项的所有旧批次分配
                    SalesOrderItemBatch.objects.filter(order_item=item).delete()
                    
                    # 获取该form在formset中的实际索引（通过prefix匹配）
                    if idx < len(formset_forms):
                        form_prefix = formset_forms[idx].prefix
                        # 获取批次分配数据（格式：items-{form_index}-batch_{batch_id}）
                        batch_keys = [key for key in request.POST.keys() if key.startswith(f'{form_prefix}-batch_')]
                        for batch_key in batch_keys:
                            batch_id = batch_key.replace(f'{form_prefix}-batch_', '')
                            batch_qty_str = request.POST.get(batch_key, '0')
                            try:
                                batch_qty_display = Decimal(batch_qty_str)
                                if batch_qty_display > 0:
                                    batch = Batch.objects.get(pk=batch_id, inventory__inventory_type='product', inventory__product=item.product)
                                    batch_qty_base = item.product.from_display(batch_qty_display)
                                    SalesOrderItemBatch.objects.create(
                                        order_item=item,
                                        batch=batch,
                                        quantity=batch_qty_base,
                                    )
                            except (ValueError, Batch.DoesNotExist, InvalidOperation):
                                pass
                
                # 删除标记为删除的明细（会自动删除关联的批次分配）
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
        from .forms import SalesOrderItemFormSet, SalesOrderItemFormSetEdit
        if order_pk:
            formset = SalesOrderItemFormSetEdit(instance=order, queryset=order.items.select_related('product'))
            # 编辑时 quantity 存基础单位，表单需显示显示单位
            for f in formset.forms:
                if f.instance and f.instance.pk and f.instance.product_id:
                    disp, _ = f.instance.product.to_display(f.instance.quantity)
                    f.initial['quantity'] = disp
        else:
            formset = SalesOrderItemFormSet(instance=None)
    
    title = '编辑订单' if order_pk else '创建订单'
    
    # 获取产品库存数据和批次数据用于前端显示
    import json
    from django.db.models import Sum, Q
    products = Product.objects.select_related('base_unit', 'display_unit').all()
    product_inventory_data = {}
    product_batches_data = {}
    
    # 计算每个批次已被锁定的数量（只统计选择了"锁定库存"且订单状态有效的订单）
    # 有效状态：pending, approved, ceo_pending, ceo_approved, in_production, ready_to_ship
    # 排除当前正在编辑的订单（如果存在）
    valid_statuses = ['pending', 'approved', 'ceo_pending', 'ceo_approved', 'in_production', 'ready_to_ship']
    batch_reserved_qty = {}
    
    # 获取所有选择了"锁定库存"且状态有效的订单的批次分配
    reserved_batch_allocations = SalesOrderItemBatch.objects.filter(
        order_item__order__reserve_inventory=True,
        order_item__order__status__in=valid_statuses
    )
    
    # 如果正在编辑订单，排除当前订单的锁定
    if order_pk:
        reserved_batch_allocations = reserved_batch_allocations.exclude(order_item__order__pk=order_pk)
    
    # 按批次汇总已锁定的数量（allocation.quantity 为基础单位）
    for allocation in reserved_batch_allocations:
        batch_id = allocation.batch.id
        if batch_id not in batch_reserved_qty:
            batch_reserved_qty[batch_id] = Decimal('0')
        batch_reserved_qty[batch_id] += allocation.quantity
    
    for product in products:
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=product)
            batches = inventory.get_batches().filter(quantity__gt=0).order_by('batch_date', 'created_at')
            inv_disp, _ = product.to_display(inventory.quantity)
            product_inventory_data[str(product.pk)] = {
                'quantity': float(inv_disp),
                'unit': product.display_unit.name if product.display_unit else '',
                'unit_price': float(product.unit_price) if product.unit_price else 0.0
            }
            product_batches_data[str(product.pk)] = []
            
            for batch in batches:
                # 计算该批次已被锁定的数量（基础单位）
                reserved_base = batch_reserved_qty.get(batch.id, Decimal('0'))
                # 可用数量 = 批次数量 - 已锁定数量（基础单位）
                available_base = batch.quantity - reserved_base
                
                # 转换为显示单位
                batch_disp, _ = product.to_display(batch.quantity)
                avail_disp, _ = product.to_display(max(Decimal('0'), available_base))
                reserved_disp, _ = product.to_display(reserved_base)
                
                product_batches_data[str(product.pk)].append({
                    'id': batch.id,
                    'batch_no': batch.batch_no,
                    'batch_date': batch.batch_date.strftime('%Y-%m-%d'),
                    'quantity': float(batch_disp),  # 总数量（显示单位）
                    'available_quantity': float(avail_disp),  # 可用数量（显示单位）
                    'reserved_quantity': float(reserved_disp),  # 已锁定数量（显示单位）
                    'unit_price': float(batch.unit_price) if batch.unit_price else None,
                    'expiry_date': batch.expiry_date.strftime('%Y-%m-%d') if batch.expiry_date else None,
                    'is_expired': batch.is_expired(),
                })
        except Inventory.DoesNotExist:
            product_inventory_data[str(product.pk)] = {
                'quantity': 0,
                'unit': product.display_unit.name if product.display_unit else '',
                'unit_price': float(product.unit_price) if product.unit_price else 0.0
            }
            product_batches_data[str(product.pk)] = []
    
    product_inventory_data_json = json.dumps(product_inventory_data)
    product_batches_data_json = json.dumps(product_batches_data)
    
    return render(request, 'sales/order_form.html', {
        'form': form, 
        'formset': formset, 
        'title': title, 
        'order': order,
        'product_inventory_data_json': product_inventory_data_json,
        'product_batches_data_json': product_batches_data_json
    })


@login_required
@role_required('sales', 'sales_mgr', 'warehouse', 'ceo')
def order_detail(request, pk):
    """订单详情"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product__base_unit', 'items__product__display_unit'), pk=pk)
    
    # 权限检查：销售员只能看自己的订单，总经理和销售经理可以看所有订单
    if request.user.profile.role == 'sales' and order.salesperson != request.user:
        messages.error(request, '您没有权限查看此订单')
        return redirect('sales:order_list')
    
    # 准备批次分配和缺口信息（quantity 均为基础单位，转为显示单位用于展示）
    items_with_batch_info = []
    for item in order.items.select_related('product', 'product__display_unit'):
        product = item.product
        batch_allocated_qty_base = Decimal('0')
        batch_allocations = []
        for order_batch in SalesOrderItemBatch.objects.filter(order_item=item).select_related('batch'):
            batch_allocated_qty_base += order_batch.quantity
            qty_disp = order_batch.get_display_quantity()
            batch_allocations.append({
                'batch_no': order_batch.batch.batch_no or f'批次-{order_batch.batch.id}',
                'batch_date': order_batch.batch.batch_date,
                'quantity': qty_disp,
                'unit': product.display_unit.name if product.display_unit else '',
            })
        
        shortage_base = max(Decimal('0'), item.quantity - batch_allocated_qty_base)
        alloc_disp = product.to_display(batch_allocated_qty_base)[0]
        shortage_disp = product.to_display(shortage_base)[0]
        
        items_with_batch_info.append({
            'item': item,
            'batch_allocated_qty': alloc_disp,
            'batch_allocations': batch_allocations,
            'shortage': shortage_disp,
        })
    
    context = {'order': order, 'items_with_batch_info': items_with_batch_info}
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
    """审批订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'pending':
        messages.error(request, '订单状态不正确')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            order.status = 'ceo_pending'  # 审批后进入总经理审批
            order.approved_by = request.user
            order.approved_at = timezone.now()
            # 清除退回信息（如果之前被退回过）
            order.rejected_by = None
            order.rejected_at = None
            order.reject_reason = ''
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 审批通过，已提交至总经理审批')
            return redirect('sales:order_detail', pk=pk)
    
    # 准备批次分配和缺口信息（quantity 为基础单位，转为显示单位展示）
    items_with_batch_info = []
    for item in order.items.select_related('product', 'product__display_unit'):
        product = item.product
        batch_allocated_qty_base = Decimal('0')
        batch_allocations = []
        for order_batch in SalesOrderItemBatch.objects.filter(order_item=item).select_related('batch'):
            batch_allocated_qty_base += order_batch.quantity
            qty_disp = order_batch.get_display_quantity()
            batch_allocations.append({
                'batch_no': order_batch.batch.batch_no or f'批次-{order_batch.batch.id}',
                'batch_date': order_batch.batch.batch_date,
                'quantity': qty_disp,
                'unit': product.display_unit.name if product.display_unit else '',
            })
        
        shortage_base = max(Decimal('0'), item.quantity - batch_allocated_qty_base)
        alloc_disp = product.to_display(batch_allocated_qty_base)[0]
        shortage_disp = product.to_display(shortage_base)[0]
        
        items_with_batch_info.append({
            'item': item,
            'batch_allocated_qty': alloc_disp,
            'batch_allocations': batch_allocations,
            'shortage': shortage_disp,
        })
    
    context = {'order': order, 'items_with_batch_info': items_with_batch_info}
    return render(request, 'sales/order_approve.html', context)


@login_required
@role_required('sales_mgr', 'ceo')
def order_reject(request, pk):
    """退回订单"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product__display_unit'), pk=pk)
    
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
@role_required('ceo')
def ceo_approve(request, pk):
    """总经理审批订单"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product__display_unit'), pk=pk)
    
    if order.status != 'ceo_pending':
        messages.error(request, '订单状态不正确，只能审批待总经理审批的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            # 锁定批次库存（order_batch.quantity 为基础单位）
            from sales.models import SalesOrderItemBatch
            from inventory.models import Batch
            for item in order.items.all():
                for order_batch in SalesOrderItemBatch.objects.filter(order_item=item):
                    batch = order_batch.batch
                    batch.locked_quantity += order_batch.quantity
                    batch.save()
            
            order.status = 'ceo_approved'
            order.ceo_approved_by = request.user
            order.ceo_approved_at = timezone.now()
            order.save()
            
            # 总经理审批完成后，进入智能库存研判
            check_inventory_and_create_tasks(order)
            
            messages.success(request, f'订单 {order.order_no} 总经理审批通过，已进入生产/物流环节')
            return redirect('sales:order_detail', pk=pk)
    
    # 审批前进行库存判断（不实际创建任务）
    inventory_check_result = check_inventory_status(order)
    
    context = {
        'order': order,
        'inventory_check': inventory_check_result,
    }
    return render(request, 'sales/ceo_approve.html', context)


@login_required
@role_required('ceo')
def ceo_reject(request, pk):
    """总经理退回订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'ceo_pending':
        messages.error(request, '只能退回待总经理审批状态的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请输入退回原因')
            return render(request, 'sales/ceo_reject.html', {'order': order})
        
        with transaction.atomic():
            order.status = 'rejected'
            order.rejected_by = request.user
            order.rejected_at = timezone.now()
            order.reject_reason = reject_reason
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 已退回给销售员 {order.salesperson.username}')
            return redirect('sales:order_detail', pk=pk)
    
    return render(request, 'sales/ceo_reject.html', {'order': order})


def terminate_order_chain(order, terminated_by, terminate_reason):
    """终结订单及其所有关联流程的完整链路"""
    from logistics.models import Shipment
    from inventory.models import Inventory, StockTransaction
    
    with transaction.atomic():
        # 获取所有关联的生产任务（用于后续处理）
        from production.models import ProductionTask
        all_production_tasks = ProductionTask.objects.filter(order=order)
        
        # 1. 检查订单是否已出库，如果已出库，需要重新入库（创建新批次）
        if order.status == 'shipped':
            # 查找该订单的所有已发货的发货单
            shipped_shipments = Shipment.objects.filter(
                order=order,
                status__in=['shipped', 'delivered']
            )
            
            if shipped_shipments.exists():
                from inventory.models import Batch
                from datetime import datetime
                # 对于已发货的商品，需要重新入库（创建新批次）
                for item in order.items.select_related('product', 'product__base_unit', 'product__display_unit'):
                    product = item.product
                    inventory, created = Inventory.objects.get_or_create(
                        inventory_type='product',
                        product=product,
                        defaults={'quantity': 0}
                    )
                    
                    # item.quantity 已是基础单位
                    qty_base = item.quantity
                    
                    # 创建新批次（批次号格式：RETURN-{原订单号}-{日期}）
                    batch_date = timezone.now().date()
                    batch_no = f"RETURN-{order.order_no}-{batch_date.strftime('%Y%m%d')}"
                    counter = 1
                    original_batch_no = batch_no
                    while Batch.objects.filter(batch_no=batch_no).exists():
                        batch_no = f"{original_batch_no}-{counter}"
                        counter += 1
                    
                    # 创建批次（基础单位）
                    batch = Batch.objects.create(
                        batch_no=batch_no,
                        inventory=inventory,
                        batch_date=batch_date,
                        quantity=qty_base,
                        unit_price=product.unit_price,
                        remark=f"订单终结退回：{order.order_no}，原因：{terminate_reason}",
                    )
                    
                    inventory.update_quantity_from_batches()
                    
                    StockTransaction.objects.create(
                        transaction_type='adjustment',
                        inventory=inventory,
                        batch=batch,
                        quantity=qty_base,
                        base_quantity=qty_base,
                        unit=product.base_unit,
                        reference_no=f"TERMINATE-{order.order_no}",
                        remark=f"订单终结退回：{terminate_reason}",
                        operator=terminated_by,
                    )
        
        # 2. 扣减已入库的成品库存（按批次FIFO，从最早入库的批次开始）
        # 如果订单未发货但成品已入库，需要扣减这些已入库的成品
        # 注意：已发货的订单在第1步已经重新入库，这里不需要再扣减
        if order.status != 'shipped':
            from production.models import FinishedProductInbound
            completed_tasks = all_production_tasks.filter(status='completed')
            
            for task in completed_tasks:
                # 查找该任务的所有入库单
                inbounds = FinishedProductInbound.objects.filter(task=task)
                total_inbound_qty = sum(inbound.quantity for inbound in inbounds)
                
                if total_inbound_qty > 0:
                    try:
                        inventory = Inventory.objects.get(
                            inventory_type='product',
                            product=task.product
                        )
                        remaining_qty = total_inbound_qty
                        
                        # 按FIFO原则从批次中扣减（从最早入库的批次开始）
                        from inventory.models import Batch
                        # get_batches()已经按batch_date和created_at排序，无需重复排序
                        for batch in inventory.get_batches():
                            if remaining_qty <= 0:
                                break
                            
                            # 获取可用数量（总数量 - 锁定数量）
                            available_qty = batch.get_available_quantity()
                            if available_qty <= 0:
                                continue
                            
                            allocate_qty = min(remaining_qty, available_qty)
                            batch.quantity -= allocate_qty
                            batch.save()
                            
                            # 记录库存变动
                            StockTransaction.objects.create(
                                transaction_type='adjustment',
                                inventory=inventory,
                                batch=batch,
                                quantity=-allocate_qty,  # 负数表示扣减
                                base_quantity=-allocate_qty,
                                unit=task.product.base_unit,
                                reference_no=f"TERMINATE-{order.order_no}",
                                remark=f"订单终结扣减已入库成品：{terminate_reason}",
                                operator=terminated_by,
                            )
                            
                            remaining_qty -= allocate_qty
                        
                        # 更新库存总数量
                        inventory.update_quantity_from_batches()
                    except Inventory.DoesNotExist:
                        pass
        
        # 3. 已发料原料重新入库（创建新批次）
        # 查找该订单关联的所有生产任务的领料单，如果已批准（已发料），需要重新入库原料
        from production.models import MaterialRequisition, MaterialRequisitionItem
        from inventory.models import Batch
        for task in all_production_tasks:
            requisitions = MaterialRequisition.objects.filter(
                task=task,
                status='approved'  # 已批准表示已发料
            )
            for requisition in requisitions:
                for req_item in requisition.items.all():
                    # 重新入库原料（创建新批次）
                    inventory, created = Inventory.objects.get_or_create(
                        inventory_type='material',
                        material=req_item.material,
                        defaults={'quantity': 0}
                    )
                    
                    # 创建新批次
                    batch_date = timezone.now().date()
                    batch_no = f"RETURN-{order.order_no}-{req_item.material.sku}-{batch_date.strftime('%Y%m%d')}"
                    # 确保批次号唯一
                    counter = 1
                    original_batch_no = batch_no
                    while Batch.objects.filter(batch_no=batch_no).exists():
                        batch_no = f"{original_batch_no}-{counter}"
                        counter += 1
                    
                    # 创建批次
                    batch = Batch.objects.create(
                        batch_no=batch_no,
                        inventory=inventory,
                        batch_date=batch_date,
                        quantity=req_item.required_quantity,
                        unit_price=req_item.material.unit_price,
                        remark=f"订单终结退回原料：{order.order_no}，领料单：{requisition.requisition_no}，原因：{terminate_reason}",
                    )
                    
                    # 更新库存总数量
                    inventory.update_quantity_from_batches()
                    
                    # 记录库存变动
                    StockTransaction.objects.create(
                        transaction_type='adjustment',
                        inventory=inventory,
                        batch=batch,
                        quantity=req_item.required_quantity,
                        base_quantity=req_item.required_quantity,
                        unit=req_item.material.base_unit,
                        reference_no=f"TERMINATE-{order.order_no}",
                        remark=f"订单终结退回原料：{terminate_reason}",
                        operator=terminated_by,
                    )
        
        # 4. 释放订单审批时锁定的批次库存
        # 如果订单状态是ready_to_ship或ceo_approved或in_production，说明审批时已经锁定了批次库存
        # 需要释放锁定的批次库存（注意：已发货的订单不需要释放，因为库存已经实际扣减）
        if order.status in ['ready_to_ship', 'ceo_approved', 'in_production']:
            from sales.models import SalesOrderItemBatch
            from inventory.models import Batch
            from decimal import Decimal
            # 释放所有批次分配中锁定的库存（order_batch.quantity 为基础单位）
            for item in order.items.all():
                for order_batch in SalesOrderItemBatch.objects.filter(order_item=item):
                    batch = order_batch.batch
                    if batch.locked_quantity >= order_batch.quantity:
                        batch.locked_quantity -= order_batch.quantity
                    else:
                        batch.locked_quantity = Decimal('0')
                    batch.save()
        
        # 5. 终结产品订单
        order.status = 'terminated'
        order.terminated_by = terminated_by
        order.terminated_at = timezone.now()
        order.terminate_reason = terminate_reason
        order.save()
        
        # 6. 终结所有关联的生产任务
        for task in all_production_tasks:
            if task.status not in ['completed', 'cancelled', 'terminated']:
                task.status = 'terminated'
                task.terminated_by = terminated_by
                task.terminated_at = timezone.now()
                task.terminate_reason = f"关联订单 {order.order_no} 已终结：{terminate_reason}"
                task.save()
                
                # 4. 终结所有关联的领料单
                requisitions = MaterialRequisition.objects.filter(task=task)
                for requisition in requisitions:
                    if requisition.status not in ['cancelled', 'terminated']:
                        requisition.status = 'terminated'
                        requisition.terminated_by = terminated_by
                        requisition.terminated_at = timezone.now()
                        requisition.terminate_reason = f"关联订单 {order.order_no} 已终结：{terminate_reason}"
                        requisition.save()
        
        # 注意：ShippingNotice和Shipment模型没有terminated状态，但可以通过订单状态判断是否已终结


@login_required
@role_required('ceo')
def order_terminate(request, pk):
    """总经理终结订单（终结整个链路）"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    # 只能终结进行中的订单
    active_statuses = ['in_production', 'ready_to_ship', 'shipped']
    if order.status not in active_statuses:
        messages.error(request, '只能终结进行中的订单（生产中、待发货、已发货）')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'sales/order_terminate.html', {'order': order})
        
        # 终结整个链路
        terminate_order_chain(order, request.user, terminate_reason)
        
        messages.success(request, f'订单 {order.order_no} 及其所有关联流程已终结')
        return redirect('sales:order_detail', pk=pk)
    
    # 显示关联流程信息
    production_tasks = ProductionTask.objects.filter(order=order)
    requisitions = MaterialRequisition.objects.filter(task__order=order)
    from logistics.models import ShippingNotice
    shipping_notices = ShippingNotice.objects.filter(order=order)
    
    context = {
        'order': order,
        'production_tasks': production_tasks,
        'requisitions': requisitions,
        'shipping_notices': shipping_notices,
    }
    return render(request, 'sales/order_terminate.html', context)


def check_inventory_status(order):
    """检查库存状态（不实际创建任务，仅用于显示判断结果）
    支持部分批次分配：如果批次分配总和小于订单数量，不足部分需要生产
    """
    from inventory.models import BOM
    from decimal import Decimal
    from sales.models import SalesOrderItemBatch
    
    result = {
        'all_sufficient': True,
        'items': [],
        'material_requirements': {},  # 汇总所有原料需求 {material_id: {'material': Material, 'required': Decimal, 'available': Decimal, 'shortage': Decimal}}
        'next_step': None,
        'next_step_display': None,
    }
    
    for item in order.items.select_related('product', 'product__base_unit', 'product__display_unit'):
        product = item.product
        # item.quantity、order_batch.quantity、inventory.quantity 均为基础单位
        
        batch_allocated_qty_base = sum(ob.quantity for ob in SalesOrderItemBatch.objects.filter(order_item=item))
        shortage_base = max(Decimal('0'), item.quantity - batch_allocated_qty_base)
        
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=product)
            avail_disp, _ = product.to_display(inventory.quantity)
        except Inventory.DoesNotExist:
            avail_disp = Decimal('0')
        
        req_disp, _ = product.to_display(item.quantity)
        alloc_disp, _ = product.to_display(batch_allocated_qty_base)
        short_disp, _ = product.to_display(shortage_base)
        
        item_result = {
            'product': product,
            'required_quantity': req_disp,
            'batch_allocated_quantity': alloc_disp,
            'available_quantity': avail_disp,
            'sufficient': batch_allocated_qty_base >= item.quantity,
            'shortage': short_disp,
            'material_needs': [],
        }
        
        # 如果有缺口（批次分配不足），计算生产缺口产品所需的原料
        if shortage_base > 0:
            bom_items = BOM.objects.filter(product=product).select_related('material', 'material__base_unit', 'material__display_unit')
            for bom_item in bom_items:
                # 以基础单位计算原料需求
                material_required_base = shortage_base * bom_item.get_base_quantity()
                mat = bom_item.material

                try:
                    material_inventory = Inventory.objects.get(
                        inventory_type='material',
                        material=mat
                    )
                    material_available_base = material_inventory.quantity
                except Inventory.DoesNotExist:
                    material_available_base = Decimal('0')

                material_shortage_base = max(Decimal('0'), material_required_base - material_available_base)

                # 转换为原料显示单位用于前端展示
                mat_req_disp, _ = mat.to_display(material_required_base)
                mat_avail_disp, _ = mat.to_display(material_available_base)
                mat_short_disp, _ = mat.to_display(material_shortage_base)

                item_result['material_needs'].append({
                    'material': mat,
                    'required': mat_req_disp,
                    'available': mat_avail_disp,
                    'shortage': mat_short_disp,
                    'unit': mat.display_unit.name if mat.display_unit else '',
                })

                material_id = mat.id
                if material_id not in result['material_requirements']:
                    result['material_requirements'][material_id] = {
                        'material': mat,
                        'required_base': Decimal('0'),
                        'available_base': material_available_base,
                        'unit': mat.display_unit.name if mat.display_unit else '',
                        '_mat': mat,
                    }
                result['material_requirements'][material_id]['required_base'] += material_required_base
        
        result['items'].append(item_result)
        
        if not item_result['sufficient']:
            result['all_sufficient'] = False
    
    # 将原料汇总的基础单位数值转换为显示单位
    for material_id, req_data in result['material_requirements'].items():
        mat = req_data.pop('_mat')
        required_base = req_data.pop('required_base')
        available_base = req_data.pop('available_base')
        shortage_base = max(Decimal('0'), required_base - available_base)
        req_disp, _ = mat.to_display(required_base)
        avail_disp, _ = mat.to_display(available_base)
        short_disp, _ = mat.to_display(shortage_base)
        req_data['required'] = req_disp
        req_data['available'] = avail_disp
        req_data['shortage'] = short_disp
    
    # 判断下一步流程
    if result['all_sufficient']:
        result['next_step'] = 'logistics'
        result['next_step_display'] = '物流发货'
    else:
        result['next_step'] = 'production'
        result['next_step_display'] = '生产环节'
    
    return result


def check_inventory_and_create_tasks(order):
    """智能库存研判 - 检查库存并创建生产任务或发货通知
    支持部分批次分配：如果批次分配总和小于订单数量，不足部分创建生产任务
    """
    from django.db import transaction
    from sales.models import SalesOrderItemBatch
    
    with transaction.atomic():
        all_sufficient = True
        
        for item in order.items.select_related('product', 'product__base_unit', 'product__display_unit'):
            product = item.product
            batch_allocated_qty_base = sum(ob.quantity for ob in SalesOrderItemBatch.objects.filter(order_item=item))
            shortage_base = item.quantity - batch_allocated_qty_base
            
            if shortage_base > 0:
                all_sufficient = False
                
                # 检查原材料是否充足
                from inventory.models import BOM
                material_sufficient = True
                bom_items = BOM.objects.filter(product=product)
                for bom_item in bom_items:
                    material_required = shortage_base * bom_item.get_base_quantity()
                    try:
                        material_inventory = Inventory.objects.get(
                            inventory_type='material',
                            material=bom_item.material
                        )
                        if material_inventory.quantity < material_required:
                            material_sufficient = False
                            break
                    except Inventory.DoesNotExist:
                        material_sufficient = False
                        break
                
                # 创建生产任务（required_quantity 为基础单位）
                task_status = 'pending' if material_sufficient else 'material_insufficient'
                task = ProductionTask.objects.create(
                    task_no=f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}{order.pk}-{item.pk}",
                    production_type='order',
                    order=order,
                    product=product,
                    required_quantity=shortage_base,
                    status=task_status,
                )
            # 如果 shortage <= 0，说明批次分配已足够，不需要生产
            # 注意：不再直接锁定库存，因为批次分配已经指定了具体批次，库存扣减在发货时进行
        
        if all_sufficient:
            # 所有产品批次分配充足，创建发货通知单
            from logistics.models import ShippingNotice
            ShippingNotice.objects.create(
                notice_no=f"SN{timezone.now().strftime('%Y%m%d%H%M%S')}",
                order=order,
                status='pending',
            )
            order.status = 'ready_to_ship'
        else:
            order.status = 'in_production'
        
        order.save()


# ========== Customer 相关视图 ==========

@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.view')
def customer_list(request):
    """客户列表"""
    customers = Customer.objects.select_related('created_by').filter(is_deleted=False)
    
    # 权限控制：销售员只能看到自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    # 销售经理和总经理可以看到所有客户
    elif request.user.profile.role in ['sales_mgr', 'ceo'] or request.user.profile.has_permission('inventory.customer.manage'):
        pass  # 显示所有客户
    # 其他角色（如仓库管理员）如果有查看权限，也只能看到自己负责的
    elif not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | 
            Q(contact_person__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # 分页处理
    paginate_by = get_paginate_by(request, desktop_count=20, mobile_count=10)
    paginator = Paginator(customers, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if search:
        extra_params = f'search={search}'
    
    context = {
        'customers': page_obj,
        'search': search,
        'extra_params': extra_params,
    }
    return render(request, 'sales/customer_list.html', context)


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.create')
def customer_create(request):
    """创建客户"""
    from .forms import CustomerForm
    
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            messages.success(request, f'客户 {customer.name} 创建成功')
            return redirect('sales:customer_list')
    else:
        form = CustomerForm()
    
    return render(request, 'sales/customer_form.html', {'form': form, 'title': '创建客户'})


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.edit')
def customer_edit(request, pk):
    """编辑客户（提交审批申请）"""
    from .forms import CustomerForm
    import json
    
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能编辑自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能编辑自己负责的客户')
            return redirect('sales:customer_list')
    
    # 如果已有待审批的编辑申请，提示用户
    if customer.edit_status == 'pending':
        messages.warning(request, '该客户已有待审批的编辑申请，请等待审批完成')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        edit_reason = request.POST.get('edit_reason', '').strip()
        
        if form.is_valid():
            if not edit_reason:
                messages.error(request, '请填写编辑原因')
                return render(request, 'sales/customer_form.html', {
                    'form': form, 
                    'title': '编辑客户', 
                    'customer': customer,
                    'is_edit_request': True
                })
            
            # 保存待审批的数据（JSON格式）
            pending_data = {
                'name': form.cleaned_data['name'],
                'contact_person': form.cleaned_data['contact_person'],
                'phone': form.cleaned_data['phone'],
                'address': form.cleaned_data['address'],
                'credit_level': form.cleaned_data['credit_level'],
            }
            
            with transaction.atomic():
                customer.edit_status = 'pending'
                customer.edit_pending_data = json.dumps(pending_data, ensure_ascii=False)
                customer.edit_reason = edit_reason
                customer.edit_requested_by = request.user
                customer.edit_requested_at = timezone.now()
                customer.save()
            
            messages.success(request, f'客户 {customer.name} 的编辑申请已提交，等待总经理审批')
            return redirect('sales:customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'sales/customer_form.html', {
        'form': form, 
        'title': '编辑客户', 
        'customer': customer,
        'is_edit_request': True
    })


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.delete')
def customer_delete(request, pk):
    """删除客户（提交审批申请）"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能删除自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能删除自己负责的客户')
            return redirect('sales:customer_list')
    
    # 如果已有待审批的删除申请，提示用户
    if customer.delete_status == 'pending':
        messages.warning(request, '该客户已有待审批的删除申请，请等待审批完成')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        delete_reason = request.POST.get('delete_reason', '').strip()
        
        if not delete_reason:
            messages.error(request, '请填写删除原因')
            return render(request, 'sales/customer_confirm_delete.html', {'customer': customer})
        
        with transaction.atomic():
            customer.delete_status = 'pending'
            customer.delete_reason = delete_reason
            customer.delete_requested_by = request.user
            customer.delete_requested_at = timezone.now()
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的删除申请已提交，等待总经理审批')
        return redirect('sales:customer_list')
    
    return render(request, 'sales/customer_confirm_delete.html', {'customer': customer})


@login_required
@role_required('ceo')
def customer_edit_approve(request, pk):
    """总经理审批客户编辑申请"""
    import json
    
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.edit_status != 'pending':
        messages.error(request, '该客户没有待审批的编辑申请')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        try:
            # 解析待审批的数据
            pending_data = json.loads(customer.edit_pending_data)
            
            with transaction.atomic():
                # 应用编辑
                customer.name = pending_data['name']
                customer.contact_person = pending_data['contact_person']
                customer.phone = pending_data['phone']
                customer.address = pending_data['address']
                customer.credit_level = pending_data['credit_level']
                
                # 更新审批状态
                customer.edit_status = 'approved'
                customer.edit_approved_by = request.user
                customer.edit_approved_at = timezone.now()
                customer.edit_pending_data = ''  # 清空待审批数据
                customer.save()
            
            messages.success(request, f'客户 {customer.name} 的编辑申请已审批通过')
            return redirect('sales:customer_list')
        except Exception as e:
            messages.error(request, f'审批失败：{str(e)}')
            return redirect('sales:customer_list')
    
    # 显示审批页面
    try:
        pending_data = json.loads(customer.edit_pending_data) if customer.edit_pending_data else {}
    except:
        pending_data = {}
    
    context = {
        'customer': customer,
        'pending_data': pending_data,
        'action': 'edit_approve',
    }
    return render(request, 'sales/customer_approve.html', context)


@login_required
@role_required('ceo')
def customer_edit_reject(request, pk):
    """总经理拒绝客户编辑申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.edit_status != 'pending':
        messages.error(request, '该客户没有待审批的编辑申请')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请填写拒绝原因')
            return redirect('sales:customer_edit_approve', pk=pk)
        
        with transaction.atomic():
            customer.edit_status = 'rejected'
            customer.edit_reject_reason = reject_reason
            customer.edit_pending_data = ''  # 清空待审批数据
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的编辑申请已拒绝')
        return redirect('sales:customer_list')
    
    context = {
        'customer': customer,
        'action': 'edit_reject',
    }
    return render(request, 'sales/customer_reject.html', context)


@login_required
@role_required('ceo')
def customer_delete_approve(request, pk):
    """总经理审批客户删除申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.delete_status != 'pending':
        messages.error(request, '该客户没有待审批的删除申请')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        customer_name = customer.name
        
        with transaction.atomic():
            customer.delete_status = 'approved'
            customer.delete_approved_by = request.user
            customer.delete_approved_at = timezone.now()
            
            # 检查是否有关联订单，如果有则只软删除，否则硬删除
            if customer.has_related_orders():
                # 有关联订单，仅软删除
                customer.is_deleted = True
                customer.save()
                messages.success(request, f'客户 {customer_name} 的删除申请已审批通过。由于该客户有关联订单，已执行软删除（标记为已删除）。')
            else:
                # 无关联订单，硬删除
                customer.delete()
                messages.success(request, f'客户 {customer_name} 的删除申请已审批通过，客户已删除')
        
        return redirect('sales:customer_list')
    
    context = {
        'customer': customer,
        'action': 'delete_approve',
    }
    return render(request, 'sales/customer_approve.html', context)


@login_required
@role_required('ceo')
def customer_delete_reject(request, pk):
    """总经理拒绝客户删除申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.delete_status != 'pending':
        messages.error(request, '该客户没有待审批的删除申请')
        return redirect('sales:customer_list')
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请填写拒绝原因')
            return redirect('sales:customer_delete_approve', pk=pk)
        
        with transaction.atomic():
            customer.delete_status = 'rejected'
            customer.delete_reject_reason = reject_reason
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的删除申请已拒绝')
        return redirect('sales:customer_list')
    
    context = {
        'customer': customer,
        'action': 'delete_reject',
    }
    return render(request, 'sales/customer_reject.html', context)


@login_required
@role_required('ceo', 'sales_mgr')
def customer_transfer(request):
    """客户转移（批量转移客户给指定销售人员）"""
    from django.contrib.auth.models import User
    
    if request.method == 'POST':
        customer_ids = request.POST.getlist('customer_ids')
        to_user_id = request.POST.get('to_user')
        remark = request.POST.get('remark', '').strip()
        
        if not customer_ids:
            messages.error(request, '请至少选择一个客户')
            return redirect('sales:customer_transfer')
        
        if not to_user_id:
            messages.error(request, '请选择新的负责人')
            return redirect('sales:customer_transfer')
        
        try:
            to_user = User.objects.get(pk=to_user_id)
            if to_user.profile.role != 'sales':
                messages.error(request, '只能将客户转移给销售人员')
                return redirect('sales:customer_transfer')
        except User.DoesNotExist:
            messages.error(request, '选择的用户不存在')
            return redirect('sales:customer_transfer')
        
        customers = Customer.objects.filter(pk__in=customer_ids)
        if not customers.exists():
            messages.error(request, '选择的客户不存在')
            return redirect('sales:customer_transfer')
        
        transferred_count = 0
        with transaction.atomic():
            for customer in customers:
                from_user = customer.created_by
                # 更新客户负责人
                customer.created_by = to_user
                customer.save()
                
                # 记录转移操作
                CustomerTransfer.objects.create(
                    customer=customer,
                    from_user=from_user,
                    to_user=to_user,
                    transferred_by=request.user,
                    remark=remark,
                )
                transferred_count += 1
        
        messages.success(request, f'成功将 {transferred_count} 个客户转移给 {to_user.username}')
        return redirect('sales:customer_list')
    
    # GET请求：显示转移页面
    customers = Customer.objects.select_related('created_by').all()
    
    # 权限检查：销售员只能看到自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    
    # 获取所有销售人员
    sales_users = User.objects.filter(profile__role='sales').order_by('username')
    
    context = {
        'customers': customers,
        'sales_users': sales_users,
    }
    return render(request, 'sales/customer_transfer.html', context)


@login_required
@role_required('ceo')
def customer_approval_list(request):
    """客户操作记录（只显示已完成的审批记录）"""
    # 已完成的编辑申请（已审批、已拒绝）
    edit_requests = Customer.objects.filter(
        edit_status__in=['approved', 'rejected']
    ).select_related('edit_requested_by', 'edit_approved_by').order_by('-edit_requested_at')
    
    # 已完成的删除申请（已审批、已拒绝）
    delete_requests = Customer.objects.filter(
        delete_status__in=['approved', 'rejected']
    ).select_related('delete_requested_by', 'delete_approved_by').order_by('-delete_requested_at')
    
    # 客户转移记录
    transfer_records = CustomerTransfer.objects.select_related(
        'customer', 'from_user', 'to_user', 'transferred_by'
    ).order_by('-transferred_at')
    
    context = {
        'edit_requests': edit_requests,
        'delete_requests': delete_requests,
        'transfer_records': transfer_records,
    }
    return render(request, 'sales/customer_approval_list.html', context)
