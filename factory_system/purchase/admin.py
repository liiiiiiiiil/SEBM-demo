from django.contrib import admin
from .models import PurchaseTask, PurchaseTaskItem, Supplier


@admin.register(PurchaseTask)
class PurchaseTaskAdmin(admin.ModelAdmin):
    list_display = ['task_no', 'supplier', 'total_amount', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['task_no', 'supplier']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PurchaseTaskItem)
class PurchaseTaskItemAdmin(admin.ModelAdmin):
    list_display = ['task', 'material', 'quantity', 'unit_price', 'subtotal', 'received_quantity']
    list_filter = ['task__status']
    search_fields = ['task__task_no', 'material__name']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'contact_phone', 'created_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'contact_person', 'contact_phone']
    readonly_fields = ['created_at', 'updated_at']
