from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required
from .models import PurchaseTask, PurchaseTaskItem, Supplier
from inventory.models import Material, Inventory, StockTransaction, Batch, BOM
from production.models import ProductionTask
from django.db.models import Q


@login_required
@role_required('warehouse', 'ceo')
def task_list(request):
    """采购任务列表"""
    tasks = PurchaseTask.objects.select_related('created_by', 'approved_by', 'terminated_by').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    
    paginator = Paginator(tasks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
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
def task_create_from_production(request, production_task_pk):
    """从生产任务跳转到采购任务创建页面（预填所需原料）"""
    production_task = get_object_or_404(
        ProductionTask.objects.select_related('product', 'product__base_unit', 'product__display_unit'),
        pk=production_task_pk,
    )
    
    bom_items = BOM.objects.filter(product=production_task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
    insufficient_materials = []

    for bom_item in bom_items:
        total_required_base = production_task.required_quantity * bom_item.get_base_quantity()
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_base = inventory.quantity
        except Inventory.DoesNotExist:
            available_base = Decimal('0')

        if available_base < total_required_base:
            mat = bom_item.material
            shortage_base = total_required_base - available_base
            shortage_disp, _ = mat.to_display(shortage_base)
            insufficient_materials.append({
                'material': mat,
                'shortage': shortage_disp,
                'unit': mat.display_unit.name,
            })
    
    if not insufficient_materials:
        messages.info(request, '该生产任务的原材料充足，无需采购')
        return redirect('purchase:task_create')
    
    material_ids = ','.join([str(m['material'].id) for m in insufficient_materials])
    quantities = ','.join([str(m['shortage']) for m in insufficient_materials])
    
    return redirect(f"{reverse('purchase:task_create')}?from_production={production_task_pk}&materials={material_ids}&quantities={quantities}")


@login_required
@role_required('warehouse', 'ceo')
def task_create(request):
    """创建采购任务"""
    from_production_task_pk = request.GET.get('from_production')
    prefill_materials = []
    production_task = None
    
    if from_production_task_pk:
        try:
            production_task = ProductionTask.objects.select_related('product').get(pk=from_production_task_pk)
            material_ids_str = request.GET.get('materials', '')
            quantities_str = request.GET.get('quantities', '')
            
            if material_ids_str and quantities_str:
                material_ids = [int(id) for id in material_ids_str.split(',') if id]
                quantities = [Decimal(q) for q in quantities_str.split(',') if q]
                
                for material_id, quantity in zip(material_ids, quantities):
                    try:
                        material = Material.objects.select_related('base_unit', 'display_unit').get(pk=material_id)
                        prefill_materials.append({
                            'material': material,
                            'quantity': quantity,
                            'unit': material.display_unit.name,
                        })
                    except Material.DoesNotExist:
                        pass
        except (ProductionTask.DoesNotExist, ValueError):
            pass
    
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        material_ids = request.POST.getlist('material_id')
        item_names = request.POST.getlist('item_name')
        item_types = request.POST.getlist('item_type')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')
        
        if not supplier_id:
            messages.error(request, '请选择供应商')
            return redirect('purchase:task_create')
        
        try:
            supplier = Supplier.objects.get(pk=supplier_id)
        except Supplier.DoesNotExist:
            messages.error(request, '选择的供应商不存在')
            return redirect('purchase:task_create')
        
        has_valid_item = False
        for i in range(len(quantities)):
            material_id = material_ids[i] if i < len(material_ids) else ''
            item_name = item_names[i] if i < len(item_names) else ''
            quantity_str = quantities[i] if i < len(quantities) else ''
            unit_price_str = unit_prices[i] if i < len(unit_prices) else ''
            
            if (material_id or item_name) and quantity_str and unit_price_str:
                has_valid_item = True
                break
        
        if not has_valid_item:
            messages.error(request, '请至少添加一个采购明细')
            return redirect('purchase:task_create')
        
        with transaction.atomic():
            task = PurchaseTask.objects.create(
                task_no=f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}",
                supplier=supplier,
                status='pending',
                created_by=request.user,
                remark=remark,
            )
            
            total_amount = Decimal('0')
            max_len = max(len(material_ids), len(item_names), len(quantities), len(unit_prices))
            
            for i in range(max_len):
                material_id = material_ids[i] if i < len(material_ids) else ''
                item_name = item_names[i].strip() if i < len(item_names) else ''
                item_type = item_types[i] if i < len(item_types) else 'material'
                quantity_str = quantities[i] if i < len(quantities) else ''
                unit_price_str = unit_prices[i] if i < len(unit_prices) else ''
                
                if not quantity_str or not unit_price_str:
                    continue
                
                if not material_id and not item_name:
                    continue
                
                quantity = Decimal(quantity_str)
                unit_price = Decimal(unit_price_str)
                subtotal = quantity * unit_price
                
                material = None
                if material_id:
                    material = Material.objects.select_related('base_unit', 'display_unit').get(pk=material_id)
                    item_name = material.name
                    item_type = 'material'
                
                PurchaseTaskItem.objects.create(
                    task=task,
                    material=material,
                    item_name=item_name,
                    item_type=item_type,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=subtotal,
                    # display_unit / display_quantity 可在后续扩展中由前端传入
                )
                total_amount += subtotal
            
            task.total_amount = total_amount
            task.save()
            
            messages.success(request, f'采购任务 {task.task_no} 创建成功，等待审批')
            return redirect('purchase:task_list')
    
    materials = Material.objects.select_related('base_unit', 'display_unit').all().order_by('sku')
    suppliers = Supplier.objects.all().order_by('name')
    
    import json
    prefill_materials_json = json.dumps([
        {
            'material_id': item['material'].id,
            'material_name': item['material'].name,
            'quantity': str(item['quantity']),
            'unit': item['unit'],
            'unit_price': str(item['material'].unit_price or 0),
        }
        for item in prefill_materials
    ])
    
    context = {
        'materials': materials,
        'suppliers': suppliers,
        'prefill_materials': prefill_materials_json,
        'production_task': production_task,
    }
    return render(request, 'purchase/task_form.html', context)


@login_required
@role_required('warehouse', 'ceo')
def task_detail(request, pk):
    """采购任务详情"""
    task = get_object_or_404(
        PurchaseTask.objects.prefetch_related('items__material', 'items__material__base_unit'),
        pk=pk,
    )
    
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
    task = get_object_or_404(
        PurchaseTask.objects.prefetch_related('items__material', 'items__material__base_unit'),
        pk=pk,
    )
    
    if task.status not in ['approved', 'purchasing']:
        messages.error(request, '只能完成已审批或采购中的任务')
        return redirect('purchase:task_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            for item in task.items.select_related('material', 'material__base_unit', 'material__display_unit'):
                received_qty_str = request.POST.get(f'received_quantity_{item.id}', '0')
                if received_qty_str:
                    received_qty_display = Decimal(received_qty_str)
                    if received_qty_display > 0:
                        inventory = None
                        mat = item.material
                        if mat:
                            inventory, created = Inventory.objects.get_or_create(
                                inventory_type='material',
                                material=mat,
                                defaults={'quantity': 0}
                            )
                        elif item.item_type in ['office', 'other']:
                            inventory, created = Inventory.objects.get_or_create(
                                inventory_type='other',
                                other_name=item.item_name,
                                defaults={'quantity': 0}
                            )
                        
                        if not inventory:
                            continue
                        
                        # 将显示单位数量转为基础单位（用于 Batch 存储）
                        if mat and hasattr(mat, 'from_display'):
                            received_qty_base = mat.from_display(received_qty_display)
                        else:
                            received_qty_base = received_qty_display
                        
                        batch_date_str = request.POST.get(f'batch_date_{item.id}', '')
                        batch_no = request.POST.get(f'batch_no_{item.id}', '')
                        batch_unit_price_str = request.POST.get(f'batch_unit_price_{item.id}', '')
                        expiry_date_str = request.POST.get(f'expiry_date_{item.id}', '')
                        
                        from django.utils import timezone
                        from datetime import datetime
                        
                        batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date() if batch_date_str else timezone.now().date()
                        
                        if not batch_no:
                            if mat:
                                batch_no = f"{mat.sku}-{batch_date.strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
                            else:
                                batch_no = f"{item.item_name[:10]}-{batch_date.strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
                        
                        batch_unit_price = None
                        if batch_unit_price_str:
                            try:
                                batch_unit_price = Decimal(batch_unit_price_str)
                            except:
                                batch_unit_price = item.unit_price
                        else:
                            batch_unit_price = item.unit_price
                        
                        expiry_date = None
                        if expiry_date_str:
                            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                        
                        batch = Batch.objects.create(
                            batch_no=batch_no,
                            inventory=inventory,
                            batch_date=batch_date,
                            quantity=received_qty_base,  # 基础单位
                            unit_price=batch_unit_price,
                            expiry_date=expiry_date,
                            supplier=task.supplier.name,
                            remark=f"采购任务：{task.task_no}",
                        )
                        
                        inventory.update_quantity_from_batches()
                        
                        op_unit = mat.base_unit if mat else None
                        if op_unit:
                            StockTransaction.objects.create(
                                transaction_type='purchase_in',
                                inventory=inventory,
                                batch=batch,
                                quantity=received_qty_base,
                                unit=op_unit,
                                base_quantity=received_qty_base,
                                reference_no=task.task_no,
                                operator=request.user,
                            )
            
            task.status = 'completed'
            task.save()
            
            messages.success(request, f'采购任务 {task.task_no} 已完成，库存已更新')
            return redirect('purchase:task_detail', pk=pk)
    
    return render(request, 'purchase/task_complete.html', {'task': task})


@login_required
@role_required('ceo')
def task_terminate(request, pk):
    """总经理终结采购任务"""
    task = get_object_or_404(PurchaseTask, pk=pk)
    
    active_statuses = ['pending', 'approved', 'purchasing']
    if task.status not in active_statuses:
        messages.error(request, '只能终结进行中的采购任务')
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


@login_required
@role_required('warehouse', 'ceo')
def supplier_list(request):
    """供应商列表"""
    suppliers = Supplier.objects.select_related('created_by').all()
    
    search = request.GET.get('search', '')
    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) | 
            Q(contact_person__icontains=search) |
            Q(contact_phone__icontains=search)
        )
    
    paginator = Paginator(suppliers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    extra_params = ''
    if search:
        extra_params = f'search={search}'
    
    context = {
        'suppliers': page_obj,
        'search': search,
        'extra_params': extra_params,
    }
    return render(request, 'purchase/supplier_list.html', context)


@login_required
@role_required('warehouse', 'ceo')
def supplier_create(request):
    """创建供应商"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        address = request.POST.get('address', '').strip()
        email = request.POST.get('email', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        if not name:
            messages.error(request, '请输入供应商名称')
            return render(request, 'purchase/supplier_form.html', {'title': '创建供应商'})
        
        if Supplier.objects.filter(name=name).exists():
            messages.error(request, '供应商名称已存在')
            return render(request, 'purchase/supplier_form.html', {'title': '创建供应商'})
        
        supplier = Supplier.objects.create(
            name=name,
            contact_person=contact_person,
            contact_phone=contact_phone,
            address=address,
            email=email,
            remark=remark,
            created_by=request.user,
        )
        
        messages.success(request, f'供应商 {supplier.name} 创建成功')
        return redirect('purchase:supplier_list')
    
    return render(request, 'purchase/supplier_form.html', {'title': '创建供应商'})


@login_required
@role_required('warehouse', 'ceo')
def supplier_edit(request, pk):
    """编辑供应商"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        address = request.POST.get('address', '').strip()
        email = request.POST.get('email', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        if not name:
            messages.error(request, '请输入供应商名称')
            return render(request, 'purchase/supplier_form.html', {'title': '编辑供应商', 'supplier': supplier})
        
        if Supplier.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, '供应商名称已被使用')
            return render(request, 'purchase/supplier_form.html', {'title': '编辑供应商', 'supplier': supplier})
        
        supplier.name = name
        supplier.contact_person = contact_person
        supplier.contact_phone = contact_phone
        supplier.address = address
        supplier.email = email
        supplier.remark = remark
        supplier.save()
        
        messages.success(request, f'供应商 {supplier.name} 更新成功')
        return redirect('purchase:supplier_list')
    
    return render(request, 'purchase/supplier_form.html', {'title': '编辑供应商', 'supplier': supplier})


@login_required
@role_required('warehouse', 'ceo')
def supplier_delete(request, pk):
    """删除供应商"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        supplier_name = supplier.name
        supplier.delete()
        messages.success(request, f'供应商 {supplier_name} 已删除')
        return redirect('purchase:supplier_list')
    
    return render(request, 'purchase/supplier_confirm_delete.html', {'supplier': supplier})
