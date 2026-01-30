# 物料单位灵活管理 - 详细架构设计与执行流程

## 目录
1. [需求分析](#需求分析)
2. [架构设计](#架构设计)
3. [数据模型设计](#数据模型设计)
4. [业务流程设计](#业务流程设计)
5. [实施步骤](#实施步骤)
6. [数据迁移方案](#数据迁移方案)
7. [代码结构建议](#代码结构建议)
8. [测试验证方案](#测试验证方案)
9. [风险控制](#风险控制)

---

## 一、需求分析

### 1.1 核心需求
- **需求1**：不同物料支持不同的包装单位（如水泥1袋=100kg，石灰石粉1袋=50kg）
- **需求2**：物料单位可以灵活更改，相关数据需要正确处理
- **需求3**：历史数据需要保持完整性，不能丢失

### 1.2 业务场景
1. **采购场景**：采购时可能按"袋"、"箱"、"桶"等包装单位采购
2. **库存场景**：库存显示需要支持多单位切换（如1000kg或10袋）
3. **生产场景**：BOM配方可能需要用不同单位（基础单位或包装单位）
4. **销售场景**：销售时可能按包装单位销售

### 1.3 技术挑战
- 单位转换的准确性（数量、单价）
- 历史数据的一致性
- 业务进行中的单位变更处理
- 多单位体系的统一管理

---

## 二、架构设计

### 2.1 三层单位体系

```
┌─────────────────────────────────────────────────────────┐
│                   显示层（Display Layer）                │
│  用户界面显示的单位，可从基础单位或包装单位中选择          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│             包装单位层（Packaging Layer）                  │
│  物料特定的包装单位（如：水泥的"袋"=100kg）                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│             基础单位层（Base Unit Layer）                 │
│  系统内部计算和存储的基础单位（kg、g、m、件等）             │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则
1. **基础单位原则**：所有计算和存储都基于基础单位
2. **包装单位原则**：包装单位是基础单位的别名，有固定换算关系
3. **历史不变原则**：历史记录保持原单位，不转换
4. **当前转换原则**：当前状态数据（库存、单价）随单位变更转换

---

## 三、数据模型设计

### 3.1 新增模型

#### 3.1.1 Unit（基础单位字典表）

```python
class Unit(models.Model):
    """基础单位字典表"""
    UNIT_CATEGORY_CHOICES = [
        ('weight', '重量'),
        ('length', '长度'),
        ('volume', '体积'),
        ('quantity', '数量'),
        ('packaging', '包装'),
    ]
    
    code = models.CharField(max_length=20, unique=True, verbose_name='单位代码')
    name = models.CharField(max_length=50, verbose_name='单位名称')
    category = models.CharField(max_length=20, choices=UNIT_CATEGORY_CHOICES, verbose_name='单位类别')
    is_base = models.BooleanField(default=False, verbose_name='是否为基础计量单位')
    display_order = models.IntegerField(default=0, verbose_name='显示顺序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '基础单位'
        verbose_name_plural = '基础单位'
        ordering = ['category', 'display_order', 'code']
    
    def __str__(self):
        return f"{self.name}({self.code})"
```

**初始化数据建议：**
- 重量：kg（基础）、g、t
- 长度：m（基础）、cm、mm、km
- 体积：L（基础）、mL、m³
- 数量：件（基础）、个、只
- 包装：袋、箱、桶、包

#### 3.1.2 MaterialPackagingUnit（物料包装单位）

```python
class MaterialPackagingUnit(models.Model):
    """物料特定的包装单位定义"""
    material = models.ForeignKey(
        Material, 
        on_delete=models.CASCADE, 
        related_name='packaging_units',
        verbose_name='物料'
    )
    packaging_unit_name = models.CharField(max_length=20, verbose_name='包装单位名称')
    base_unit = models.ForeignKey(
        Unit, 
        on_delete=models.PROTECT,
        related_name='material_packaging_units',
        verbose_name='基础单位'
    )
    conversion_factor = models.DecimalField(
        max_digits=10, 
        decimal_places=4,
        validators=[MinValueValidator(0.0001)],
        verbose_name='转换系数'
    )
    # 转换说明：1个包装单位 = conversion_factor 个基础单位
    # 例如：1袋 = 100kg，则 conversion_factor = 100
    
    is_default = models.BooleanField(default=False, verbose_name='是否默认包装单位')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    display_order = models.IntegerField(default=0, verbose_name='显示顺序')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '物料包装单位'
        verbose_name_plural = '物料包装单位'
        unique_together = ['material', 'packaging_unit_name']
        ordering = ['material', 'display_order', 'packaging_unit_name']
    
    def __str__(self):
        return f"{self.material.name} - {self.packaging_unit_name} ({self.conversion_factor}{self.base_unit.code})"
    
    def convert_to_base(self, packaging_quantity):
        """将包装单位数量转换为基础单位数量"""
        from decimal import Decimal
        return Decimal(str(packaging_quantity)) * self.conversion_factor
    
    def convert_from_base(self, base_quantity):
        """将基础单位数量转换为包装单位数量"""
        from decimal import Decimal
        return Decimal(str(base_quantity)) / self.conversion_factor
```

**示例数据：**
- 水泥：包装单位"袋"，基础单位"kg"，转换系数100（1袋=100kg）
- 石灰石粉：包装单位"袋"，基础单位"kg"，转换系数50（1袋=50kg）
- 钢筋：包装单位"捆"，基础单位"kg"，转换系数500（1捆=500kg）

#### 3.1.3 MaterialUnitChangeHistory（物料单位变更历史）

```python
class MaterialUnitChangeHistory(models.Model):
    """物料单位变更历史记录"""
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='unit_change_history',
        verbose_name='物料'
    )
    
    # 变更前信息
    old_unit = models.CharField(max_length=20, verbose_name='旧单位')
    old_unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='旧单价')
    old_safety_stock = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='旧安全库存')
    
    # 变更后信息
    new_unit = models.CharField(max_length=20, verbose_name='新单位')
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='新单价')
    new_safety_stock = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='新安全库存')
    
    # 转换信息
    conversion_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        verbose_name='转换系数'
    )
    # 说明：新单位数量 = 旧单位数量 × conversion_factor
    #      新单价 = 旧单价 ÷ conversion_factor
    
    # 变更时的库存快照
    old_inventory_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='变更前库存数量')
    new_inventory_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='变更后库存数量')
    
    # 变更信息
    changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='material_unit_changes',
        verbose_name='变更人'
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='变更时间')
    reason = models.TextField(verbose_name='变更原因')
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('auto', '自动通过'),
            ('approved', '已审批'),
            ('rejected', '已拒绝'),
        ],
        default='auto',
        verbose_name='审批状态'
    )
    approved_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_unit_changes',
        verbose_name='审批人'
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    
    class Meta:
        verbose_name = '物料单位变更历史'
        verbose_name_plural = '物料单位变更历史'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.material.name} - {self.old_unit} → {self.new_unit} ({self.changed_at})"
