from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
from decimal import Decimal
from accounts.decorators import role_required
from .models import ProductionTask, MaterialRequisition, MaterialRequisitionItem, MaterialRequisitionItemBatch, QCRecord, FinishedProductInbound, TaskMaterialOverride
from inventory.models import BOM, Inventory, StockTransaction, Product
from factory_system.utils import get_paginate_by


# ===== 公共工具函数 =====

def _load_overrides(task):
    """加载任务的所有物料用量覆盖，返回 {material_id: TaskMaterialOverride}"""
    return {
        o.material_id: o
        for o in TaskMaterialOverride.objects.filter(task=task).select_related('unit')
    }


def _effective_base_quantity(bom_item, overrides):
    """获取 bom_item 对应的有效单位产品用量（基础单位），优先取任务覆盖值。
    
    返回: (base_quantity, display_quantity, display_unit_name, is_overridden)
    """
    override = overrides.get(bom_item.material_id)
    if override:
        return override.get_base_quantity(), override.quantity, override.unit.name, True
    return bom_item.get_base_quantity(), bom_item.quantity, bom_item.unit.name, False


def _is_task_material_sufficient(task):
    """检查任务所需原料库存是否充足。考虑 BOM 与任务级用量覆盖。"""
    bom_items = BOM.objects.filter(product=task.product).select_related('material')
    overrides = _load_overrides(task)
    for bom_item in bom_items:
        base_qty, _, _, _ = _effective_base_quantity(bom_item, overrides)
        total_required_base = task.required_quantity * base_qty
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_base = inventory.quantity
        except Inventory.DoesNotExist:
            available_base = Decimal('0')
        if available_base < total_required_base:
            return False
    return True


def _refresh_material_insufficient_status(task):
    """若任务状态为「原料不足」且当前原料已充足，则更新为「待接收」。"""
    if task.status != 'material_insufficient':
        return
    if _is_task_material_sufficient(task):
        task.status = 'pending'
        task.save(update_fields=['status', 'updated_at'])


# ===== 视图 =====

