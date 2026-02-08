"""物料单位换算表管理视图

双单位体系重构后，替代原 MaterialPackagingUnit 的管理界面。
现在管理 ItemUnitConversion (content_type='material') 记录。
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_or_permission_required
from inventory.models import Material, Unit, ItemUnitConversion


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def packaging_unit_list(request, material_id):
    """物料换算表列表"""
    material = get_object_or_404(Material.objects.select_related('base_unit', 'display_unit'), pk=material_id)
    conversions = ItemUnitConversion.objects.filter(
        content_type='material', material=material
    ).select_related('base_unit', 'target_unit').order_by('created_at')
    
    context = {
        'material': material,
        'conversions': conversions,
    }
    return render(request, 'inventory/packaging_unit_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def packaging_unit_create(request, material_id):
    """新增物料换算关系"""
    material = get_object_or_404(Material.objects.select_related('base_unit'), pk=material_id)
    
    if request.method == 'POST':
        target_unit_id = request.POST.get('target_unit', '').strip()
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        if not target_unit_id or not factor:
            messages.error(request, '请填写目标单位和换算系数')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        try:
            from decimal import Decimal
            target_unit = Unit.objects.get(pk=target_unit_id)
            factor_val = Decimal(factor)
            
            if target_unit.pk == material.base_unit_id:
                messages.error(request, '目标单位不能与基础单位相同')
                return redirect('inventory:packaging_unit_create', material_id=material_id)
            
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('inventory:packaging_unit_create', material_id=material_id)
            
            # 检查是否已存在
            if ItemUnitConversion.objects.filter(
                content_type='material', material=material, target_unit=target_unit
            ).exists():
                messages.error(request, f'已存在到「{target_unit.name}」的换算关系')
                return redirect('inventory:packaging_unit_create', material_id=material_id)
            
            ItemUnitConversion.objects.create(
                content_type='material',
                material=material,
                base_unit=material.base_unit,
                target_unit=target_unit,
                factor=factor_val,
                is_default=is_default,
                remark=remark,
            )
            messages.success(request, f'换算关系创建成功：1 {target_unit.name} = {factor_val} {material.base_unit.name}')
            return redirect('inventory:packaging_unit_list', material_id=material_id)
        except (Unit.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'创建失败：{str(e)}')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
    
    # 排除已有换算关系的单位和基础单位
    existing_unit_ids = list(
        ItemUnitConversion.objects.filter(content_type='material', material=material)
        .values_list('target_unit_id', flat=True)
    )
    existing_unit_ids.append(material.base_unit_id)
    available_units = Unit.objects.filter(is_active=True).exclude(pk__in=existing_unit_ids)
    
    context = {
        'material': material,
        'available_units': available_units,
    }
    return render(request, 'inventory/packaging_unit_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def packaging_unit_edit(request, material_id, packaging_unit_id):
    """编辑物料换算关系"""
    material = get_object_or_404(Material.objects.select_related('base_unit'), pk=material_id)
    conversion = get_object_or_404(
        ItemUnitConversion.objects.select_related('target_unit'),
        pk=packaging_unit_id,
        content_type='material',
        material=material,
    )
    
    if request.method == 'POST':
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        if not factor:
            messages.error(request, '请填写换算系数')
            return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
        
        try:
            from decimal import Decimal
            factor_val = Decimal(factor)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('inventory:packaging_unit_edit', material_id=material_id, packaging_unit_id=packaging_unit_id)
            
            conversion.factor = factor_val
            conversion.is_default = is_default
            conversion.is_active = is_active
            conversion.remark = remark
            conversion.save()
            
            messages.success(request, f'换算关系更新成功')
            return redirect('inventory:packaging_unit_list', material_id=material_id)
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    
    context = {
        'material': material,
        'conversion': conversion,
    }
    return render(request, 'inventory/packaging_unit_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def set_display_unit(request, material_id, unit_id):
    """将物料的显示单位设置为指定单位（基础单位或换算表中的单位）"""
    material = get_object_or_404(Material.objects.select_related('base_unit', 'display_unit'), pk=material_id)
    unit = get_object_or_404(Unit, pk=unit_id)

    if request.method == 'POST':
        # 校验：必须是基础单位或换算表中已定义的单位
        if unit.pk == material.base_unit_id:
            material.display_unit = unit
            material.save(update_fields=['display_unit'])
            messages.success(request, f'显示单位已切换为「{unit.name}」（基础单位）')
        else:
            exists = ItemUnitConversion.objects.filter(
                content_type='material', material=material,
                target_unit=unit, is_active=True,
            ).exists()
            if not exists:
                messages.error(request, f'「{unit.name}」不在该物料的换算表中')
                return redirect('inventory:packaging_unit_list', material_id=material_id)
            material.display_unit = unit
            material.save(update_fields=['display_unit'])
            messages.success(request, f'显示单位已切换为「{unit.name}」')
        return redirect('inventory:packaging_unit_list', material_id=material_id)
    return redirect('inventory:packaging_unit_list', material_id=material_id)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def packaging_unit_delete(request, material_id, packaging_unit_id):
    """删除物料换算关系"""
    material = get_object_or_404(Material, pk=material_id)
    conversion = get_object_or_404(
        ItemUnitConversion,
        pk=packaging_unit_id,
        content_type='material',
        material=material,
    )
    
    if request.method == 'POST':
        # 检查该单位是否被 BOM 使用
        from inventory.models import BOM
        bom_using = BOM.objects.filter(material=material, unit=conversion.target_unit).exists()
        if bom_using:
            messages.error(request, f'无法删除：该换算单位「{conversion.target_unit.name}」正在被 BOM 配方使用')
            return redirect('inventory:packaging_unit_list', material_id=material_id)
        
        # 检查是否是当前显示单位
        if material.display_unit_id == conversion.target_unit_id:
            messages.error(request, f'无法删除：该换算单位「{conversion.target_unit.name}」是当前的显示单位，请先修改显示单位')
            return redirect('inventory:packaging_unit_list', material_id=material_id)
        
        conversion.delete()
        messages.success(request, '换算关系已删除')
        return redirect('inventory:packaging_unit_list', material_id=material_id)
    
    # GET 请求：重定向到列表（删除应通过 POST 表单发起）
    return redirect('inventory:packaging_unit_list', material_id=material_id)
