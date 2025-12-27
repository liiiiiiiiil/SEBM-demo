from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """用户角色扩展"""
    ROLE_CHOICES = [
        ('sales', '销售员'),
        ('sales_mgr', '销售经理'),
        ('warehouse', '仓库管理员'),
        ('production', '生产管理员'),
        ('qc', '质检员'),
        ('logistics', '物流管理员'),
        ('ceo', '总经理'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    phone = models.CharField(max_length=20, blank=True, verbose_name='电话')
    department = models.CharField(max_length=50, blank=True, verbose_name='部门')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '用户角色'
        verbose_name_plural = '用户角色'
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
