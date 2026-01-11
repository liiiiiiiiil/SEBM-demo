from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Material


class PurchaseTask(models.Model):
    """采购任务"""
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('purchasing', '采购中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('terminated', '已终结'),
    ]
    
    task_no = models.CharField(max_length=50, unique=True, verbose_name='采购任务号')
    supplier = models.CharField(max_length=200, verbose_name='供应商')
    contact_person = models.CharField(max_length=100, blank=True, verbose_name='联系人')
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name='联系电话')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='采购总额')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='created_purchase_tasks', verbose_name='创建人')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_purchase_tasks', verbose_name='审批人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    terminated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='terminated_purchase_tasks', verbose_name='终结人')
    terminated_at = models.DateTimeField(null=True, blank=True, verbose_name='终结时间')
    terminate_reason = models.TextField(blank=True, verbose_name='终结原因')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '采购任务'
        verbose_name_plural = '采购任务'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task_no} - {self.supplier} - {self.get_status_display()}"


class PurchaseTaskItem(models.Model):
    """采购任务明细"""
    task = models.ForeignKey(PurchaseTask, on_delete=models.CASCADE, related_name='items', verbose_name='采购任务')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='物料')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='采购数量')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='单价')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='小计')
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='已收货数量')
    
    class Meta:
        verbose_name = '采购任务明细'
        verbose_name_plural = '采购任务明细'
    
    def __str__(self):
        return f"{self.task.task_no} - {self.material.name} x {self.quantity}"
