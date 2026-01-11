from django.urls import path
from . import views

app_name = 'production'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/status-api/', views.task_status_api, name='task_status_api'),
    path('tasks/<int:pk>/receive/', views.task_receive, name='task_receive'),
    path('tasks/<int:pk>/complete/', views.task_complete, name='task_complete'),
    path('tasks/<int:pk>/terminate/', views.task_terminate, name='task_terminate'),
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/<int:pk>/approve/', views.requisition_approve, name='requisition_approve'),
    path('requisitions/<int:pk>/terminate/', views.requisition_terminate, name='requisition_terminate'),
    path('tasks/<int:task_pk>/qc/', views.qc_create, name='qc_create'),
    path('tasks/<int:task_pk>/inbound/', views.inbound_create, name='inbound_create'),
]

