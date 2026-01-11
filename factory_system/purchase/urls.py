from django.urls import path
from . import views

app_name = 'purchase'

urlpatterns = [
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/approve/', views.task_approve, name='task_approve'),
    path('tasks/<int:pk>/complete/', views.task_complete, name='task_complete'),
    path('tasks/<int:pk>/terminate/', views.task_terminate, name='task_terminate'),
]
