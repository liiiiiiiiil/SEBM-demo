from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from inventory.models import Material, MaterialUnitChangeHistory
from inventory.services.unit_change import MaterialUnitChangeService
from accounts.decorators import role_required


@login_required
@role_required('warehouse', 'ceo')
def unit_change_request(request, material_id):
    """单位变更申请"""
    material = get_object_or_404(Material, pk=material_id)
    
    if request.method == 'POST':
        new_unit = request.POST.get('new_unit', '').strip()
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        reason = request.POST.get('reason', '').strip()
        force_change = request.POST.get('force_change') == 'on'  # 强制变更
        
        # 验证
        if not new_unit:
            messages.error(request, '请输入新单位')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        if not reason:
            messages.error(request, '请输入变更原因')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        # 前置检查
        check_result = MaterialUnitChangeService.check_can_change_unit(material)
        
        # 如果有严重问题且未选择强制变更
        if not check_result['can_change'] and not force_change:
            messages.error(request, '无法变更单位，存在业务冲突。如需强制变更，请勾选"强制变更"选项。')
            return render(request, 'inventory/unit_change_form.html', {
                'material': material,
                'check_result': check_result,
                'form_data': request.POST
            })
        
        # 执行变更
        try:
            change_history = MaterialUnitChangeService.change_unit(
                material=material,
                new_unit=new_unit,
                conversion_factor=conversion_factor,
                reason=reason,
                changed_by=request.user,
                auto_approve=True  # 根据业务规则决定是否需要审批
            )
            
            messages.success(request, '单位变更成功')
            return redirect('inventory:unit_change_history', material_id=material_id)
        
        except Exception as e:
            messages.error(request, f'单位变更失败：{str(e)}')
            return redirect('inventory:unit_change_request', material_id=material_id)
    
    # GET请求：显示变更表单
    check_result = MaterialUnitChangeService.check_can_change_unit(material)
    
    # 获取可用单位列表
    available_units = material.get_available_units()
    
    # 计算预览数据
    preview_data = None
    if material.unit and material.unit_price:
        preview_data = {
            'current_unit': material.unit,
            'current_unit_price': material.unit_price,
            'current_safety_stock': material.safety_stock,
        }
        # 获取当前库存
        try:
            from inventory.models import Inventory
            inventory = Inventory.objects.get(
                inventory_type='material',
                material=material
            )
            preview_data['current_inventory_quantity'] = inventory.quantity
        except:
            preview_data['current_inventory_quantity'] = Decimal('0')
    
    return render(request, 'inventory/unit_change_form.html', {
        'material': material,
        'check_result': check_result,
        'available_units': available_units,
        'preview_data': preview_data
    })


@login_required
@role_required('warehouse', 'ceo')
def unit_change_history(request, material_id):
    """单位变更历史"""
    material = get_object_or_404(Material, pk=material_id)
    history_list = MaterialUnitChangeHistory.objects.filter(
        material=material
    ).order_by('-changed_at').select_related('changed_by', 'approved_by')
    
    return render(request, 'inventory/unit_change_history.html', {
        'material': material,
        'history_list': history_list
    })
