from django.db import models
from django.core.validators import MinValueValidator


class MaterialCategory(models.Model):
    """原料分类"""
    name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    
    class Meta:
        verbose_name = '原料分类'
        verbose_name_plural = '原料分类'
    
    def __str__(self):
        return self.name


class Material(models.Model):
    """原料与杂项库"""
    MATERIAL_TYPE_CHOICES = [
        ('raw', '原料'),
        ('auxiliary', '辅料'),
        ('tool', '工具'),
        ('office', '办公用品'),
    ]
    
    sku = models.CharField(max_length=50, unique=True, verbose_name='SKU编码')
    name = models.CharField(max_length=200, verbose_name='名称')
    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, null=True, blank=True, verbose_name='分类')
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPE_CHOICES, default='raw', verbose_name='类型')
    unit = models.CharField(max_length=20, default='kg', verbose_name='单位')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='单价')
    safety_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='安全库存')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '原料'
        verbose_name_plural = '原料'
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"


class ProductCategory(models.Model):
    """成品分类"""
    name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    
    class Meta:
        verbose_name = '成品分类'
        verbose_name_plural = '成品分类'
    
    def __str__(self):
        return self.name


class Product(models.Model):
    """成品信息"""
    sku = models.CharField(max_length=50, unique=True, verbose_name='SKU编码')
    name = models.CharField(max_length=200, verbose_name='产品名称')
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, null=True, blank=True, verbose_name='分类')
    specification = models.TextField(blank=True, verbose_name='规格说明')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='基础单价')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='售价')
    safety_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='安全库存')
    unit = models.CharField(max_length=20, default='件', verbose_name='单位')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '成品'
        verbose_name_plural = '成品'
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"


