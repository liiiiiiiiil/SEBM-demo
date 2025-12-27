from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from accounts.decorators import role_required
from .models import Inventory, StockTransaction, Product, Material, Customer


@login_required
@role_required('warehouse', 'production', 'ceo')
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
@role_required('warehouse', 'ceo')
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
@role_required('warehouse', 'ceo')
def customer_list(request):
    """客户列表"""
    customers = Customer.objects.all()
    
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
@role_required('warehouse', 'ceo')
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
