# 成品单位管理 - 统一实现方案

## 一、成品与原料单位管理的差异分析

### 1.1 相同点

| 特性 | Material（原料） | Product（成品） | 说明 |
|------|-----------------|----------------|------|
| 基础字段 | `unit`（单位） | `unit`（单位） | ✅ 相同 |
| 价格字段 | `unit_price`（单价） | `unit_price`（基础单价） | ✅ 相同 |
| 库存字段 | `safety_stock`（安全库存） | `safety_stock`（安全库存） | ✅ 相同 |
| 包装单位需求 | 需要（如：袋、箱） | 需要（如：箱、套） | ✅ 相同 |
| 单位变更需求 | 需要 | 需要 | ✅ 相同 |
| 单位转换逻辑 | 需要 | 需要 | ✅ 相同 |

### 1.2 不同点

| 特性 | Material（原料） | Product（成品） | 影响 |
|------|-----------------|----------------|------|
| 额外价格字段 | 无 | `sale_price`（售价） | ⚠️ 单位变更时需考虑 |
| 主要使用场景 | 采购、生产领料 | 销售、生产入库 | ⚠️ 业务检查不同 |
| 包装单位类型 | 重量类（袋、桶） | 数量类（箱、套、组） | ⚠️ 转换系数通常较小 |
| 单位变更影响 | 采购任务、生产任务 | 销售订单、生产任务 | ⚠️ 前置检查不同 |
| BOM关联 | 作为BOM的原料 | 作为BOM的成品 | ⚠️ 变更检查不同 |

### 1.3 业务场景差异

#### Material（原料）单位变更影响：
- ✅ 未完成的采购任务
- ✅ 进行中的生产任务（领料单）
- ✅ BOM配方（作为原料使用）

#### Product（成品）单位变更影响：
- ✅ 未完成的销售订单
- ✅ 进行中的生产任务（成品入库）
- ✅ BOM配方（作为成品使用）

---

## 二、统一实现方案

### 2.1 方案选择：复用 + 扩展

**推荐方案**：在现有Material单位管理基础上，为Product创建对应的模型和服务，复用相同的转换逻辑。

**理由：**
1. ✅ 保持代码结构清晰，Material和Product分离
2. ✅ 复用UnitConversionService（已支持product参数）
3. ✅ 业务逻辑相似但检查项不同，需要分别处理
4. ✅ 便于维护和扩展

### 2.2 实施策略

#### 策略A：完全复用（不推荐）
- 使用GenericForeignKey创建通用包装单位模型
- **缺点**：类型检查复杂，代码可读性差

#### 策略B：对称实现（推荐）⭐
- 创建ProductPackagingUnit（对应MaterialPackagingUnit）
- 创建ProductUnitChangeHistory（对应MaterialUnitChangeHistory）
- 复用UnitConversionService
- 创建ProductUnitChangeService（参考MaterialUnitChangeService）
- **优点**：代码清晰，易于维护，类型安全

---

## 三、具体实现方案

### 3.1 数据模型设计

#### 3.1.1 Product模型扩展

```python
# inventory/models.py

class Product(models.Model):
    """成品信息"""
    # ... 现有字段保持不变 ...
    
    # 新增字段（与Material对称）
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='基础单位'
    )
    
    # 新增方法（与Material对称）
    def get_base_unit(self):
        """获取基础单位代码"""
        if self.base_unit:
            return self.base_unit.code
        return self.unit
    
    def get_packaging_units(self):
        """获取所有启用的包装单位"""
        return self.packaging_units.filter(is_active=True).order_by('display_order')
    
    def get_default_packaging_unit(self):
        """获取默认包装单位"""
        return self.packaging_units.filter(is_active=True, is_default=True).first()
    
    def convert_quantity(self, quantity, from_unit, to_unit):
        """转换数量（便捷方法）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.convert_quantity(
            quantity, from_unit, to_unit, product=self
        )
    
    def convert_price(self, price, from_unit, to_unit):
        """转换单价（便捷方法）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.convert_price(
            price, from_unit, to_unit, product=self
        )
    
    def get_available_units(self):
        """获取可用单位列表"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.get_available_units(product=self)
```

#### 3.1.2 ProductPackagingUnit模型

