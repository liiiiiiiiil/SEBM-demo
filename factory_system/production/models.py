from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Product, Material
from sales.models import SalesOrder


class ProductionTask(models.Model):
    """生产任务单"""
    STATUS_CHOICES = [
        ('pending', '待接收'),
        ('material_insufficient', '原料不足'),
        ('received', '已接收'),
        ('material_preparing', '备料中'),
        ('in_production', '生产中'),
        ('qc_checking', '质检中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('terminated', '已终结'),
    ]
    
    task_no = models.CharField(max_length=50, unique=True, verbose_name='任务单号')
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='production_tasks', verbose_name='关联订单')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='产品')
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='需求数量')
    completed_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='完成数量')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    planned_completion_date = models.DateField(null=True, blank=True, verbose_name='计划完成日期')
    received_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_tasks', verbose_name='接收人')
    received_at = models.DateTimeField(null=True, blank=True, verbose_name='接收时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    terminated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='terminated_tasks', verbose_name='终结人')
    terminated_at = models.DateTimeField(null=True, blank=True, verbose_name='终结时间')
    terminate_reason = models.TextField(blank=True, verbose_name='终结原因')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '生产任务单'
        verbose_name_plural = '生产任务单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task_no} - {self.product.name} x {self.required_quantity}"


class MaterialRequisition(models.Model):
    """领料单"""
    STATUS_CHOICES = [
        ('pending', '待审核'),
        ('approved', '已批准'),
        ('issued', '已发料'),
        ('cancelled', '已取消'),
        ('terminated', '已终结'),
    ]
    
    requisition_no = models.CharField(max_length=50, unique=True, verbose_name='领料单号')
    task = models.ForeignKey(ProductionTask, on_delete=models.CASCADE, related_name='material_requisitions', verbose_name='生产任务')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    requested_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='requested_requisitions', verbose_name='申请人')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_requisitions', verbose_name='审批人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    issued_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_requisitions', verbose_name='发料人')
    issued_at = models.DateTimeField(null=True, blank=True, verbose_name='发料时间')
    terminated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='terminated_requisitions', verbose_name='终结人')
    terminated_at = models.DateTimeField(null=True, blank=True, verbose_name='终结时间')
    terminate_reason = models.TextField(blank=True, verbose_name='终结原因')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '领料单'
        verbose_name_plural = '领料单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.requisition_no} - {self.task.task_no}"


class MaterialRequisitionItem(models.Model):
    """领料单明细"""
    requisition = models.ForeignKey(MaterialRequisition, on_delete=models.CASCADE, related_name='items', verbose_name='领料单')
    material = models.ForeignKey('inventory.Material', on_delete=models.PROTECT, verbose_name='原料')
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='需求数量')
    issued_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='实发数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    
    class Meta:
        verbose_name = '领料单明细'
        verbose_name_plural = '领料单明细'
    
    def __str__(self):
        return f"{self.requisition.requisition_no} - {self.material.name} x {self.required_quantity}"


class QCRecord(models.Model):
    """质检记录"""
    RESULT_CHOICES = [
        ('qualified', '合格'),
        ('unqualified', '不合格'),
        ('rework', '返工'),
    ]
    
    task = models.ForeignKey(ProductionTask, on_delete=models.CASCADE, related_name='qc_records', verbose_name='生产任务')
    batch_no = models.CharField(max_length=50, verbose_name='批次号')
    inspected_quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='抽检数量')
    qualified_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='合格数量')
    unqualified_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='不合格数量')
    qualification_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='合格率(%)')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, verbose_name='质检结果')
    inspector = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='qc_records', verbose_name='质检员')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '质检记录'
        verbose_name_plural = '质检记录'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task.task_no} - {self.batch_no} - {self.get_result_display()}"


class FinishedProductInbound(models.Model):
    """成品入库单"""
    inbound_no = models.CharField(max_length=50, unique=True, verbose_name='入库单号')
    task = models.ForeignKey(ProductionTask, on_delete=models.CASCADE, related_name='inbounds', verbose_name='生产任务')
    qc_record = models.ForeignKey(QCRecord, on_delete=models.PROTECT, null=True, blank=True, verbose_name='质检记录')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='入库数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    operator = models.ForeignKey('auth.User', on_delete=models.PROTECT, verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '成品入库单'
        verbose_name_plural = '成品入库单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.inbound_no} - {self.task.product.name} x {self.quantity}"
