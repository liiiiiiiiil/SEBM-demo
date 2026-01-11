from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required, permission_required, role_or_permission_required
from .models import Inventory, StockTransaction, Product, Material, Customer, ProductCategory, MaterialCategory, InventoryAdjustmentRequest, BOM


@login_required
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.view')
def inventory_list(request):
    """库存列表"""
    inventory_type = request.GET.get('type', '')
    
    # 合并两类记录，创建一个统一的记录列表
    all_records = []
    
    # 添加库存变动记录（排除调整类型，因为调整记录会单独处理）
    stock_transactions = StockTransaction.objects.filter(
        ~Q(transaction_type='adjustment')
    ).select_related('inventory', 'operator').order_by('-created_at')
    
    for trans in stock_transactions:
        # 根据transaction_type判断是入库还是出库
        # 出库类型：sale_out, production_out 显示负数
        # 入库类型：production_in, purchase_in 显示正数
        if trans.transaction_type in ['sale_out', 'production_out']:
            display_quantity = -trans.quantity  # 出库显示负数
        else:
            display_quantity = trans.quantity  # 入库显示正数
        
        all_records.append({
            'type': 'transaction',
            'record_type': '出入库',
            'transaction_type': trans.get_transaction_type_display(),
            'item_name': trans.inventory.product.name if trans.inventory.inventory_type == 'product' else trans.inventory.material.name,
            'item_type': trans.inventory.get_inventory_type_display(),
            'quantity': display_quantity,  # 使用带符号的数量
            'unit': trans.unit,
            'reference_no': trans.reference_no,
            'operator': trans.operator.username,
            'created_at': trans.created_at,
            'remark': trans.remark,
        })
    
    # 添加库存调整记录（从StockTransaction中获取，因为已经记录了价格变动）
    adjustment_transactions = StockTransaction.objects.filter(
        transaction_type='adjustment'
    ).select_related('inventory', 'operator').order_by('-created_at')
    
    for trans in adjustment_transactions:
        # 查找对应的调整申请以获取详细信息
        try:
            adj = InventoryAdjustmentRequest.objects.get(request_no=trans.reference_no)
            all_records.append({
                'type': 'adjustment',
                'record_type': '库存调整',
                'transaction_type': '库存调整',
                'item_name': trans.inventory.product.name if trans.inventory.inventory_type == 'product' else trans.inventory.material.name,
                'item_type': trans.inventory.get_inventory_type_display(),
                'quantity': trans.quantity,
                'unit': trans.unit,
                'reference_no': trans.reference_no,
                'operator': trans.operator.username,
                'created_at': trans.created_at,
                'remark': trans.remark,
                'old_unit_price': trans.old_unit_price,
                'new_unit_price': trans.new_unit_price,
                'current_quantity': adj.current_quantity if hasattr(adj, 'current_quantity') else None,
                'new_quantity': adj.new_quantity if hasattr(adj, 'new_quantity') else None,
            })
        except InventoryAdjustmentRequest.DoesNotExist:
            # 如果找不到对应的调整申请，仍然显示记录
            all_records.append({
                'type': 'adjustment',
                'record_type': '库存调整',
                'transaction_type': '库存调整',
                'item_name': trans.inventory.product.name if trans.inventory.inventory_type == 'product' else trans.inventory.material.name,
                'item_type': trans.inventory.get_inventory_type_display(),
                'quantity': trans.quantity,
                'unit': trans.unit,
                'reference_no': trans.reference_no,
                'operator': trans.operator.username,
                'created_at': trans.created_at,
                'remark': trans.remark,
                'old_unit_price': trans.old_unit_price,
                'new_unit_price': trans.new_unit_price,
            })
    
    # 按时间倒序排序
    all_records.sort(key=lambda x: x['created_at'], reverse=True)
    
    # 分页处理
    paginator = Paginator(all_records, 20)  # 每页20条记录
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # 获取库存列表
    inventories = Inventory.objects.select_related('product', 'material').all()
    
    if inventory_type == 'product':
        inventories = inventories.filter(inventory_type='product')
    elif inventory_type == 'material':
        inventories = inventories.filter(inventory_type='material')
    
    # 为每个库存查询是否有待审批的调整申请
    # 只对总经理显示审批选项
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
    
    # 将待审批的调整申请信息附加到每个库存对象上
    inventories_list = list(inventories)
    for inv in inventories_list:
        inv.pending_adjustments = pending_adjustments.get(inv.pk, [])
    
    context = {
        'page_obj': page_obj,  # 分页的记录
        'inventories': inventories_list,
        'inventory_type': inventory_type,
        'can_approve': can_approve,
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
    
    # 分页处理
    paginator = Paginator(customers, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if search:
        extra_params = f'search={search}'
    
    context = {
        'customers': page_obj,
        'search': search,
        'extra_params': extra_params,
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
    
    # 分页处理
    paginator = Paginator(products, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
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
            adjustment.current_unit_price = inventory.get_unit_price()
            adjustment.applicant = request.user
            adjustment.request_no = f"IAR{timezone.now().strftime('%Y%m%d%H%M%S')}"
            
            # 根据调整类型处理数量和单价
            adjustment_type = form.cleaned_data.get('adjustment_type')
            adjust_quantity = form.cleaned_data.get('adjust_quantity') or 0
            adjust_unit_price = form.cleaned_data.get('adjust_unit_price')
            
            if adjustment_type == 'quantity' or adjustment_type == 'both':
                adjustment.adjust_quantity = adjust_quantity
                adjustment.new_quantity = adjustment.current_quantity + adjust_quantity
            else:
                adjustment.adjust_quantity = 0
                adjustment.new_quantity = adjustment.current_quantity
            
            if adjustment_type == 'price' or adjustment_type == 'both':
                if adjust_unit_price is not None:
                    adjustment.adjust_unit_price = adjust_unit_price
                    adjustment.new_unit_price = adjust_unit_price
                else:
                    adjustment.new_unit_price = adjustment.current_unit_price
            else:
                adjustment.adjust_unit_price = None
                adjustment.new_unit_price = adjustment.current_unit_price
            
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
    
    # 分页处理
    paginator = Paginator(adjustments, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
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
                
                # 执行单价调整（如果调整了单价）
                price_adjusted = False
                if adjustment.adjust_unit_price is not None and adjustment.new_unit_price != adjustment.current_unit_price:
                    item = inventory.get_item()
                    if item:
                        item.unit_price = adjustment.new_unit_price
                        item.save()
                        price_adjusted = True
                
                # 创建库存变动记录
                remark_parts = [f"库存调整：{adjustment.reason}"]
                if price_adjusted:
                    remark_parts.append(f"单价从¥{adjustment.current_unit_price}调整为¥{adjustment.new_unit_price}")
                
                StockTransaction.objects.create(
                    transaction_type='adjustment',
                    inventory=inventory,
                    quantity=adjustment.adjust_quantity,
                    unit=inventory.unit,
                    old_unit_price=adjustment.current_unit_price if price_adjusted else None,
                    new_unit_price=adjustment.new_unit_price if price_adjusted else None,
                    reference_no=adjustment.request_no,
                    remark="；".join(remark_parts),
                    operator=request.user,
                )
                
                adjustment.status = 'completed'
                adjustment.save()
                
                success_msg = f'库存调整申请 {adjustment.request_no} 已审批通过，库存已更新'
                if price_adjusted:
                    success_msg += f'，单价已从¥{adjustment.current_unit_price}更新为¥{adjustment.new_unit_price}'
                messages.success(request, success_msg)
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


