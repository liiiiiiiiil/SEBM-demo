from django.urls import path
from . import views

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
]

