# 产品主数据（字典/标准源），独立于库存表
from django.db import models
from django.core.validators import MinValueValidator


class Product(models.Model):
    """物料主数据：定义「这个东西是什么」（编码、名称、单位、类型等）；库存管理只引用本表。"""
    CATEGORY_CHOICES = [
        ('finished', '成品'),
        ('semi', '半成品'),
        ('raw', '原料'),
        ('auxiliary', '辅料'),
        ('tool', '工具'),
        ('office', '办公物品'),
        ('other', '其它'),
    ]

    sku = models.CharField(max_length=50, unique=True, verbose_name='产品编码/SKU')
    name = models.CharField(max_length=200, verbose_name='产品名称')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='产品分类')
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='单价（基础单位）',
    )
    base_unit = models.ForeignKey(
        'inventory.Unit',
        on_delete=models.PROTECT,
        related_name='product_master_base',
        verbose_name='基础单位',
    )
    display_unit = models.ForeignKey(
        'inventory.Unit',
        on_delete=models.PROTECT,
        related_name='product_master_display',
        verbose_name='显示单位',
    )
    specification = models.TextField(blank=True, default='', verbose_name='规格说明')
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='售价（基础单位，仅成品）',
    )
    safety_stock = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name='安全库存（基础单位）',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'product_product'
        verbose_name = '产品主数据'
        verbose_name_plural = '产品主数据'
        ordering = ['category', 'sku']

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def is_finished(self):
        return self.category == 'finished'

    def is_raw(self):
        return self.category == 'raw'

    def is_semi(self):
        return self.category == 'semi'

    def is_auxiliary(self):
        return self.category == 'auxiliary'

    def is_office(self):
        return self.category == 'office'

    def is_tool(self):
        return self.category == 'tool'

    def is_other(self):
        return self.category == 'other'

    def is_non_finished(self):
        """是否非成品（可作为 BOM 组件）"""
        return self.category in ('raw', 'semi', 'auxiliary', 'tool', 'office', 'other')

    def to_display(self, base_quantity, unit=None):
        """将基础单位数量转为显示单位（委托库存单位换算服务；unit 暂未使用，以 display_unit 为准）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.to_display(self, base_quantity)

    def from_display(self, display_quantity, unit=None):
        """将显示单位数量转为基础单位（委托库存单位换算服务；unit 暂未使用，以 display_unit 为准）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.from_display(self, display_quantity)

    def get_display_unit_price(self):
        """显示单位下的单价。当显示单位≠基础单位时，单价按换算系数放大：显示单位单价 = 基础单价 × factor（1 显示单位 = factor × 基础单位）。"""
        from decimal import Decimal
        base_price = Decimal(str(self.unit_price or 0))
        if self.display_unit_id and self.base_unit_id and self.display_unit_id != self.base_unit_id:
            try:
                from inventory.services.unit_conversion import UnitConversionService
                factor = UnitConversionService.get_factor(self, self.display_unit)
                return float(base_price * factor)
            except (ValueError, Exception):
                pass
        return float(base_price)


class BOM(models.Model):
    """BOM 配方：仅成品可配置，关联产品主数据"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='bom_items',
        limit_choices_to={'category': 'finished'},
        verbose_name='成品',
    )
    component = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='bom_as_component',
        limit_choices_to=models.Q(category='raw') | models.Q(category='semi') | models.Q(category='auxiliary') | models.Q(category='tool') | models.Q(category='office') | models.Q(category='other'),
        verbose_name='原料/半成品/辅料/工具/办公物品/其它',
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=4,
        validators=[MinValueValidator(0.0001)],
        verbose_name='用量',
    )
    unit = models.ForeignKey(
        'inventory.Unit',
        on_delete=models.PROTECT,
        related_name='product_bom_units',
        verbose_name='用量单位',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'product_bom'
        verbose_name = 'BOM 配方'
        verbose_name_plural = 'BOM 配方'
        unique_together = [['product', 'component']]
        ordering = ['product', 'component']

    def __str__(self):
        return f"{self.product.name} -> {self.component.name} ({self.quantity} {self.unit.code})"
