from django.db import models
from django.core.validators import MinValueValidator


class Customer(models.Model):
    """客户中心"""
    CREDIT_LEVEL_CHOICES = [
        ('A', 'A级（优秀）'),
        ('B', 'B级（良好）'),
        ('C', 'C级（一般）'),
        ('D', 'D级（较差）'),
    ]
    
    name = models.CharField(max_length=200, unique=True, verbose_name='客户名称')
    contact_person = models.CharField(max_length=100, verbose_name='联系人')
    phone = models.CharField(max_length=20, verbose_name='联系电话')
    address = models.TextField(verbose_name='地址')
    credit_level = models.CharField(max_length=1, choices=CREDIT_LEVEL_CHOICES, default='C', verbose_name='信用等级')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_customers', verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '客户'
        verbose_name_plural = '客户'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


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


class Product(models.Model):
    """成品信息"""
    sku = models.CharField(max_length=50, unique=True, verbose_name='SKU编码')
    name = models.CharField(max_length=200, verbose_name='产品名称')
    specification = models.TextField(blank=True, verbose_name='规格说明')
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
    ]
    
    inventory_type = models.CharField(max_length=20, choices=INVENTORY_TYPE_CHOICES, verbose_name='库存类型')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='成品')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory', verbose_name='原料')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '库存'
        verbose_name_plural = '库存'
        unique_together = [
            ['inventory_type', 'product'],
            ['inventory_type', 'material'],
        ]
    
    def __str__(self):
        if self.inventory_type == 'product' and self.product:
            return f"{self.product.name} - {self.quantity}{self.unit}"
        elif self.inventory_type == 'material' and self.material:
            return f"{self.material.name} - {self.quantity}{self.unit}"
        return f"库存 - {self.quantity}{self.unit}"
    
    def get_item(self):
        """获取关联的产品或原料对象"""
        return self.product if self.inventory_type == 'product' else self.material
    
    def check_safety_stock(self):
        """检查是否低于安全库存"""
        item = self.get_item()
        if item and hasattr(item, 'safety_stock'):
            return self.quantity < item.safety_stock
        return False


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
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='数量')
    unit = models.CharField(max_length=20, verbose_name='单位')
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
