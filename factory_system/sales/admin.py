from django.contrib import admin
from .models import SalesOrder, SalesOrderItem, ShippingNotice


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 1


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_no', 'customer', 'salesperson', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['order_no', 'customer__name']
    inlines = [SalesOrderItemInline]


@admin.register(ShippingNotice)
class ShippingNoticeAdmin(admin.ModelAdmin):
    list_display = ['notice_no', 'order', 'status', 'created_at']
    list_filter = ['status', 'created_at']
