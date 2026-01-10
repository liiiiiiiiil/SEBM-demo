from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from accounts.decorators import role_required, permission_required, role_or_permission_required
from .models import Inventory, StockTransaction, Product, Material, Customer, ProductCategory, MaterialCategory, InventoryAdjustmentRequest, BOM, PurchaseOrder, PurchaseOrderItem
from production.models import MaterialRequisition, MaterialRequisitionItem


@login_required
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.view')
def inventory_list(request):
    """库存列表"""
    inventory_type = request.GET.get('type', '')
    
    inventories = Inventory.objects.select_related('product', 'material').all()
    
    if inventory_type == 'product':
        inventories = inventories.filter(inventory_type='product')
    elif inventory_type == 'material':
        inventories = inventories.filter(inventory_type='material')
    
    # 检查安全库存预警
    warnings = []
    for inv in inventories:
        if inv.check_safety_stock():
            warnings.append(inv)
    
    context = {
        'inventories': inventories,
        'inventory_type': inventory_type,
        'warnings': warnings,
    }
    return render(request, 'inventory/inventory_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.transaction.view')
def stock_transactions(request):
    """库存变动记录"""
    transactions = StockTransaction.objects.select_related('inventory', 'operator').all()
    
    transaction_type = request.GET.get('type', '')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    context = {
        'transactions': transactions[:100],  # 限制显示数量
        'transaction_type': transaction_type,
    }
    return render(request, 'inventory/stock_transactions.html', context)


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.view')
def customer_list(request):
    """客户列表"""
    customers = Customer.objects.select_related('created_by').all()
    
    # 权限控制：销售员只能看到自己创建的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    # 销售经理和总经理可以看到所有客户
    elif request.user.profile.role in ['sales_mgr', 'ceo'] or request.user.profile.has_permission('inventory.customer.manage'):
        pass  # 显示所有客户
    # 其他角色（如仓库管理员）如果有查看权限，也只能看到自己创建的
    elif not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | 
            Q(contact_person__icontains=search) |
            Q(phone__icontains=search)
        )
    
    context = {
        'customers': customers,
        'search': search,
    }
    return render(request, 'inventory/customer_list.html', context)


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.create')
def customer_create(request):
    """创建客户"""
    from .forms import CustomerForm
    
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            messages.success(request, f'客户 {customer.name} 创建成功')
            return redirect('inventory:customer_list')
    else:
        form = CustomerForm()
    
    return render(request, 'inventory/customer_form.html', {'form': form, 'title': '创建客户'})


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.edit')
def customer_edit(request, pk):
    """编辑客户"""
    from .forms import CustomerForm
    
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能编辑自己创建的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能编辑自己创建的客户')
            return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f'客户 {customer.name} 更新成功')
            return redirect('inventory:customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'inventory/customer_form.html', {'form': form, 'title': '编辑客户', 'customer': customer})


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.delete')
def customer_delete(request, pk):
    """删除客户"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能删除自己创建的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能删除自己创建的客户')
            return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        customer_name = customer.name
        customer.delete()
        messages.success(request, f'客户 {customer_name} 已删除')
        return redirect('inventory:customer_list')
    
    return render(request, 'inventory/customer_confirm_delete.html', {'customer': customer})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.view')
def product_list(request):
    """产品列表"""
    products = Product.objects.all()
    
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(sku__icontains=search) | 
            Q(name__icontains=search)
        )
    
    context = {
        'products': products,
        'search': search,
        'can_manage': request.user.profile.has_permission('inventory.product.manage'),
    }
    return render(request, 'inventory/product_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_create(request):
    """创建产品"""
    from .forms import ProductForm
    
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
    from .forms import ProductForm
    
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


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.adjustment.create')
def inventory_adjustment_create(request, inventory_pk):
    """创建库存调整申请"""
    from .forms import InventoryAdjustmentRequestForm
    from django.utils import timezone
    
    inventory = get_object_or_404(Inventory, pk=inventory_pk)
    
    if request.method == 'POST':
        form = InventoryAdjustmentRequestForm(request.POST)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.inventory = inventory
            adjustment.current_quantity = inventory.quantity
            adjustment.applicant = request.user
            adjustment.request_no = f"IAR{timezone.now().strftime('%Y%m%d%H%M%S')}"
            adjustment.new_quantity = adjustment.current_quantity + adjustment.adjust_quantity
            
            if adjustment.new_quantity < 0:
                messages.error(request, '调整后数量不能为负数')
                return render(request, 'inventory/adjustment_form.html', {'form': form, 'inventory': inventory})
            
            adjustment.save()
            messages.success(request, f'库存调整申请 {adjustment.request_no} 已提交，等待总经理审批')
            return redirect('inventory:adjustment_list')
    else:
        form = InventoryAdjustmentRequestForm()
    
    return render(request, 'inventory/adjustment_form.html', {'form': form, 'inventory': inventory})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.adjustment.create')
def adjustment_list(request):
    """库存调整申请列表"""
    adjustments = InventoryAdjustmentRequest.objects.select_related('inventory', 'applicant', 'approved_by').all()
    
    # 仓库管理员只能看自己申请的
    if request.user.profile.role == 'warehouse' and not request.user.profile.has_permission('inventory.adjustment.approve'):
        adjustments = adjustments.filter(applicant=request.user)
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        adjustments = adjustments.filter(status=status_filter)
    
    context = {
        'adjustments': adjustments,
        'status_filter': status_filter,
        'can_approve': request.user.profile.has_permission('inventory.adjustment.approve'),
    }
    return render(request, 'inventory/adjustment_list.html', context)


@login_required
@role_or_permission_required('ceo', permission_code='inventory.adjustment.approve')
def adjustment_approve(request, pk):
    """审批库存调整申请"""
    from django.db import transaction
    from django.utils import timezone
    
    adjustment = get_object_or_404(InventoryAdjustmentRequest, pk=pk)
    
    if adjustment.status != 'pending':
        messages.error(request, '只能审批待审批状态的申请')
        return redirect('inventory:adjustment_list')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            with transaction.atomic():
                adjustment.status = 'approved'
                adjustment.approved_by = request.user
                adjustment.approved_at = timezone.now()
                adjustment.save()
                
                # 执行库存调整
                inventory = adjustment.inventory
                inventory.quantity = adjustment.new_quantity
                inventory.save()
                
                # 创建库存变动记录
                StockTransaction.objects.create(
                    transaction_type='adjustment',
                    inventory=inventory,
                    quantity=adjustment.adjust_quantity,
                    unit=inventory.unit,
                    reference_no=adjustment.request_no,
                    remark=f"库存调整：{adjustment.reason}",
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
    boms = BOM.objects.select_related('product', 'material').all()
    
    # 按产品筛选
    product_filter = request.GET.get('product', '')
    if product_filter:
        boms = boms.filter(product_id=product_filter)
    
    # 获取所有产品用于筛选
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
@role_or_permission_required('warehouse', 'ceo', permission_code='production.requisition.approve')
def requisition_list(request):
    """领料单列表"""
    requisitions = MaterialRequisition.objects.select_related('task', 'requested_by').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        requisitions = requisitions.filter(status=status_filter)
    
    context = {
        'requisitions': requisitions,
        'status_filter': status_filter,
    }
    return render(request, 'inventory/requisition_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='production.requisition.approve')
def requisition_approve(request, pk):
    """审核领料单"""
    requisition = get_object_or_404(MaterialRequisition.objects.prefetch_related('items__material'), pk=pk)
    
    if requisition.status != 'pending':
        messages.error(request, '领料单状态不正确')
        return redirect('inventory:requisition_list')
    
    # 检查库存是否充足
    insufficient_items = []
    for item in requisition.items.all():
        try:
            inventory = Inventory.objects.get(inventory_type='material', material=item.material)
            if inventory.quantity < item.required_quantity:
                shortage = item.required_quantity - inventory.quantity
                insufficient_items.append({
                    'material': item.material,
                    'material_name': item.material.name,
                    'required': item.required_quantity,
                    'available': inventory.quantity,
                    'shortage': shortage,
                    'unit': item.unit,
                })
        except Inventory.DoesNotExist:
            insufficient_items.append({
                'material': item.material,
                'material_name': item.material.name,
                'required': item.required_quantity,
                'available': Decimal('0'),
                'shortage': item.required_quantity,
                'unit': item.unit,
            })
    
    if request.method == 'POST':
        if insufficient_items:
            messages.error(request, '部分原料库存不足，无法批准')
            return redirect('inventory:requisition_approve', pk=pk)
        
        with transaction.atomic():
            requisition.status = 'approved'
            requisition.approved_by = request.user
            requisition.approved_at = timezone.now()
            requisition.save()
            
            # 扣减库存
            for item in requisition.items.all():
                inventory = Inventory.objects.get(inventory_type='material', material=item.material)
                inventory.quantity -= item.required_quantity
                inventory.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='production_out',
                    inventory=inventory,
                    quantity=item.required_quantity,
                    unit=item.unit,
                    reference_no=requisition.requisition_no,
                    operator=request.user,
                )
            
            requisition.task.status = 'material_preparing'
            requisition.task.save()
            
            messages.success(request, f'领料单 {requisition.requisition_no} 已批准，库存已扣减')
            return redirect('inventory:requisition_list')
    
    context = {
        'requisition': requisition,
        'insufficient_items': insufficient_items,
    }
    return render(request, 'inventory/requisition_approve.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.purchase.create')
def purchase_order_create(request):
    """创建采购单"""
    # 从URL参数获取预填充的原料信息（从领料单审核页面跳转）
    material_id = request.GET.get('material_id')
    quantity = request.GET.get('quantity')
    
    if request.method == 'POST':
        supplier = request.POST.get('supplier', '').strip()
        contact_person = request.POST.get('contact_person', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        remark = request.POST.get('remark', '').strip()
        
        # 获取采购明细
        material_ids = request.POST.getlist('material_id')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')
        
        if not supplier:
            messages.error(request, '请输入供应商名称')
            return redirect('inventory:purchase_order_create')
        
        if not material_ids or not all(material_ids):
            messages.error(request, '请至少添加一个采购明细')
            return redirect('inventory:purchase_order_create')
        
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.create(
                order_no=f"PO{timezone.now().strftime('%Y%m%d%H%M%S')}",
                supplier=supplier,
                contact_person=contact_person,
                contact_phone=contact_phone,
                status='pending',
                created_by=request.user,
                remark=remark,
            )
            
            total_amount = Decimal('0')
            for material_id, quantity_str, unit_price_str in zip(material_ids, quantities, unit_prices):
                if not material_id or not quantity_str or not unit_price_str:
                    continue
                
                material = Material.objects.get(pk=material_id)
                quantity = Decimal(quantity_str)
                unit_price = Decimal(unit_price_str)
                subtotal = quantity * unit_price
                
                PurchaseOrderItem.objects.create(
                    order=purchase_order,
                    material=material,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=subtotal,
                )
                total_amount += subtotal
            
            purchase_order.total_amount = total_amount
            purchase_order.save()
            
            messages.success(request, f'采购单 {purchase_order.order_no} 创建成功')
            return redirect('inventory:purchase_order_list')
    
    # GET 请求：显示创建表单
    materials = Material.objects.all().order_by('sku')
    prefill_material = None
    prefill_quantity = None
    if material_id:
        try:
            prefill_material = Material.objects.get(pk=material_id)
            if quantity:
                prefill_quantity = Decimal(quantity)
        except Material.DoesNotExist:
            pass
    
    context = {
        'materials': materials,
        'prefill_material': prefill_material,
        'prefill_quantity': prefill_quantity,
    }
    return render(request, 'inventory/purchase_order_form.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.purchase.view')
def purchase_order_list(request):
    """采购单列表"""
    purchase_orders = PurchaseOrder.objects.select_related('created_by', 'received_by').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        purchase_orders = purchase_orders.filter(status=status_filter)
    
    context = {
        'purchase_orders': purchase_orders,
        'status_filter': status_filter,
    }
    return render(request, 'inventory/purchase_order_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.purchase.view')
def purchase_order_detail(request, pk):
    """采购单详情"""
    purchase_order = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__material'), pk=pk)
    
    context = {
        'purchase_order': purchase_order,
    }
    return render(request, 'inventory/purchase_order_detail.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.purchase.receive')
def purchase_order_receive(request, pk):
    """采购单收货"""
    purchase_order = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__material'), pk=pk)
    
    if purchase_order.status not in ['pending', 'ordered']:
        messages.error(request, '只能对待采购或已下单的采购单进行收货')
        return redirect('inventory:purchase_order_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            # 更新收货数量并增加库存
            for item in purchase_order.items.all():
                received_qty_str = request.POST.get(f'received_quantity_{item.id}', '0')
                if received_qty_str:
                    received_qty = Decimal(received_qty_str)
                    if received_qty > 0:
                        item.received_quantity = received_qty
                        item.save()
                        
                        # 增加原料库存
                        inventory, created = Inventory.objects.get_or_create(
                            inventory_type='material',
                            material=item.material,
                            defaults={'quantity': 0, 'unit': item.material.unit}
                        )
                        inventory.quantity += received_qty
                        inventory.save()
                        
                        # 记录库存变动
                        StockTransaction.objects.create(
                            transaction_type='purchase_in',
                            inventory=inventory,
                            quantity=received_qty,
                            unit=item.material.unit,
                            reference_no=purchase_order.order_no,
                            operator=request.user,
                        )
            
            # 检查是否全部收货
            all_received = all(
                item.received_quantity >= item.quantity 
                for item in purchase_order.items.all()
            )
            
            if all_received:
                purchase_order.status = 'completed'
            else:
                purchase_order.status = 'received'
            
            purchase_order.received_by = request.user
            purchase_order.received_at = timezone.now()
            purchase_order.save()
            
            messages.success(request, f'采购单 {purchase_order.order_no} 收货成功，库存已更新')
            return redirect('inventory:purchase_order_detail', pk=pk)
    
    return render(request, 'inventory/purchase_order_receive.html', {'purchase_order': purchase_order})