```

#### 3.1.4 ProductPackagingUnit（成品包装单位，可选）

```python
class ProductPackagingUnit(models.Model):
    """成品特定的包装单位定义（如果需要）"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='packaging_units',
        verbose_name='成品'
    )
    packaging_unit_name = models.CharField(max_length=20, verbose_name='包装单位名称')
    base_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, verbose_name='基础单位')
    conversion_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(0.0001)],
        verbose_name='转换系数'
    )
    is_default = models.BooleanField(default=False, verbose_name='是否默认')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '成品包装单位'
        verbose_name_plural = '成品包装单位'
        unique_together = ['product', 'packaging_unit_name']
```

### 3.2 修改现有模型

#### 3.2.1 Material 模型修改

```python
class Material(models.Model):
    # ... 现有字段保持不变 ...
    
    # 修改单位字段
    unit = models.CharField(max_length=20, default='kg', verbose_name='单位（显示单位）')
    
    # 新增字段
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='基础单位'
    )
    # 如果base_unit为空，则unit就是基础单位
    
    # 新增方法
    def get_base_unit(self):
        """获取基础单位"""
        if self.base_unit:
            return self.base_unit.code
        return self.unit
    
    def get_packaging_units(self):
        """获取所有启用的包装单位"""
        return self.packaging_units.filter(is_active=True)
    
    def get_default_packaging_unit(self):
        """获取默认包装单位"""
        packaging_unit = self.packaging_units.filter(is_active=True, is_default=True).first()
        if packaging_unit:
            return packaging_unit
        return None
    
    def convert_quantity(self, quantity, from_unit, to_unit):
        """转换数量（从from_unit到to_unit）"""
        # 实现转换逻辑
        pass
```

#### 3.2.2 Product 模型修改

```python
class Product(models.Model):
    # ... 现有字段保持不变 ...
    
    # 新增字段（可选）
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='基础单位'
    )
```

#### 3.2.3 Inventory 模型修改

```python
class Inventory(models.Model):
    # ... 现有字段保持不变 ...
    
    # unit字段保持不变，但需要与material/product的base_unit保持一致
    
    def sync_unit_from_item(self):
        """从关联的物料/产品同步单位"""
        if self.inventory_type == 'material' and self.material:
            self.unit = self.material.get_base_unit()
            self.save(update_fields=['unit'])
        elif self.inventory_type == 'product' and self.product:
            self.unit = self.product.get_base_unit() if hasattr(self.product, 'get_base_unit') else self.product.unit
            self.save(update_fields=['unit'])
```

---

## 四、业务流程设计

### 4.1 单位变更流程

```
┌─────────────────┐
│  提交变更申请    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  系统前置检查    │
│  - 未完成订单    │
│  - 进行中生产    │
│  - 未完成采购    │
│  - BOM使用情况   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
  有冲突    无冲突
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│提示用户│ │继续执行   │
│选择处理│ │          │
└────────┘ └────┬──────┘
                │
                ▼
        ┌───────────────┐
        │  是否需要审批  │
        └───────┬───────┘
                │
        ┌───────┴───────┐
        │                │
      需要             不需要
        │                │
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│  提交审批     │  │  直接执行转换 │
└──────┬───────┘  └──────┬───────┘
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│  审批通过     │  │  执行数据转换 │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                │
                ▼
        ┌───────────────┐
        │  记录变更历史   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  通知相关人员   │
        │  - 检查BOM     │
        │  - 更新配方     │
        └────────────────┘
```

### 4.2 单位变更前置检查详细逻辑

#### 检查项1：未完成的销售订单
```python
def check_pending_sales_orders(material):
    """检查是否有未完成的销售订单使用该物料"""
    # 注意：这里检查的是成品，不是物料
    # 如果物料单位变更，需要检查使用该物料生产的成品是否有未完成订单
    pass
```

#### 检查项2：进行中的生产任务
```python
def check_active_production_tasks(material):
    """检查是否有进行中的生产任务使用该物料"""
    from production.models import ProductionTask, MaterialRequisitionItem
    
    # 检查是否有使用该物料的领料单未完成
    active_requisitions = MaterialRequisitionItem.objects.filter(
        material=material,
        requisition__status__in=['pending', 'approved', 'issued']
    ).exists()
    
    return active_requisitions
```

#### 检查项3：未完成的采购任务
```python
def check_pending_purchase_tasks(material):
    """检查是否有未完成的采购任务"""
    from purchase.models import PurchaseTask, PurchaseTaskItem
    
    pending_items = PurchaseTaskItem.objects.filter(
        material=material,
        task__status__in=['pending', 'approved', 'purchasing']
    ).exists()
    
    return pending_items
```

#### 检查项4：BOM配方使用情况
```python
def check_bom_usage(material):
    """检查BOM配方使用情况"""
    from inventory.models import BOM
    
    bom_items = BOM.objects.filter(material=material)
    return {
        'count': bom_items.count(),
        'products': [bom.product for bom in bom_items],
        'bom_items': bom_items
    }
```

### 4.3 数据转换逻辑

#### 转换服务类设计

```python
class UnitConversionService:
    """单位转换服务"""
    
    @staticmethod
    def convert_quantity(quantity, from_unit, to_unit, material=None):
        """
        转换数量
        
        参数:
            quantity: 数量（Decimal）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象（用于获取包装单位转换系数）
        
        返回:
            转换后的数量（Decimal）
        """
        from decimal import Decimal
        
        # 如果单位相同，直接返回
        if from_unit == to_unit:
            return Decimal(str(quantity))
        
        # 如果物料有包装单位定义
        if material:
            # 检查是否是包装单位转换
            packaging_unit = material.packaging_units.filter(
                packaging_unit_name=from_unit,
                is_active=True
            ).first()
            
            if packaging_unit:
                # 从包装单位转换为基础单位
                base_quantity = packaging_unit.convert_to_base(quantity)
                
                # 如果目标单位也是包装单位
                target_packaging = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
                
                if target_packaging:
                    # 从基础单位转换为目标包装单位
                    return target_packaging.convert_from_base(base_quantity)
                else:
                    # 目标单位是基础单位
                    return base_quantity
        
        # 通用单位转换（如果未来需要）
        # 这里可以扩展通用单位转换表
        
        raise ValueError(f"无法转换：{from_unit} → {to_unit}")
    
    @staticmethod
    def convert_price(price, from_unit, to_unit, material=None):
        """
        转换单价
        
        参数:
            price: 单价（Decimal）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象
        
        返回:
            转换后的单价（Decimal）
        """
        from decimal import Decimal
        
        if from_unit == to_unit:
            return Decimal(str(price))
        
        # 获取转换系数
        conversion_factor = UnitConversionService.get_conversion_factor(
            from_unit, to_unit, material
        )
        
        # 单价转换：新单价 = 旧单价 ÷ 转换系数
        # 例如：0.5元/kg → 50元/袋（1袋=100kg）
        return Decimal(str(price)) / conversion_factor
    
    @staticmethod
    def get_conversion_factor(from_unit, to_unit, material=None):
        """获取转换系数"""
        if from_unit == to_unit:
            return Decimal('1')
        
        if material:
            # 从包装单位到基础单位
            from_packaging = material.packaging_units.filter(
                packaging_unit_name=from_unit,
                is_active=True
            ).first()
            
            if from_packaging:
                base_factor = from_packaging.conversion_factor
                
                # 目标单位是基础单位
                if to_unit == from_packaging.base_unit.code:
                    return base_factor
                
                # 目标单位也是包装单位
                to_packaging = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
                
                if to_packaging:
                    # 从包装单位A到包装单位B的转换系数
                    # 例如：从"袋"到"箱"，需要知道1箱=多少袋
                    # 这里假设都是基于同一个基础单位
                    if from_packaging.base_unit == to_packaging.base_unit:
                        return base_factor / to_packaging.conversion_factor
        
        raise ValueError(f"无法获取转换系数：{from_unit} → {to_unit}")
```

### 4.4 单位变更执行流程

```python
class MaterialUnitChangeService:
    """物料单位变更服务"""
    
    @staticmethod
    def change_unit(material, new_unit, conversion_factor, reason, changed_by, 
                   auto_approve=False, approved_by=None):
        """
        执行单位变更
        
        参数:
            material: 物料对象
            new_unit: 新单位
            conversion_factor: 转换系数（新单位数量 = 旧单位数量 × 系数）
            reason: 变更原因
            changed_by: 变更人
            auto_approve: 是否自动审批
            approved_by: 审批人
        """
        from decimal import Decimal
        from django.db import transaction
        
        old_unit = material.unit
        old_unit_price = material.unit_price
        old_safety_stock = material.safety_stock
        
        # 获取当前库存
        try:
            inventory = Inventory.objects.get(
                inventory_type='material',
                material=material
            )
            old_inventory_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            old_inventory_quantity = Decimal('0')
        
        with transaction.atomic():
            # 1. 转换物料基础数据
            # 单价转换：新单价 = 旧单价 ÷ 转换系数
            new_unit_price = old_unit_price / Decimal(str(conversion_factor))
            # 安全库存转换：新安全库存 = 旧安全库存 × 转换系数
            new_safety_stock = old_safety_stock * Decimal(str(conversion_factor))
            
            # 2. 更新物料信息
            material.unit = new_unit
            material.unit_price = new_unit_price
            material.safety_stock = new_safety_stock
            material.save()
            
            # 3. 转换库存数据
            if inventory:
                new_inventory_quantity = old_inventory_quantity * Decimal(str(conversion_factor))
                inventory.quantity = new_inventory_quantity
                inventory.unit = new_unit
                inventory.save()
            
            # 4. 转换批次数据
            batches = Batch.objects.filter(inventory=inventory)
            for batch in batches:
                new_batch_quantity = batch.quantity * Decimal(str(conversion_factor))
                if batch.unit_price:
                    new_batch_unit_price = batch.unit_price / Decimal(str(conversion_factor))
                    batch.unit_price = new_batch_unit_price
                batch.quantity = new_batch_quantity
                batch.save()
            
            # 5. 记录变更历史
            change_history = MaterialUnitChangeHistory.objects.create(
                material=material,
                old_unit=old_unit,
                old_unit_price=old_unit_price,
                old_safety_stock=old_safety_stock,
                new_unit=new_unit,
                new_unit_price=new_unit_price,
                new_safety_stock=new_safety_stock,
                conversion_factor=conversion_factor,
                old_inventory_quantity=old_inventory_quantity,
                new_inventory_quantity=new_inventory_quantity if inventory else Decimal('0'),
                changed_by=changed_by,
                reason=reason,
                approval_status='auto' if auto_approve else 'approved',
                approved_by=approved_by if not auto_approve else changed_by,
                approved_at=timezone.now() if auto_approve else None
            )
            
            return change_history
    
    @staticmethod
    def check_can_change_unit(material):
        """检查是否可以变更单位"""
        issues = []
        
        # 检查1：进行中的生产任务
        from production.models import MaterialRequisitionItem
        active_requisitions = MaterialRequisitionItem.objects.filter(
            material=material,
            requisition__status__in=['pending', 'approved', 'issued']
        ).exists()
        if active_requisitions:
            issues.append({
                'type': 'active_production',
                'message': '存在进行中的生产任务使用该物料',
                'severity': 'warning'
            })
        
        # 检查2：未完成的采购任务
        from purchase.models import PurchaseTaskItem
        pending_purchases = PurchaseTaskItem.objects.filter(
            material=material,
            task__status__in=['pending', 'approved', 'purchasing']
        ).exists()
        if pending_purchases:
            issues.append({
                'type': 'pending_purchase',
                'message': '存在未完成的采购任务',
                'severity': 'warning'
            })
        
        # 检查3：BOM使用情况
        from inventory.models import BOM
        bom_count = BOM.objects.filter(material=material).count()
        if bom_count > 0:
            issues.append({
                'type': 'bom_usage',
                'message': f'该物料被{bom_count}个BOM配方使用，需要检查配方单位',
                'severity': 'info'
            })
        
        return {
            'can_change': len([i for i in issues if i['severity'] == 'error']) == 0,
            'issues': issues
        }
```

---

## 五、实施步骤

### 阶段一：数据模型准备（1-2天）

#### 步骤1.1：创建Unit模型
1. 在 `inventory/models.py` 中添加 `Unit` 模型
2. 创建迁移文件：`python manage.py makemigrations inventory`
3. 执行迁移：`python manage.py migrate`
4. 创建初始化脚本，导入基础单位数据

#### 步骤1.2：创建MaterialPackagingUnit模型
1. 在 `inventory/models.py` 中添加 `MaterialPackagingUnit` 模型
2. 创建迁移文件并执行

#### 步骤1.3：创建MaterialUnitChangeHistory模型
1. 在 `inventory/models.py` 中添加 `MaterialUnitChangeHistory` 模型
2. 创建迁移文件并执行

#### 步骤1.4：修改Material模型
1. 添加 `base_unit` 字段（允许为空，向后兼容）
2. 添加相关方法（`get_base_unit`, `get_packaging_units` 等）
3. 创建迁移文件并执行

### 阶段二：数据迁移（2-3天）

#### 步骤2.1：初始化基础单位数据
创建管理命令 `init_units.py`：
```python
# inventory/management/commands/init_units.py
from django.core.management.base import BaseCommand
from inventory.models import Unit

class Command(BaseCommand):
    def handle(self, *args, **options):
        units_data = [
            # 重量单位
            {'code': 'kg', 'name': '千克', 'category': 'weight', 'is_base': True},
            {'code': 'g', 'name': '克', 'category': 'weight', 'is_base': False},
            {'code': 't', 'name': '吨', 'category': 'weight', 'is_base': False},
            # 长度单位
            {'code': 'm', 'name': '米', 'category': 'length', 'is_base': True},
            {'code': 'cm', 'name': '厘米', 'category': 'length', 'is_base': False},
            {'code': 'mm', 'name': '毫米', 'category': 'length', 'is_base': False},
            # 数量单位
            {'code': '件', 'name': '件', 'category': 'quantity', 'is_base': True},
            {'code': '个', 'name': '个', 'category': 'quantity', 'is_base': False},
            {'code': '只', 'name': '只', 'category': 'quantity', 'is_base': False},
            # 包装单位（作为通用包装单位）
            {'code': '袋', 'name': '袋', 'category': 'packaging', 'is_base': False},
            {'code': '箱', 'name': '箱', 'category': 'packaging', 'is_base': False},
            {'code': '桶', 'name': '桶', 'category': 'packaging', 'is_base': False},
        ]
        
        for unit_data in units_data:
            Unit.objects.get_or_create(
                code=unit_data['code'],
                defaults=unit_data
            )
        
        self.stdout.write(self.style.SUCCESS('基础单位初始化完成'))
```

执行：`python manage.py init_units`

#### 步骤2.2：迁移现有物料数据
创建管理命令 `migrate_material_units.py`：
```python
# inventory/management/commands/migrate_material_units.py
from django.core.management.base import BaseCommand
from inventory.models import Material, Unit

class Command(BaseCommand):
    def handle(self, *args, **options):
        # 为现有物料设置基础单位
        kg_unit = Unit.objects.get(code='kg')
        piece_unit = Unit.objects.get(code='件')
        
        materials = Material.objects.all()
        for material in materials:
            # 根据现有unit字段推断基础单位
            if material.unit in ['kg', 'g', 't']:
                material.base_unit = kg_unit
            elif material.unit in ['件', '个', '只']:
                material.base_unit = piece_unit
            # 如果无法匹配，base_unit保持为None（向后兼容）
            
            material.save(update_fields=['base_unit'])
        
        self.stdout.write(self.style.SUCCESS('物料单位迁移完成'))
```

### 阶段三：服务层开发（3-4天）

#### 步骤3.1：创建单位转换服务
创建文件 `inventory/services/unit_conversion.py`：
- 实现 `UnitConversionService` 类
- 实现数量转换、单价转换方法

#### 步骤3.2：创建单位变更服务
创建文件 `inventory/services/unit_change.py`：
- 实现 `MaterialUnitChangeService` 类
- 实现前置检查、数据转换、历史记录功能

#### 步骤3.3：创建工具函数
创建文件 `inventory/utils/unit_utils.py`：
- 单位显示格式化
- 多单位选择器数据准备
- 单位验证函数

### 阶段四：视图层开发（4-5天）

#### 步骤4.1：物料包装单位管理界面
- 列表页面：显示物料的包装单位
- 添加页面：添加新的包装单位
- 编辑页面：修改包装单位
- 删除功能：软删除（设置is_active=False）

#### 步骤4.2：单位变更申请界面
- 变更申请表单
- 前置检查结果展示
- 变更预览（显示转换前后的数据对比）
- 审批流程（如果需要）

#### 步骤4.3：单位变更历史查看
- 历史记录列表
- 历史记录详情
- 支持回滚功能（可选）

### 阶段五：业务集成（5-7天）

#### 步骤5.1：采购模块集成
- 采购入库支持包装单位输入
- 自动转换为基础单位存储
- 显示时支持多单位切换

#### 步骤5.2：库存模块集成
- 库存列表支持单位切换显示
- 库存详情显示多单位
- 批次信息支持多单位显示

#### 步骤5.3：BOM模块集成
- BOM配方支持包装单位输入
- 自动转换为基础单位计算
- BOM检查工具（单位变更后检查）

#### 步骤5.4：生产模块集成
- 领料单支持包装单位
- 生产计算使用基础单位

### 阶段六：测试验证（3-4天）

#### 步骤6.1：单元测试
- 单位转换服务测试
- 单位变更服务测试
- 数据转换准确性测试

#### 步骤6.2：集成测试
- 完整单位变更流程测试
- 业务场景测试（采购、生产、销售）

#### 步骤6.3：数据一致性测试
- 变更前后数据对比
- 历史数据完整性检查

---

## 六、数据迁移方案

### 6.1 迁移策略

#### 策略A：渐进式迁移（推荐）
1. **阶段1**：添加新字段（base_unit），允许为空
2. **阶段2**：逐步为物料设置base_unit
3. **阶段3**：添加包装单位定义
4. **阶段4**：启用新功能

**优点**：不影响现有功能，风险低
**缺点**：迁移周期较长

#### 策略B：一次性迁移
1. 一次性完成所有数据迁移
2. 立即启用新功能

**优点**：迁移速度快
**缺点**：风险较高，需要充分测试

### 6.2 数据迁移脚本示例

```python
# inventory/management/commands/migrate_to_new_unit_system.py
from django.core.management.base import BaseCommand
from django.db import transaction
from inventory.models import Material, Unit, MaterialPackagingUnit
from decimal import Decimal

class Command(BaseCommand):
    help = '迁移到新单位体系'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅预览，不实际执行',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('=== 预览模式 ==='))
        
        # 1. 初始化基础单位
        self.init_base_units(dry_run)
        
        # 2. 迁移物料基础单位
        self.migrate_material_base_units(dry_run)
        
        # 3. 创建包装单位（示例：水泥）
        self.create_packaging_units(dry_run)
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS('迁移完成！'))
        else:
            self.stdout.write(self.style.WARNING('预览完成，使用 --no-dry-run 执行实际迁移'))
    
    def init_base_units(self, dry_run):
        """初始化基础单位"""
        # ... 实现代码 ...
        pass
    
    def migrate_material_base_units(self, dry_run):
        """迁移物料基础单位"""
        # ... 实现代码 ...
        pass
    
    def create_packaging_units(self, dry_run):
        """创建包装单位"""
        # 示例：为水泥创建"袋"包装单位
        cement = Material.objects.filter(name__icontains='水泥').first()
        if cement:
            kg_unit = Unit.objects.get(code='kg')
            
            packaging_unit_data = {
                'material': cement,
                'packaging_unit_name': '袋',
                'base_unit': kg_unit,
                'conversion_factor': Decimal('100'),  # 1袋=100kg
                'is_default': True,
                'is_active': True
            }
            
            if not dry_run:
                MaterialPackagingUnit.objects.get_or_create(
                    material=cement,
                    packaging_unit_name='袋',
                    defaults=packaging_unit_data
                )
                self.stdout.write(f'  创建包装单位：{cement.name} - 袋')
            else:
                self.stdout.write(f'  [预览] 将创建：{cement.name} - 袋')
```

### 6.3 回滚方案

创建回滚脚本，支持：
1. 恢复物料单位字段
2. 恢复库存数量（基于变更历史）
3. 恢复单价和安全库存

---

## 七、代码结构建议

### 7.1 目录结构

```
factory_system/
├── inventory/
│   ├── models.py                    # 数据模型（包含新增的Unit等模型）
│   ├── services/                    # 服务层（新建）
│   │   ├── __init__.py
│   │   ├── unit_conversion.py      # 单位转换服务
│   │   └── unit_change.py          # 单位变更服务
│   ├── utils/                       # 工具函数（新建）
│   │   ├── __init__.py
│   │   └── unit_utils.py           # 单位相关工具函数
│   ├── views/                       # 视图（新建或修改）
│   │   ├── unit_management.py      # 单位管理视图
│   │   └── unit_change.py          # 单位变更视图
│   ├── forms.py                     # 表单（修改）
│   ├── urls.py                      # URL配置（修改）
│   └── templates/                   # 模板（新建或修改）
│       ├── inventory/
│       │   ├── packaging_unit_list.html
│       │   ├── packaging_unit_form.html
│       │   ├── unit_change_form.html
│       │   ├── unit_change_history.html
│       │   └── unit_change_detail.html
```

### 7.2 API设计建议

#### 7.2.1 单位管理API

```python
# inventory/views/unit_management.py

@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_list(request, material_id):
    """物料包装单位列表"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_units = material.packaging_units.filter(is_active=True)
    return render(request, 'inventory/packaging_unit_list.html', {
        'material': material,
        'packaging_units': packaging_units
    })

