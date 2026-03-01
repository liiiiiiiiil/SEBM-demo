from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required, permission_required, role_or_permission_required
from inventory.models import Inventory, StockTransaction, Product, Material, ProductCategory, MaterialCategory, InventoryAdjustmentRequest, BOM, Unit


@login_required
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.view')
def inventory_list(request):
    """库存列表。按类型细分：成品(product)、原料(raw)、半成品(semi)、辅料(auxiliary)、工具(tool)、办公物品(office)、其它(other)。"""
    inventory_type = request.GET.get('type', 'product')
    
    # 合并两类记录，创建一个统一的记录列表
    all_records = []
    
    # 添加库存变动记录（排除调整类类型）
    stock_transactions = StockTransaction.objects.filter(
        ~Q(transaction_type='adjustment'), ~Q(transaction_type='unit_change')
    ).select_related(
        'inventory', 'inventory__product', 'inventory__material',
        'inventory__product__base_unit', 'inventory__product__display_unit',
        'inventory__material__base_unit', 'inventory__material__display_unit',
        'operator', 'unit'
    ).order_by('-created_at')
    
    for trans in stock_transactions:
        # 使用基础单位数量（或回退到操作数量）转换为显示单位
        base_qty = trans.base_quantity if trans.base_quantity is not None else trans.quantity
        item = trans.inventory.get_item()
        if item and hasattr(item, 'to_display'):
            qty_disp, _ = item.to_display(abs(base_qty))
            disp_unit_name = item.display_unit.name if item.display_unit else (trans.unit.name if trans.unit else '')
        else:
            qty_disp = abs(base_qty)
            disp_unit_name = trans.unit.name if trans.unit else (trans.inventory.other_unit.name if trans.inventory.other_unit else '')
        if trans.transaction_type in ['sale_out', 'production_out']:
            qty_disp = -qty_disp
        
        if trans.inventory.inventory_type == 'product':
            item_name = trans.inventory.product.name if trans.inventory.product else '-'
        elif trans.inventory.inventory_type == 'material':
            item_name = trans.inventory.material.name if trans.inventory.material else '-'
        elif trans.inventory.inventory_type == 'other':
            item_name = trans.inventory.other_name if trans.inventory.other_name else '-'
        else:
            item_name = '-'
        
        all_records.append({
            'type': 'transaction',
            'record_type': '出入库',
            'transaction_type': trans.get_transaction_type_display(),
            'item_name': item_name,
            'item_type': trans.inventory.get_detailed_type_display(),
            'quantity': qty_disp,
            'unit': disp_unit_name,
            'reference_no': trans.reference_no,
            'operator': trans.operator.username,
            'created_at': trans.created_at,
            'remark': trans.remark,
        })
    
    # 添加库存调整记录
    adjustment_transactions = StockTransaction.objects.filter(
        transaction_type__in=['adjustment', 'unit_change']
    ).select_related(
        'inventory', 'inventory__product', 'inventory__material',
        'inventory__product__base_unit', 'inventory__product__display_unit',
        'inventory__material__base_unit', 'inventory__material__display_unit',
        'operator', 'unit'
    ).order_by('-created_at')
    
    for trans in adjustment_transactions:
        item = trans.inventory.get_item()
        if item and hasattr(item, 'to_display'):
            def to_disp(base_val):
                if base_val is None:
                    return None
                d, _ = item.to_display(abs(Decimal(str(base_val))))
                return d
            disp_unit_name = item.display_unit.name if item.display_unit else (trans.unit.name if trans.unit else '')
        else:
            def to_disp(base_val):
                return base_val
            disp_unit_name = trans.unit.name if trans.unit else (trans.inventory.other_unit.name if trans.inventory.other_unit else '')
        
        if trans.inventory.inventory_type == 'product':
            item_name = trans.inventory.product.name if trans.inventory.product else '-'
        elif trans.inventory.inventory_type == 'material':
            item_name = trans.inventory.material.name if trans.inventory.material else '-'
        elif trans.inventory.inventory_type == 'other':
            item_name = trans.inventory.other_name if trans.inventory.other_name else '-'
        else:
            item_name = '-'
        
        is_unit_change = (trans.transaction_type == 'unit_change')
        record_type_label = '单位调整' if is_unit_change else '库存调整'
        
        current_quantity = None
        new_quantity = None
        adjust_quantity = None
        old_unit_price = None
        new_unit_price = None
        if not is_unit_change:
            try:
                adj = InventoryAdjustmentRequest.objects.select_related('inventory').get(request_no=trans.reference_no)
                # 转换为显示单位
                current_quantity = to_disp(adj.current_quantity)
                new_quantity = to_disp(adj.new_quantity)
                adjust_quantity = to_disp(adj.adjust_quantity)
                # 单价：基础单位单价转换为显示单位单价
                if adj.current_unit_price is not None and adj.new_unit_price is not None and item:
                    from inventory.services.unit_conversion import UnitConversionService
                    try:
                        factor = UnitConversionService.get_factor(item, item.display_unit)
                        old_unit_price = float(adj.current_unit_price) * float(factor)
                        new_unit_price = float(adj.new_unit_price) * float(factor)
                    except (ValueError, Exception):
                        old_unit_price = float(adj.current_unit_price)
                        new_unit_price = float(adj.new_unit_price)
            except InventoryAdjustmentRequest.DoesNotExist:
                pass
        
        # 变动数量转为显示单位
        base_qty = trans.base_quantity if trans.base_quantity is not None else trans.quantity
        if item and hasattr(item, 'to_display'):
            qty_disp, _ = item.to_display(abs(base_qty))
            qty_disp = qty_disp if base_qty >= 0 else -qty_disp
        else:
            qty_disp = trans.quantity
        
        all_records.append({
            'type': 'adjustment',
            'record_type': record_type_label,
            'transaction_type': record_type_label,
            'item_name': item_name,
            'item_type': trans.inventory.get_detailed_type_display(),
            'quantity': qty_disp,
            'unit': disp_unit_name,
            'reference_no': trans.reference_no,
            'operator': trans.operator.username,
            'created_at': trans.created_at,
            'remark': trans.remark,
            'current_quantity': current_quantity,
            'new_quantity': new_quantity,
            'adjust_quantity': adjust_quantity,
            'old_unit_price': old_unit_price,
            'new_unit_price': new_unit_price,
        })
    
    # 按时间倒序排序
    all_records.sort(key=lambda x: x['created_at'], reverse=True)
    
    # 分页处理
    paginator = Paginator(all_records, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # 获取库存列表
    inventories = Inventory.objects.select_related(
        'product_master', 'product_master__base_unit', 'product_master__display_unit',
        'product', 'material',
        'product__base_unit', 'product__display_unit',
        'material__base_unit', 'material__display_unit',
    ).prefetch_related('batches').all()
    
    # 按类型细分：成品 | 原料/半成品/辅料/工具/办公物品/其它（物料+库存其它）
    if inventory_type == 'product':
        inventories = inventories.filter(inventory_type='product')
    elif inventory_type == 'other':
        inventories = inventories.filter(
            Q(inventory_type='other') | Q(inventory_type='material', material__material_type='other')
        )
    elif inventory_type == 'material':
        # 兼容旧链接：原料
        inventories = inventories.filter(inventory_type='material', material__material_type='raw')
    elif inventory_type in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        inventories = inventories.filter(inventory_type='material', material__material_type=inventory_type)
    else:
        inventories = inventories.filter(inventory_type='product')
    
    # 为每个库存计算显示信息
    inventories_list = list(inventories)
    for inv in inventories_list:
        raw_batches = inv.get_batches().filter(quantity__gt=0)
        item = inv.get_item()
        batch_display_list = []
        for b in raw_batches:
            if item and hasattr(item, 'to_display'):
                d_qty, _ = item.to_display(b.quantity)
            else:
                d_qty = b.quantity
            # 附加 display_quantity 属性
            b.display_quantity = d_qty
            batch_display_list.append(b)
        inv.batches_list = batch_display_list
        inv.display_qty = inv.get_display_quantity()
        inv.display_unit_name = inv.get_display_unit_name()
        inv.base_unit_name = inv.get_unit_name()
        # 统一显示名称：优先产品主数据，其次 other_name（兼容未迁移的其它）
        inv.display_name = (item.name if item else None) or getattr(inv, 'other_name', None) or '-'
    
    # 查询待审批的调整申请
    can_approve = request.user.profile.role == 'ceo' or request.user.profile.has_permission('inventory.adjustment.approve')
    pending_adjustments = {}
    if can_approve:
        pending_adjs = InventoryAdjustmentRequest.objects.filter(
            status='pending'
        ).select_related('inventory', 'applicant')
        for adj in pending_adjs:
            inv_id = adj.inventory_id
            if inv_id not in pending_adjustments:
                pending_adjustments[inv_id] = []
            pending_adjustments[inv_id].append(adj)
    
    for inv in inventories_list:
        inv.pending_adjustments = pending_adjustments.get(inv.pk, [])
    
    context = {
        'page_obj': page_obj,
        'inventories': inventories_list,
        'inventory_type': inventory_type,
        'can_approve': can_approve,
    }
    return render(request, 'inventory/inventory_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.transaction.view')
def stock_transactions(request):
    """库存变动记录"""
    transactions = StockTransaction.objects.select_related('inventory', 'operator', 'unit').all()
    
    transaction_type = request.GET.get('type', '')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    context = {
        'transactions': transactions[:100],
        'transaction_type': transaction_type,
    }
    return render(request, 'inventory/stock_transactions.html', context)


@login_required
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.view')
def inventory_detail(request, pk):
    """库存详情"""
    inventory = get_object_or_404(
        Inventory.objects.select_related(
            'product_master', 'product_master__base_unit', 'product_master__display_unit',
            'product', 'material',
            'product__base_unit', 'product__display_unit',
            'material__base_unit', 'material__display_unit',
        ),
        pk=pk,
    )
    
    transactions_qs = StockTransaction.objects.filter(
        inventory=inventory
    ).select_related('batch', 'operator', 'unit').order_by('-created_at')
    
    paginator = Paginator(transactions_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 为进出记录附加显示单位下的数量和单位
    item = inventory.get_item()
    for trans in page_obj.object_list:
        base_qty = trans.base_quantity if trans.base_quantity is not None else trans.quantity
        if item and hasattr(item, 'to_display'):
            qty_disp, _ = item.to_display(abs(base_qty))
            qty_disp = qty_disp if base_qty >= 0 else -qty_disp
            disp_unit_name = item.display_unit.name if item.display_unit else (trans.unit.name if trans.unit else '')
        else:
            qty_disp = trans.quantity
            disp_unit_name = trans.unit.name if trans.unit else (inventory.other_unit.name if inventory.other_unit else '')
        if trans.transaction_type in ['sale_out', 'production_out']:
            qty_disp = -abs(qty_disp)
        trans.quantity_display = qty_disp
        trans.unit_display = disp_unit_name
    
    raw_batches = inventory.get_batches().order_by('-batch_date', '-created_at')
    
    # 为批次附加显示单位数量
    item = inventory.get_item()
    batches = []
    for batch in raw_batches:
        if item and hasattr(item, 'to_display'):
            disp_qty, _ = item.to_display(batch.quantity)
        else:
            disp_qty = batch.quantity
        batches.append({
            'batch_no': batch.batch_no,
            'batch_date': batch.batch_date,
            'quantity': batch.quantity,
            'display_quantity': disp_qty,
            'unit_price': batch.unit_price,
            'expiry_date': batch.expiry_date,
            'is_expired': batch.is_expired(),
            'supplier': getattr(batch, 'supplier', None),
            'remark': batch.remark,
        })
    
    context = {
        'inventory': inventory,
        'transactions': page_obj,
        'batches': batches,
    }
    return render(request, 'inventory/inventory_detail.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.view')
def product_list(request):
    """产品列表"""
    products = Product.objects.select_related('base_unit', 'display_unit').all()
    
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(sku__icontains=search) | 
            Q(name__icontains=search)
        )
    
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    extra_params = ''
    if search:
        extra_params = f'search={search}'
    
    context = {
        'products': page_obj,
        'search': search,
        'extra_params': extra_params,
        'can_manage': request.user.profile.has_permission('inventory.product.manage'),
    }
    return render(request, 'inventory/product_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_create(request):
    """创建产品"""
    from inventory.forms import ProductForm
    
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'产品 {product.name} 创建成功')
            return redirect('inventory:product_list')
    else:
        form = ProductForm()
    
    return render(request, 'inventory/product_form.html', {'form': form, 'title': '创建产品'})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_edit(request, pk):
    """编辑产品"""
    from inventory.forms import ProductForm
    
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'产品 {product.name} 更新成功')
            return redirect('inventory:product_list')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'inventory/product_form.html', {'form': form, 'title': '编辑产品', 'product': product})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_delete(request, pk):
    """删除产品"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.delete()
        messages.success(request, f'产品 {product.name} 删除成功')
        return redirect('inventory:product_list')
    
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


def _adjustment_create_context(inventory, form):
    """调整申请页上下文"""
    return {
        'form': form,
        'inventory': inventory,
    }


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.adjustment.create')
def inventory_adjustment_create(request, inventory_pk):
    """创建库存调整申请（数量/单价统一入口，不再支持单位调整）"""
    from inventory.forms import InventoryAdjustmentRequestForm
    from django.utils import timezone
    
    inventory = get_object_or_404(Inventory, pk=inventory_pk)
    
    if request.method == 'POST':
        form = InventoryAdjustmentRequestForm(request.POST)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.inventory = inventory
            adjustment.current_quantity = inventory.quantity
            adjustment.current_unit_price = inventory.get_unit_price()
            adjustment.applicant = request.user
            adjustment.request_no = f"IAR{timezone.now().strftime('%Y%m%d%H%M%S')}"
            
            # 库存管理仅支持数量调整；单价/单位请在「产品管理」中修改
            adjust_quantity = form.cleaned_data.get('adjust_quantity') or 0
            adjustment.adjustment_type = 'quantity'
            adjustment.adjust_quantity = adjust_quantity
            adjustment.new_quantity = adjustment.current_quantity + adjust_quantity
            adjustment.adjust_unit_price = None
            adjustment.new_unit_price = adjustment.current_unit_price
            
            if adjustment.new_quantity < 0:
                messages.error(request, '调整后数量不能为负数')
                return render(request, 'inventory/adjustment_form.html', _adjustment_create_context(inventory, form))
            
            adjustment.save()
            messages.success(request, f'库存调整申请 {adjustment.request_no} 已提交，等待总经理审批')
            return redirect('inventory:adjustment_list')
    else:
        form = InventoryAdjustmentRequestForm()
    
    return render(request, 'inventory/adjustment_form.html', _adjustment_create_context(inventory, form))


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.adjustment.create')
def adjustment_list(request):
    """库存调整申请列表"""
    adjustments = InventoryAdjustmentRequest.objects.select_related('inventory', 'applicant', 'approved_by').all()
    
    if request.user.profile.role == 'warehouse' and not request.user.profile.has_permission('inventory.adjustment.approve'):
        adjustments = adjustments.filter(applicant=request.user)
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        adjustments = adjustments.filter(status=status_filter)
    
    paginator = Paginator(adjustments, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    extra_params = ''
    if status_filter:
        extra_params = f'status={status_filter}'
    
    context = {
        'adjustments': page_obj,
        'status_filter': status_filter,
        'extra_params': extra_params,
        'can_approve': request.user.profile.has_permission('inventory.adjustment.approve'),
    }
    return render(request, 'inventory/adjustment_list.html', context)


@login_required
@role_or_permission_required('ceo', permission_code='inventory.adjustment.approve')
def adjustment_approve(request, pk):
    """审批库存调整申请（仅数量/单价调整，不再支持单位调整）"""
    from django.db import transaction
    from django.utils import timezone
    
    adjustment = get_object_or_404(InventoryAdjustmentRequest, pk=pk)
    
    if adjustment.status != 'pending':
        messages.error(request, '只能审批待审批状态的申请')
        return redirect('inventory:adjustment_list')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            inventory = adjustment.inventory
            
            with transaction.atomic():
                adjustment.status = 'approved'
                adjustment.approved_by = request.user
                adjustment.approved_at = timezone.now()
                adjustment.save()
                
                # 仅数量调整（单价/单位请在「产品管理」中修改）
                inventory.quantity = adjustment.new_quantity
                inventory.save()
                remark_parts = [f"库存调整：{adjustment.reason}"]
                
                # 获取基础单位用于 StockTransaction
                item = inventory.get_item()
                base_unit = item.base_unit if item and hasattr(item, 'base_unit') else None
                if base_unit is None and inventory.inventory_type == 'other':
                    base_unit = inventory.other_unit
                
                if base_unit:
                    StockTransaction.objects.create(
                        transaction_type='adjustment',
                        inventory=inventory,
                        quantity=adjustment.adjust_quantity,
                        unit=base_unit,
                        base_quantity=adjustment.adjust_quantity,
                        reference_no=adjustment.request_no,
                        remark="；".join(remark_parts),
                        operator=request.user,
                    )
                
                adjustment.status = 'completed'
                adjustment.save()
                messages.success(request, f'库存调整申请 {adjustment.request_no} 已审批通过，库存已更新')
        
        elif action == 'reject':
            reject_reason = request.POST.get('reject_reason', '').strip()
            if not reject_reason:
                messages.error(request, '请输入拒绝原因')
                return render(request, 'inventory/adjustment_approve.html', {'adjustment': adjustment})
            
            adjustment.status = 'rejected'
            adjustment.approved_by = request.user
            adjustment.approved_at = timezone.now()
            adjustment.reject_reason = reject_reason
            adjustment.save()
            
            messages.success(request, f'库存调整申请 {adjustment.request_no} 已拒绝')
        
        return redirect('inventory:adjustment_list')
    
    return render(request, 'inventory/adjustment_approve.html', {'adjustment': adjustment})


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.view')
def bom_list(request):
    """BOM配方列表"""
    boms = BOM.objects.select_related('product', 'material', 'unit', 'material__base_unit').all()
    
    product_filter = request.GET.get('product', '')
    if product_filter:
        boms = boms.filter(product_id=product_filter)
    
    products = Product.objects.all().order_by('sku')
    
    # 按产品分组
    bom_by_product = {}
    for bom in boms:
        product_id = bom.product.id
        if product_id not in bom_by_product:
            bom_by_product[product_id] = {
                'product': bom.product,
                'items': []
            }
        bom_by_product[product_id]['items'].append(bom)
    
    context = {
        'bom_by_product': bom_by_product,
        'products': products,
        'product_filter': product_filter,
        'can_manage': request.user.profile.has_permission('inventory.bom.manage'),
    }
    return render(request, 'inventory/bom_list.html', context)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_edit(request, product_id):
    """编辑某产品的 BOM 配方（整体管理页面）"""
    product = get_object_or_404(Product.objects.select_related('base_unit', 'display_unit'), pk=product_id)
    bom_items = BOM.objects.filter(product=product).select_related('material', 'material__base_unit', 'material__display_unit', 'unit').order_by('material__sku')
    materials = Material.objects.select_related('base_unit', 'display_unit').all().order_by('sku')
    # 排除已在 BOM 中的原料
    existing_material_ids = bom_items.values_list('material_id', flat=True)
    available_materials = materials.exclude(id__in=existing_material_ids)

    context = {
        'product': product,
        'bom_items': bom_items,
        'available_materials': available_materials,
    }
    return render(request, 'inventory/bom_edit.html', context)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_add(request, product_id):
    """添加 BOM 行"""
    product = get_object_or_404(Product, pk=product_id)

    if request.method == 'POST':
        material_id = request.POST.get('material')
        quantity = request.POST.get('quantity')
        unit_id = request.POST.get('unit')

        if not material_id or not quantity or not unit_id:
            messages.error(request, '请填写完整的原料、用量和单位信息')
            return redirect('inventory:bom_edit', product_id=product_id)

        try:
            material = Material.objects.select_related('base_unit').get(pk=material_id)
            unit = Unit.objects.get(pk=unit_id)
            qty = Decimal(quantity)

            if qty <= 0:
                messages.error(request, '用量必须大于0')
                return redirect('inventory:bom_edit', product_id=product_id)

            if BOM.objects.filter(product=product, material=material).exists():
                messages.error(request, f'原料「{material.name}」已在该产品的 BOM 中')
                return redirect('inventory:bom_edit', product_id=product_id)

            BOM.objects.create(
                product=product,
                material=material,
                quantity=qty,
                unit=unit,
            )
            messages.success(request, f'已添加原料「{material.name}」到 BOM 配方')
        except Material.DoesNotExist:
            messages.error(request, '原料不存在')
        except Unit.DoesNotExist:
            messages.error(request, '单位不存在')
        except (ValueError, Exception) as e:
            messages.error(request, f'添加失败：{str(e)}')

    return redirect('inventory:bom_edit', product_id=product_id)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_edit(request, product_id, bom_id):
    """编辑 BOM 行"""
    product = get_object_or_404(Product, pk=product_id)
    bom_item = get_object_or_404(BOM.objects.select_related('material', 'material__base_unit', 'unit'), pk=bom_id, product=product)

    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        unit_id = request.POST.get('unit')

        if not quantity or not unit_id:
            messages.error(request, '请填写用量和单位')
            return redirect('inventory:bom_edit', product_id=product_id)

        try:
            unit = Unit.objects.get(pk=unit_id)
            qty = Decimal(quantity)

            if qty <= 0:
                messages.error(request, '用量必须大于0')
                return redirect('inventory:bom_edit', product_id=product_id)

            bom_item.quantity = qty
            bom_item.unit = unit
            bom_item.save()
            messages.success(request, f'已更新原料「{bom_item.material.name}」的配方')
        except Unit.DoesNotExist:
            messages.error(request, '单位不存在')
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')

    return redirect('inventory:bom_edit', product_id=product_id)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_delete(request, product_id, bom_id):
    """删除 BOM 行"""
    product = get_object_or_404(Product, pk=product_id)
    bom_item = get_object_or_404(BOM, pk=bom_id, product=product)

    if request.method == 'POST':
        material_name = bom_item.material.name
        bom_item.delete()
        messages.success(request, f'已从 BOM 配方中删除原料「{material_name}」')

    return redirect('inventory:bom_edit', product_id=product_id)
