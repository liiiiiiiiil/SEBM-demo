from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
import json
from accounts.decorators import role_required
from .models import SalesOrder, SalesOrderItem, ShippingNotice
from inventory.models import Customer, Product, Inventory
from production.models import ProductionTask, MaterialRequisition


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
    paginator = Paginator(orders, 20)  # 每页20条
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
    
    # 获取产品库存数据用于前端显示
    import json
    products = Product.objects.all()
    product_inventory_data = {}
    for product in products:
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=product)
            product_inventory_data[str(product.pk)] = {
                'quantity': float(inventory.quantity),
                'unit': inventory.unit,
                'unit_price': float(product.unit_price) if product.unit_price else 0.0
            }
        except Inventory.DoesNotExist:
            product_inventory_data[str(product.pk)] = {
                'quantity': 0,
                'unit': product.unit,
                'unit_price': float(product.unit_price) if product.unit_price else 0.0
            }
    
    product_inventory_data_json = json.dumps(product_inventory_data)
    
    return render(request, 'sales/order_form.html', {
        'form': form, 
        'formset': formset, 
        'title': title, 
        'order': order,
        'product_inventory_data_json': product_inventory_data_json
    })


@login_required
@role_required('sales', 'sales_mgr', 'warehouse', 'ceo')
def order_detail(request, pk):
    """订单详情"""
    order = get_object_or_404(SalesOrder.objects.prefetch_related('items__product'), pk=pk)
    
    # 权限检查：销售员只能看自己的订单，总经理和销售经理可以看所有订单
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
            order.status = 'ceo_pending'  # 销售审批后进入总经理审批
            order.approved_by = request.user
            order.approved_at = timezone.now()
            # 清除退回信息（如果之前被退回过）
            order.rejected_by = None
            order.rejected_at = None
            order.reject_reason = ''
            order.save()
            
            messages.success(request, f'订单 {order.order_no} 销售审批通过，已提交至总经理审批')
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
@role_required('ceo')
def ceo_approve(request, pk):
    """总经理审批订单"""
    order = get_object_or_404(SalesOrder, pk=pk)
    
    if order.status != 'ceo_pending':
        messages.error(request, '订单状态不正确，只能审批待总经理审批的订单')
        return redirect('sales:order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
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
        # 1. 检查订单是否已出库，如果已出库，需要重新入库
        if order.status == 'shipped':
            # 查找该订单的所有已发货的发货单
            shipped_shipments = Shipment.objects.filter(
                order=order,
                status__in=['shipped', 'delivered']
            )
            
            if shipped_shipments.exists():
                # 对于已发货的商品，需要重新入库
                for item in order.items.all():
                    try:
                        inventory = Inventory.objects.get(
                            inventory_type='product',
                            product=item.product
                        )
                        # 重新入库：增加库存
                        inventory.quantity += item.quantity
                        inventory.save()
                        
                        # 记录库存变动（使用adjustment类型，备注说明是终结退回）
                        StockTransaction.objects.create(
                            transaction_type='adjustment',
                            inventory=inventory,
                            quantity=item.quantity,
                            unit=item.product.unit,
                            reference_no=f"TERMINATE-{order.order_no}",
                            remark=f"订单终结退回：{terminate_reason}",
                            operator=terminated_by,
                        )
                    except Inventory.DoesNotExist:
                        # 如果库存不存在，创建新的库存记录
                        inventory = Inventory.objects.create(
                            inventory_type='product',
                            product=item.product,
                            quantity=item.quantity,
                            unit=item.product.unit,
                        )
                        # 记录库存变动
                        StockTransaction.objects.create(
                            transaction_type='adjustment',
                            inventory=inventory,
                            quantity=item.quantity,
                            unit=item.product.unit,
                            reference_no=f"TERMINATE-{order.order_no}",
                            remark=f"订单终结退回：{terminate_reason}",
                            operator=terminated_by,
                        )
        
        # 2. 检查订单是否在审核时锁定了库存（ready_to_ship状态但未发货）
        # 如果订单状态是ready_to_ship，说明审核时库存充足，已经锁定了库存
        # 需要退回锁定的库存
        if order.status == 'ready_to_ship':
            # 对于审核时锁定库存的商品，需要退回库存
            for item in order.items.all():
                # 检查该商品是否有生产任务
                from production.models import ProductionTask
                has_production_task = ProductionTask.objects.filter(
                    order=order,
                    product=item.product
                ).exists()
                
                # 如果没有生产任务，说明审核时库存充足，已经锁定了库存
                if not has_production_task:
                    try:
                        inventory = Inventory.objects.get(
                            inventory_type='product',
                            product=item.product
                        )
                        # 退回锁定的库存：增加库存
                        inventory.quantity += item.quantity
                        inventory.save()
                        
                        # 记录库存变动
                        StockTransaction.objects.create(
                            transaction_type='adjustment',
                            inventory=inventory,
                            quantity=item.quantity,
                            unit=item.product.unit,
                            reference_no=f"TERMINATE-{order.order_no}",
                            remark=f"订单终结退回锁定库存：{terminate_reason}",
                            operator=terminated_by,
                        )
                    except Inventory.DoesNotExist:
                        # 如果库存不存在，创建新的库存记录
                        inventory = Inventory.objects.create(
                            inventory_type='product',
                            product=item.product,
                            quantity=item.quantity,
                            unit=item.product.unit,
                        )
                        # 记录库存变动
                        StockTransaction.objects.create(
                            transaction_type='adjustment',
                            inventory=inventory,
                            quantity=item.quantity,
                            unit=item.product.unit,
                            reference_no=f"TERMINATE-{order.order_no}",
                            remark=f"订单终结退回锁定库存：{terminate_reason}",
                            operator=terminated_by,
                        )
        
        # 2. 终结销售订单
        order.status = 'terminated'
        order.terminated_by = terminated_by
        order.terminated_at = timezone.now()
        order.terminate_reason = terminate_reason
        order.save()
        
        # 3. 终结所有关联的生产任务
        production_tasks = ProductionTask.objects.filter(order=order)
        for task in production_tasks:
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
    shipping_notices = ShippingNotice.objects.filter(order=order)
    
    context = {
        'order': order,
        'production_tasks': production_tasks,
        'requisitions': requisitions,
        'shipping_notices': shipping_notices,
    }
    return render(request, 'sales/order_terminate.html', context)


def check_inventory_status(order):
    """检查库存状态（不实际创建任务，仅用于显示判断结果）"""
    from inventory.models import BOM
    from decimal import Decimal
    
    result = {
        'all_sufficient': True,
        'items': [],
        'material_requirements': {},  # 汇总所有原料需求 {material_id: {'material': Material, 'required': Decimal, 'available': Decimal, 'shortage': Decimal}}
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
        
        shortage = max(Decimal('0'), item.quantity - available_qty)
        item_result = {
            'product': item.product,
            'required_quantity': item.quantity,
            'available_quantity': available_qty,
            'sufficient': available_qty >= item.quantity,
            'shortage': shortage,
            'material_needs': [],  # 该产品缺口所需的原料列表
        }
        
        # 如果有缺口，计算生产缺口产品所需的原料
        if shortage > 0:
            bom_items = BOM.objects.filter(product=item.product)
            for bom_item in bom_items:
                # 计算生产缺口数量所需该原料的数量
                material_required = bom_item.quantity * shortage
                
                # 获取该原料的库存
                try:
                    material_inventory = Inventory.objects.get(
                        inventory_type='material',
                        material=bom_item.material
                    )
                    material_available = material_inventory.quantity
                except Inventory.DoesNotExist:
                    material_available = Decimal('0')
                
                material_shortage = max(Decimal('0'), material_required - material_available)
                
                # 记录该产品的原料需求
                item_result['material_needs'].append({
                    'material': bom_item.material,
                    'required': material_required,
                    'available': material_available,
                    'shortage': material_shortage,
                    'unit': bom_item.unit,
                })
                
                # 汇总到总原料需求中
                material_id = bom_item.material.id
                if material_id not in result['material_requirements']:
                    result['material_requirements'][material_id] = {
                        'material': bom_item.material,
                        'required': Decimal('0'),
                        'available': material_available,
                        'shortage': Decimal('0'),
                        'unit': bom_item.unit,
                    }
                result['material_requirements'][material_id]['required'] += material_required
                result['material_requirements'][material_id]['shortage'] = max(
                    Decimal('0'),
                    result['material_requirements'][material_id]['required'] - 
                    result['material_requirements'][material_id]['available']
                )
        
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
                
                # 检查原材料是否充足
                from inventory.models import BOM
                material_sufficient = True
                bom_items = BOM.objects.filter(product=item.product)
                for bom_item in bom_items:
                    material_required = bom_item.quantity * shortage
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
                
                # 创建生产任务，根据原材料是否充足设置状态
                task_status = 'pending' if material_sufficient else 'material_insufficient'
                task = ProductionTask.objects.create(
                    task_no=f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}{order.pk}",
                    order=order,
                    product=item.product,
                    required_quantity=shortage,
                    status=task_status,
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
