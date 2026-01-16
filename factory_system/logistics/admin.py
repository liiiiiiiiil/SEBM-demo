from django.contrib import admin
from .models import Driver, Vehicle, Shipment, ShipmentImage


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'license_no', 'license_type']
    search_fields = ['name', 'license_no']


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['plate_no', 'vehicle_type', 'model', 'capacity']
    list_filter = ['vehicle_type']
    search_fields = ['plate_no']


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ['shipment_no', 'order', 'driver', 'vehicle', 'status', 'freight_cost', 'shipped_at']
    list_filter = ['status', 'created_at']
    search_fields = ['shipment_no', 'order__order_no']


@admin.register(ShipmentImage)
class ShipmentImageAdmin(admin.ModelAdmin):
    list_display = ['shipment', 'uploaded_at', 'uploaded_by', 'remark']
    list_filter = ['uploaded_at']
    search_fields = ['shipment__shipment_no', 'remark']
