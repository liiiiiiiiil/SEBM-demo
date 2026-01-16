from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('transactions/', views.stock_transactions, name='stock_transactions'),
    path('<int:pk>/', views.inventory_detail, name='inventory_detail'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/edit/approve/', views.customer_edit_approve, name='customer_edit_approve'),
    path('customers/<int:pk>/edit/reject/', views.customer_edit_reject, name='customer_edit_reject'),
    path('customers/<int:pk>/delete/approve/', views.customer_delete_approve, name='customer_delete_approve'),
    path('customers/<int:pk>/delete/reject/', views.customer_delete_reject, name='customer_delete_reject'),
    path('customers/approvals/', views.customer_approval_list, name='customer_approval_list'),
    path('customers/transfer/', views.customer_transfer, name='customer_transfer'),
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('adjustments/', views.adjustment_list, name='adjustment_list'),
    path('adjustments/create/<int:inventory_pk>/', views.inventory_adjustment_create, name='adjustment_create'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment_approve'),
    path('boms/', views.bom_list, name='bom_list'),
]

