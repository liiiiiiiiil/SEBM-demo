"""成品显示单位变更视图

双单位体系重构后，只需修改 display_unit 字段即可。
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_or_permission_required
from inventory.models import Product, Unit, ItemUnitConversion


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_unit_change_request(request, product_id):
    """修改成品显示单位"""
    product = get_object_or_404(Product.objects.select_related('base_unit', 'display_unit'), pk=product_id)
    
    if request.method == 'POST':
        new_display_unit_id = request.POST.get('display_unit', '').strip()
        
        if not new_display_unit_id:
            messages.error(request, '请选择新的显示单位')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
        
        try:
            new_display_unit = Unit.objects.get(pk=new_display_unit_id)
            
            if new_display_unit.pk != product.base_unit_id:
                exists = ItemUnitConversion.objects.filter(
                    content_type='product',
                    product=product,
                    target_unit=new_display_unit,
                    is_active=True,
                ).exists()
                if not exists:
                    messages.error(request, f'「{new_display_unit.name}」不在该成品的换算表中，请先添加换算关系')
                    return redirect('inventory:product_unit_change_request', product_id=product_id)
            
            old_display_unit = product.display_unit
            product.display_unit = new_display_unit
            product.save(update_fields=['display_unit'])
            
            messages.success(request, f'显示单位已从「{old_display_unit.name}」修改为「{new_display_unit.name}」，不影响任何存储数据')
            return redirect('inventory:product_packaging_unit_list', product_id=product_id)
        
        except Unit.DoesNotExist:
            messages.error(request, '选择的单位不存在')
        except Exception as e:
            messages.error(request, f'修改失败：{str(e)}')
    
    available_units = [product.base_unit]
    conversions = ItemUnitConversion.objects.filter(
        content_type='product', product=product, is_active=True
    ).select_related('target_unit')
    for conv in conversions:
        available_units.append(conv.target_unit)
    
    context = {
        'product': product,
        'available_units': available_units,
    }
    return render(request, 'inventory/product_unit_change_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_unit_change_history(request, product_id):
    """成品单位变更历史 — 不再需要"""
    product = get_object_or_404(Product, pk=product_id)
    messages.info(request, '双单位体系重构后，显示单位变更不影响数据，无需记录历史')
    return redirect('inventory:product_packaging_unit_list', product_id=product_id)
