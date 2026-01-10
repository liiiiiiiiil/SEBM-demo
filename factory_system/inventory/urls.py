from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('transactions/', views.stock_transactions, name='stock_transactions'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('adjustments/', views.adjustment_list, name='adjustment_list'),
    path('adjustments/create/<int:inventory_pk>/', views.inventory_adjustment_create, name='adjustment_create'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment_approve'),
    path('boms/', views.bom_list, name='bom_list'),
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/<int:pk>/approve/', views.requisition_approve, name='requisition_approve'),
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/create/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
]

