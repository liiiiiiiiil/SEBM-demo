from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required
from .models import PurchaseTask, PurchaseTaskItem
from inventory.models import Material, Inventory, StockTransaction


@login_required
@role_required('warehouse', 'ceo')
def task_list(request):
    """采购任务列表"""
    tasks = PurchaseTask.objects.select_related('created_by', 'approved_by', 'terminated_by').all()
    
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
    return render(request, 'purchase/task_list.html', context)


@login_required
@role_required('warehouse', 'ceo')
def task_create(request):
    """创建采购任务"""
    if request.method == 'POST':
        supplier = request.POST.get('supplier', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        # 获取采购明细
        material_ids = request.POST.getlist('material_id')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')
        
        if not supplier:
            messages.error(request, '请输入供应商名称')
            return redirect('purchase:task_create')
        
        if not material_ids or not all(material_ids):
            messages.error(request, '请至少添加一个采购明细')
            return redirect('purchase:task_create')
        
        with transaction.atomic():
            task = PurchaseTask.objects.create(
                task_no=f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}",
                supplier=supplier,
                contact_person=contact_person,
                contact_phone=contact_phone,
                status='pending',
                created_by=request.user,
                remark=remark,
            )
            
            total_amount = Decimal('0')
            for material_id, quantity_str, unit_price_str in zip(material_ids, quantities, unit_prices):
                if not material_id or not quantity_str or not unit_price_str:
                    continue
                
                material = Material.objects.get(pk=material_id)
                quantity = Decimal(quantity_str)
                unit_price = Decimal(unit_price_str)
                subtotal = quantity * unit_price
                
                PurchaseTaskItem.objects.create(
                    task=task,
                    material=material,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=subtotal,
                )
                total_amount += subtotal
            
            task.total_amount = total_amount
            task.save()
            
            messages.success(request, f'采购任务 {task.task_no} 创建成功，等待审批')
            return redirect('purchase:task_list')
    
    # GET 请求：显示创建表单
    materials = Material.objects.all().order_by('sku')
    context = {
        'materials': materials,
    }
    return render(request, 'purchase/task_form.html', context)


@login_required
@role_required('warehouse', 'ceo')
def task_detail(request, pk):
    """采购任务详情"""
    task = get_object_or_404(PurchaseTask.objects.prefetch_related('items__material'), pk=pk)
    
    context = {
        'task': task,
    }
    return render(request, 'purchase/task_detail.html', context)


@login_required
@role_required('ceo')
def task_approve(request, pk):
    """总经理审批采购任务"""
    task = get_object_or_404(PurchaseTask.objects.prefetch_related('items__material'), pk=pk)
    
    if task.status != 'pending':
        messages.error(request, '只能审批待审批状态的采购任务')
        return redirect('purchase:task_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            task.status = 'approved'
            task.approved_by = request.user
            task.approved_at = timezone.now()
            task.save()
            
            messages.success(request, f'采购任务 {task.task_no} 已审批通过，可以开始采购')
            return redirect('purchase:task_detail', pk=pk)
    
    return render(request, 'purchase/task_approve.html', {'task': task})


@login_required
@role_required('warehouse', 'ceo')
def task_complete(request, pk):
    """完成采购任务（直接入库）"""
    task = get_object_or_404(PurchaseTask.objects.prefetch_related('items__material'), pk=pk)
    
    if task.status not in ['approved', 'purchasing']:
        messages.error(request, '只能完成已审批或采购中的任务')
        return redirect('purchase:task_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            # 更新收货数量并增加库存
            for item in task.items.all():
                received_qty_str = request.POST.get(f'received_quantity_{item.id}', '0')
                if received_qty_str:
                    received_qty = Decimal(received_qty_str)
                    if received_qty > 0:
                        item.received_quantity = received_qty
                        item.save()
                        
                        # 增加物料库存
                        inventory, created = Inventory.objects.get_or_create(
                            inventory_type='material',
                            material=item.material,
                            defaults={'quantity': 0, 'unit': item.material.unit}
                        )
                        inventory.quantity += received_qty
                        inventory.save()
                        
                        # 记录库存变动
                        StockTransaction.objects.create(
                            transaction_type='purchase_in',
                            inventory=inventory,
                            quantity=received_qty,
                            unit=item.material.unit,
                            reference_no=task.task_no,
                            operator=request.user,
                        )
            
            # 检查是否全部收货
            all_received = all(
                item.received_quantity >= item.quantity 
                for item in task.items.all()
            )
            
            if all_received:
                task.status = 'completed'
            else:
                task.status = 'purchasing'
            
            task.save()
            
            messages.success(request, f'采购任务 {task.task_no} 收货完成，库存已更新')
            return redirect('purchase:task_detail', pk=pk)
    
    return render(request, 'purchase/task_complete.html', {'task': task})


@login_required
@role_required('ceo')
def task_terminate(request, pk):
    """总经理终结采购任务"""
    task = get_object_or_404(PurchaseTask, pk=pk)
    
    # 只能终结进行中的任务
    active_statuses = ['pending', 'approved', 'purchasing']
    if task.status not in active_statuses:
        messages.error(request, '只能终结进行中的采购任务（待审批、已审批、采购中）')
        return redirect('purchase:task_detail', pk=pk)
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'purchase/task_terminate.html', {'task': task})
        
        task.status = 'terminated'
        task.terminated_by = request.user
        task.terminated_at = timezone.now()
        task.terminate_reason = terminate_reason
        task.save()
        
        messages.success(request, f'采购任务 {task.task_no} 已终结')
        return redirect('purchase:task_detail', pk=pk)
    
    return render(request, 'purchase/task_terminate.html', {'task': task})
