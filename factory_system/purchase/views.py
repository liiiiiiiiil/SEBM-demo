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
def task_create_from_production(request, production_task_pk):
    """从生产任务跳转到采购任务创建页面（预填所需原料）"""
    production_task = get_object_or_404(ProductionTask, pk=production_task_pk)
    
    # 检查原材料是否不足
    bom_items = BOM.objects.filter(product=production_task.product)
    insufficient_materials = []
    
    for bom_item in bom_items:
        total_required = bom_item.quantity * production_task.required_quantity
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            available_quantity = Decimal('0')
        
        if available_quantity < total_required:
            shortage = total_required - available_quantity
            insufficient_materials.append({
                'material': bom_item.material,
                'shortage': shortage,
                'unit': bom_item.unit,
            })
    
    # 如果没有不足的原料，重定向到普通创建页面
    if not insufficient_materials:
        messages.info(request, '该生产任务的原材料充足，无需采购')
        return redirect('purchase:task_create')
    
    # 重定向到创建页面，通过 URL 参数传递预填数据
    material_ids = ','.join([str(m['material'].id) for m in insufficient_materials])
    quantities = ','.join([str(m['shortage']) for m in insufficient_materials])
    
    return redirect(f"{reverse('purchase:task_create')}?from_production={production_task_pk}&materials={material_ids}&quantities={quantities}")


@login_required
@role_required('warehouse', 'ceo')
def task_create(request):
    """创建采购任务"""
    # 检查是否从生产任务跳转过来
    from_production_task_pk = request.GET.get('from_production')
    prefill_materials = []
    production_task = None
    
    if from_production_task_pk:
        try:
            production_task = ProductionTask.objects.get(pk=from_production_task_pk)
            material_ids_str = request.GET.get('materials', '')
            quantities_str = request.GET.get('quantities', '')
            
            if material_ids_str and quantities_str:
                material_ids = [int(id) for id in material_ids_str.split(',') if id]
                quantities = [Decimal(q) for q in quantities_str.split(',') if q]
                
                for material_id, quantity in zip(material_ids, quantities):
                    try:
                        material = Material.objects.get(pk=material_id)
                        prefill_materials.append({
                            'material': material,
                            'quantity': quantity,
                            'unit': material.unit,
                        })
                    except Material.DoesNotExist:
                        pass
        except (ProductionTask.DoesNotExist, ValueError):
            pass
    
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        # 获取采购明细
        material_ids = request.POST.getlist('material_id')
        item_names = request.POST.getlist('item_name')
        item_types = request.POST.getlist('item_type')
        units = request.POST.getlist('unit')
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
        
        # 验证至少有一个有效的明细项
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
                unit = units[i].strip() if i < len(units) else ''
                quantity_str = quantities[i] if i < len(quantities) else ''
                unit_price_str = unit_prices[i] if i < len(unit_prices) else ''
                
                if not quantity_str or not unit_price_str:
                    continue
                
                # 必须选择物料或填写物品名称
                if not material_id and not item_name:
                    continue
                
                quantity = Decimal(quantity_str)
                unit_price = Decimal(unit_price_str)
                subtotal = quantity * unit_price
                
                # 如果选择了物料，从物料获取信息
                material = None
                if material_id:
                    material = Material.objects.get(pk=material_id)
                    # 如果选择了物料，使用物料的信息
                    item_name = material.name
                    unit = material.unit
                    item_type = 'material'
                
                PurchaseTaskItem.objects.create(
                    task=task,
                    material=material,
                    item_name=item_name,
                    item_type=item_type,
                    unit=unit,
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
    suppliers = Supplier.objects.all().order_by('name')
    
    # 准备预填数据（转换为 JSON 格式供模板使用）
    import json
    prefill_materials_json = json.dumps([
        {
            'material_id': item['material'].id,
            'material_name': item['material'].name,
            'quantity': str(item['quantity']),
            'unit': item['unit'],
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
            # 处理收货并增加库存
            for item in task.items.all():
                received_qty_str = request.POST.get(f'received_quantity_{item.id}', '0')
                if received_qty_str:
                    received_qty = Decimal(received_qty_str)
                    if received_qty > 0:
                        # 增加库存（只对已有物料进行库存管理）
                        inventory = None
                        if item.material:
                            inventory, created = Inventory.objects.get_or_create(
                                inventory_type='material',
                                material=item.material,
                                defaults={'quantity': 0, 'unit': item.material.unit}
                            )
                        elif item.item_type in ['office', 'other']:
                            # 办公用品或其它类型，创建其它库存
                            inventory, created = Inventory.objects.get_or_create(
                                inventory_type='other',
                                other_name=item.item_name,
                                defaults={'quantity': 0, 'unit': item.unit}
                            )
                        
                        if not inventory:
                            # 如果是原料类型但未关联物料，跳过库存管理
                            continue
                        
                        # 获取批次信息
                        batch_date_str = request.POST.get(f'batch_date_{item.id}', '')
                        batch_no = request.POST.get(f'batch_no_{item.id}', '')
                        batch_unit_price_str = request.POST.get(f'batch_unit_price_{item.id}', '')
                        expiry_date_str = request.POST.get(f'expiry_date_{item.id}', '')
                        
                        from django.utils import timezone
                        from datetime import datetime
                        
                        # 批次日期，默认为今天
                        if batch_date_str:
                            batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date()
                        else:
                            batch_date = timezone.now().date()
                        
                        # 批次号，如果没有提供则自动生成
                        if not batch_no:
                            if item.material:
                                batch_no = f"{item.material.sku}-{batch_date.strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
                            else:
                                batch_no = f"{item.item_name[:10]}-{batch_date.strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
                        
                        # 批次单价
                        batch_unit_price = None
                        if batch_unit_price_str:
                            try:
                                batch_unit_price = Decimal(batch_unit_price_str)
                            except:
                                batch_unit_price = item.unit_price
                        else:
                            batch_unit_price = item.unit_price
                        
                        # 过期日期
                        expiry_date = None
                        if expiry_date_str:
                            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                        
                        # 创建批次
                        from inventory.models import Batch
                        batch = Batch.objects.create(
                            batch_no=batch_no,
                            inventory=inventory,
                            batch_date=batch_date,
                            quantity=received_qty,
                            unit_price=batch_unit_price,
                            expiry_date=expiry_date,
                            supplier=task.supplier.name,
                            remark=f"采购任务：{task.task_no}",
                        )
                        
                        # 更新库存总数量
                        inventory.update_quantity_from_batches()
                        
                        # 记录库存变动
                        from inventory.models import StockTransaction
                        StockTransaction.objects.create(
                            transaction_type='purchase_in',
                            inventory=inventory,
                            batch=batch,
                            quantity=received_qty,
                            unit=item.unit or (item.material.unit if item.material else ''),
                            reference_no=task.task_no,
                            operator=request.user,
                        )
            
            # 直接完成任务
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
    
    # 分页处理
    paginator = Paginator(suppliers, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
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
        
        # 检查供应商名称是否已存在
        if Supplier.objects.filter(name=name).exists():
            messages.error(request, '供应商名称已存在')
            context = {
                'title': '创建供应商',
                'name': name,
                'contact_person': contact_person,
                'contact_phone': contact_phone,
                'address': address,
                'email': email,
                'remark': remark,
            }
            return render(request, 'purchase/supplier_form.html', context)
        
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
        
        # 检查供应商名称是否已被其他供应商使用
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
