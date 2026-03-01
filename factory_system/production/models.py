from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Product, Material, Unit
from sales.models import SalesOrder


class ProductionTask(models.Model):
    """生产任务单
    
    required_quantity / completed_quantity 始终为「成品基础单位」下的数量。
    """
    STATUS_CHOICES = [
        ('pending', '待接收'),
        ('material_insufficient', '原料不足'),
        ('received', '已接收'),
        ('material_preparing', '备料中'),
        ('in_production', '生产中'),
        ('qc_checking', '质检中'),
        ('pending_inbound', '待入库'),  # 生产已完成、未质检，等待成品入库；入库足量后变为已完成
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('terminated', '已终结'),
    ]
    
    PRODUCTION_TYPE_CHOICES = [
        ('order', '订单生产'),
        ('stock', '备货生产'),
    ]
    
    task_no = models.CharField(max_length=50, unique=True, verbose_name='任务单号')
    production_type = models.CharField(max_length=10, choices=PRODUCTION_TYPE_CHOICES, default='order', verbose_name='生产类型')
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, null=True, blank=True, related_name='production_tasks', verbose_name='关联订单')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='产品')
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='需求数量（基础单位）')
    completed_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='完成数量（基础单位）')
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

    # ---- 显示单位转换属性 ----

    def get_display_required_quantity(self):
        """需求数量（显示单位）"""
        if self.product and hasattr(self.product, 'to_display'):
            display_qty, _ = self.product.to_display(self.required_quantity)
            return display_qty
        return self.required_quantity

    def get_display_completed_quantity(self):
        """完成数量（显示单位）"""
        if self.product and hasattr(self.product, 'to_display'):
            display_qty, _ = self.product.to_display(self.completed_quantity)
            return display_qty
        return self.completed_quantity

    def get_display_shortage_quantity(self):
        """剩余数量（显示单位）= 需求 - 完成"""
        from decimal import Decimal
        shortage = self.required_quantity - self.completed_quantity
        if shortage < 0:
            shortage = Decimal('0')
        if self.product and hasattr(self.product, 'to_display'):
            display_qty, _ = self.product.to_display(shortage)
            return display_qty
        return shortage

    def get_display_unit_name(self):
        """成品显示单位名"""
        if self.product and hasattr(self.product, 'display_unit') and self.product.display_unit:
            return self.product.display_unit.name
        return ''


class TaskMaterialOverride(models.Model):
    """生产任务物料用量覆盖

    当实际生产中某原料用量与 BOM 配方不同时，可在任务级别覆盖单位产品用量。
    - 如果某 task + material 组合不存在记录，则沿用 BOM 默认值。
    - quantity / unit 含义与 BOM 行一致：每 1 基础单位成品所需的原料量。
    """
    task = models.ForeignKey(
        ProductionTask, on_delete=models.CASCADE,
        related_name='material_overrides', verbose_name='生产任务',
    )
    material = models.ForeignKey(
        'inventory.Material', on_delete=models.PROTECT,
        verbose_name='原料',
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=4,
        validators=[MinValueValidator(0)],
        verbose_name='单位产品用量',
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT,
        verbose_name='用量单位',
    )
    remark = models.CharField(max_length=200, blank=True, verbose_name='调整说明')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    updated_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='操作人',
    )

    class Meta:
        verbose_name = '任务物料用量覆盖'
        verbose_name_plural = '任务物料用量覆盖'
        unique_together = ['task', 'material']

    def __str__(self):
        return f"{self.task.task_no} - {self.material.name}: {self.quantity}{self.unit.name}"

    def get_base_quantity(self):
        """将覆盖用量转换为原料基础单位数量（与 BOM.get_base_quantity 语义相同）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.to_base(self.material, self.quantity, self.unit)


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
    
    def release_locked_material(self):
        """释放本领料单锁定的原料批次。任务终结时调用。"""
        from decimal import Decimal
        from .models import MaterialRequisitionItemBatch
        for allocation in MaterialRequisitionItemBatch.objects.filter(
            requisition_item__requisition=self
        ).select_related('batch'):
            batch = allocation.batch
            batch.locked_quantity = max(
                Decimal('0'),
                (batch.locked_quantity or Decimal('0')) - allocation.quantity_locked
            )
            batch.save()
            allocation.delete()


class MaterialRequisitionItem(models.Model):
    """领料单明细
    
    变更说明：
    - 删除 unit 字段：单位恒为 material.base_unit，不冗余存储
    - required_quantity / issued_quantity 始终为「原料基础单位」下的数量
    """
    requisition = models.ForeignKey(MaterialRequisition, on_delete=models.CASCADE, related_name='items', verbose_name='领料单')
    material = models.ForeignKey('inventory.Material', on_delete=models.PROTECT, verbose_name='原料')
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='需求数量（基础单位）')
    issued_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='实发数量（基础单位）')
    
    class Meta:
        verbose_name = '领料单明细'
        verbose_name_plural = '领料单明细'
    
    def __str__(self):
        return f"{self.requisition.requisition_no} - {self.material.name} x {self.required_quantity}"


class MaterialRequisitionItemBatch(models.Model):
    """领料单明细-批次锁定"""
    requisition_item = models.ForeignKey(
        MaterialRequisitionItem,
        on_delete=models.CASCADE,
        related_name='batch_allocations',
        verbose_name='领料明细'
    )
    batch = models.ForeignKey(
        'inventory.Batch',
        on_delete=models.CASCADE,
        related_name='requisition_allocations',
        verbose_name='批次'
    )
    quantity_locked = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='锁定数量（基础单位）'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '领料批次锁定'
        verbose_name_plural = '领料批次锁定'
        ordering = ['requisition_item', 'batch']
    
    def __str__(self):
        return f"{self.requisition_item} @ {self.batch.batch_no} 锁{self.quantity_locked}"


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
    """成品入库单
    
    变更说明：
    - 删除 unit 字段：单位恒为 task.product.base_unit
    - quantity 始终为「成品基础单位」下的数量
    """
    inbound_no = models.CharField(max_length=50, unique=True, verbose_name='入库单号')
    task = models.ForeignKey(ProductionTask, on_delete=models.CASCADE, related_name='inbounds', verbose_name='生产任务')
    qc_record = models.ForeignKey(QCRecord, on_delete=models.PROTECT, null=True, blank=True, verbose_name='质检记录')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='入库数量（基础单位）')
    operator = models.ForeignKey('auth.User', on_delete=models.PROTECT, verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '成品入库单'
        verbose_name_plural = '成品入库单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.inbound_no} - {self.task.product.name} x {self.quantity}"
