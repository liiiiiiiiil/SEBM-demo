from django.urls import path
from . import views

app_name = 'production'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/receive/', views.task_receive, name='task_receive'),
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/<int:pk>/approve/', views.requisition_approve, name='requisition_approve'),
    path('tasks/<int:task_pk>/qc/', views.qc_create, name='qc_create'),
    path('tasks/<int:task_pk>/inbound/', views.inbound_create, name='inbound_create'),
]

