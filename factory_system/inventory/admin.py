from django.contrib import admin
from .models import (
    MaterialCategory, Material, Product, BOM, Inventory, StockTransaction,
    Unit, MaterialPackagingUnit, MaterialUnitChangeHistory,
    ProductPackagingUnit, ProductUnitChangeHistory
)


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


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'is_base', 'display_order', 'is_active']
    list_filter = ['category', 'is_base', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['category', 'display_order', 'code']


@admin.register(MaterialPackagingUnit)
class MaterialPackagingUnitAdmin(admin.ModelAdmin):
    list_display = ['material', 'packaging_unit_name', 'base_unit', 'conversion_factor', 'is_default', 'is_active']
    list_filter = ['is_default', 'is_active', 'base_unit']
    search_fields = ['material__name', 'material__sku', 'packaging_unit_name']
    ordering = ['material', 'display_order', 'packaging_unit_name']


@admin.register(MaterialUnitChangeHistory)
class MaterialUnitChangeHistoryAdmin(admin.ModelAdmin):
    list_display = ['material', 'old_unit', 'new_unit', 'conversion_factor', 'changed_by', 'changed_at', 'approval_status']
    list_filter = ['approval_status', 'changed_at']
    search_fields = ['material__name', 'material__sku', 'old_unit', 'new_unit', 'reason']
    readonly_fields = ['changed_at', 'old_inventory_quantity', 'new_inventory_quantity']
    ordering = ['-changed_at']


@admin.register(ProductPackagingUnit)
class ProductPackagingUnitAdmin(admin.ModelAdmin):
    list_display = ['product', 'packaging_unit_name', 'base_unit', 'conversion_factor', 'is_default', 'is_active']
    list_filter = ['is_default', 'is_active', 'base_unit']
    search_fields = ['product__name', 'product__sku', 'packaging_unit_name']
    ordering = ['product', 'display_order', 'packaging_unit_name']


@admin.register(ProductUnitChangeHistory)
class ProductUnitChangeHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'old_unit', 'new_unit', 'conversion_factor', 'changed_by', 'changed_at', 'approval_status']
    list_filter = ['approval_status', 'changed_at']
    search_fields = ['product__name', 'product__sku', 'old_unit', 'new_unit', 'reason']
    readonly_fields = ['changed_at', 'old_inventory_quantity', 'new_inventory_quantity']
    ordering = ['-changed_at']

