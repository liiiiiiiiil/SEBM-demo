from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Product


class Customer(models.Model):
    """客户中心"""
    CREDIT_LEVEL_CHOICES = [
        ('A', 'A级（优秀）'),
        ('B', 'B级（良好）'),
        ('C', 'C级（一般）'),
        ('D', 'D级（较差）'),
    ]
    
    EDIT_STATUS_CHOICES = [
        ('none', '无编辑申请'),
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('rejected', '已拒绝'),
    ]
    
    DELETE_STATUS_CHOICES = [
        ('none', '无删除申请'),
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('rejected', '已拒绝'),
    ]
    
    name = models.CharField(max_length=200, unique=True, verbose_name='客户名称')
    contact_person = models.CharField(max_length=100, verbose_name='联系人')
    phone = models.CharField(max_length=20, verbose_name='联系电话')
    address = models.TextField(verbose_name='地址')
    credit_level = models.CharField(max_length=1, choices=CREDIT_LEVEL_CHOICES, default='C', verbose_name='信用等级')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_customers', verbose_name='负责人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    # 编辑审批相关字段
    edit_status = models.CharField(max_length=20, choices=EDIT_STATUS_CHOICES, default='none', verbose_name='编辑审批状态')
    edit_pending_data = models.TextField(blank=True, verbose_name='待审批编辑数据')  # JSON格式存储待审批的数据
    edit_reason = models.TextField(blank=True, verbose_name='编辑原因')
    edit_requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_edit_requests', verbose_name='编辑申请人')
    edit_requested_at = models.DateTimeField(null=True, blank=True, verbose_name='编辑申请时间')
    edit_approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_customer_edits', verbose_name='编辑审批人')
    edit_approved_at = models.DateTimeField(null=True, blank=True, verbose_name='编辑审批时间')
    edit_reject_reason = models.TextField(blank=True, verbose_name='编辑拒绝原因')
    
    # 删除审批相关字段
    delete_status = models.CharField(max_length=20, choices=DELETE_STATUS_CHOICES, default='none', verbose_name='删除审批状态')
    delete_reason = models.TextField(blank=True, verbose_name='删除原因')
    delete_requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_delete_requests', verbose_name='删除申请人')
    delete_requested_at = models.DateTimeField(null=True, blank=True, verbose_name='删除申请时间')
    delete_approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_customer_deletes', verbose_name='删除审批人')
    delete_approved_at = models.DateTimeField(null=True, blank=True, verbose_name='删除审批时间')
    delete_reject_reason = models.TextField(blank=True, verbose_name='删除拒绝原因')
    is_deleted = models.BooleanField(default=False, verbose_name='是否已删除（软删除）')
    
    class Meta:
        verbose_name = '客户'
        verbose_name_plural = '客户'
        ordering = ['-created_at']
    
    def has_related_orders(self):
        """检查是否有关联订单（包括所有状态的订单）"""
        return SalesOrder.objects.filter(customer=self).exists()
    
    def __str__(self):
        return self.name


class CustomerTransfer(models.Model):
    """客户转移记录"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='transfers', verbose_name='客户')
    from_user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='transferred_from_customers', verbose_name='原负责人')
    to_user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='transferred_to_customers', verbose_name='新负责人')
    transferred_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_transfers', verbose_name='操作人')
    transferred_at = models.DateTimeField(auto_now_add=True, verbose_name='转移时间')
    remark = models.TextField(blank=True, verbose_name='备注')
    
    class Meta:
        verbose_name = '客户转移记录'
        verbose_name_plural = '客户转移记录'
        ordering = ['-transferred_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.from_user.username if self.from_user else '无'} -> {self.to_user.username if self.to_user else '无'}"


class SalesOrder(models.Model):
    """产品订单"""
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('ceo_pending', '待总经理审批'),
        ('ceo_approved', '总经理已审批'),
        ('rejected', '已退回'),
        ('in_production', '生产中'),
        ('ready_to_ship', '待发货'),
        ('shipped', '已发货'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('terminated', '已终结'),
    ]
    
    order_no = models.CharField(max_length=50, unique=True, verbose_name='订单号')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name='客户')
    salesperson = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='sales_orders', verbose_name='销售员')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='订单总额')
    delivery_date = models.DateField(null=True, blank=True, verbose_name='交付日期')
    reserve_inventory = models.BooleanField(default=False, verbose_name='预占库存')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_orders', verbose_name='审批人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    ceo_approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='ceo_approved_orders', verbose_name='总经理审批人')
    ceo_approved_at = models.DateTimeField(null=True, blank=True, verbose_name='总经理审批时间')
    rejected_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_orders', verbose_name='退回人')
    rejected_at = models.DateTimeField(null=True, blank=True, verbose_name='退回时间')
    reject_reason = models.TextField(blank=True, verbose_name='退回原因')
    terminated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='terminated_orders', verbose_name='终结人')
    terminated_at = models.DateTimeField(null=True, blank=True, verbose_name='终结时间')
    terminate_reason = models.TextField(blank=True, verbose_name='终结原因')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '产品订单'
        verbose_name_plural = '产品订单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.order_no} - {self.customer.name} - {self.get_status_display()}"


class SalesOrderItem(models.Model):
    """订单明细"""
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items', verbose_name='订单')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='产品')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='数量')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='单价')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='小计')
    
    class Meta:
        verbose_name = '订单明细'
        verbose_name_plural = '订单明细'
    
    def __str__(self):
        return f"{self.order.order_no} - {self.product.name} x {self.quantity}"


class SalesOrderItemBatch(models.Model):
    """订单明细批次分配"""
    order_item = models.ForeignKey(SalesOrderItem, on_delete=models.CASCADE, related_name='batch_allocations', verbose_name='订单明细')
    batch = models.ForeignKey('inventory.Batch', on_delete=models.PROTECT, verbose_name='批次')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='分配数量')
    
    class Meta:
        verbose_name = '订单明细批次分配'
        verbose_name_plural = '订单明细批次分配'
        unique_together = ['order_item', 'batch']
    
    def __str__(self):
        return f"{self.order_item.order.order_no} - {self.batch.batch_no} x {self.quantity}"