```python
# inventory/models.py

class ProductPackagingUnit(models.Model):
    """成品特定的包装单位定义（与MaterialPackagingUnit对称）"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='packaging_units',
        verbose_name='成品'
    )
    packaging_unit_name = models.CharField(max_length=20, verbose_name='包装单位名称')
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='product_packaging_units',
        verbose_name='基础单位'
    )
    conversion_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(0.0001)],
        verbose_name='转换系数',
        help_text='1个包装单位 = 转换系数 个基础单位。例如：1箱=12件，则系数为12'
    )
    is_default = models.BooleanField(default=False, verbose_name='是否默认包装单位')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    display_order = models.IntegerField(default=0, verbose_name='显示顺序')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '成品包装单位'
        verbose_name_plural = '成品包装单位'
        unique_together = ['product', 'packaging_unit_name']
        ordering = ['product', 'display_order', 'packaging_unit_name']
        db_table = 'inventory_product_packaging_unit'
    
    def __str__(self):
        return f"{self.product.name} - {self.packaging_unit_name} ({self.conversion_factor}{self.base_unit.code})"
    
    def convert_to_base(self, packaging_quantity):
        """将包装单位数量转换为基础单位数量"""
        from decimal import Decimal
        return Decimal(str(packaging_quantity)) * self.conversion_factor
    
    def convert_from_base(self, base_quantity):
        """将基础单位数量转换为包装单位数量"""
        from decimal import Decimal
        if self.conversion_factor == 0:
            raise ValueError("转换系数不能为0")
        return Decimal(str(base_quantity)) / self.conversion_factor
    
    def get_display_text(self):
        """获取显示文本：如"箱(12件/箱)" """
        return f"{self.packaging_unit_name}({self.conversion_factor}{self.base_unit.code}/{self.packaging_unit_name})"
```

#### 3.1.3 ProductUnitChangeHistory模型

```python
# inventory/models.py

class ProductUnitChangeHistory(models.Model):
    """成品单位变更历史记录（与MaterialUnitChangeHistory对称）"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='unit_change_history',
        verbose_name='成品'
    )
    
    # 变更前信息
    old_unit = models.CharField(max_length=20, verbose_name='旧单位')
    old_unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='旧单价')
    old_sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='旧售价')
    old_safety_stock = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='旧安全库存')
    
    # 变更后信息
    new_unit = models.CharField(max_length=20, verbose_name='新单位')
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='新单价')
    new_sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='新售价')
    new_safety_stock = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='新安全库存')
    
    # 转换信息
    conversion_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        verbose_name='转换系数'
    )
    
    # 变更时的库存快照
    old_inventory_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='变更前库存数量')
    new_inventory_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='变更后库存数量')
    
    # 变更信息
    changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='product_unit_changes',
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
        related_name='approved_product_unit_changes',
        verbose_name='审批人'
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    
    class Meta:
        verbose_name = '成品单位变更历史'
        verbose_name_plural = '成品单位变更历史'
        ordering = ['-changed_at']
        db_table = 'inventory_product_unit_change_history'
    
    def __str__(self):
        return f"{self.product.name} - {self.old_unit} → {self.new_unit} ({self.changed_at})"
```

### 3.2 服务层实现

#### 3.2.1 ProductUnitChangeService

```python
# inventory/services/product_unit_change.py

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from inventory.models import Product, Inventory, Batch, ProductUnitChangeHistory
from inventory.services.unit_conversion import UnitConversionService

class ProductUnitChangeService:
    """成品单位变更服务（与MaterialUnitChangeService对称）"""
    
    @staticmethod
    def check_can_change_unit(product):
        """检查是否可以变更单位"""
        issues = []
        
        # 检查1：未完成的销售订单
        from sales.models import SalesOrder, SalesOrderItem
        pending_orders = SalesOrderItem.objects.filter(
            product=product,
            order__status__in=['pending', 'approved', 'ceo_pending', 'ceo_approved', 'in_production', 'ready_to_ship']
        ).exists()
        if pending_orders:
            issues.append({
                'type': 'pending_sales_order',
                'message': '存在未完成的销售订单',
                'severity': 'warning'
            })
        
        # 检查2：进行中的生产任务
        from production.models import ProductionTask
        active_tasks = ProductionTask.objects.filter(
            product=product,
            status__in=['pending', 'received', 'material_preparing', 'in_production', 'qc_checking']
        ).exists()
        if active_tasks:
            issues.append({
                'type': 'active_production',
                'message': '存在进行中的生产任务',
                'severity': 'warning'
            })
        
        # 检查3：BOM使用情况（作为成品）
        from inventory.models import BOM
        bom_count = BOM.objects.filter(product=product).count()
        if bom_count > 0:
            issues.append({
                'type': 'bom_usage',
                'message': f'该成品被{bom_count}个BOM配方使用，需要检查配方单位',
                'severity': 'info'
            })
        
        return {
            'can_change': len([i for i in issues if i['severity'] == 'error']) == 0,
            'issues': issues
        }
    
    @staticmethod
    def change_unit(product, new_unit, conversion_factor, reason, changed_by, 
                   auto_approve=False, approved_by=None):
        """
        执行单位变更
        
        参数:
            product: 成品对象
            new_unit: 新单位
            conversion_factor: 转换系数（新单位数量 = 旧单位数量 × 系数）
            reason: 变更原因
            changed_by: 变更人
            auto_approve: 是否自动审批
            approved_by: 审批人
        """
        old_unit = product.unit
        old_unit_price = product.unit_price
        old_sale_price = product.sale_price
        old_safety_stock = product.safety_stock
        
        # 获取当前库存
        try:
            inventory = Inventory.objects.get(
                inventory_type='product',
                product=product
            )
            old_inventory_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            old_inventory_quantity = Decimal('0')
        
        with transaction.atomic():
            # 1. 转换成品基础数据
            # 单价转换：新单价 = 旧单价 ÷ 转换系数
            new_unit_price = old_unit_price / Decimal(str(conversion_factor))
            # 售价转换：新售价 = 旧售价 ÷ 转换系数
            new_sale_price = old_sale_price / Decimal(str(conversion_factor)) if old_sale_price else None
            # 安全库存转换：新安全库存 = 旧安全库存 × 转换系数
            new_safety_stock = old_safety_stock * Decimal(str(conversion_factor))
            
            # 2. 更新成品信息
            product.unit = new_unit
            product.unit_price = new_unit_price
            if new_sale_price:
                product.sale_price = new_sale_price
            product.safety_stock = new_safety_stock
            product.save()
            
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
            change_history = ProductUnitChangeHistory.objects.create(
                product=product,
                old_unit=old_unit,
                old_unit_price=old_unit_price,
                old_sale_price=old_sale_price,
                old_safety_stock=old_safety_stock,
                new_unit=new_unit,
                new_unit_price=new_unit_price,
                new_sale_price=new_sale_price,
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
```