@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_create(request, material_id):
    """创建包装单位"""
    material = get_object_or_404(Material, pk=material_id)
    # ... 实现代码 ...
    pass

@login_required
@role_required('warehouse', 'ceo')
def unit_change_request(request, material_id):
    """单位变更申请"""
    material = get_object_or_404(Material, pk=material_id)
    
    if request.method == 'POST':
        # 处理变更申请
        new_unit = request.POST.get('new_unit')
        conversion_factor = Decimal(request.POST.get('conversion_factor'))
        reason = request.POST.get('reason')
        
        # 前置检查
        check_result = MaterialUnitChangeService.check_can_change_unit(material)
        
        if not check_result['can_change']:
            messages.error(request, '无法变更单位，存在业务冲突')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        # 执行变更
        change_history = MaterialUnitChangeService.change_unit(
            material=material,
            new_unit=new_unit,
            conversion_factor=conversion_factor,
            reason=reason,
            changed_by=request.user,
            auto_approve=True  # 根据业务规则决定
        )
        
        messages.success(request, '单位变更成功')
        return redirect('inventory:unit_change_history', material_id=material_id)
    
    # GET请求：显示变更表单
    return render(request, 'inventory/unit_change_form.html', {
        'material': material,
        'check_result': MaterialUnitChangeService.check_can_change_unit(material)
    })
