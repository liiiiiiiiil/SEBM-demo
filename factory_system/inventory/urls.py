from django.urls import path
from . import views

app_name = 'inventory'

# 库存管理仅保留数量调整；单价、单位仅引用产品管理，不提供单位修改功能
urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('transactions/', views.stock_transactions, name='stock_transactions'),
    path('<int:pk>/', views.inventory_detail, name='inventory_detail'),
    path('adjustments/', views.adjustment_list, name='adjustment_list'),
    path('adjustments/create/<int:inventory_pk>/', views.inventory_adjustment_create, name='adjustment_create'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment_approve'),
]