### 3.3 视图层实现

#### 3.3.1 成品包装单位管理视图

```python
# inventory/views/product_unit_management.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal
from inventory.models import Product, ProductPackagingUnit, Unit
from inventory.decorators import role_required

@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_list(request, product_id):
    """成品包装单位列表"""
    product = get_object_or_404(Product, pk=product_id)
    packaging_units = product.packaging_units.filter(is_active=True).order_by('display_order')
    
    return render(request, 'inventory/product_packaging_unit_list.html', {
        'product': product,
        'packaging_units': packaging_units
    })

@login_required
@role_required('warehouse', 'ceo')
def product_packaging_unit_create(request, product_id):
    """创建成品包装单位"""
    product = get_object_or_404(Product, pk=product_id)
    
    if request.method == 'POST':
        packaging_unit_name = request.POST.get('packaging_unit_name', '').strip()
        base_unit_id = request.POST.get('base_unit')
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        # 验证（与MaterialPackagingUnit相同）
        if not packaging_unit_name:
            messages.error(request, '请输入包装单位名称')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在
        if ProductPackagingUnit.objects.filter(
            product=product,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:product_packaging_unit_create', product_id=product_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            ProductPackagingUnit.objects.filter(
                product=product,
                is_default=True
            ).update(is_default=False)
        
        # 创建
        packaging_unit = ProductPackagingUnit.objects.create(
            product=product,
            packaging_unit_name=packaging_unit_name,
            base_unit=base_unit,
            conversion_factor=conversion_factor,
            is_default=is_default,
            remark=remark
        )
        
        messages.success(request, f'包装单位"{packaging_unit_name}"创建成功')
        return redirect('inventory:product_packaging_unit_list', product_id=product_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/product_packaging_unit_form.html', {
        'product': product,
        'base_units': base_units,
        'action': 'create'
    })
```

#### 3.3.2 成品单位变更视图

```python
# inventory/views/product_unit_change.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal
from inventory.models import Product, ProductUnitChangeHistory
from inventory.services.product_unit_change import ProductUnitChangeService
from inventory.decorators import role_required

@login_required
@role_required('warehouse', 'ceo')
def product_unit_change_request(request, product_id):
    """成品单位变更申请"""
    product = get_object_or_404(Product, pk=product_id)
    
    if request.method == 'POST':
        new_unit = request.POST.get('new_unit', '').strip()
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        reason = request.POST.get('reason', '').strip()
        force_change = request.POST.get('force_change') == 'on'
        
        # 验证
        if not new_unit:
            messages.error(request, '请输入新单位')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
        
        if not reason:
            messages.error(request, '请输入变更原因')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
        
        # 前置检查
        check_result = ProductUnitChangeService.check_can_change_unit(product)
        
        if not check_result['can_change'] and not force_change:
            messages.error(request, '无法变更单位，存在业务冲突。如需强制变更，请勾选"强制变更"选项。')
            return render(request, 'inventory/product_unit_change_form.html', {
                'product': product,
                'check_result': check_result,
                'form_data': request.POST
            })
        
        # 执行变更
        try:
            change_history = ProductUnitChangeService.change_unit(
                product=product,
                new_unit=new_unit,
                conversion_factor=conversion_factor,
                reason=reason,
                changed_by=request.user,
                auto_approve=True
            )
            
            messages.success(request, '单位变更成功')
            return redirect('inventory:product_unit_change_history', product_id=product_id)
        
        except Exception as e:
            messages.error(request, f'单位变更失败：{str(e)}')
            return redirect('inventory:product_unit_change_request', product_id=product_id)
    
    # GET请求
    check_result = ProductUnitChangeService.check_can_change_unit(product)
    available_units = product.get_available_units()
    
    return render(request, 'inventory/product_unit_change_form.html', {
        'product': product,
        'check_result': check_result,
        'available_units': available_units
    })
```

