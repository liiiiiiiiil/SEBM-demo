from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Material, Unit


class Supplier(models.Model):
    """供应商信息"""
    name = models.CharField(max_length=200, unique=True, verbose_name='供应商名称')
    contact_person = models.CharField(max_length=100, blank=True, verbose_name='联系人')
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name='联系电话')
    address = models.CharField(max_length=500, blank=True, verbose_name='地址')
    email = models.EmailField(blank=True, verbose_name='邮箱')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='created_suppliers', verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '供应商'
        verbose_name_plural = '供应商'
        ordering = ['name']
    
    def __str__(self):
        return self.name


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
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name='供应商')
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
        return f"{self.task_no} - {self.supplier.name} - {self.get_status_display()}"


class PurchaseTaskItem(models.Model):
    """采购任务明细
    
    变更说明（双单位体系重构）：
    - quantity / unit_price 始终是「基础单位」口径
    - 删除旧 unit CharField
    - 新增 display_unit / display_quantity 记录采购人填写时的原始单位和数量
    """
    ITEM_TYPE_CHOICES = [
        ('material', '原料'),
        ('office', '办公用品'),
        ('other', '其它'),
    ]
    
    task = models.ForeignKey(PurchaseTask, on_delete=models.CASCADE, related_name='items', verbose_name='采购任务')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, null=True, blank=True, verbose_name='物料')
    item_name = models.CharField(max_length=200, blank=True, verbose_name='物品名称')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, default='material', verbose_name='物品类型')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='采购数量（基础单位）')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='单价（基础单位）')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='小计')
    display_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_items',
        verbose_name='采购业务单位',
    )
    display_quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name='采购业务数量',
    )
    
    class Meta:
        verbose_name = '采购任务明细'
        verbose_name_plural = '采购任务明细'
    
    def __str__(self):
        if self.material:
            return f"{self.task.task_no} - {self.material.name} x {self.quantity}"
        else:
            return f"{self.task.task_no} - {self.item_name} x {self.quantity}"
    
    def get_item_display_name(self):
        """获取物品显示名称"""
        if self.material:
            return self.material.name
        else:
            return self.item_name or '-'
