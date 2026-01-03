from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from accounts.decorators import role_required, permission_required, role_or_permission_required
from .models import Inventory, StockTransaction, Product, Material, Customer


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
@role_or_permission_required('sales', 'sales_mgr', 'warehouse', 'ceo', permission_code='inventory.customer.view')
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
@role_or_permission_required('sales', 'sales_mgr', 'warehouse', 'ceo', permission_code='inventory.customer.create')
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
@role_or_permission_required('sales', 'sales_mgr', 'warehouse', 'ceo', permission_code='inventory.customer.edit')
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
@role_or_permission_required('sales', 'sales_mgr', 'warehouse', 'ceo', permission_code='inventory.customer.delete')
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
    }
    return render(request, 'inventory/product_list.html', context)
