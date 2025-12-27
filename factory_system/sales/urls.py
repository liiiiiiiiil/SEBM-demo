from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('orders/', views.order_list, name='order_list'),
    path('orders/create/', views.order_create, name='order_create'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/approve/', views.order_approve, name='order_approve'),
]