class BOM(models.Model):
    """BOM配方库 - 定义1个成品由哪些原料组成"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bom_items', verbose_name='成品')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='原料')
    quantity = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(0.0001)], verbose_name='用量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = 'BOM配方'
        verbose_name_plural = 'BOM配方'
        unique_together = ['product', 'material']
        ordering = ['product', 'material']
    
    def __str__(self):
        return f"{self.product.name} -> {self.material.name} ({self.quantity}{self.unit})"


class Inventory(models.Model):
    """实时库存"""
    INVENTORY_TYPE_CHOICES = [
        ('product', '成品'),
        ('material', '原料'),
        ('other', '其它'),
    ]
    
    inventory_type = models.CharField(max_length=20, choices=INVENTORY_TYPE_CHOICES, verbose_name='库存类型')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='成品')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='原料')
    other_name = models.CharField(max_length=200, blank=True, verbose_name='其它物品名称')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '库存'
        verbose_name_plural = '库存'
        constraints = [
            models.UniqueConstraint(
                fields=['inventory_type', 'product'],
                condition=models.Q(inventory_type='product'),
                name='unique_product_inventory'
            ),
            models.UniqueConstraint(
                fields=['inventory_type', 'material'],
                condition=models.Q(inventory_type='material'),
                name='unique_material_inventory'
            ),
            models.UniqueConstraint(
                fields=['inventory_type', 'other_name'],
                condition=models.Q(inventory_type='other') & ~models.Q(other_name=''),
                name='unique_other_inventory'
            ),
        ]
    
    def __str__(self):
        if self.inventory_type == 'product' and self.product:
            return f"{self.product.name} - {self.quantity}{self.unit}"
        elif self.inventory_type == 'material' and self.material:
            return f"{self.material.name} - {self.quantity}{self.unit}"
        elif self.inventory_type == 'other' and self.other_name:
            return f"{self.other_name} - {self.quantity}{self.unit}"
        return f"库存 - {self.quantity}{self.unit}"
    
    def get_item(self):
        """获取关联的产品或原料对象"""
        if self.inventory_type == 'product':
            return self.product
        elif self.inventory_type == 'material':
            return self.material
        return None
    
    def check_safety_stock(self):
        """检查是否低于安全库存"""
        item = self.get_item()
        if item and hasattr(item, 'safety_stock'):
            return self.quantity < item.safety_stock
        return False
    
    def get_unit_price(self):
        """获取基础单价"""
        if self.inventory_type == 'product' and self.product:
            return self.product.unit_price or 0
        elif self.inventory_type == 'material' and self.material:
            return self.material.unit_price or 0
        elif self.inventory_type == 'other':
            # 其它类型库存可能没有关联的产品或原料，返回0或需要单独存储单价
            return 0
        return 0
    
    def get_total_value(self):
        """计算总价值（单价 * 数量）"""
        from decimal import Decimal
        unit_price = Decimal(str(self.get_unit_price()))
        quantity = Decimal(str(self.quantity))
        return float(unit_price * quantity)
    
    def get_batches(self):
        """获取所有批次"""
        return Batch.objects.filter(inventory=self).order_by('batch_date', 'created_at')
    
    def update_quantity_from_batches(self):
        """从批次汇总更新总数量"""
        from django.db.models import Sum
        total = self.get_batches().aggregate(total=Sum('quantity'))['total'] or 0
        self.quantity = total
        self.save(update_fields=['quantity'])


class Batch(models.Model):
    """库存批次"""
    batch_no = models.CharField(max_length=100, verbose_name='批次号')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='batches', verbose_name='库存')
    batch_date = models.DateField(verbose_name='批次日期')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='数量')
    locked_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='锁定数量')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='批次单价')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='过期日期')
    supplier = models.CharField(max_length=200, blank=True, verbose_name='供应商')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '库存批次'
        verbose_name_plural = '库存批次'
        ordering = ['batch_date', 'created_at']
        indexes = [
            models.Index(fields=['inventory', 'batch_date']),
        ]
    
    def __str__(self):
        item_name = self.inventory.product.name if self.inventory.inventory_type == 'product' else self.inventory.material.name
        return f"{item_name} - {self.batch_no} ({self.quantity}{self.inventory.unit})"
    
    def is_expired(self):
        """检查是否过期"""
        if self.expiry_date:
            from django.utils import timezone
            return timezone.now().date() > self.expiry_date
        return False
    
    def get_available_quantity(self):
        """获取可用数量（总数量 - 锁定数量）"""
        from decimal import Decimal
        return max(Decimal('0'), self.quantity - self.locked_quantity)


class StockTransaction(models.Model):
    """库存变动记录"""
    TRANSACTION_TYPE_CHOICES = [
        ('sale_out', '销售出库'),
        ('production_out', '生产领料出库'),
        ('production_in', '生产完工入库'),
        ('purchase_in', '采购入库'),
        ('adjustment', '库存调整'),
    ]
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, verbose_name='变动类型')
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, verbose_name='库存')
    batch = models.ForeignKey('Batch', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name='批次')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    old_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整前单价')
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整后单价')
    reference_no = models.CharField(max_length=100, blank=True, verbose_name='关联单号')
    remark = models.TextField(blank=True, verbose_name='备注')
    operator = models.ForeignKey('auth.User', on_delete=models.PROTECT, verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '库存变动记录'
        verbose_name_plural = '库存变动记录'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.inventory} - {self.quantity}{self.unit}"


class InventoryAdjustmentRequest(models.Model):
    """库存调整申请"""
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('rejected', '已拒绝'),
        ('completed', '已完成'),
    ]
    
    request_no = models.CharField(max_length=50, unique=True, verbose_name='申请单号')
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, verbose_name='库存')
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='当前数量')
    adjust_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='调整数量')
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='调整后数量')
    current_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='当前单价')
    adjust_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整单价')
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整后单价')
    reason = models.TextField(verbose_name='调整原因')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    applicant = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='inventory_adjustment_requests', verbose_name='申请人')
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_inventory_adjustments', verbose_name='审批人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    reject_reason = models.TextField(blank=True, verbose_name='拒绝原因')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '库存调整申请'
        verbose_name_plural = '库存调整申请'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.request_no} - {self.inventory} - {self.get_status_display()}"



