from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required
from .models import ProductionTask, MaterialRequisition, MaterialRequisitionItem, QCRecord, FinishedProductInbound
from inventory.models import BOM, Inventory, StockTransaction


@login_required
@role_required('production', 'ceo')
def task_list(request):
    """生产任务列表"""
    tasks = ProductionTask.objects.select_related('order', 'product').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    
    # 分页处理
    paginator = Paginator(tasks, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if status_filter:
        extra_params = f'status={status_filter}'
    
    context = {
        'tasks': page_obj,
        'status_filter': status_filter,
        'extra_params': extra_params,
    }
    return render(request, 'production/task_list.html', context)


@login_required
@role_required('production', 'ceo')
def task_detail(request, pk):
    """生产任务详情"""
    task = get_object_or_404(ProductionTask.objects.prefetch_related('material_requisitions__items'), pk=pk)
    
    # 获取BOM信息
    bom_items = BOM.objects.filter(product=task.product)
    
    # 计算每种原料的总需求量（BOM用量 × 需求数量）和缺口数量
    material_requirements = []
    total_materials_summary = {}  # {material_id: {'material': Material, 'total_quantity': Decimal, 'unit': str, 'available_quantity': Decimal, 'shortage': Decimal}}
    
    for bom_item in bom_items:
        total_required = bom_item.quantity * task.required_quantity
        
        # 获取当前库存
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            available_quantity = Decimal('0')
        
        # 计算缺口数量
        shortage = total_required - available_quantity
        if shortage < 0:
            shortage = Decimal('0')
        
        material_requirements.append({
            'material': bom_item.material,
            'material_id': bom_item.material.id,  # 用于JavaScript更新
            'bom_quantity': bom_item.quantity,  # 单位产品用量
            'total_required': total_required,  # 总需求量
            'available_quantity': available_quantity,  # 当前库存
            'shortage': shortage,  # 缺口数量
            'unit': bom_item.unit,
        })
        
        # 汇总到总原料统计中
        material_id = bom_item.material.id
        if material_id in total_materials_summary:
            total_materials_summary[material_id]['total_quantity'] += total_required
            # 更新可用库存和缺口（取最小值，因为同一原料可能在不同BOM中出现）
            try:
                inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
                available_qty = inventory.quantity
            except Inventory.DoesNotExist:
                available_qty = Decimal('0')
            total_shortage = total_materials_summary[material_id]['total_quantity'] - available_qty
            if total_shortage < 0:
                total_shortage = Decimal('0')
            total_materials_summary[material_id]['available_quantity'] = available_qty
            total_materials_summary[material_id]['shortage'] = total_shortage
        else:
            try:
                inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
                available_qty = inventory.quantity
            except Inventory.DoesNotExist:
                available_qty = Decimal('0')
            total_shortage = total_required - available_qty
            if total_shortage < 0:
                total_shortage = Decimal('0')
            total_materials_summary[material_id] = {
                'material': bom_item.material,
                'material_id': bom_item.material.id,
                'total_quantity': total_required,
                'available_quantity': available_qty,
                'shortage': total_shortage,
                'unit': bom_item.unit,
            }
    
    # 计算产品缺口数量
    shortage_quantity = task.required_quantity - task.completed_quantity
    if shortage_quantity < 0:
        shortage_quantity = 0  # 如果完成数量超过需求数量，缺口为0
    
    context = {
        'task': task,
        'bom_items': bom_items,
        'material_requirements': material_requirements,  # 每种产品所需原料
        'total_materials_summary': list(total_materials_summary.values()),  # 全部所需原料总数（汇总）
        'shortage_quantity': shortage_quantity,  # 缺口数量
    }
    return render(request, 'production/task_detail.html', context)


@login_required
@role_required('production', 'ceo')
def task_status_api(request, pk):
    """获取生产任务最新状态的API（用于动态更新）"""
    task = get_object_or_404(ProductionTask, pk=pk)
    
    # 计算产品缺口数量
    shortage_quantity = task.required_quantity - task.completed_quantity
    if shortage_quantity < 0:
        shortage_quantity = 0
    
    # 计算每种原料的缺口数量
    bom_items = BOM.objects.filter(product=task.product)
    material_shortages = {}
    
    for bom_item in bom_items:
        total_required = bom_item.quantity * task.required_quantity
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            available_quantity = Decimal('0')
        
        shortage = total_required - available_quantity
        if shortage < 0:
            shortage = Decimal('0')
        
        material_shortages[bom_item.material.id] = {
            'total_required': float(total_required),
            'available_quantity': float(available_quantity),
            'shortage': float(shortage),
        }
    
    return JsonResponse({
        'completed_quantity': float(task.completed_quantity),
        'required_quantity': float(task.required_quantity),
        'shortage_quantity': float(shortage_quantity),
        'status': task.status,
        'status_display': task.get_status_display(),
        'material_shortages': material_shortages,  # 每种原料的缺口信息
    })


@login_required
@role_required('production', 'ceo')
def task_receive(request, pk):
    """接收生产任务"""
    task = get_object_or_404(ProductionTask, pk=pk)
    
    # 只能接收待接收或原料不足状态的任务
    if task.status not in ['pending', 'material_insufficient']:
        messages.error(request, '任务状态不正确，只能接收待接收或原料不足状态的任务')
        return redirect('production:task_detail', pk=pk)
    
    # 检查原材料是否充足
    bom_items = BOM.objects.filter(product=task.product)
    insufficient_materials = []
    all_sufficient = True
    
    for bom_item in bom_items:
        total_required = bom_item.quantity * task.required_quantity
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            available_quantity = Decimal('0')
        
        if available_quantity < total_required:
            all_sufficient = False
            shortage = total_required - available_quantity
            insufficient_materials.append({
                'material': bom_item.material,
                'required': total_required,
                'available': available_quantity,
                'shortage': shortage,
                'unit': bom_item.unit,
            })
    
    if request.method == 'POST':
        if not all_sufficient:
            # 原材料不足，更新状态为原料不足
            task.status = 'material_insufficient'
            task.save()
            messages.warning(request, f'任务 {task.task_no} 原材料不足，无法接收。请先采购补齐原材料。')
            return redirect('production:task_detail', pk=pk)
        
        # 原材料充足，可以接收
        task.status = 'in_production'  # 直接进入生产中状态
        task.received_by = request.user
        task.received_at = timezone.now()
        task.started_at = timezone.now()
        task.save()
        
        # 自动创建领料单并扣减库存
        requisition = create_material_requisition(task)
        if requisition:
            # 自动批准领料单并扣减库存
            from inventory.models import StockTransaction
            requisition.status = 'approved'
            requisition.approved_by = request.user
            requisition.approved_at = timezone.now()
            requisition.save()
            
            # 扣减库存
            for item in requisition.items.all():
                inventory = Inventory.objects.get(inventory_type='material', material=item.material)
                inventory.quantity -= item.required_quantity
                inventory.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='production_out',
                    inventory=inventory,
                    quantity=item.required_quantity,
                    unit=item.unit,
                    reference_no=requisition.requisition_no,
                    operator=request.user,
                )
        
        messages.success(request, f'任务 {task.task_no} 已接收，已进入生产中状态')
        return redirect('production:task_detail', pk=pk)
    
    # GET请求：显示接收页面，包含原材料检查结果
    context = {
        'task': task,
        'insufficient_materials': insufficient_materials,
        'all_sufficient': all_sufficient,
    }
    return render(request, 'production/task_receive.html', context)


