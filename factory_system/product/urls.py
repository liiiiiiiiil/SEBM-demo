from django.urls import path
from . import views

app_name = 'product'

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('create/', views.item_create, name='item_create'),
    path('items/<int:pk>/edit/', views.item_edit, name='item_edit'),
    # 成品（保留旧 URL，重定向到统一创建/编辑）
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    # 原料
    path('materials/create/', views.material_create, name='material_create'),
    path('materials/<int:pk>/edit/', views.material_edit, name='material_edit'),
    path('materials/<int:pk>/delete/', views.material_delete, name='material_delete'),
    path('materials/<int:pk>/packaging-units/', views.material_packaging_unit_list, name='material_packaging_unit_list'),
    # 辅料（与原料并列，参考库存管理）
    path('auxiliaries/create/', views.auxiliary_create, name='auxiliary_create'),
    path('auxiliaries/<int:pk>/edit/', views.auxiliary_edit, name='auxiliary_edit'),
    path('auxiliaries/<int:pk>/delete/', views.auxiliary_delete, name='auxiliary_delete'),
    path('auxiliaries/<int:pk>/packaging-units/', views.auxiliary_packaging_unit_list, name='auxiliary_packaging_unit_list'),
    path('materials/<int:pk>/packaging-units/create/', views.material_packaging_unit_create, name='material_packaging_unit_create'),
    path('materials/<int:pk>/packaging-units/<int:packaging_unit_id>/edit/', views.material_packaging_unit_edit, name='material_packaging_unit_edit'),
    path('materials/<int:pk>/packaging-units/<int:packaging_unit_id>/delete/', views.material_packaging_unit_delete, name='material_packaging_unit_delete'),
    path('materials/<int:pk>/packaging-units/set-display-unit/<int:unit_id>/', views.material_set_display_unit, name='material_set_display_unit'),
    # 其它（低值易耗品、辅料等）
    path('others/create/', views.other_create, name='other_create'),
    path('others/<int:pk>/edit/', views.other_edit, name='other_edit'),
    path('others/<int:pk>/delete/', views.other_delete, name='other_delete'),
    path('others/<int:pk>/packaging-units/', views.other_packaging_unit_list, name='other_packaging_unit_list'),
    path('others/<int:pk>/packaging-units/create/', views.other_packaging_unit_create, name='other_packaging_unit_create'),
    path('others/<int:pk>/packaging-units/<int:packaging_unit_id>/edit/', views.other_packaging_unit_edit, name='other_packaging_unit_edit'),
    path('others/<int:pk>/packaging-units/<int:packaging_unit_id>/delete/', views.other_packaging_unit_delete, name='other_packaging_unit_delete'),
    path('others/<int:pk>/packaging-units/set-display-unit/<int:unit_id>/', views.other_set_display_unit, name='other_set_display_unit'),
    # BOM 配方（仅成品）
    path('boms/', views.bom_list, name='bom_list'),
    path('boms/<int:product_id>/edit/', views.bom_edit, name='bom_edit'),
    path('boms/<int:product_id>/add/', views.bom_item_add, name='bom_item_add'),
    path('boms/<int:product_id>/item/<int:bom_id>/edit/', views.bom_item_edit, name='bom_item_edit'),
    path('boms/<int:product_id>/item/<int:bom_id>/delete/', views.bom_item_delete, name='bom_item_delete'),
    # 成品单位换算与显示单位（单位/单价在产品管理维护）
    path('product/<int:product_id>/packaging-units/', views.product_packaging_unit_list, name='product_packaging_unit_list'),
    path('product/<int:product_id>/packaging-units/create/', views.product_packaging_unit_create, name='product_packaging_unit_create'),
    path('product/<int:product_id>/packaging-units/<int:packaging_unit_id>/edit/', views.product_packaging_unit_edit, name='product_packaging_unit_edit'),
    path('product/<int:product_id>/packaging-units/<int:packaging_unit_id>/delete/', views.product_packaging_unit_delete, name='product_packaging_unit_delete'),
    path('product/<int:product_id>/set-display-unit/<int:unit_id>/', views.product_set_display_unit, name='product_set_display_unit'),
    path('product/<int:product_id>/unit-change/', views.product_unit_change_request, name='product_unit_change_request'),
    path('product/<int:product_id>/unit-change/history/', views.product_unit_change_history, name='product_unit_change_history'),
]
