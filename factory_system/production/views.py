from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
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
    
    context = {
        'tasks': tasks,
        'status_filter': status_filter,
    }
    return render(request, 'production/task_list.html', context)


@login_required
@role_required('production', 'ceo')
def task_detail(request, pk):
    """生产任务详情"""
    task = get_object_or_404(ProductionTask.objects.prefetch_related('material_requisitions__items'), pk=pk)
    
    # 获取BOM信息
    bom_items = BOM.objects.filter(product=task.product)
    
    context = {
        'task': task,
        'bom_items': bom_items,
    }
    return render(request, 'production/task_detail.html', context)


@login_required
@role_required('production', 'ceo')
def task_receive(request, pk):
    """接收生产任务"""
    task = get_object_or_404(ProductionTask, pk=pk)
    
    if task.status != 'pending':
        messages.error(request, '任务状态不正确')
        return redirect('production:task_detail', pk=pk)
    
    if request.method == 'POST':
        task.status = 'received'
        task.received_by = request.user
        task.received_at = timezone.now()
        task.save()
        
        # 自动创建领料单
        create_material_requisition(task)
        
        messages.success(request, f'任务 {task.task_no} 已接收，领料单已生成')
        return redirect('production:task_detail', pk=pk)
    
    return render(request, 'production/task_receive.html', {'task': task})


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
    
    context = {
        'requisitions': requisitions,
        'status_filter': status_filter,
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
        quantity = float(request.POST.get('quantity'))
        qc_record_id = request.POST.get('qc_record_id')
        
        qc_record = None
        if qc_record_id:
            qc_record = QCRecord.objects.get(pk=qc_record_id)
        
        with transaction.atomic():
            inbound = FinishedProductInbound.objects.create(
                inbound_no=f"IN{timezone.now().strftime('%Y%m%d%H%M%S')}",
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
