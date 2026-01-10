from django.contrib.auth.models import User
from django.db import models


class Permission(models.Model):
    """系统权限定义"""
    PERMISSION_CATEGORIES = [
        ('sales', '销售权限'),
        ('inventory', '库存权限'),
        ('production', '生产权限'),
        ('logistics', '物流权限'),
        ('system', '系统权限'),
    ]
    
    code = models.CharField(max_length=50, unique=True, verbose_name='权限代码')
    name = models.CharField(max_length=100, verbose_name='权限名称')
    category = models.CharField(max_length=20, choices=PERMISSION_CATEGORIES, verbose_name='权限分类')
    description = models.TextField(blank=True, verbose_name='权限描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '权限'
        verbose_name_plural = '权限'
        ordering = ['category', 'code']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


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
    permissions = models.ManyToManyField(Permission, blank=True, related_name='user_profiles', verbose_name='额外权限')
    phone = models.CharField(max_length=20, blank=True, verbose_name='电话')
    department = models.CharField(max_length=50, blank=True, verbose_name='部门')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '用户角色'
        verbose_name_plural = '用户角色'
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    def has_permission(self, permission_code):
        """检查用户是否有指定权限"""
        # CEO拥有所有权限
        if self.role == 'ceo':
            return True
        
        # 检查角色默认权限
        role_permissions = self.get_role_default_permissions()
        if permission_code in role_permissions:
            return True
        
        # 检查额外配置的权限
        return self.permissions.filter(code=permission_code).exists()
    
    def get_role_default_permissions(self):
        """获取角色默认权限列表"""
        role_permission_map = {
            'sales': [
                'sales.order.create',
                'sales.order.view',
                'sales.order.edit',
                'inventory.customer.view',
                'inventory.customer.create',
                'inventory.customer.edit',
                'inventory.customer.delete',
            ],
            'sales_mgr': [
                'sales.order.create',
                'sales.order.view',
                'sales.order.edit',
                'sales.order.approve',
                'sales.order.view_all',
                'inventory.customer.view',
                'inventory.customer.create',
                'inventory.customer.edit',
                'inventory.customer.delete',
                'inventory.customer.manage',
            ],
            'warehouse': [
                'inventory.view',
                'inventory.transaction.view',
                'inventory.product.view',
                'inventory.product.manage',
                'inventory.material.manage',
                'inventory.category.manage',
                'inventory.adjustment.create',
                'production.requisition.approve',
                'production.inbound.create',
            ],
            'production': [
                'production.task.view',
                'production.task.receive',
                'production.requisition.create',
                'production.task.view',
            ],
            'qc': [
                'production.qc.create',
                'production.task.view',
            ],
            'logistics': [
                'logistics.shipment.create',
                'logistics.shipment.view',
                'logistics.driver.manage',
                'logistics.vehicle.manage',
            ],
            'ceo': [],  # CEO通过has_permission方法直接返回True
        }
        return role_permission_map.get(self.role, [])
    
    def get_all_permissions(self):
        """获取用户所有权限（角色默认权限 + 额外权限）"""
        permissions = set(self.get_role_default_permissions())
        permissions.update(self.permissions.values_list('code', flat=True))
        return list(permissions)
