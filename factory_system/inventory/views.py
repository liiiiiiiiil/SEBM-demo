from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from accounts.decorators import role_required, permission_required, role_or_permission_required
from .models import Inventory, StockTransaction, Product, Material, Customer, ProductCategory, MaterialCategory, InventoryAdjustmentRequest, BOM, CustomerTransfer, CustomerTransfer


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
        
        # 获取物品名称
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
            # 获取物品名称
            if trans.inventory.inventory_type == 'product':
                item_name = trans.inventory.product.name if trans.inventory.product else '-'
            elif trans.inventory.inventory_type == 'material':
                item_name = trans.inventory.material.name if trans.inventory.material else '-'
            elif trans.inventory.inventory_type == 'other':
                item_name = trans.inventory.other_name if trans.inventory.other_name else '-'
            else:
                item_name = '-'
            
            all_records.append({
                'type': 'adjustment',
                'record_type': '库存调整',
                'transaction_type': '库存调整',
                'item_name': item_name,
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
            # 获取物品名称
            if trans.inventory.inventory_type == 'product':
                item_name = trans.inventory.product.name if trans.inventory.product else '-'
            elif trans.inventory.inventory_type == 'material':
                item_name = trans.inventory.material.name if trans.inventory.material else '-'
            elif trans.inventory.inventory_type == 'other':
                item_name = trans.inventory.other_name if trans.inventory.other_name else '-'
            else:
                item_name = '-'
            
            all_records.append({
                'type': 'adjustment',
                'record_type': '库存调整',
                'transaction_type': '库存调整',
                'item_name': item_name,
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
    inventories = Inventory.objects.select_related('product', 'material').prefetch_related('batches').all()
    
    if inventory_type == 'product':
        inventories = inventories.filter(inventory_type='product')
    elif inventory_type == 'material':
        inventories = inventories.filter(inventory_type='material')
    elif inventory_type == 'other':
        inventories = inventories.filter(inventory_type='other')
    
    # 为每个库存获取批次信息
    for inv in inventories:
        inv.batches_list = inv.get_batches().filter(quantity__gt=0)
    
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
    
    # 将待审批的调整申请信息附加到每个库存对象上，并获取批次信息
    inventories_list = list(inventories)
    for inv in inventories_list:
        inv.pending_adjustments = pending_adjustments.get(inv.pk, [])
        inv.batches_list = inv.get_batches().filter(quantity__gt=0)
    
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
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.view')
def inventory_detail(request, pk):
    """库存详情 - 显示该库存的进出记录"""
    inventory = get_object_or_404(Inventory.objects.select_related('product', 'material'), pk=pk)
    
    # 获取该库存的所有变动记录
    transactions = StockTransaction.objects.filter(
        inventory=inventory
    ).select_related('batch', 'operator').order_by('-created_at')
    
    # 分页处理
    paginator = Paginator(transactions, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 获取批次信息
    batches = inventory.get_batches().order_by('-batch_date', '-created_at')
    
    context = {
        'inventory': inventory,
        'transactions': page_obj,
        'batches': batches,
    }
    return render(request, 'inventory/inventory_detail.html', context)


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.view')
def customer_list(request):
    """客户列表"""
    customers = Customer.objects.select_related('created_by').all()
    
    # 权限控制：销售员只能看到自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    # 销售经理和总经理可以看到所有客户
    elif request.user.profile.role in ['sales_mgr', 'ceo'] or request.user.profile.has_permission('inventory.customer.manage'):
        pass  # 显示所有客户
    # 其他角色（如仓库管理员）如果有查看权限，也只能看到自己负责的
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
    """编辑客户（提交审批申请）"""
    from .forms import CustomerForm
    import json
    
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能编辑自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能编辑自己负责的客户')
            return redirect('inventory:customer_list')
    
    # 如果已有待审批的编辑申请，提示用户
    if customer.edit_status == 'pending':
        messages.warning(request, '该客户已有待审批的编辑申请，请等待审批完成')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        edit_reason = request.POST.get('edit_reason', '').strip()
        
        if form.is_valid():
            if not edit_reason:
                messages.error(request, '请填写编辑原因')
                return render(request, 'inventory/customer_form.html', {
                    'form': form, 
                    'title': '编辑客户', 
                    'customer': customer,
                    'is_edit_request': True
                })
            
            # 保存待审批的数据（JSON格式）
            pending_data = {
                'name': form.cleaned_data['name'],
                'contact_person': form.cleaned_data['contact_person'],
                'phone': form.cleaned_data['phone'],
                'address': form.cleaned_data['address'],
                'credit_level': form.cleaned_data['credit_level'],
            }
            
            with transaction.atomic():
                customer.edit_status = 'pending'
                customer.edit_pending_data = json.dumps(pending_data, ensure_ascii=False)
                customer.edit_reason = edit_reason
                customer.edit_requested_by = request.user
                customer.edit_requested_at = timezone.now()
                customer.save()
            
            messages.success(request, f'客户 {customer.name} 的编辑申请已提交，等待总经理审批')
            return redirect('inventory:customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'inventory/customer_form.html', {
        'form': form, 
        'title': '编辑客户', 
        'customer': customer,
        'is_edit_request': True
    })


@login_required
@role_or_permission_required('sales', 'sales_mgr', 'ceo', permission_code='inventory.customer.delete')
def customer_delete(request, pk):
    """删除客户（提交审批申请）"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # 权限检查：销售员只能删除自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        if customer.created_by != request.user:
            messages.error(request, '您只能删除自己负责的客户')
            return redirect('inventory:customer_list')
    
    # 如果已有待审批的删除申请，提示用户
    if customer.delete_status == 'pending':
        messages.warning(request, '该客户已有待审批的删除申请，请等待审批完成')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        delete_reason = request.POST.get('delete_reason', '').strip()
        
        if not delete_reason:
            messages.error(request, '请填写删除原因')
            return render(request, 'inventory/customer_confirm_delete.html', {'customer': customer})
        
        with transaction.atomic():
            customer.delete_status = 'pending'
            customer.delete_reason = delete_reason
            customer.delete_requested_by = request.user
            customer.delete_requested_at = timezone.now()
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的删除申请已提交，等待总经理审批')
        return redirect('inventory:customer_list')
    
    return render(request, 'inventory/customer_confirm_delete.html', {'customer': customer})


@login_required
@role_required('ceo')
def customer_edit_approve(request, pk):
    """总经理审批客户编辑申请"""
    import json
    
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.edit_status != 'pending':
        messages.error(request, '该客户没有待审批的编辑申请')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        try:
            # 解析待审批的数据
            pending_data = json.loads(customer.edit_pending_data)
            
            with transaction.atomic():
                # 应用编辑
                customer.name = pending_data['name']
                customer.contact_person = pending_data['contact_person']
                customer.phone = pending_data['phone']
                customer.address = pending_data['address']
                customer.credit_level = pending_data['credit_level']
                
                # 更新审批状态
                customer.edit_status = 'approved'
                customer.edit_approved_by = request.user
                customer.edit_approved_at = timezone.now()
                customer.edit_pending_data = ''  # 清空待审批数据
                customer.save()
            
            messages.success(request, f'客户 {customer.name} 的编辑申请已审批通过')
            return redirect('inventory:customer_list')
        except Exception as e:
            messages.error(request, f'审批失败：{str(e)}')
            return redirect('inventory:customer_list')
    
    # 显示审批页面
    try:
        pending_data = json.loads(customer.edit_pending_data) if customer.edit_pending_data else {}
    except:
        pending_data = {}
    
    context = {
        'customer': customer,
        'pending_data': pending_data,
        'action': 'edit_approve',
    }
    return render(request, 'inventory/customer_approve.html', context)


@login_required
@role_required('ceo')
def customer_edit_reject(request, pk):
    """总经理拒绝客户编辑申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.edit_status != 'pending':
        messages.error(request, '该客户没有待审批的编辑申请')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请填写拒绝原因')
            return redirect('inventory:customer_edit_approve', pk=pk)
        
        with transaction.atomic():
            customer.edit_status = 'rejected'
            customer.edit_reject_reason = reject_reason
            customer.edit_pending_data = ''  # 清空待审批数据
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的编辑申请已拒绝')
        return redirect('inventory:customer_list')
    
    context = {
        'customer': customer,
        'action': 'edit_reject',
    }
    return render(request, 'inventory/customer_reject.html', context)


@login_required
@role_required('ceo')
def customer_delete_approve(request, pk):
    """总经理审批客户删除申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.delete_status != 'pending':
        messages.error(request, '该客户没有待审批的删除申请')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        customer_name = customer.name
        
        with transaction.atomic():
            customer.delete_status = 'approved'
            customer.delete_approved_by = request.user
            customer.delete_approved_at = timezone.now()
            customer.save()
            
            # 执行删除
            customer.delete()
        
        messages.success(request, f'客户 {customer_name} 的删除申请已审批通过，客户已删除')
        return redirect('inventory:customer_list')
    
    context = {
        'customer': customer,
        'action': 'delete_approve',
    }
    return render(request, 'inventory/customer_approve.html', context)


@login_required
@role_required('ceo')
def customer_delete_reject(request, pk):
    """总经理拒绝客户删除申请"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if customer.delete_status != 'pending':
        messages.error(request, '该客户没有待审批的删除申请')
        return redirect('inventory:customer_list')
    
    if request.method == 'POST':
        reject_reason = request.POST.get('reject_reason', '').strip()
        
        if not reject_reason:
            messages.error(request, '请填写拒绝原因')
            return redirect('inventory:customer_delete_approve', pk=pk)
        
        with transaction.atomic():
            customer.delete_status = 'rejected'
            customer.delete_reject_reason = reject_reason
            customer.save()
        
        messages.success(request, f'客户 {customer.name} 的删除申请已拒绝')
        return redirect('inventory:customer_list')
    
    context = {
        'customer': customer,
        'action': 'delete_reject',
    }
    return render(request, 'inventory/customer_reject.html', context)


@login_required
@role_required('ceo', 'sales_mgr')
def customer_transfer(request):
    """客户转移（批量转移客户给指定销售人员）"""
    from django.contrib.auth.models import User
    
    if request.method == 'POST':
        customer_ids = request.POST.getlist('customer_ids')
        to_user_id = request.POST.get('to_user')
        remark = request.POST.get('remark', '').strip()
        
        if not customer_ids:
            messages.error(request, '请至少选择一个客户')
            return redirect('inventory:customer_transfer')
        
        if not to_user_id:
            messages.error(request, '请选择新的负责人')
            return redirect('inventory:customer_transfer')
        
        try:
            to_user = User.objects.get(pk=to_user_id)
            if to_user.profile.role != 'sales':
                messages.error(request, '只能将客户转移给销售人员')
                return redirect('inventory:customer_transfer')
        except User.DoesNotExist:
            messages.error(request, '选择的用户不存在')
            return redirect('inventory:customer_transfer')
        
        customers = Customer.objects.filter(pk__in=customer_ids)
        if not customers.exists():
            messages.error(request, '选择的客户不存在')
            return redirect('inventory:customer_transfer')
        
        transferred_count = 0
        with transaction.atomic():
            for customer in customers:
                from_user = customer.created_by
                # 更新客户负责人
                customer.created_by = to_user
                customer.save()
                
                # 记录转移操作
                CustomerTransfer.objects.create(
                    customer=customer,
                    from_user=from_user,
                    to_user=to_user,
                    transferred_by=request.user,
                    remark=remark,
                )
                transferred_count += 1
        
        messages.success(request, f'成功将 {transferred_count} 个客户转移给 {to_user.username}')
        return redirect('inventory:customer_list')
    
    # GET请求：显示转移页面
    customers = Customer.objects.select_related('created_by').all()
    
    # 权限检查：销售员只能看到自己负责的客户
    if request.user.profile.role == 'sales' and not request.user.profile.has_permission('inventory.customer.manage'):
        customers = customers.filter(created_by=request.user)
    
    # 获取所有销售人员
    sales_users = User.objects.filter(profile__role='sales').order_by('username')
    
    context = {
        'customers': customers,
        'sales_users': sales_users,
    }
    return render(request, 'inventory/customer_transfer.html', context)


@login_required
@role_required('ceo')
def customer_approval_list(request):
    """客户操作记录（只显示已完成的审批记录）"""
    # 已完成的编辑申请（已审批、已拒绝）
    edit_requests = Customer.objects.filter(
        edit_status__in=['approved', 'rejected']
    ).select_related('edit_requested_by', 'edit_approved_by').order_by('-edit_requested_at')
    
    # 已完成的删除申请（已审批、已拒绝）
    delete_requests = Customer.objects.filter(
        delete_status__in=['approved', 'rejected']
    ).select_related('delete_requested_by', 'delete_approved_by').order_by('-delete_requested_at')
    
    # 客户转移记录
    transfer_records = CustomerTransfer.objects.select_related(
        'customer', 'from_user', 'to_user', 'transferred_by'
    ).order_by('-transferred_at')
    
    context = {
        'edit_requests': edit_requests,
        'delete_requests': delete_requests,
        'transfer_records': transfer_records,
    }
    return render(request, 'inventory/customer_approval_list.html', context)


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


