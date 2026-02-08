"""物料显示单位变更视图

双单位体系重构后，只需修改 display_unit 字段即可，无需走审批流程。
基础单位不可变。
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_or_permission_required
from inventory.models import Material, Unit, ItemUnitConversion


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def unit_change_request(request, material_id):
    """修改物料显示单位（直接修改，无需审批）"""
    material = get_object_or_404(Material.objects.select_related('base_unit', 'display_unit'), pk=material_id)
    
    if request.method == 'POST':
        new_display_unit_id = request.POST.get('display_unit', '').strip()
        
        if not new_display_unit_id:
            messages.error(request, '请选择新的显示单位')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        try:
            new_display_unit = Unit.objects.get(pk=new_display_unit_id)
            
            # 校验：必须是基础单位或换算表中已定义的单位
            if new_display_unit.pk != material.base_unit_id:
                exists = ItemUnitConversion.objects.filter(
                    content_type='material',
                    material=material,
                    target_unit=new_display_unit,
                    is_active=True,
                ).exists()
                if not exists:
                    messages.error(request, f'「{new_display_unit.name}」不在该物料的换算表中，请先添加换算关系')
                    return redirect('inventory:unit_change_request', material_id=material_id)
            
            old_display_unit = material.display_unit
            material.display_unit = new_display_unit
            material.save(update_fields=['display_unit'])
            
            messages.success(request, f'显示单位已从「{old_display_unit.name}」修改为「{new_display_unit.name}」，不影响任何存储数据')
            return redirect('inventory:packaging_unit_list', material_id=material_id)
        
        except Unit.DoesNotExist:
            messages.error(request, '选择的单位不存在')
        except Exception as e:
            messages.error(request, f'修改失败：{str(e)}')
    
    # 获取可用的显示单位列表（基础单位 + 换算表中的单位）
    available_units = [material.base_unit]
    conversions = ItemUnitConversion.objects.filter(
        content_type='material', material=material, is_active=True
    ).select_related('target_unit')
    for conv in conversions:
        available_units.append(conv.target_unit)
    
    context = {
        'material': material,
        'available_units': available_units,
    }
    return render(request, 'inventory/unit_change_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def unit_change_history(request, material_id):
    """物料单位变更历史 — 双单位体系重构后不再需要历史记录"""
    material = get_object_or_404(Material, pk=material_id)
    messages.info(request, '双单位体系重构后，显示单位变更不影响数据，无需记录历史')
    return redirect('inventory:packaging_unit_list', material_id=material_id)
