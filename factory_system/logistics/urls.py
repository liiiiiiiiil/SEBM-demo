from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    path('notices/', views.shipping_notice_list, name='shipping_notice_list'),
    path('notices/<int:notice_pk>/shipment/', views.shipment_create, name='shipment_create'),
    path('shipments/<int:pk>/', views.shipment_detail, name='shipment_detail'),
    path('shipments/<int:pk>/ship/', views.shipment_ship, name='shipment_ship'),
    path('drivers/', views.driver_list, name='driver_list'),
    path('vehicles/', views.vehicle_list, name='vehicle_list'),
]

