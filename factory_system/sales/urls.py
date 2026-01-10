from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('orders/', views.order_list, name='order_list'),
    path('orders/create/', views.order_create, name='order_create'),
    path('orders/<int:order_pk>/edit/', views.order_create, name='order_edit'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/approve/', views.order_approve, name='order_approve'),
    path('orders/<int:pk>/reject/', views.order_reject, name='order_reject'),
    path('orders/<int:pk>/ceo-approve/', views.ceo_approve, name='ceo_approve'),
    path('orders/<int:pk>/ceo-reject/', views.ceo_reject, name='ceo_reject'),
    path('orders/<int:pk>/terminate/', views.order_terminate, name='order_terminate'),
    path('orders/<int:pk>/cancel/', views.order_cancel, name='order_cancel'),
]

