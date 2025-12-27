from django.contrib import admin
from .models import ProductionTask, MaterialRequisition, MaterialRequisitionItem, QCRecord, FinishedProductInbound


class MaterialRequisitionItemInline(admin.TabularInline):
    model = MaterialRequisitionItem
    extra = 1


@admin.register(ProductionTask)
class ProductionTaskAdmin(admin.ModelAdmin):
    list_display = ['task_no', 'order', 'product', 'required_quantity', 'completed_quantity', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['task_no', 'order__order_no']


@admin.register(MaterialRequisition)
class MaterialRequisitionAdmin(admin.ModelAdmin):
    list_display = ['requisition_no', 'task', 'status', 'requested_by', 'approved_by', 'created_at']
    list_filter = ['status', 'created_at']
    inlines = [MaterialRequisitionItemInline]


@admin.register(QCRecord)
class QCRecordAdmin(admin.ModelAdmin):
    list_display = ['task', 'batch_no', 'inspected_quantity', 'qualified_quantity', 'qualification_rate', 'result', 'inspector', 'created_at']
    list_filter = ['result', 'created_at']


@admin.register(FinishedProductInbound)
class FinishedProductInboundAdmin(admin.ModelAdmin):
    list_display = ['inbound_no', 'task', 'quantity', 'operator', 'created_at']
    list_filter = ['created_at']
