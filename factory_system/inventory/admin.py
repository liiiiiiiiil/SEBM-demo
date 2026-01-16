from django.contrib import admin
from .models import Customer, MaterialCategory, Material, Product, BOM, Inventory, StockTransaction
# PurchaseOrder, PurchaseOrderItem 已废弃，使用 purchase.PurchaseTask 替代


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'credit_level', 'created_at']
    list_filter = ['credit_level', 'created_at']
    search_fields = ['name', 'contact_person', 'phone']


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'material_type', 'unit', 'unit_price', 'safety_stock']
    list_filter = ['material_type', 'category']
    search_fields = ['sku', 'name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'sale_price', 'safety_stock', 'unit', 'created_at']
    search_fields = ['sku', 'name']


@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ['product', 'material', 'quantity', 'unit']
    list_filter = ['product']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['inventory_type', 'get_item_name', 'quantity', 'unit', 'updated_at']
    list_filter = ['inventory_type']
    
    def get_item_name(self, obj):
        return str(obj.get_item())
    get_item_name.short_description = '物品名称'


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_type', 'inventory', 'quantity', 'operator', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    readonly_fields = ['created_at']


# ⚠️ 已废弃/冻结：PurchaseOrder 和 PurchaseOrderItem 已被 purchase.PurchaseTask 替代
# 保留以下代码仅用于历史数据兼容，不再使用
# @admin.register(PurchaseOrder)
# class PurchaseOrderAdmin(admin.ModelAdmin):
#     list_display = ['order_no', 'supplier', 'total_amount', 'status', 'created_by', 'created_at']
#     list_filter = ['status', 'created_at']
#     search_fields = ['order_no', 'supplier']
#     readonly_fields = ['created_at', 'updated_at']
#
#
# @admin.register(PurchaseOrderItem)
# class PurchaseOrderItemAdmin(admin.ModelAdmin):
#     list_display = ['order', 'material', 'quantity', 'unit_price', 'subtotal', 'received_quantity']
#     list_filter = ['order__status']
#     search_fields = ['order__order_no', 'material__name']
