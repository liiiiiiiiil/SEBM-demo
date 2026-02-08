from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Unit(models.Model):
    """基础单位字典表
    
    变更说明（双单位体系重构）：
    - 去除 is_base 字段（"是否基础单位"由每个物料/成品自行指定）
    - 新增 symbol 用于简洁显示
    - category 去掉 packaging（包装不是物理量纲），新增 area
    - 「袋」「箱」等包装单位仍录入 Unit 表，category 设为 quantity
    """
    UNIT_CATEGORY_CHOICES = [
        ('weight', '重量'),
        ('length', '长度'),
        ('volume', '体积'),
        ('quantity', '数量'),
        ('area', '面积'),
    ]
    
    code = models.CharField(max_length=20, unique=True, verbose_name='单位代码')
    name = models.CharField(max_length=50, verbose_name='单位名称')
    symbol = models.CharField(max_length=10, blank=True, default='', verbose_name='简写符号')
    category = models.CharField(max_length=20, choices=UNIT_CATEGORY_CHOICES, verbose_name='单位类别')
    display_order = models.IntegerField(default=0, verbose_name='显示顺序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '基础单位'
        verbose_name_plural = '基础单位'
        ordering = ['category', 'display_order', 'code']
        db_table = 'inventory_unit'
    
    def __str__(self):
        return f"{self.name}({self.code})"


class MaterialCategory(models.Model):
    """原料分类"""
    name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    
    class Meta:
        verbose_name = '原料分类'
        verbose_name_plural = '原料分类'
    
    def __str__(self):
        return self.name


class UnitMixin:
    """Material 和 Product 共享的单位换算便捷方法。
    
    所有方法委托给 UnitConversionService，保持模型层轻薄。
    """

    def to_base(self, quantity, from_unit):
        """将任意单位数量转换为基础单位数量"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.to_base(self, quantity, from_unit)

    def from_base(self, base_quantity, to_unit):
        """将基础单位数量转换为目标单位数量"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.from_base(self, base_quantity, to_unit)

    def to_display(self, base_quantity):
        """将基础单位数量转换为当前显示单位数量，返回 (数量, Unit实例)"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.to_display(self, base_quantity)

    def from_display(self, display_quantity):
        """将显示单位数量转换为基础单位数量"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.from_display(self, display_quantity)

    def convert(self, quantity, from_unit, to_unit):
        """任意两个合法单位之间互转"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.convert(self, quantity, from_unit, to_unit)

    def get_available_units(self):
        """获取所有可用单位列表（基础单位 + 换算表中的目标单位）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.get_available_units(self)


class Material(UnitMixin, models.Model):
    """原料与杂项库
    
    变更说明（双单位体系重构）：
    - 删除旧 unit CharField → 被 display_unit 取代
    - base_unit 从可空改为必填、不可变
    - 新增 display_unit（FK→Unit, 必填）：当前显示单位，可随时修改
    - unit_price / safety_stock 语义锁定为「基础单位」下的值
    """
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
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='base_unit_materials',
        verbose_name='基础单位'
    )
    display_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='display_unit_materials',
        verbose_name='显示单位'
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='单价（基础单位）')
    safety_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='安全库存（基础单位）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '原料'
        verbose_name_plural = '原料'
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        # 默认显示单位 = 基础单位
        if not self.display_unit_id and self.base_unit_id:
            self.display_unit_id = self.base_unit_id
        # 基础单位不可变校验（仅已有关联数据时）
        if self.pk:
            try:
                old = Material.objects.filter(pk=self.pk).values('base_unit_id').first()
                if old and old['base_unit_id'] and old['base_unit_id'] != self.base_unit_id:
                    has_data = (
                        Inventory.objects.filter(material=self).exists()
                        or BOM.objects.filter(material=self).exists()
                    )
                    if has_data:
                        raise ValidationError('该物料已有关联数据（库存/BOM），不允许修改基础单位')
            except Material.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # 显示单位必须是基础单位或在换算表中已定义
        if self.pk and self.display_unit_id and self.base_unit_id:
            if self.display_unit_id != self.base_unit_id:
                exists = ItemUnitConversion.objects.filter(
                    content_type='material',
                    material=self,
                    target_unit=self.display_unit,
                    is_active=True,
                ).exists()
                if not exists:
                    raise ValidationError({
                        'display_unit': '显示单位必须是基础单位或在换算表中已定义的单位'
                    })


class ProductCategory(models.Model):
    """成品分类"""
    name = models.CharField(max_length=100, unique=True, verbose_name='分类名称')
    
    class Meta:
        verbose_name = '成品分类'
        verbose_name_plural = '成品分类'
    
    def __str__(self):
        return self.name


