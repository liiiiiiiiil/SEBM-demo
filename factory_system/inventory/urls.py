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
    path('boms/<int:product_id>/edit/', views.bom_edit, name='bom_edit'),
    path('boms/<int:product_id>/add/', views.bom_item_add, name='bom_item_add'),
    path('boms/<int:product_id>/item/<int:bom_id>/edit/', views.bom_item_edit, name='bom_item_edit'),
    path('boms/<int:product_id>/item/<int:bom_id>/delete/', views.bom_item_delete, name='bom_item_delete'),
    
    # 物料单位换算表管理（替代原包装单位管理）
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
    path('material/<int:material_id>/set-display-unit/<int:unit_id>/', 
         unit_management.set_display_unit, 
         name='set_display_unit'),
    
    # 物料显示单位变更（简化后：直接修改 display_unit）
    path('material/<int:material_id>/unit-change/', 
         unit_change.unit_change_request, 
         name='unit_change_request'),
    path('material/<int:material_id>/unit-change/history/', 
         unit_change.unit_change_history, 
         name='unit_change_history'),
    
    # 成品单位换算表管理
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
    path('product/<int:product_id>/set-display-unit/<int:unit_id>/', 
         product_unit_management.product_set_display_unit, 
         name='product_set_display_unit'),
    
    # 成品显示单位变更
    path('product/<int:product_id>/unit-change/', 
         product_unit_change.product_unit_change_request, 
         name='product_unit_change_request'),
    path('product/<int:product_id>/unit-change/history/', 
         product_unit_change.product_unit_change_history, 
         name='product_unit_change_history'),
]