```

#### 7.2.2 单位转换API

```python
# inventory/views/unit_conversion.py

@login_required
def convert_quantity_api(request):
    """数量转换API（AJAX）"""
    if request.method == 'POST':
        material_id = request.POST.get('material_id')
        quantity = Decimal(request.POST.get('quantity'))
        from_unit = request.POST.get('from_unit')
        to_unit = request.POST.get('to_unit')
        
        material = Material.objects.get(pk=material_id)
        
        try:
            converted_quantity = UnitConversionService.convert_quantity(
                quantity, from_unit, to_unit, material
            )
            return JsonResponse({
                'success': True,
                'converted_quantity': str(converted_quantity)
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
```

---

## 八、测试验证方案

### 8.1 单元测试

```python
# inventory/tests/test_unit_conversion.py

from django.test import TestCase
from decimal import Decimal
from inventory.models import Material, Unit, MaterialPackagingUnit
from inventory.services.unit_conversion import UnitConversionService

class UnitConversionTestCase(TestCase):
    def setUp(self):
        # 创建测试数据
        self.kg_unit = Unit.objects.create(code='kg', name='千克', category='weight', is_base=True)
        self.cement = Material.objects.create(
            sku='CEMENT001',
            name='水泥',
            unit='kg',
            unit_price=Decimal('0.5'),
            base_unit=self.kg_unit
        )
        # 创建包装单位：1袋=100kg
        MaterialPackagingUnit.objects.create(
            material=self.cement,
            packaging_unit_name='袋',
            base_unit=self.kg_unit,
            conversion_factor=Decimal('100'),
            is_default=True
        )
    
    def test_convert_packaging_to_base(self):
        """测试包装单位转基础单位"""
        # 10袋 = 1000kg
        result = UnitConversionService.convert_quantity(
            Decimal('10'), '袋', 'kg', self.cement
        )
        self.assertEqual(result, Decimal('1000'))
    
    def test_convert_base_to_packaging(self):
        """测试基础单位转包装单位"""
        # 1000kg = 10袋
        result = UnitConversionService.convert_quantity(
            Decimal('1000'), 'kg', '袋', self.cement
        )
        self.assertEqual(result, Decimal('10'))
    
    def test_convert_price(self):
        """测试单价转换"""
        # 0.5元/kg = 50元/袋
        result = UnitConversionService.convert_price(
            Decimal('0.5'), 'kg', '袋', self.cement
        )
        self.assertEqual(result, Decimal('50'))
```

### 8.2 集成测试

```python
# inventory/tests/test_unit_change_integration.py

class UnitChangeIntegrationTestCase(TestCase):
    def test_complete_unit_change_flow(self):
        """测试完整的单位变更流程"""
        # 1. 创建物料和库存
        # 2. 执行单位变更
        # 3. 验证数据转换正确性
        # 4. 验证历史记录
        pass
```

### 8.3 数据一致性验证

创建验证脚本：
```python
# inventory/management/commands/verify_unit_consistency.py

class Command(BaseCommand):
    def handle(self, *args, **options):
        """验证单位一致性"""
        issues = []
        
        # 检查1：Inventory.unit 是否与 Material.unit 一致
        inventories = Inventory.objects.filter(inventory_type='material')
        for inv in inventories:
            if inv.material and inv.unit != inv.material.unit:
                issues.append(f"库存单位不一致：{inv.material.name} - 库存:{inv.unit}, 物料:{inv.material.unit}")
        
        # 检查2：Batch数量总和是否等于Inventory数量
        # ... 更多检查 ...
        
        if issues:
            self.stdout.write(self.style.ERROR(f'发现 {len(issues)} 个问题：'))
            for issue in issues:
                self.stdout.write(f'  - {issue}')
        else:
            self.stdout.write(self.style.SUCCESS('单位一致性检查通过'))
```

---

## 九、风险控制

### 9.1 数据备份

**迁移前必须：**
1. 完整数据库备份
2. 导出关键数据（Material, Inventory, Batch）
3. 记录当前单位使用情况

### 9.2 回滚准备

1. **数据库回滚脚本**：支持恢复到迁移前状态
2. **数据恢复脚本**：基于变更历史恢复数据
3. **验证脚本**：验证回滚后数据正确性

### 9.3 灰度发布

1. **阶段1**：选择少量物料测试
2. **阶段2**：扩展到部分物料类别
3. **阶段3**：全量发布

### 9.4 监控告警

1. **单位变更监控**：记录所有单位变更操作
2. **数据一致性监控**：定期检查数据一致性
3. **异常告警**：转换失败、数据不一致时告警

---

## 十、实施时间表

| 阶段 | 任务 | 预计时间 | 负责人 |
|------|------|----------|--------|
| 阶段一 | 数据模型准备 | 1-2天 | 后端开发 |
| 阶段二 | 数据迁移 | 2-3天 | 后端开发 |
| 阶段三 | 服务层开发 | 3-4天 | 后端开发 |
| 阶段四 | 视图层开发 | 4-5天 | 全栈开发 |
| 阶段五 | 业务集成 | 5-7天 | 全栈开发 |
| 阶段六 | 测试验证 | 3-4天 | QA + 开发 |
| **总计** | | **18-25天** | |

---

## 十一、后续优化建议

1. **通用单位转换表**：支持kg↔g、m↔cm等通用转换
2. **单位变更审批流程**：重要物料需要审批
3. **批量单位变更**：支持批量物料单位变更
4. **单位使用统计**：统计各单位的使用频率
5. **智能单位推荐**：根据历史使用推荐单位

---

## 十二、总结

本方案提供了完整的物料单位灵活管理解决方案，包括：
- ✅ 支持物料特定的包装单位（解决水泥袋、石灰石粉袋问题）
- ✅ 完整的单位变更流程和数据转换逻辑
- ✅ 历史数据保护机制
- ✅ 详细的实施步骤和测试方案
- ✅ 完善的风险控制措施

**关键成功因素：**
1. 充分的前置检查和数据验证
2. 完整的数据迁移和回滚方案
3. 全面的测试覆盖
4. 清晰的用户界面和操作流程

**建议：**
- 先在测试环境完整验证
- 选择非关键物料进行试点
- 充分培训用户使用新功能
- 建立完善的监控和告警机制
