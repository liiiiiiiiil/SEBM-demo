from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    path('notices/', views.shipping_notice_list, name='shipping_notice_list'),
    path('notices/<int:notice_pk>/shipment/', views.shipment_create, name='shipment_create'),
    path('shipments/', views.shipment_list, name='shipment_list'),
    path('shipments/<int:pk>/', views.shipment_detail, name='shipment_detail'),
    path('shipments/<int:pk>/ship/', views.shipment_ship, name='shipment_ship'),
    path('shipments/<int:pk>/delivery-confirm/', views.shipment_delivery_confirm, name='shipment_delivery_confirm'),
    path('drivers/', views.driver_list, name='driver_list'),
    path('drivers/create/', views.driver_create, name='driver_create'),
    path('drivers/<int:pk>/edit/', views.driver_edit, name='driver_edit'),
    path('drivers/<int:pk>/delete/', views.driver_delete, name='driver_delete'),
    path('vehicles/', views.vehicle_list, name='vehicle_list'),
]