@login_required
@role_required('production', 'ceo')
def task_list(request):
    """生产任务列表"""
    tasks = ProductionTask.objects.select_related('order', 'product', 'product__base_unit', 'product__display_unit').all().order_by('-created_at')
    
    production_type_filter = request.GET.get('production_type', '')
    if production_type_filter:
        tasks = tasks.filter(production_type=production_type_filter)
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    
    paginate_by = get_paginate_by(request, desktop_count=20, mobile_count=10)
    paginator = Paginator(tasks, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    # 刷新本页中「原料不足」任务：若采购后原料已充足，则更新为「待接收」
    for task in page_obj.object_list:
        _refresh_material_insufficient_status(task)
    
    extra_params = []
    if production_type_filter:
        extra_params.append(f'production_type={production_type_filter}')
    if status_filter:
        extra_params.append(f'status={status_filter}')
    extra_params = '&'.join(extra_params)
    
    context = {
        'tasks': page_obj,
        'status_filter': status_filter,
        'production_type_filter': production_type_filter,
        'extra_params': extra_params,
    }
    return render(request, 'production/task_list.html', context)


@login_required
@role_required('production', 'ceo')
def task_detail(request, pk):
    """生产任务详情"""
    task = get_object_or_404(
        ProductionTask.objects.select_related('product', 'product__base_unit', 'product__display_unit')
        .prefetch_related('material_requisitions__items'),
        pk=pk,
    )
    # 若当前为「原料不足」且原料已充足（如采购后），刷新为「待接收」
    _refresh_material_insufficient_status(task)
    
    bom_items = BOM.objects.filter(product=task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
    overrides = _load_overrides(task)
    
    material_requirements = []
    total_materials_summary = {}
    
    # 任务是否允许编辑用量（未完成/未终结的任务可以调整）
    can_edit_qty = task.status not in ('completed', 'cancelled', 'terminated')
    
    # required_quantity 已是成品基础单位，无需额外换算
    for bom_item in bom_items:
        base_qty, disp_qty, disp_unit_name, is_overridden = _effective_base_quantity(bom_item, overrides)
        total_required_base = task.required_quantity * base_qty
        
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_base = inventory.quantity
        except Inventory.DoesNotExist:
            available_base = Decimal('0')
        
        shortage_base = max(Decimal('0'), total_required_base - available_base)
        
        # 转换为原料的显示单位用于前端展示
        mat = bom_item.material
        total_required_disp, _ = mat.to_display(total_required_base)
        available_disp, _ = mat.to_display(available_base)
        shortage_disp, _ = mat.to_display(shortage_base)
        
        material_requirements.append({
            'material': mat,
            'material_id': mat.id,
            'bom_quantity': disp_qty,
            'bom_unit': disp_unit_name,
            'bom_original_quantity': bom_item.quantity,
            'bom_original_unit': bom_item.unit.name,
            'is_overridden': is_overridden,
            'total_required': total_required_disp,
            'available_quantity': available_disp,
            'shortage': shortage_disp,
            'unit': mat.display_unit.name,
        })
        
        material_id = mat.id
        bom_default_base = bom_item.get_base_quantity()
        original_total_base = task.required_quantity * bom_default_base
        original_total_disp, _ = mat.to_display(original_total_base)
        if material_id in total_materials_summary:
            total_materials_summary[material_id]['total_quantity_base'] += total_required_base
            total_materials_summary[material_id]['original_total'] = (
                Decimal(str(total_materials_summary[material_id].get('original_total', 0))) + original_total_disp
            )
            total_materials_summary[material_id]['is_overridden'] = (
                total_materials_summary[material_id].get('is_overridden', False) or is_overridden
            )
            ts_base = total_materials_summary[material_id]['total_quantity_base'] - available_base
            ts_disp, _ = mat.to_display(max(Decimal('0'), ts_base))
            tq_disp, _ = mat.to_display(total_materials_summary[material_id]['total_quantity_base'])
            total_materials_summary[material_id]['total_quantity'] = tq_disp
            total_materials_summary[material_id]['available_quantity'] = available_disp
            total_materials_summary[material_id]['shortage'] = ts_disp
        else:
            total_materials_summary[material_id] = {
                'material': mat,
                'material_id': mat.id,
                'total_quantity_base': total_required_base,
                'total_quantity': total_required_disp,
                'original_total': original_total_disp,
                'available_quantity': available_disp,
                'shortage': shortage_disp,
                'unit': mat.display_unit.name,
                'is_overridden': is_overridden,
            }
    
    shortage_quantity = task.get_display_shortage_quantity()
    
    # 入库成功跳转或任务已完成时，显示「已消耗原料汇总」（不显示当前库存、缺口）
    show_consumed_summary = request.GET.get('from_inbound') == '1' or task.status == 'completed'
    consumed_materials_summary = []
    if show_consumed_summary:
        inbound_nos = list(task.inbounds.values_list('inbound_no', flat=True))
        if inbound_nos:
            from inventory.models import Material
            consumed_qs = StockTransaction.objects.filter(
                transaction_type='production_out',
                reference_no__in=inbound_nos,
                inventory__inventory_type='material',
            ).values('inventory__material_id').annotate(consumed_base=Sum('base_quantity'))
            material_ids = [r['inventory__material_id'] for r in consumed_qs]
            materials = {m.id: m for m in Material.objects.filter(pk__in=material_ids).select_related('base_unit', 'display_unit')}
            for row in consumed_qs:
                mid = row['inventory__material_id']
                consumed_base = row['consumed_base'] or Decimal('0')
                if consumed_base <= 0:
                    continue
                mat = materials.get(mid)
                if not mat:
                    continue
                disp, _ = mat.to_display(consumed_base)
                consumed_materials_summary.append({
                    'material': mat,
                    'material_id': mid,
                    'consumed_quantity': disp,
                    'unit': mat.display_unit.name,
                })
            consumed_materials_summary.sort(key=lambda x: x['material'].name)
    
    context = {
        'task': task,
        'bom_items': bom_items,
        'material_requirements': material_requirements,
        'total_materials_summary': list(total_materials_summary.values()),
        'shortage_quantity': shortage_quantity,
        'can_edit_qty': can_edit_qty,
        'show_consumed_summary': show_consumed_summary,
        'consumed_materials_summary': consumed_materials_summary,
    }
    return render(request, 'production/task_detail.html', context)


@login_required
@role_required('production', 'ceo')
def task_status_api(request, pk):
    """获取生产任务最新状态的API"""
    task = get_object_or_404(ProductionTask.objects.select_related('product', 'product__base_unit', 'product__display_unit'), pk=pk)
    
    shortage_quantity = task.get_display_shortage_quantity()
    
    bom_items = BOM.objects.filter(product=task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
    overrides = _load_overrides(task)
    material_shortages = {}

    for bom_item in bom_items:
        base_qty, _, _, _ = _effective_base_quantity(bom_item, overrides)
        total_required_base = task.required_quantity * base_qty
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_base = inventory.quantity
        except Inventory.DoesNotExist:
            available_base = Decimal('0')
        
        shortage_base = max(Decimal('0'), total_required_base - available_base)
        
        mat = bom_item.material
        total_disp, _ = mat.to_display(total_required_base)
        avail_disp, _ = mat.to_display(available_base)
        short_disp, _ = mat.to_display(shortage_base)
        
        material_shortages[bom_item.material.id] = {
            'total_required': float(total_disp),
            'available_quantity': float(avail_disp),
            'shortage': float(short_disp),
            'unit': mat.display_unit.name,
        }
    
    return JsonResponse({
        'completed_quantity': float(task.get_display_completed_quantity()),
        'required_quantity': float(task.get_display_required_quantity()),
        'shortage_quantity': float(shortage_quantity),
        'status': task.status,
        'status_display': task.get_status_display(),
        'material_shortages': material_shortages,
    })


@login_required
@role_required('production', 'ceo')
def task_material_override_api(request, pk):
    """保存 / 重置某条任务的单种原料用量覆盖（AJAX POST）"""
    import json as _json

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': '仅支持 POST'}, status=405)

    task = get_object_or_404(ProductionTask.objects.select_related('product'), pk=pk)
    if task.status in ('completed', 'cancelled', 'terminated'):
        return JsonResponse({'ok': False, 'error': '任务已结束，无法调整'}, status=400)

    try:
        body = _json.loads(request.body)
        material_id = int(body['material_id'])
        # 支持两种输入：quantity（单位产品用量，BOM单位）或 total_quantity（总需求量，显示单位）
        total_quantity_raw = body.get('total_quantity')
        quantity_raw = body.get('quantity')
        if total_quantity_raw is not None:
            total_display = Decimal(str(total_quantity_raw))
            new_quantity = None
        elif quantity_raw is not None:
            total_display = None
            new_quantity = Decimal(str(quantity_raw))
        else:
            return JsonResponse({'ok': False, 'error': '缺少 quantity 或 total_quantity'}, status=400)
    except (ValueError, TypeError) as e:
        return JsonResponse({'ok': False, 'error': f'参数错误: {e}'}, status=400)

    from inventory.models import Material
    material = get_object_or_404(Material.objects.select_related('base_unit', 'display_unit'), pk=material_id)

    bom_item = BOM.objects.filter(product=task.product, material=material).select_related('unit').first()
    if not bom_item:
        return JsonResponse({'ok': False, 'error': '该原料不在 BOM 配方中'}, status=400)

    from inventory.services.unit_conversion import UnitConversionService

    if total_display is not None:
        # 用户输入为总需求量（显示单位），转换为单位产品用量后保存
        if total_display < 0:
            return JsonResponse({'ok': False, 'error': '总需求量不能为负'}, status=400)
        total_base = material.from_display(total_display)
        per_unit_base = total_base / task.required_quantity if task.required_quantity else Decimal('0')
        bom_default_base = bom_item.get_base_quantity()
        if abs(per_unit_base - bom_default_base) < Decimal('0.0001'):
            TaskMaterialOverride.objects.filter(task=task, material=material).delete()
            is_overridden = False
        else:
            qty_in_bom_unit = UnitConversionService.from_base(material, per_unit_base, bom_item.unit)
            TaskMaterialOverride.objects.update_or_create(
                task=task, material=material,
                defaults={'quantity': qty_in_bom_unit, 'unit': bom_item.unit, 'updated_by': request.user},
            )
            is_overridden = True
    else:
        if new_quantity < 0:
            return JsonResponse({'ok': False, 'error': '用量不能为负'}, status=400)
        if new_quantity == bom_item.quantity:
            TaskMaterialOverride.objects.filter(task=task, material=material).delete()
            is_overridden = False
        else:
            TaskMaterialOverride.objects.update_or_create(
                task=task, material=material,
                defaults={'quantity': new_quantity, 'unit': bom_item.unit, 'updated_by': request.user},
            )
            is_overridden = True

    # 重新计算该原料的需求
    overrides = _load_overrides(task)
    base_qty, disp_qty, disp_unit_name, _ = _effective_base_quantity(bom_item, overrides)
    total_required_base = task.required_quantity * base_qty

    try:
        inventory = Inventory.objects.get(inventory_type='material', material=material)
        available_base = inventory.quantity
    except Inventory.DoesNotExist:
        available_base = Decimal('0')

    shortage_base = max(Decimal('0'), total_required_base - available_base)
    total_disp, _ = material.to_display(total_required_base)
    avail_disp, _ = material.to_display(available_base)
    short_disp, _ = material.to_display(shortage_base)

    return JsonResponse({
        'ok': True,
        'is_overridden': is_overridden,
        'bom_quantity': float(disp_qty),
        'bom_unit': disp_unit_name,
        'total_required': float(total_disp),
        'available_quantity': float(avail_disp),
        'shortage': float(short_disp),
    })


@login_required
@role_required('production', 'ceo')
def task_receive(request, pk):
    """接收生产任务"""
    task = get_object_or_404(ProductionTask.objects.select_related('product', 'product__base_unit', 'product__display_unit'), pk=pk)
    
    if task.status not in ['pending', 'material_insufficient']:
        messages.error(request, '任务状态不正确，只能接收待接收或原料不足状态的任务')
        return redirect('production:task_detail', pk=pk)
    
    bom_items = BOM.objects.filter(product=task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
    overrides = _load_overrides(task)
    insufficient_materials = []
    all_sufficient = True

    for bom_item in bom_items:
        base_qty, _, _, _ = _effective_base_quantity(bom_item, overrides)
        total_required_base = task.required_quantity * base_qty
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=bom_item.material)
            available_base = inventory.quantity
        except Inventory.DoesNotExist:
            available_base = Decimal('0')

        if available_base < total_required_base:
            all_sufficient = False
            mat = bom_item.material
            req_disp, _ = mat.to_display(total_required_base)
            avail_disp, _ = mat.to_display(available_base)
            short_disp, _ = mat.to_display(total_required_base - available_base)
            insufficient_materials.append({
                'material': mat,
                'required': req_disp,
                'available': avail_disp,
                'shortage': short_disp,
                'unit': mat.display_unit.name,
            })
    
    if request.method == 'POST':
        if not all_sufficient:
            task.status = 'material_insufficient'
            task.save()
            messages.warning(request, f'任务 {task.task_no} 原材料不足，无法接收。请先采购补齐原材料。')
            return redirect('production:task_detail', pk=pk)
        
        task.status = 'in_production'
        task.received_by = request.user
        task.received_at = timezone.now()
        task.started_at = timezone.now()
        task.save()
        
        requisition = create_material_requisition(task)
        
        messages.success(request, f'任务 {task.task_no} 已接收，已进入生产中状态。已自动创建领料单。')
        return redirect('production:task_detail', pk=pk)
    
    context = {
        'task': task,
        'insufficient_materials': insufficient_materials,
        'all_sufficient': all_sufficient,
    }
    return render(request, 'production/task_receive.html', context)


def create_material_requisition(task):
    """根据BOM自动创建领料单（考虑任务级用量覆盖）"""
    bom_items = BOM.objects.filter(product=task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')

    if not bom_items.exists():
        return None

    overrides = _load_overrides(task)

    requisition = MaterialRequisition.objects.create(
        requisition_no=f"MR{timezone.now().strftime('%Y%m%d%H%M%S')}",
        task=task,
        status='pending',
        requested_by=task.received_by,
    )

    for bom_item in bom_items:
        base_qty, _, _, _ = _effective_base_quantity(bom_item, overrides)
        required_qty = task.required_quantity * base_qty
        MaterialRequisitionItem.objects.create(
            requisition=requisition,
            material=bom_item.material,
            required_quantity=required_qty,
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
    
    paginate_by = get_paginate_by(request, desktop_count=20, mobile_count=10)
    paginator = Paginator(requisitions, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
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
    requisition = get_object_or_404(
        MaterialRequisition.objects.prefetch_related('items__material', 'items__material__base_unit', 'items__material__display_unit'),
        pk=pk,
    )
    
    if requisition.status != 'pending':
        messages.error(request, '领料单状态不正确')
        return redirect('production:requisition_list')
    
    insufficient_items = []
    for item in requisition.items.all():
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=item.material)
            from inventory.models import Batch
            available_quantity = Decimal('0')
            for batch in inventory.get_batches():
                available_quantity += batch.get_available_quantity()
            
            if available_quantity < item.required_quantity:
                mat = item.material
                req_disp, _ = mat.to_display(item.required_quantity)
                avail_disp, _ = mat.to_display(available_quantity)
                insufficient_items.append({
                    'material': mat.name,
                    'required': req_disp,
                    'available': avail_disp,
                    'unit': mat.display_unit.name if mat.display_unit else '',
                })
        except Inventory.DoesNotExist:
            mat = item.material
            req_disp, _ = mat.to_display(item.required_quantity)
            insufficient_items.append({
                'material': mat.name,
                'required': req_disp,
                'available': 0,
                'unit': mat.display_unit.name if mat.display_unit else '',
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
            
            from inventory.models import Batch
            for item in requisition.items.all():
                inventory = Inventory.objects.get(inventory_type='material', material=item.material)
                remaining_qty = item.required_quantity
                for batch in inventory.get_batches().order_by('batch_date', 'created_at'):
                    if remaining_qty <= 0:
                        break
                    available_qty = batch.get_available_quantity()
                    if available_qty <= 0:
                        continue
                    allocate_qty = min(remaining_qty, available_qty)
                    batch.locked_quantity = (batch.locked_quantity or Decimal('0')) + allocate_qty
                    batch.save()
                    MaterialRequisitionItemBatch.objects.create(
                        requisition_item=item,
                        batch=batch,
                        quantity_locked=allocate_qty,
                    )
                    remaining_qty -= allocate_qty
                if remaining_qty > 0:
                    raise ValueError(f'原料 {item.material.name} 可用数量不足，无法锁定')
            
            requisition.task.status = 'material_preparing'
            requisition.task.save()
            
            messages.success(request, f'领料单 {requisition.requisition_no} 已批准，原料已锁定')
            return redirect('production:requisition_list')
    
    # 为模板准备显示单位数量的领料明细
    requisition_display_items = []
    for item in requisition.items.select_related('material', 'material__base_unit', 'material__display_unit').all():
        mat = item.material
        disp_qty, _ = mat.to_display(item.required_quantity)
        requisition_display_items.append({
            'material': mat,
            'display_quantity': disp_qty,
            'unit': mat.display_unit.name if mat.display_unit else '',
        })
    
    context = {
        'requisition': requisition,
        'insufficient_items': insufficient_items,
        'requisition_display_items': requisition_display_items,
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
    task = get_object_or_404(
        ProductionTask.objects.select_related('product', 'product__base_unit', 'product__display_unit'),
        pk=task_pk,
    )
    
    if request.method == 'POST':
        try:
            quantity_str = request.POST.get('quantity', '').strip()
            if not quantity_str:
                messages.error(request, '请输入入库数量')
                return redirect('production:inbound_create', task_pk=task_pk)
            
            display_quantity = Decimal(quantity_str)
            if display_quantity <= 0:
                messages.error(request, '入库数量必须大于0')
                return redirect('production:inbound_create', task_pk=task_pk)
            
            # 用户输入的是显示单位数量，转换为基础单位
            quantity = task.product.from_display(display_quantity)
            
            qc_record_id = request.POST.get('qc_record_id', '').strip()
            qc_record = None
            if qc_record_id:
                try:
                    qc_record = QCRecord.objects.get(pk=qc_record_id, task=task)
                except QCRecord.DoesNotExist:
                    messages.error(request, '质检记录不存在')
                    return redirect('production:inbound_create', task_pk=task_pk)
            
            with transaction.atomic():
                import random
                inbound_no = f"IN{timezone.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                while FinishedProductInbound.objects.filter(inbound_no=inbound_no).exists():
                    inbound_no = f"IN{timezone.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
                
                # 入库单不再存储 unit 字段
                inbound = FinishedProductInbound.objects.create(
                    inbound_no=inbound_no,
                    task=task,
                    qc_record=qc_record,
                    quantity=quantity,
                    operator=request.user,
                )
                
                # 成品库存不再存储 unit 字段
                inventory, created = Inventory.objects.get_or_create(
                    inventory_type='product',
                    product=task.product,
                    defaults={'quantity': 0}
                )
                
                # 批次信息
                batch_date_str = request.POST.get('batch_date', '')
                batch_no = request.POST.get('batch_no', '')
                batch_unit_price_str = request.POST.get('batch_unit_price', '')
                expiry_date_str = request.POST.get('expiry_date', '')
                
                from datetime import datetime
                
                batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date() if batch_date_str else timezone.now().date()
                
                if not batch_no:
                    batch_no = f"{task.product.sku}-{batch_date.strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
                
                batch_unit_price = None
                if batch_unit_price_str:
                    try:
                        batch_unit_price = Decimal(batch_unit_price_str)
                    except:
                        batch_unit_price = task.product.unit_price
                else:
                    batch_unit_price = task.product.unit_price
                
                expiry_date = None
                if expiry_date_str:
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                
                from inventory.models import Batch
                batch = Batch.objects.create(
                    batch_no=batch_no,
                    inventory=inventory,
                    batch_date=batch_date,
                    quantity=quantity,
                    unit_price=batch_unit_price,
                    expiry_date=expiry_date,
                    remark=f"生产任务：{task.task_no}，入库单：{inbound.inbound_no}",
                )
                
                inventory.update_quantity_from_batches()
                
                # 库存变动记录使用成品基础单位
                StockTransaction.objects.create(
                    transaction_type='production_in',
                    inventory=inventory,
                    batch=batch,
                    quantity=quantity,
                    unit=task.product.base_unit,
                    base_quantity=quantity,
                    reference_no=inbound.inbound_no,
                    operator=request.user,
                )
                
                # 按 BOM（考虑任务覆盖）扣减原料
                from inventory.models import Batch
                bom_items = BOM.objects.filter(product=task.product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
                inbound_overrides = _load_overrides(task)
                for bom_item in bom_items:
                    eff_base_qty, _, _, _ = _effective_base_quantity(bom_item, inbound_overrides)
                    required_qty = quantity * eff_base_qty
                    if required_qty <= 0:
                        continue
                    remaining_qty = required_qty
                    
                    # 1) 优先从本任务领料锁定的批次扣减
                    allocations = MaterialRequisitionItemBatch.objects.filter(
                        requisition_item__requisition__task=task,
                        requisition_item__material=bom_item.material,
                    ).select_related('batch').order_by('batch__batch_date', 'batch__created_at')
                    
                    for allocation in allocations:
                        if remaining_qty <= 0:
                            break
                        batch_obj = allocation.batch
                        deduct_qty = min(remaining_qty, allocation.quantity_locked, batch_obj.quantity)
                        if deduct_qty <= 0:
                            continue
                        batch_obj.quantity -= deduct_qty
                        allocation.quantity_locked -= deduct_qty
                        if allocation.quantity_locked <= 0:
                            allocation.delete()
                        else:
                            allocation.save()
                        batch_obj.locked_quantity = max(
                            Decimal('0'),
                            (batch_obj.locked_quantity or Decimal('0')) - deduct_qty,
                        )
                        batch_obj.save()
                        StockTransaction.objects.create(
                            transaction_type='production_out',
                            inventory=batch_obj.inventory,
                            batch=batch_obj,
                            quantity=deduct_qty,
                            unit=bom_item.material.base_unit,
                            base_quantity=deduct_qty,
                            reference_no=inbound.inbound_no,
                            remark=f'生产完工出库：{task.task_no}，入库单 {inbound.inbound_no}',
                            operator=request.user,
                        )
                        remaining_qty -= deduct_qty
                    
                    # 2) FIFO 扣减
                    if remaining_qty > 0:
                        try:
                            mat_inventory = Inventory.objects.get(
                                inventory_type='material',
                                material=bom_item.material,
                            )
                        except Inventory.DoesNotExist:
                            mat_inventory = None
                        if mat_inventory:
                            for mat_batch in mat_inventory.get_batches().order_by('batch_date', 'created_at'):
                                if remaining_qty <= 0:
                                    break
                                if mat_batch.quantity <= 0:
                                    continue
                                allocate_qty = min(remaining_qty, mat_batch.quantity)
                                mat_batch.quantity -= allocate_qty
                                mat_batch.save()
                                StockTransaction.objects.create(
                                    transaction_type='production_out',
                                    inventory=mat_inventory,
                                    batch=mat_batch,
                                    quantity=allocate_qty,
                                    unit=bom_item.material.base_unit,
                                    base_quantity=allocate_qty,
                                    reference_no=inbound.inbound_no,
                                    remark=f'生产完工出库：{task.task_no}，入库单 {inbound.inbound_no}',
                                    operator=request.user,
                                )
                                remaining_qty -= allocate_qty
                    
                    if remaining_qty > 0:
                        # 原料不足时仍允许入库，但记录警告
                        # 生产已完成，原料实际已消耗，不应阻止成品入库
                        shortage = remaining_qty
                        deducted = required_qty - remaining_qty
                        mat = bom_item.material
                        req_disp, _ = mat.to_display(required_qty)
                        ded_disp, _ = mat.to_display(deducted)
                        sho_disp, _ = mat.to_display(shortage)
                        messages.warning(
                            request,
                            f'⚠ 原料「{mat.name}」库存不足：需 {req_disp} {mat.display_unit.name}，'
                            f'实际扣减 {ded_disp} {mat.display_unit.name}，'
                            f'差额 {sho_disp} {mat.display_unit.name} 未扣减（可能已在领料阶段扣减或需补录调整）'
                        )
                    try:
                        mat_inventory = Inventory.objects.get(
                            inventory_type='material',
                            material=bom_item.material,
                        )
                        mat_inventory.update_quantity_from_batches()
                    except Inventory.DoesNotExist:
                        pass
                
                task.completed_quantity += quantity
                task_was_completed = False
                if task.completed_quantity >= task.required_quantity and task.status != 'completed':
                    task.status = 'completed'
                    task.completed_at = timezone.now()
                    task_was_completed = True
                task.save()
                
                if (task_was_completed or task.status == 'completed') and task.production_type == 'order' and task.order:
                    check_order_ready_to_ship(task.order)
                
                messages.success(request, f'入库单 {inbound.inbound_no} 创建成功')
                return redirect(reverse('production:task_detail', kwargs={'pk': task_pk}) + '?from_inbound=1')
        except ValueError:
            messages.error(request, '入库数量格式不正确')
            return redirect('production:inbound_create', task_pk=task_pk)
        except RuntimeError as e:
            messages.error(request, str(e))
            return redirect('production:inbound_create', task_pk=task_pk)
        except Exception as e:
            messages.error(request, f'创建入库单失败：{str(e)}')
            return redirect('production:inbound_create', task_pk=task_pk)
    
    qc_records = QCRecord.objects.filter(task=task, result='qualified')
    
    remaining_base = task.required_quantity - task.completed_quantity
    if remaining_base < 0:
        remaining_base = Decimal('0')
    remaining_display = task.get_display_shortage_quantity()
    
    context = {
        'task': task,
        'qc_records': qc_records,
        'remaining_quantity': remaining_display,
    }
    return render(request, 'production/inbound_form.html', context)


def check_order_ready_to_ship(order):
    """检查订单是否可以发货"""
    from logistics.models import ShippingNotice
    
    all_ready = True
    for item in order.items.all():
        production_tasks = ProductionTask.objects.filter(
            order=order,
            product=item.product
        ).exclude(status__in=['completed', 'cancelled', 'terminated'])
        
        if production_tasks.exists():
            all_ready = False
            break
        
        completed_tasks = ProductionTask.objects.filter(
            order=order,
            product=item.product,
            status='completed'
        )
        
        total_produced = sum(task.completed_quantity for task in completed_tasks)
        
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=item.product)
            current_inventory = inventory.quantity
        except Inventory.DoesNotExist:
            current_inventory = 0
        
        if completed_tasks.exists():
            if current_inventory < item.quantity:
                all_ready = False
                break
        else:
            if current_inventory < 0:
                all_ready = False
                break
    
    if all_ready and order.status == 'in_production':
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
    """总经理终结生产任务"""
    task = get_object_or_404(ProductionTask, pk=pk)
    
    active_statuses = ['pending', 'material_insufficient', 'received', 'material_preparing', 'in_production', 'qc_checking']
    if task.status not in active_statuses:
        messages.error(request, '只能终结未完成的任务')
        return redirect('production:task_detail', pk=pk)
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'production/task_terminate.html', {'task': task})
        
        if task.production_type == 'order' and task.order:
            from sales.views import terminate_order_chain
            terminate_order_chain(task.order, request.user, f"通过生产任务 {task.task_no} 终结：{terminate_reason}")
            messages.success(request, f'生产任务 {task.task_no} 及其关联订单 {task.order.order_no} 的所有流程已终结')
        else:
            task.status = 'terminated'
            task.terminated_by = request.user
            task.terminated_at = timezone.now()
            task.terminate_reason = terminate_reason
            task.save()
            messages.success(request, f'备货生产任务 {task.task_no} 已终结')
        
        return redirect('production:task_detail', pk=pk)
    
    order = task.order if task.production_type == 'order' else None
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
    """总经理终结领料单"""
    requisition = get_object_or_404(MaterialRequisition, pk=pk)
    
    active_statuses = ['pending', 'approved', 'issued']
    if requisition.status not in active_statuses:
        messages.error(request, '只能终结进行中的领料单')
        return redirect('production:requisition_list')
    
    if request.method == 'POST':
        terminate_reason = request.POST.get('terminate_reason', '').strip()
        
        if not terminate_reason:
            messages.error(request, '请输入终结原因')
            return render(request, 'production/requisition_terminate.html', {'requisition': requisition})
        
        task = requisition.task
        if task.production_type == 'order' and task.order:
            from sales.views import terminate_order_chain
            terminate_order_chain(task.order, request.user, f"通过领料单 {requisition.requisition_no} 终结：{terminate_reason}")
            messages.success(request, f'领料单 {requisition.requisition_no} 及其关联订单的所有流程已终结')
        else:
            task.status = 'terminated'
            task.terminated_by = request.user
            task.terminated_at = timezone.now()
            task.terminate_reason = f"通过领料单 {requisition.requisition_no} 终结：{terminate_reason}"
            task.save()
            
            requisition.status = 'terminated'
            requisition.terminated_by = request.user
            requisition.terminated_at = timezone.now()
            requisition.terminate_reason = terminate_reason
            requisition.save()
            
            messages.success(request, f'领料单 {requisition.requisition_no} 及备货生产任务 {task.task_no} 已终结')
        
        return redirect('production:requisition_list')
    
    task = requisition.task
    order = task.order if task.production_type == 'order' else None
    
    context = {
        'requisition': requisition,
        'task': task,
        'order': order,
    }
    return render(request, 'production/requisition_terminate.html', context)


@login_required
@role_required('production', 'ceo')
def stock_task_create(request):
    """创建备货生产任务"""
    if request.method == 'POST':
        product_id = request.POST.get('product')
        required_quantity = request.POST.get('required_quantity')
        planned_completion_date = request.POST.get('planned_completion_date') or None
        remark = request.POST.get('remark', '')
        
        if not product_id or not required_quantity:
            messages.error(request, '请选择产品并填写需求数量')
            return redirect('production:stock_task_create')
        
        try:
            product = Product.objects.select_related('base_unit', 'display_unit').get(pk=product_id)
            display_qty = Decimal(required_quantity)
            
            if display_qty <= 0:
                messages.error(request, '需求数量必须大于0')
                return redirect('production:stock_task_create')
            
            # 用户输入的是显示单位数量，需要转换为基础单位存储
            required_qty = product.from_display(display_qty)
            
            bom_items = BOM.objects.filter(product=product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit')
            material_sufficient = True
            insufficient_materials = []

            for bom_item in bom_items:
                material_required_base = required_qty * bom_item.get_base_quantity()
                mat = bom_item.material
                try:
                    material_inventory = Inventory.objects.get(
                        inventory_type='material',
                        material=mat
                    )
                    if material_inventory.quantity < material_required_base:
                        material_sufficient = False
                        req_disp, _ = mat.to_display(material_required_base)
                        avail_disp, _ = mat.to_display(material_inventory.quantity)
                        short_disp, _ = mat.to_display(material_required_base - material_inventory.quantity)
                        insufficient_materials.append({
                            'material': mat,
                            'required': req_disp,
                            'available': avail_disp,
                            'shortage': short_disp,
                            'unit': mat.display_unit.name,
                        })
                except Inventory.DoesNotExist:
                    material_sufficient = False
                    req_disp, _ = mat.to_display(material_required_base)
                    insufficient_materials.append({
                        'material': mat,
                        'required': req_disp,
                        'available': Decimal('0'),
                        'shortage': req_disp,
                        'unit': mat.display_unit.name,
                    })
            
            task_no = f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}ST"
            while ProductionTask.objects.filter(task_no=task_no).exists():
                task_no = f"PT{timezone.now().strftime('%Y%m%d%H%M%S')}ST{timezone.now().microsecond}"
            
            task_status = 'pending' if material_sufficient else 'material_insufficient'
            task = ProductionTask.objects.create(
                task_no=task_no,
                production_type='stock',
                product=product,
                required_quantity=required_qty,
                status=task_status,
                planned_completion_date=planned_completion_date,
                remark=remark,
            )
            
            if material_sufficient:
                messages.success(request, f'备货生产任务 {task.task_no} 创建成功')
            else:
                messages.warning(request, f'备货生产任务 {task.task_no} 创建成功，但原材料不足')
            
            return redirect('production:task_detail', pk=task.pk)
            
        except Product.DoesNotExist:
            messages.error(request, '产品不存在')
            return redirect('production:stock_task_create')
        except ValueError:
            messages.error(request, '需求数量格式不正确')
            return redirect('production:stock_task_create')
        except Exception as e:
            messages.error(request, f'创建备货生产任务失败：{str(e)}')
            return redirect('production:stock_task_create')
    
    products = Product.objects.select_related('base_unit', 'display_unit').all().order_by('sku')
    context = {
        'products': products,
    }
    return render(request, 'production/stock_task_form.html', context)
