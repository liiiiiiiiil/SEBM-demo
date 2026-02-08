from django.contrib import admin
from .models import (
    MaterialCategory, Material, Product, BOM, Inventory, StockTransaction,
    Unit, ItemUnitConversion, InventoryAdjustmentRequest,
)


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'material_type', 'base_unit', 'display_unit', 'unit_price', 'safety_stock']
    list_filter = ['material_type', 'category']
    search_fields = ['sku', 'name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'sale_price', 'safety_stock', 'base_unit', 'display_unit', 'created_at']
    search_fields = ['sku', 'name']


@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ['product', 'material', 'quantity', 'unit']
    list_filter = ['product']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['inventory_type', 'get_item_name', 'quantity', 'get_unit_name', 'updated_at']
    list_filter = ['inventory_type']
    
    def get_item_name(self, obj):
        item = obj.get_item()
        return str(item) if item else obj.other_name
    get_item_name.short_description = '物品名称'

    def get_unit_name(self, obj):
        return obj.get_unit_name()
    get_unit_name.short_description = '基础单位'


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_type', 'inventory', 'quantity', 'unit', 'base_quantity', 'operator', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    readonly_fields = ['created_at']


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'category', 'display_order', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['category', 'display_order', 'code']


@admin.register(ItemUnitConversion)
class ItemUnitConversionAdmin(admin.ModelAdmin):
    list_display = ['content_type', 'get_item_name', 'base_unit', 'target_unit', 'factor', 'is_default', 'is_active']
    list_filter = ['content_type', 'is_default', 'is_active']
    search_fields = ['material__name', 'material__sku', 'product__name', 'product__sku']
    ordering = ['content_type', 'created_at']

    def get_item_name(self, obj):
        if obj.content_type == 'material' and obj.material:
            return obj.material.name
        elif obj.content_type == 'product' and obj.product:
            return obj.product.name
        return '-'
    get_item_name.short_description = '物料/成品'


@admin.register(InventoryAdjustmentRequest)
class InventoryAdjustmentRequestAdmin(admin.ModelAdmin):
    list_display = ['request_no', 'inventory', 'adjustment_type', 'status', 'applicant', 'created_at']
    list_filter = ['adjustment_type', 'status']
    search_fields = ['request_no']
    readonly_fields = ['created_at', 'updated_at']
