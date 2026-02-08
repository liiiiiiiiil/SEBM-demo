"""成品单位换算表管理视图

双单位体系重构后，替代原 ProductPackagingUnit 的管理界面。
管理 ItemUnitConversion (content_type='product') 记录。
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_or_permission_required
from inventory.models import Product, Unit, ItemUnitConversion


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_list(request, product_id):
    """成品换算表列表"""
    product = get_object_or_404(Product.objects.select_related('base_unit', 'display_unit'), pk=product_id)
    conversions = ItemUnitConversion.objects.filter(
        content_type='product', product=product
    ).select_related('base_unit', 'target_unit').order_by('created_at')
    
    context = {
        'product': product,
        'conversions': conversions,
    }
    return render(request, 'inventory/product_packaging_unit_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_create(request, product_id):
    """新增成品换算关系"""
    product = get_object_or_404(Product.objects.select_related('base_unit'), pk=product_id)
    
    if request.method == 'POST':
        target_unit_id = request.POST.get('target_unit', '').strip()
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        if not target_unit_id or not factor:
            messages.error(request, '请填写目标单位和换算系数')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        try:
            from decimal import Decimal
            target_unit = Unit.objects.get(pk=target_unit_id)
            factor_val = Decimal(factor)
            
            if target_unit.pk == product.base_unit_id:
                messages.error(request, '目标单位不能与基础单位相同')
                return redirect('inventory:product_packaging_unit_create', product_id=product_id)
            
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('inventory:product_packaging_unit_create', product_id=product_id)
            
            if ItemUnitConversion.objects.filter(
                content_type='product', product=product, target_unit=target_unit
            ).exists():
                messages.error(request, f'已存在到「{target_unit.name}」的换算关系')
                return redirect('inventory:product_packaging_unit_create', product_id=product_id)
            
            ItemUnitConversion.objects.create(
                content_type='product',
                product=product,
                base_unit=product.base_unit,
                target_unit=target_unit,
                factor=factor_val,
                is_default=is_default,
                remark=remark,
            )
            messages.success(request, f'换算关系创建成功：1 {target_unit.name} = {factor_val} {product.base_unit.name}')
            return redirect('inventory:product_packaging_unit_list', product_id=product_id)
        except (Unit.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'创建失败：{str(e)}')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
    
    existing_unit_ids = list(
        ItemUnitConversion.objects.filter(content_type='product', product=product)
        .values_list('target_unit_id', flat=True)
    )
    existing_unit_ids.append(product.base_unit_id)
    available_units = Unit.objects.filter(is_active=True).exclude(pk__in=existing_unit_ids)
    
    context = {
        'product': product,
        'available_units': available_units,
    }
    return render(request, 'inventory/product_packaging_unit_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_edit(request, product_id, packaging_unit_id):
    """编辑成品换算关系"""
    product = get_object_or_404(Product.objects.select_related('base_unit'), pk=product_id)
    conversion = get_object_or_404(
        ItemUnitConversion.objects.select_related('target_unit'),
        pk=packaging_unit_id,
        content_type='product',
        product=product,
    )
    
    if request.method == 'POST':
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        if not factor:
            messages.error(request, '请填写换算系数')
            return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        
        try:
            from decimal import Decimal
            factor_val = Decimal(factor)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
            
            conversion.factor = factor_val
            conversion.is_default = is_default
            conversion.is_active = is_active
            conversion.remark = remark
            conversion.save()
            
            messages.success(request, f'换算关系更新成功')
            return redirect('inventory:product_packaging_unit_list', product_id=product_id)
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    
    context = {
        'product': product,
        'conversion': conversion,
    }
    return render(request, 'inventory/product_packaging_unit_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_set_display_unit(request, product_id, unit_id):
    """将成品的显示单位设置为指定单位"""
    product = get_object_or_404(Product.objects.select_related('base_unit', 'display_unit'), pk=product_id)
    unit = get_object_or_404(Unit, pk=unit_id)

    if request.method == 'POST':
        if unit.pk == product.base_unit_id:
            product.display_unit = unit
            product.save(update_fields=['display_unit'])
            messages.success(request, f'显示单位已切换为「{unit.name}」（基础单位）')
        else:
            exists = ItemUnitConversion.objects.filter(
                content_type='product', product=product,
                target_unit=unit, is_active=True,
            ).exists()
            if not exists:
                messages.error(request, f'「{unit.name}」不在该成品的换算表中')
                return redirect('inventory:product_packaging_unit_list', product_id=product_id)
            product.display_unit = unit
            product.save(update_fields=['display_unit'])
            messages.success(request, f'显示单位已切换为「{unit.name}」')
        return redirect('inventory:product_packaging_unit_list', product_id=product_id)
    return redirect('inventory:product_packaging_unit_list', product_id=product_id)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_delete(request, product_id, packaging_unit_id):
    """删除成品换算关系"""
    product = get_object_or_404(Product, pk=product_id)
    conversion = get_object_or_404(
        ItemUnitConversion,
        pk=packaging_unit_id,
        content_type='product',
        product=product,
    )
    
    if request.method == 'POST':
        if product.display_unit_id == conversion.target_unit_id:
            messages.error(request, f'无法删除：该换算单位「{conversion.target_unit.name}」是当前的显示单位，请先修改显示单位')
            return redirect('inventory:product_packaging_unit_list', product_id=product_id)
        
        conversion.delete()
        messages.success(request, '换算关系已删除')
        return redirect('inventory:product_packaging_unit_list', product_id=product_id)
    
    return redirect('inventory:product_packaging_unit_list', product_id=product_id)