def create_material_requisition(task):
    """根据BOM自动创建领料单"""
    from inventory.models import BOM
    
    bom_items = BOM.objects.filter(product=task.product)
    
    if not bom_items.exists():
        return None
    
    requisition = MaterialRequisition.objects.create(
        requisition_no=f"MR{timezone.now().strftime('%Y%m%d%H%M%S')}",
        task=task,
        status='pending',
        requested_by=task.received_by,
    )
    
    for bom_item in bom_items:
        required_qty = bom_item.quantity * task.required_quantity
        MaterialRequisitionItem.objects.create(
            requisition=requisition,
            material=bom_item.material,
            required_quantity=required_qty,
            unit=bom_item.unit,
        )
    
    return requisition


@login_required
@role_required('warehouse', 'ceo')
def requisition_list(request):
    """领料单列表"""
    requisitions = MaterialRequisition.objects.select_related('task', 'requested_by').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        requisitions = requisitions.filter(status=status_filter)
    
    # 分页处理
    paginator = Paginator(requisitions, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if status_filter:
        extra_params = f'status={status_filter}'
    
    context = {
        'requisitions': page_obj,
        'status_filter': status_filter,
        'extra_params': extra_params,
    }
    return render(request, 'production/requisition_list.html', context)


@login_required
@role_required('warehouse', 'ceo')
def requisition_approve(request, pk):
    """审核领料单"""
    requisition = get_object_or_404(MaterialRequisition.objects.prefetch_related('items__material'), pk=pk)
    
    if requisition.status != 'pending':
        messages.error(request, '领料单状态不正确')
        return redirect('production:requisition_list')
    
    # 检查库存是否充足
    insufficient_items = []
    for item in requisition.items.all():
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=item.material)
            if inventory.quantity < item.required_quantity:
                insufficient_items.append({
                    'material': item.material.name,
                    'required': item.required_quantity,
                    'available': inventory.quantity,
                })
        except Inventory.DoesNotExist:
            insufficient_items.append({
                'material': item.material.name,
                'required': item.required_quantity,
                'available': 0,
            })
    
    if request.method == 'POST':
        if insufficient_items:
            messages.error(request, '部分原料库存不足，无法批准')
            return redirect('production:requisition_approve', pk=pk)
        
        with transaction.atomic():
            requisition.status = 'approved'
            requisition.approved_by = request.user
            requisition.approved_at = timezone.now()
            requisition.save()
            
            # 扣减库存
            for item in requisition.items.all():
                inventory = Inventory.objects.get(inventory_type='material', material=item.material)
                inventory.quantity -= item.required_quantity
                inventory.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='production_out',
                    inventory=inventory,
                    quantity=item.required_quantity,
                    unit=item.unit,
                    reference_no=requisition.requisition_no,
                    operator=request.user,
                )
            
            requisition.task.status = 'material_preparing'
            requisition.task.save()
            
            messages.success(request, f'领料单 {requisition.requisition_no} 已批准，库存已扣减')
            return redirect('production:requisition_list')
    
    context = {
        'requisition': requisition,
        'insufficient_items': insufficient_items,
    }
    return render(request, 'production/requisition_approve.html', context)