class Product(UnitMixin, models.Model):
    """成品信息
    
    变更说明（双单位体系重构）：
    - 删除旧 unit CharField → 被 display_unit 取代
    - base_unit 从可空改为必填、不可变
    - 新增 display_unit（FK→Unit, 必填）：当前显示单位，可随时修改
    - unit_price / sale_price / safety_stock 语义锁定为「基础单位」下的值
    """
    sku = models.CharField(max_length=50, unique=True, verbose_name='SKU编码')
    name = models.CharField(max_length=200, verbose_name='产品名称')
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, null=True, blank=True, verbose_name='分类')
    specification = models.TextField(blank=True, verbose_name='规格说明')
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='base_unit_products',
        verbose_name='基础单位'
    )
    display_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='display_unit_products',
        verbose_name='显示单位'
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='基础单价（基础单位）')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='售价（基础单位）')
    safety_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='安全库存（基础单位）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '成品'
        verbose_name_plural = '成品'
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        # 默认显示单位 = 基础单位
        if not self.display_unit_id and self.base_unit_id:
            self.display_unit_id = self.base_unit_id
        # 基础单位不可变校验（仅已有关联数据时）
        if self.pk:
            try:
                old = Product.objects.filter(pk=self.pk).values('base_unit_id').first()
                if old and old['base_unit_id'] and old['base_unit_id'] != self.base_unit_id:
                    has_data = (
                        Inventory.objects.filter(product=self).exists()
                        or BOM.objects.filter(product=self).exists()
                    )
                    if has_data:
                        raise ValidationError('该成品已有关联数据（库存/BOM），不允许修改基础单位')
            except Product.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # 显示单位必须是基础单位或在换算表中已定义
        if self.pk and self.display_unit_id and self.base_unit_id:
            if self.display_unit_id != self.base_unit_id:
                exists = ItemUnitConversion.objects.filter(
                    content_type='product',
                    product=self,
                    target_unit=self.display_unit,
                    is_active=True,
                ).exists()
                if not exists:
                    raise ValidationError({
                        'display_unit': '显示单位必须是基础单位或在换算表中已定义的单位'
                    })


class ItemUnitConversion(models.Model):
    """统一单位换算表
    
    替代原 MaterialPackagingUnit + ProductPackagingUnit。
    
    语义：1 target_unit = factor × base_unit
    例：1 吨 = 1000 kg → factor=1000
    例：1 袋 = 50 kg  → factor=50
    """
    CONTENT_TYPE_CHOICES = [
        ('material', '原料'),
        ('product', '成品'),
    ]

    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, verbose_name='类型')
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='unit_conversions',
        verbose_name='原料',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='unit_conversions',
        verbose_name='成品',
    )
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='conversion_base_units',
        verbose_name='换算基准单位',
    )
    target_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='conversion_target_units',
        verbose_name='换算目标单位',
    )
    factor = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        validators=[MinValueValidator(0.000001)],
        verbose_name='换算系数',
        help_text='1 目标单位 = 系数 × 基础单位。例：1吨=1000kg，系数为1000',
    )
    is_default = models.BooleanField(default=False, verbose_name='是否默认显示换算')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '单位换算'
        verbose_name_plural = '单位换算'
        db_table = 'inventory_item_unit_conversion'
        constraints = [
            models.UniqueConstraint(
                fields=['material', 'target_unit'],
                condition=models.Q(content_type='material'),
                name='unique_material_target_unit',
            ),
            models.UniqueConstraint(
                fields=['product', 'target_unit'],
                condition=models.Q(content_type='product'),
                name='unique_product_target_unit',
            ),
        ]
        ordering = ['content_type', 'created_at']

    def __str__(self):
        item_name = ''
        if self.content_type == 'material' and self.material:
            item_name = self.material.name
        elif self.content_type == 'product' and self.product:
            item_name = self.product.name
        return f"{item_name}: 1{self.target_unit.code}={self.factor}{self.base_unit.code}"

    def clean(self):
        super().clean()
        # base_unit 必须等于关联物料/成品的 base_unit
        if self.content_type == 'material' and self.material_id:
            if self.base_unit_id != self.material.base_unit_id:
                raise ValidationError({
                    'base_unit': '换算基准单位必须与物料的基础单位一致'
                })
        elif self.content_type == 'product' and self.product_id:
            if self.base_unit_id != self.product.base_unit_id:
                raise ValidationError({
                    'base_unit': '换算基准单位必须与成品的基础单位一致'
                })
        # target_unit 不能等于 base_unit
        if self.target_unit_id == self.base_unit_id:
            raise ValidationError({
                'target_unit': '目标单位不能与基础单位相同'
            })

    def get_display_text(self):
        """获取显示文本：如"吨(1000kg/吨)" """
        return f"{self.target_unit.name}({self.factor}{self.base_unit.code}/{self.target_unit.code})"


