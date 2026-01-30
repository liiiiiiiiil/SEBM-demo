from django.urls import path
from . import views
from .views import unit_management, unit_change, product_unit_management, product_unit_change

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('transactions/', views.stock_transactions, name='stock_transactions'),
    path('<int:pk>/', views.inventory_detail, name='inventory_detail'),
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('adjustments/', views.adjustment_list, name='adjustment_list'),
    path('adjustments/create/<int:inventory_pk>/', views.inventory_adjustment_create, name='adjustment_create'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment_approve'),
    path('boms/', views.bom_list, name='bom_list'),
    
    # 包装单位管理
    path('material/<int:material_id>/packaging-units/', 
         unit_management.packaging_unit_list, 
         name='packaging_unit_list'),
    path('material/<int:material_id>/packaging-units/create/', 
         unit_management.packaging_unit_create, 
         name='packaging_unit_create'),
    path('material/<int:material_id>/packaging-units/<int:packaging_unit_id>/edit/', 
         unit_management.packaging_unit_edit, 
         name='packaging_unit_edit'),
    path('material/<int:material_id>/packaging-units/<int:packaging_unit_id>/delete/', 
         unit_management.packaging_unit_delete, 
         name='packaging_unit_delete'),
    
    # 单位变更
    path('material/<int:material_id>/unit-change/', 
         unit_change.unit_change_request, 
         name='unit_change_request'),
    path('material/<int:material_id>/unit-change/history/', 
         unit_change.unit_change_history, 
         name='unit_change_history'),
    
    # 成品包装单位管理
    path('product/<int:product_id>/packaging-units/', 
         product_unit_management.product_packaging_unit_list, 
         name='product_packaging_unit_list'),
    path('product/<int:product_id>/packaging-units/create/', 
         product_unit_management.product_packaging_unit_create, 
         name='product_packaging_unit_create'),
    path('product/<int:product_id>/packaging-units/<int:packaging_unit_id>/edit/', 
         product_unit_management.product_packaging_unit_edit, 
         name='product_packaging_unit_edit'),
    path('product/<int:product_id>/packaging-units/<int:packaging_unit_id>/delete/', 
         product_unit_management.product_packaging_unit_delete, 
         name='product_packaging_unit_delete'),
    
    # 成品单位变更
    path('product/<int:product_id>/unit-change/', 
         product_unit_change.product_unit_change_request, 
         name='product_unit_change_request'),
    path('product/<int:product_id>/unit-change/history/', 
         product_unit_change.product_unit_change_history, 
         name='product_unit_change_history'),
]

