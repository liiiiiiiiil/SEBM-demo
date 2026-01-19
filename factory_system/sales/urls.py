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
    # Customer 相关 URL
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
]