@login_required
@role_required('production', 'ceo')
def task_complete(request, pk):
    """完成生产，进入质检环节"""
    task = get_object_or_404(ProductionTask, pk=pk)
    
    if task.status != 'in_production':
        messages.error(request, '只能完成处于生产中状态的任务')
        return redirect('production:task_detail', pk=pk)
    
    if request.method == 'POST':
        task.status = 'qc_checking'
        task.save()
        messages.success(request, f'任务 {task.task_no} 已完成生产，已进入质检环节')
        return redirect('production:task_detail', pk=pk)
    
    return render(request, 'production/task_complete.html', {'task': task})


@login_required
@role_required('qc', 'ceo')
def qc_create(request, task_pk):
    """创建质检记录"""
    task = get_object_or_404(ProductionTask, pk=task_pk)
    
    if request.method == 'POST':
        batch_no = request.POST.get('batch_no')
        inspected_qty = float(request.POST.get('inspected_quantity'))
        qualified_qty = float(request.POST.get('qualified_quantity'))
        unqualified_qty = float(request.POST.get('unqualified_quantity', 0))
        result = request.POST.get('result')
        remark = request.POST.get('remark', '')
        
        qualification_rate = (qualified_qty / inspected_qty * 100) if inspected_qty > 0 else 0
        
        qc_record = QCRecord.objects.create(
            task=task,
            batch_no=batch_no,
            inspected_quantity=inspected_qty,
            qualified_quantity=qualified_qty,
            unqualified_quantity=unqualified_qty,
            qualification_rate=qualification_rate,
            result=result,
            inspector=request.user,
            remark=remark,
        )
        
        if result == 'qualified':
            task.status = 'qc_checking'
            task.save()
            messages.success(request, '质检记录已创建，可以入库')
        else:
            messages.warning(request, '质检不合格，需要返工或报废')
        
        return redirect('production:task_detail', pk=task_pk)
    
    return render(request, 'production/qc_form.html', {'task': task})


