from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal, InvalidOperation
from inventory.models import Product, ProductPackagingUnit, Unit
from accounts.decorators import role_required


@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_list(request, product_id):
    """成品包装单位列表"""
    product = get_object_or_404(Product, pk=product_id)
    packaging_units = product.packaging_units.filter(is_active=True).order_by('display_order')
    
    return render(request, 'inventory/product_packaging_unit_list.html', {
        'product': product,
        'packaging_units': packaging_units
    })


@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_create(request, product_id):
    """创建成品包装单位"""
    product = get_object_or_404(Product, pk=product_id)
    
    if request.method == 'POST':
        packaging_unit_name = request.POST.get('packaging_unit_name', '').strip()
        base_unit_id = request.POST.get('base_unit')
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        # 验证
        if not packaging_unit_name:
            messages.error(request, '请输入包装单位名称')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在
        if ProductPackagingUnit.objects.filter(
            product=product,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            ProductPackagingUnit.objects.filter(
                product=product,
                is_default=True
            ).update(is_default=False)
        
        # 创建
        packaging_unit = ProductPackagingUnit.objects.create(
            product=product,
            packaging_unit_name=packaging_unit_name,
            base_unit=base_unit,
            conversion_factor=conversion_factor,
            is_default=is_default,
            remark=remark
        )
        
        messages.success(request, f'包装单位"{packaging_unit_name}"创建成功')
        return redirect('inventory:product_packaging_unit_list', product_id=product_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/product_packaging_unit_form.html', {
        'product': product,
        'base_units': base_units,
        'action': 'create'
    })


@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_edit(request, product_id, packaging_unit_id):
    """编辑成品包装单位"""
    product = get_object_or_404(Product, pk=product_id)
    packaging_unit = get_object_or_404(
        ProductPackagingUnit,
        pk=packaging_unit_id,
        product=product
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
            return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在（排除自己）
        if ProductPackagingUnit.objects.filter(
            product=product,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exclude(pk=packaging_unit_id).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            ProductPackagingUnit.objects.filter(
                product=product,
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
        return redirect('inventory:product_packaging_unit_list', product_id=product_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/product_packaging_unit_form.html', {
        'product': product,
        'packaging_unit': packaging_unit,
        'base_units': base_units,
        'action': 'edit'
    })


@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_delete(request, product_id, packaging_unit_id):
    """删除成品包装单位（软删除）"""
    product = get_object_or_404(Product, pk=product_id)
    packaging_unit = get_object_or_404(
        ProductPackagingUnit,
        pk=packaging_unit_id,
        product=product
    )
    
    # 软删除
    packaging_unit.is_active = False
    packaging_unit.save()
    
    messages.success(request, f'包装单位"{packaging_unit.packaging_unit_name}"已删除')
    return redirect('inventory:product_packaging_unit_list', product_id=product_id)