### 3.4 URL配置

```python
# inventory/urls.py

urlpatterns = [
    # ... 现有URL ...
    
    # 成品包装单位管理
    path('product/<int:product_id>/packaging-units/', 
         product_unit_management.product_packaging_unit_list, 
         name='product_packaging_unit_list'),
    path('product/<int:product_id>/packaging-units/create/', 
         product_unit_management.product_packaging_unit_create, 
         name='product_packaging_unit_create'),
    
    # 成品单位变更
    path('product/<int:product_id>/unit-change/', 
         product_unit_change.product_unit_change_request, 
         name='product_unit_change_request'),
    path('product/<int:product_id>/unit-change/history/', 
         product_unit_change.product_unit_change_history, 
         name='product_unit_change_history'),
]
```

---

## 四、统一实现的优势

### 4.1 代码复用

| 组件 | 复用情况 | 说明 |
|------|---------|------|
| `UnitConversionService` | ✅ 完全复用 | 已支持material和product参数 |
| `Unit`模型 | ✅ 完全复用 | 基础单位字典表 |
| 转换逻辑 | ✅ 完全复用 | 数量、单价转换公式相同 |
| 视图模板 | ⚠️ 部分复用 | 可复用大部分HTML结构 |

### 4.2 维护性

- ✅ 代码结构清晰，Material和Product对称
- ✅ 业务逻辑分离，便于独立维护
- ✅ 类型安全，避免GenericForeignKey的复杂性
- ✅ 易于扩展，未来可支持其他类型

### 4.3 性能

- ✅ 查询效率高，直接外键关联
- ✅ 索引优化，unique_together约束
- ✅ 无额外JOIN，避免GenericForeignKey的查询开销

---

## 五、实施步骤

### 阶段一：数据模型（1天）

1. 修改Product模型，添加base_unit字段和方法
2. 创建ProductPackagingUnit模型
3. 创建ProductUnitChangeHistory模型
4. 创建并执行数据库迁移

### 阶段二：服务层（1-2天）

1. 创建ProductUnitChangeService
2. 复用UnitConversionService（已支持product）
3. 编写单元测试

### 阶段三：视图层（2-3天）

1. 创建成品包装单位管理视图
2. 创建成品单位变更视图
3. 创建对应的模板文件（可参考Material的模板）

### 阶段四：集成测试（1天）

1. 测试包装单位创建和管理
2. 测试单位变更流程
3. 测试业务场景（销售订单、生产任务）

---

## 六、关键差异处理

### 6.1 售价字段处理

**问题**：Product有sale_price字段，Material没有

**处理**：
- 单位变更时，同时转换sale_price
- 变更历史中记录old_sale_price和new_sale_price

### 6.2 业务检查差异

**Material检查**：
- 未完成的采购任务
- 进行中的生产任务（领料）

**Product检查**：
- 未完成的销售订单
- 进行中的生产任务（成品入库）

**处理**：在各自的Service中实现不同的检查逻辑

### 6.3 包装单位类型差异

**Material**：通常是大单位（袋=100kg，桶=200kg）
**Product**：通常是小单位（箱=12件，套=1件）

**处理**：转换系数不同，但逻辑相同，无需特殊处理

---

## 七、总结

### 7.1 统一实现可行性

✅ **高度可行**：
- 核心逻辑（单位转换）完全相同
- 数据模型结构对称
- 服务层可复用大部分代码
- 视图层可参考Material实现

### 7.2 实施建议

1. **优先实施**：先完成Product的基础单位支持（base_unit字段）
2. **逐步扩展**：再添加包装单位功能
3. **充分测试**：重点测试销售订单和生产任务的单位变更影响
4. **文档完善**：更新用户手册，说明成品单位管理功能

### 7.3 预期收益

- ✅ 代码复用率高（约70%）
- ✅ 开发周期短（3-5天）
- ✅ 维护成本低（结构清晰）
- ✅ 用户体验一致（Material和Product操作方式相同）

---

## 八、注意事项

1. **数据迁移**：为现有Product设置base_unit字段
2. **向后兼容**：base_unit允许为空，兼容旧数据
3. **业务影响**：成品单位变更需谨慎，影响销售订单
4. **测试覆盖**：重点测试销售、生产相关场景