class BOM(models.Model):
    """BOM配方库
    
    语义：每 1 个「成品基础单位」的成品，需要 quantity 个 unit 的该原料。
    
    变更说明：
    - 新增 unit 字段（FK→Unit），BOM 行的用量单位
    - unit 必须是 material 的合法单位（base_unit 或换算表中的 target_unit）
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bom_items', verbose_name='成品')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name='原料')
    quantity = models.DecimalField(
        max_digits=10, decimal_places=4,
        validators=[MinValueValidator(0.0001)],
        verbose_name='用量',
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='bom_units',
        verbose_name='用量单位',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = 'BOM配方'
        verbose_name_plural = 'BOM配方'
        unique_together = ['product', 'material']
        ordering = ['product', 'material']
    
    def __str__(self):
        return f"{self.product.name} -> {self.material.name} ({self.quantity} {self.unit.code})"

    def clean(self):
        super().clean()
        # unit 必须是 material 的合法单位
        if self.material_id and self.unit_id:
            from inventory.services.unit_conversion import UnitConversionService
            if not UnitConversionService.validate_bom_unit(self):
                raise ValidationError({
                    'unit': f'BOM用量单位必须是原料「{self.material.name}」的基础单位或其换算表中已定义的单位'
                })

    def save(self, *args, **kwargs):
        # 保存前也做一次校验
        if self.material_id and self.unit_id:
            from inventory.services.unit_conversion import UnitConversionService
            if not UnitConversionService.validate_bom_unit(self):
                raise ValidationError(
                    f'BOM用量单位必须是原料「{self.material.name}」的基础单位或其换算表中已定义的单位'
                )
        super().save(*args, **kwargs)

    def get_base_quantity(self):
        """将 BOM 用量转换为原料基础单位数量"""
        if self.unit_id == self.material.base_unit_id:
            return self.quantity
        return self.material.to_base(self.quantity, self.unit)


class Inventory(models.Model):
    """实时库存
    
    变更说明：
    - 删除 unit 字段：单位恒等于关联物料/成品的 base_unit，不再冗余存储
    - quantity 语义锁定为「基础单位」下的数量
    """
    INVENTORY_TYPE_CHOICES = [
        ('product', '成品'),
        ('material', '原料'),
        ('other', '其它'),
    ]
    
    inventory_type = models.CharField(max_length=20, choices=INVENTORY_TYPE_CHOICES, verbose_name='库存类型')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='成品')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='原料')
    other_name = models.CharField(max_length=200, blank=True, verbose_name='其它物品名称')
    other_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name='other_inventories', verbose_name='其它物品单位')
    other_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='其它物品单价')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='数量（基础单位）')
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
        unit_name = self.get_unit_name()
        if self.inventory_type == 'product' and self.product:
            return f"{self.product.name} - {self.quantity}{unit_name}"
        elif self.inventory_type == 'material' and self.material:
            return f"{self.material.name} - {self.quantity}{unit_name}"
        elif self.inventory_type == 'other' and self.other_name:
            return f"{self.other_name} - {self.quantity}"
        return f"库存 - {self.quantity}"

    def get_unit_name(self):
        """获取基础单位显示名称"""
        item = self.get_item()
        if item and hasattr(item, 'base_unit') and item.base_unit:
            return item.base_unit.name
        if self.inventory_type == 'other' and self.other_unit:
            return self.other_unit.name
        return ''

    def get_display_unit_name(self):
        """获取显示单位名称"""
        item = self.get_item()
        if item and hasattr(item, 'display_unit') and item.display_unit:
            return item.display_unit.name
        if self.inventory_type == 'other' and self.other_unit:
            return self.other_unit.name
        return self.get_unit_name()

    def get_display_quantity(self):
        """获取显示单位下的数量"""
        item = self.get_item()
        if item and hasattr(item, 'to_display'):
            display_qty, _ = item.to_display(self.quantity)
            return display_qty
        return self.quantity
    
    def get_item(self):
        """获取关联的产品或原料对象"""
        if self.inventory_type == 'product':
            return self.product
        elif self.inventory_type == 'material':
            return self.material
        return None
    
    def check_safety_stock(self):
        """检查是否低于安全库存（基础单位比较）"""
        item = self.get_item()
        if item and hasattr(item, 'safety_stock'):
            return self.quantity < item.safety_stock
        return False
    
    def get_unit_price(self):
        """获取基础单价（基础单位）"""
        if self.inventory_type == 'product' and self.product:
            return self.product.unit_price or 0
        elif self.inventory_type == 'material' and self.material:
            return self.material.unit_price or 0
        elif self.inventory_type == 'other':
            return self.other_unit_price or 0
        return 0

    def get_display_unit_price(self):
        """获取显示单位下的单价。
        
        显示单位单价 = 基础单价 × factor（因为 1 显示单位 = factor × 基础单位）
        例：基础单价 0.35元/千克，1吨=1000千克 → 显示单价 = 0.35×1000 = 350元/吨
        """
        from decimal import Decimal
        base_price = Decimal(str(self.get_unit_price()))
        item = self.get_item()
        if item and hasattr(item, 'display_unit') and item.display_unit:
            if item.display_unit_id != item.base_unit_id:
                try:
                    from inventory.services.unit_conversion import UnitConversionService
                    factor = UnitConversionService.get_factor(item, item.display_unit)
                    return float(base_price * factor)
                except (ValueError, Exception):
                    pass
        return float(base_price)

    def get_total_value(self):
        """计算总价值（基础单价 × 基础单位数量，与显示单位无关）"""
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
    """库存批次
    
    变更说明：
    - 无独立 unit 字段，所有数量隐含为 base_unit
    - unit_price 始终为基础单位下的单价
    """
    batch_no = models.CharField(max_length=100, verbose_name='批次号')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='batches', verbose_name='库存')
    batch_date = models.DateField(verbose_name='批次日期')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='数量（基础单位）')
    locked_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='锁定数量（基础单位）')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='批次单价（基础单位）')
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
        item = self.inventory.get_item()
        item_name = item.name if item else (self.inventory.other_name or '未知')
        unit_name = item.base_unit.name if item and hasattr(item, 'base_unit') and item.base_unit else ''
        return f"{item_name} - {self.batch_no} ({self.quantity}{unit_name})"
    
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
    """库存变动记录
    
    变更说明：
    - unit 从 CharField 改为 FK→Unit，记录操作时的「操作单位」（用于审计追溯）
    - 新增 base_quantity：基础单位下的实际变动量（冗余但便于查询）
    - 删除 old_unit_price / new_unit_price（单价调整走 InventoryAdjustmentRequest）
    """
    TRANSACTION_TYPE_CHOICES = [
        ('sale_out', '销售出库'),
        ('production_out', '生产领料出库'),
        ('production_in', '生产完工入库'),
        ('purchase_in', '采购入库'),
        ('adjustment', '库存调整'),
        ('unit_change', '单位调整'),  # 保留用于历史数据
    ]
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, verbose_name='变动类型')
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, verbose_name='库存')
    batch = models.ForeignKey('Batch', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name='批次')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='操作数量（操作单位）')
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='stock_transactions',
        verbose_name='操作单位',
    )
    base_quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name='基础单位数量',
        help_text='系统自动换算后的基础单位量，用于库存增减',
    )
    reference_no = models.CharField(max_length=100, blank=True, verbose_name='关联单号')
    remark = models.TextField(blank=True, verbose_name='备注')
    operator = models.ForeignKey('auth.User', on_delete=models.PROTECT, verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '库存变动记录'
        verbose_name_plural = '库存变动记录'
        ordering = ['-created_at']
    
    def __str__(self):
        unit_name = self.unit.name if self.unit_id else ''
        return f"{self.get_transaction_type_display()} - {self.inventory} - {self.quantity}{unit_name}"


class InventoryAdjustmentRequest(models.Model):
    """库存调整申请（数量/单价两种类型）
    
    变更说明：
    - 删除 'unit' 调整类型（显示单位可直接改，不需走审批；基础单位不允许改）
    - 删除 new_unit / conversion_factor 字段
    """
    ADJUSTMENT_TYPE_CHOICES = [
        ('quantity', '数量调整'),
        ('price', '单价调整'),
        ('both', '数量+单价调整'),
    ]
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('rejected', '已拒绝'),
        ('completed', '已完成'),
    ]
    
    request_no = models.CharField(max_length=50, unique=True, verbose_name='申请单号')
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, verbose_name='库存')
    adjustment_type = models.CharField(
        max_length=20,
        choices=ADJUSTMENT_TYPE_CHOICES,
        default='quantity',
        verbose_name='调整类型'
    )
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='当前数量（基础单位）')
    adjust_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='调整数量（基础单位）')
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='调整后数量（基础单位）')
    current_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='当前单价（基础单位）')
    adjust_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整单价（基础单位）')
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='调整后单价（基础单位）')
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
