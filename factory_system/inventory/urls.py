from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('transactions/', views.stock_transactions, name='stock_transactions'),
    path('customers/', views.customer_list, name='customer_list'),
    path('products/', views.product_list, name='product_list'),
]

