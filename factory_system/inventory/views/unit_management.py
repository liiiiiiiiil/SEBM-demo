from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
from inventory.models import Material, MaterialPackagingUnit, Unit
from accounts.decorators import role_required


@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_list(request, material_id):
    """物料包装单位列表"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_units = material.packaging_units.filter(is_active=True).order_by('display_order')
    
    return render(request, 'inventory/packaging_unit_list.html', {
        'material': material,
        'packaging_units': packaging_units
    })


@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_create(request, material_id):
    """创建包装单位"""
    material = get_object_or_404(Material, pk=material_id)
    
    if request.method == 'POST':
        packaging_unit_name = request.POST.get('packaging_unit_name', '').strip()
        base_unit_id = request.POST.get('base_unit')
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        # 验证
        if not packaging_unit_name:
            messages.error(request, '请输入包装单位名称')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在
        if MaterialPackagingUnit.objects.filter(
            material=material,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            MaterialPackagingUnit.objects.filter(
                material=material,
                is_default=True
            ).update(is_default=False)
        
        # 创建
        packaging_unit = MaterialPackagingUnit.objects.create(
            material=material,
            packaging_unit_name=packaging_unit_name,
            base_unit=base_unit,
            conversion_factor=conversion_factor,
            is_default=is_default,
            remark=remark
        )
        
        messages.success(request, f'包装单位"{packaging_unit_name}"创建成功')
        return redirect('inventory:packaging_unit_list', material_id=material_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/packaging_unit_form.html', {
        'material': material,
        'base_units': base_units,
        'action': 'create'
    })


@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_edit(request, material_id, packaging_unit_id):
    """编辑包装单位"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_unit = get_object_or_404(
        MaterialPackagingUnit,
        pk=packaging_unit_id,
        material=material
    )
    
    if request.method == 'POST':
        packaging_unit_name = request.POST.get('packaging_unit_name', '').strip()
        base_unit_id = request.POST.get('base_unit')
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        # 验证
        if not packaging_unit_name:
            messages.error(request, '请输入包装单位名称')
            return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在（排除自己）
        if MaterialPackagingUnit.objects.filter(
            material=material,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exclude(pk=packaging_unit_id).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            MaterialPackagingUnit.objects.filter(
                material=material,
                is_default=True
            ).exclude(pk=packaging_unit_id).update(is_default=False)
        
        # 更新
        packaging_unit.packaging_unit_name = packaging_unit_name
        packaging_unit.base_unit = base_unit
        packaging_unit.conversion_factor = conversion_factor
        packaging_unit.is_default = is_default
        packaging_unit.remark = remark
        packaging_unit.save()
        
        messages.success(request, f'包装单位"{packaging_unit_name}"更新成功')
        return redirect('inventory:packaging_unit_list', material_id=material_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/packaging_unit_form.html', {
        'material': material,
        'packaging_unit': packaging_unit,
        'base_units': base_units,
        'action': 'edit'
    })


@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_delete(request, material_id, packaging_unit_id):
    """删除包装单位（软删除）"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_unit = get_object_or_404(
        MaterialPackagingUnit,
        pk=packaging_unit_id,
        material=material
    )
    
    # 软删除
    packaging_unit.is_active = False
    packaging_unit.save()
    
    messages.success(request, f'包装单位"{packaging_unit.packaging_unit_name}"已删除')
    return redirect('inventory:packaging_unit_list', material_id=material_id)