@login_required
@role_required('warehouse', 'ceo')
def inbound_create(request, task_pk):
    """创建成品入库单"""
    task = get_object_or_404(ProductionTask, pk=task_pk)
    
    if request.method == 'POST':
        try:
            quantity_str = request.POST.get('quantity', '').strip()
            if not quantity_str:
                messages.error(request, '请输入入库数量')
                return redirect('production:inbound_create', task_pk=task_pk)
            
            quantity = Decimal(quantity_str)
            if quantity <= 0:
                messages.error(request, '入库数量必须大于0')
                return redirect('production:inbound_create', task_pk=task_pk)
            
            qc_record_id = request.POST.get('qc_record_id', '').strip()
            qc_record = None
            if qc_record_id:
                try:
                    qc_record = QCRecord.objects.get(pk=qc_record_id, task=task)
                except QCRecord.DoesNotExist:
                    messages.error(request, '质检记录不存在')
                    return redirect('production:inbound_create', task_pk=task_pk)
            
            with transaction.atomic():
                # 生成唯一的入库单号
                import random
                inbound_no = f"IN{timezone.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                # 确保入库单号唯一
                while FinishedProductInbound.objects.filter(inbound_no=inbound_no).exists():
                    inbound_no = f"IN{timezone.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                
                inbound = FinishedProductInbound.objects.create(
                    inbound_no=inbound_no,
                    task=task,
                    qc_record=qc_record,
                    quantity=quantity,
                    unit=task.product.unit,
                    operator=request.user,
                )
                
                # 增加成品库存
                inventory, created = Inventory.objects.get_or_create(
                    inventory_type='product',
                    product=task.product,
                    defaults={'quantity': 0, 'unit': task.product.unit}
                )
                inventory.quantity += quantity
                inventory.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='production_in',
                    inventory=inventory,
                    quantity=quantity,
                    unit=task.product.unit,
                    reference_no=inbound.inbound_no,
                    operator=request.user,
                )
                
                # 更新任务完成数量
                task.completed_quantity += quantity
                if task.completed_quantity >= task.required_quantity:
                    task.status = 'completed'
                    task.completed_at = timezone.now()
                task.save()
                
                # 检查订单是否可以发货
                check_order_ready_to_ship(task.order)
                
                messages.success(request, f'入库单 {inbound.inbound_no} 创建成功')
                return redirect('production:task_detail', pk=task_pk)
        except ValueError:
            messages.error(request, '入库数量格式不正确')
            return redirect('production:inbound_create', task_pk=task_pk)
        except Exception as e:
            messages.error(request, f'创建入库单失败：{str(e)}')
            return redirect('production:inbound_create', task_pk=task_pk)
    
    qc_records = QCRecord.objects.filter(task=task, result='qualified')
    context = {
        'task': task,
        'qc_records': qc_records,
    }
    return render(request, 'production/inbound_form.html', context)


def check_order_ready_to_ship(order):
    """检查订单是否可以发货"""
    from sales.models import ShippingNotice
    
    # 检查所有订单项是否都有足够库存
    all_ready = True
    for item in order.items.all():
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=item.product)
            if inventory.quantity < item.quantity:
                all_ready = False
                break
        except Inventory.DoesNotExist:
            all_ready = False
            break
    
    if all_ready and order.status == 'in_production':
        # 创建发货通知单
        ShippingNotice.objects.get_or_create(
            order=order,
            defaults={
                'notice_no': f"SN{timezone.now().strftime('%Y%m%d%H%M%S')}",
                'status': 'pending',
            }
        )
        order.status = 'ready_to_ship'
        order.save()


@login_required
@role_required('ceo')
def task_terminate(request, pk):
    """总经理终结生产任务（终结整个链路）"""
    from sales.views import terminate_order_chain
    
    task = get_object_or_404(ProductionTask, pk=pk)
    
    # 只能终结进行中的任务
    active_statuses = ['received', 'material_preparing', 'in_production', 'qc_checking']
    if task.status not in active_statuses:
        messages.error(request, '只能终结进行中的任务（已接收、备料中、生产中、质检中）')
        return redirect('production:task_detail', pk=pk)
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'production/task_terminate.html', {'task': task})
        
        # 向上追溯到销售订单，终结整个链路
        order = task.order
        # 导入终结函数（避免循环导入）
        from sales.views import terminate_order_chain
        terminate_order_chain(order, request.user, f"通过生产任务 {task.task_no} 终结：{terminate_reason}")
        
        messages.success(request, f'生产任务 {task.task_no} 及其关联订单 {order.order_no} 的所有流程已终结')
        return redirect('production:task_detail', pk=pk)
    
    # 显示关联信息
    order = task.order
    requisitions = MaterialRequisition.objects.filter(task=task)
    
    context = {
        'task': task,
        'order': order,
        'requisitions': requisitions,
    }
    return render(request, 'production/task_terminate.html', context)


@login_required
@role_required('ceo')
def requisition_terminate(request, pk):
    """总经理终结领料单（终结整个链路）"""
    requisition = get_object_or_404(MaterialRequisition, pk=pk)
    
    # 只能终结进行中的领料单
    active_statuses = ['pending', 'approved', 'issued']
    if requisition.status not in active_statuses:
        messages.error(request, '只能终结进行中的领料单（待审核、已批准、已发料）')
        return redirect('production:requisition_list')
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'production/requisition_terminate.html', {'requisition': requisition})
        
        # 向上追溯到销售订单，终结整个链路
        task = requisition.task
        order = task.order
        # 导入终结函数（避免循环导入）
        from sales.views import terminate_order_chain
        terminate_order_chain(order, request.user, f"通过领料单 {requisition.requisition_no} 终结：{terminate_reason}")
        
        messages.success(request, f'领料单 {requisition.requisition_no} 及其关联订单 {order.order_no} 的所有流程已终结')
        return redirect('production:requisition_list')
    
    # 显示关联信息
    task = requisition.task
    order = task.order
    
    context = {
        'requisition': requisition,
        'task': task,
        'order': order,
    }
    return render(request, 'production/requisition_terminate.html', context)
