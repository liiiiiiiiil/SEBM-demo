from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Customer, Product


class SalesOrder(models.Model):
    """销售订单"""
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审核'),
        ('in_production', '生产中'),
        ('ready_to_ship', '待发货'),
        ('shipped', '已发货'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    ]
    
    order_no = models.CharField(max_length=50, unique=True, verbose_name='订单号')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name='客户')
    salesperson = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='sales_orders', verbose_name='销售员')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='订单总额')
    reserve_inventory = models.BooleanField(default=False, verbose_name='预占库存')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_orders', verbose_name='审批人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '销售订单'
        verbose_name_plural = '销售订单'
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


class ShippingNotice(models.Model):
    """发货通知单"""
    notice_no = models.CharField(max_length=50, unique=True, verbose_name='通知单号')
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='shipping_notices', verbose_name='订单')
    status = models.CharField(max_length=20, default='pending', choices=[('pending', '待发货'), ('shipped', '已发货')], verbose_name='状态')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '发货通知单'
        verbose_name_plural = '发货通知单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notice_no} - {self.order.order_no}"
