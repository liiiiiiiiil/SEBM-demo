# 物料单位管理 - 实施操作手册

## 目录
1. [快速开始](#快速开始)
2. [代码实现示例](#代码实现示例)
3. [操作流程](#操作流程)
4. [常见问题](#常见问题)
5. [故障排查](#故障排查)

---

## 一、快速开始

### 1.1 环境准备

确保已安装：
- Django 5.2+
- Python 3.10+

### 1.2 实施检查清单

- [ ] 数据库备份完成
- [ ] 测试环境已搭建
- [ ] 开发环境代码已更新
- [ ] 相关文档已阅读

---

## 二、代码实现示例

### 2.1 模型定义完整示例

#### Unit模型（基础单位）

```python
# inventory/models.py

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
        db_table = 'inventory_unit'
    
    def __str__(self):
        return f"{self.name}({self.code})"
```

#### MaterialPackagingUnit模型（物料包装单位）

```python
# inventory/models.py

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
        verbose_name='转换系数',
        help_text='1个包装单位 = 转换系数 个基础单位。例如：1袋=100kg，则系数为100'
    )
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
        db_table = 'inventory_material_packaging_unit'
    
    def __str__(self):
        return f"{self.material.name} - {self.packaging_unit_name} ({self.conversion_factor}{self.base_unit.code})"
    
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
        """获取显示文本：如"袋(100kg/袋)" """
        return f"{self.packaging_unit_name}({self.conversion_factor}{self.base_unit.code}/{self.packaging_unit_name})"
```

### 2.2 服务层完整实现

#### UnitConversionService（单位转换服务）

```python
# inventory/services/unit_conversion.py

from decimal import Decimal
from django.core.exceptions import ValidationError

class UnitConversionService:
    """单位转换服务类"""
    
    @staticmethod
    def convert_quantity(quantity, from_unit, to_unit, material=None, product=None):
        """
        转换数量
        
        参数:
            quantity: 数量（Decimal或数字）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象（可选）
            product: 成品对象（可选）
        
        返回:
            转换后的数量（Decimal）
        
        异常:
            ValueError: 无法转换时抛出
        """
        quantity = Decimal(str(quantity))
        
        # 如果单位相同，直接返回
        if from_unit == to_unit:
            return quantity
        
        # 优先使用物料
        item = material or product
        if not item:
            raise ValueError("需要提供物料或成品对象以进行单位转换")
        
        # 获取基础单位
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        
        # 情况1：从包装单位转换为基础单位
        if from_unit != base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                # 转换为基础单位
                base_quantity = packaging_unit.convert_to_base(quantity)
                
                # 如果目标单位是基础单位，直接返回
                if to_unit == base_unit_code:
                    return base_quantity
                
                # 如果目标单位也是包装单位
                target_packaging = None
                if material:
                    target_packaging = material.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                elif product and hasattr(product, 'packaging_units'):
                    target_packaging = product.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                
                if target_packaging:
                    # 从基础单位转换为目标包装单位
                    return target_packaging.convert_from_base(base_quantity)
        
        # 情况2：从基础单位转换为包装单位
        if from_unit == base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                return packaging_unit.convert_from_base(quantity)
        
        # 无法转换
        raise ValueError(
            f"无法转换：{from_unit} → {to_unit}。"
            f"请检查物料/成品是否定义了相应的包装单位。"
        )
    
    @staticmethod
    def convert_price(price, from_unit, to_unit, material=None, product=None):
        """
        转换单价
        
        参数:
            price: 单价（Decimal或数字）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象（可选）
            product: 成品对象（可选）
        
        返回:
            转换后的单价（Decimal）
        
        说明:
            单价转换公式：新单价 = 旧单价 ÷ 转换系数
            例如：0.5元/kg，1袋=100kg，则50元/袋
        """
        price = Decimal(str(price))
        
        if from_unit == to_unit:
            return price
        
        # 获取转换系数
        conversion_factor = UnitConversionService.get_conversion_factor(
            from_unit, to_unit, material, product
        )
        
        # 单价转换：新单价 = 旧单价 ÷ 转换系数
        return price / conversion_factor
    
    @staticmethod
    def get_conversion_factor(from_unit, to_unit, material=None, product=None):
        """获取转换系数"""
        if from_unit == to_unit:
            return Decimal('1')
        
        item = material or product
        if not item:
            raise ValueError("需要提供物料或成品对象")
        
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        
        # 从包装单位到基础单位
        if from_unit != base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                factor = packaging_unit.conversion_factor
                
                # 目标单位是基础单位
                if to_unit == base_unit_code:
                    return factor
                
                # 目标单位也是包装单位
                target_packaging = None
                if material:
                    target_packaging = material.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                elif product and hasattr(product, 'packaging_units'):
                    target_packaging = product.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                
                if target_packaging:
                    # 从包装单位A到包装单位B
                    # 例如：从"袋"到"箱"，需要知道1箱=多少袋
                    # 这里假设都是基于同一个基础单位
                    if packaging_unit.base_unit == target_packaging.base_unit:
                        return factor / target_packaging.conversion_factor
        
        # 从基础单位到包装单位
        if from_unit == base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                return Decimal('1') / packaging_unit.conversion_factor
        
        raise ValueError(f"无法获取转换系数：{from_unit} → {to_unit}")
    
    @staticmethod
    def get_available_units(material=None, product=None):
        """
        获取可用的单位列表（基础单位 + 包装单位）
        
        返回:
            [
                {'code': 'kg', 'name': '千克', 'type': 'base'},
                {'code': '袋', 'name': '袋(100kg/袋)', 'type': 'packaging'},
            ]
        """
        units = []
        item = material or product
        
        if not item:
            return units
        
        # 添加基础单位
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        base_unit_obj = None
        if hasattr(item, 'base_unit') and item.base_unit:
            base_unit_obj = item.base_unit
            units.append({
                'code': base_unit_obj.code,
                'name': base_unit_obj.name,
                'type': 'base',
                'display_text': base_unit_obj.name
            })
        else:
            units.append({
                'code': base_unit_code,
                'name': base_unit_code,
                'type': 'base',
                'display_text': base_unit_code
            })
        
        # 添加包装单位
        packaging_units = []
        if material:
            packaging_units = material.packaging_units.filter(is_active=True)
        elif product and hasattr(product, 'packaging_units'):
            packaging_units = product.packaging_units.filter(is_active=True)
        
        for pkg_unit in packaging_units:
            units.append({
                'code': pkg_unit.packaging_unit_name,
                'name': pkg_unit.packaging_unit_name,
                'type': 'packaging',
                'display_text': pkg_unit.get_display_text(),
                'conversion_factor': pkg_unit.conversion_factor,
                'base_unit': pkg_unit.base_unit.code
            })
        
        return units
```

### 2.3 Material模型扩展方法

```python
# inventory/models.py (Material类中添加)

class Material(models.Model):
    # ... 现有字段 ...
    
    # 新增字段
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='基础单位'
    )
    
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
            quantity, from_unit, to_unit, material=self
        )
    
    def convert_price(self, price, from_unit, to_unit):
        """转换单价（便捷方法）"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.convert_price(
            price, from_unit, to_unit, material=self
        )
    
    def get_available_units(self):
        """获取可用单位列表"""
        from inventory.services.unit_conversion import UnitConversionService
        return UnitConversionService.get_available_units(material=self)
```

### 2.4 视图层实现示例

#### 包装单位管理视图

```python
# inventory/views/unit_management.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal
from inventory.models import Material, MaterialPackagingUnit, Unit
from inventory.decorators import role_required

@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_list(request, material_id):
    """物料包装单位列表"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_units = material.packaging_units.filter(is_active=True).order_by('display_order')
    
    return render(request, 'inventory/packaging_unit_list.html', {
        'material': material,
        'packaging_units': packaging_units
    })

@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_create(request, material_id):
    """创建包装单位"""
    material = get_object_or_404(Material, pk=material_id)
    
    if request.method == 'POST':
        packaging_unit_name = request.POST.get('packaging_unit_name', '').strip()
        base_unit_id = request.POST.get('base_unit')
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        
        # 验证
        if not packaging_unit_name:
            messages.error(request, '请输入包装单位名称')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        base_unit = get_object_or_404(Unit, pk=base_unit_id)
        
        # 检查是否已存在
        if MaterialPackagingUnit.objects.filter(
            material=material,
            packaging_unit_name=packaging_unit_name,
            is_active=True
        ).exists():
            messages.error(request, f'包装单位"{packaging_unit_name}"已存在')
            return redirect('inventory:packaging_unit_create', material_id=material_id)
        
        # 如果设置为默认，取消其他默认
        if is_default:
            MaterialPackagingUnit.objects.filter(
                material=material,
                is_default=True
            ).update(is_default=False)
        
        # 创建
        packaging_unit = MaterialPackagingUnit.objects.create(
            material=material,
            packaging_unit_name=packaging_unit_name,
            base_unit=base_unit,
            conversion_factor=conversion_factor,
            is_default=is_default,
            remark=remark
        )
        
        messages.success(request, f'包装单位"{packaging_unit_name}"创建成功')
        return redirect('inventory:packaging_unit_list', material_id=material_id)
    
    # GET请求
    base_units = Unit.objects.filter(is_active=True).order_by('category', 'display_order')
    
    return render(request, 'inventory/packaging_unit_form.html', {
        'material': material,
        'base_units': base_units,
        'action': 'create'
    })

@login_required
@role_required('warehouse', 'ceo')
def packaging_unit_delete(request, material_id, packaging_unit_id):
    """删除包装单位（软删除）"""
    material = get_object_or_404(Material, pk=material_id)
    packaging_unit = get_object_or_404(
        MaterialPackagingUnit,
        pk=packaging_unit_id,
        material=material
    )
    
    # 软删除
    packaging_unit.is_active = False
    packaging_unit.save()
    
    messages.success(request, f'包装单位"{packaging_unit.packaging_unit_name}"已删除')
    return redirect('inventory:packaging_unit_list', material_id=material_id)
```

#### 单位变更视图

```python
# inventory/views/unit_change.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal
from django.utils import timezone
from inventory.models import Material, MaterialUnitChangeHistory
from inventory.services.unit_change import MaterialUnitChangeService
from inventory.decorators import role_required

@login_required
@role_required('warehouse', 'ceo')
def unit_change_request(request, material_id):
    """单位变更申请"""
    material = get_object_or_404(Material, pk=material_id)
    
    if request.method == 'POST':
        new_unit = request.POST.get('new_unit', '').strip()
        conversion_factor_str = request.POST.get('conversion_factor', '').strip()
        reason = request.POST.get('reason', '').strip()
        force_change = request.POST.get('force_change') == 'on'  # 强制变更
        
        # 验证
        if not new_unit:
            messages.error(request, '请输入新单位')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        if not conversion_factor_str:
            messages.error(request, '请输入转换系数')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        try:
            conversion_factor = Decimal(conversion_factor_str)
            if conversion_factor <= 0:
                raise ValueError("转换系数必须大于0")
        except (ValueError, InvalidOperation):
            messages.error(request, '转换系数格式错误')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        if not reason:
            messages.error(request, '请输入变更原因')
            return redirect('inventory:unit_change_request', material_id=material_id)
        
        # 前置检查
        check_result = MaterialUnitChangeService.check_can_change_unit(material)
        
        # 如果有严重问题且未选择强制变更
        if not check_result['can_change'] and not force_change:
            messages.error(request, '无法变更单位，存在业务冲突。如需强制变更，请勾选"强制变更"选项。')
            return render(request, 'inventory/unit_change_form.html', {
                'material': material,
                'check_result': check_result,
                'form_data': request.POST
            })
        
        # 执行变更
        try:
            change_history = MaterialUnitChangeService.change_unit(
                material=material,
                new_unit=new_unit,
                conversion_factor=conversion_factor,
                reason=reason,
                changed_by=request.user,
                auto_approve=True  # 根据业务规则决定是否需要审批
            )
            
            messages.success(request, '单位变更成功')
            return redirect('inventory:unit_change_history', material_id=material_id)
        
        except Exception as e:
            messages.error(request, f'单位变更失败：{str(e)}')
            return redirect('inventory:unit_change_request', material_id=material_id)
    
    # GET请求：显示变更表单
    check_result = MaterialUnitChangeService.check_can_change_unit(material)
    
    # 获取可用单位列表
    available_units = material.get_available_units()
    
    return render(request, 'inventory/unit_change_form.html', {
        'material': material,
        'check_result': check_result,
        'available_units': available_units
    })

@login_required
@role_required('warehouse', 'ceo')
def unit_change_history(request, material_id):
    """单位变更历史"""
    material = get_object_or_404(Material, pk=material_id)
    history_list = MaterialUnitChangeHistory.objects.filter(
        material=material
    ).order_by('-changed_at')
    
    return render(request, 'inventory/unit_change_history.html', {
        'material': material,
        'history_list': history_list
    })
```

### 2.5 URL配置

```python
# inventory/urls.py

from django.urls import path
from inventory.views import unit_management, unit_change

urlpatterns = [
    # ... 现有URL ...
    
    # 包装单位管理
    path('material/<int:material_id>/packaging-units/', 
         unit_management.packaging_unit_list, 
         name='packaging_unit_list'),
    path('material/<int:material_id>/packaging-units/create/', 
         unit_management.packaging_unit_create, 
         name='packaging_unit_create'),
    path('material/<int:material_id>/packaging-units/<int:packaging_unit_id>/delete/', 
         unit_management.packaging_unit_delete, 
         name='packaging_unit_delete'),
    
    # 单位变更
    path('material/<int:material_id>/unit-change/', 
         unit_change.unit_change_request, 
         name='unit_change_request'),
    path('material/<int:material_id>/unit-change/history/', 
         unit_change.unit_change_history, 
         name='unit_change_history'),
]
```

---

## 三、操作流程

### 3.1 创建包装单位

**场景**：为水泥创建"袋"包装单位（1袋=100kg）

**步骤：**
1. 进入物料详情页
2. 点击"包装单位管理"
3. 点击"添加包装单位"
4. 填写信息：
   - 包装单位名称：袋
   - 基础单位：选择"kg"
   - 转换系数：100（表示1袋=100kg）
   - 是否默认：是
5. 保存

**验证：**
- 在采购入库时，可以选择"袋"作为单位
- 输入10袋，系统自动转换为1000kg存储

### 3.2 执行单位变更

**场景**：将水泥的单位从"kg"改为"袋"

**步骤：**
1. 进入物料详情页
2. 点击"单位变更"
3. 系统自动检查：
   - 是否有未完成的业务
   - BOM使用情况
4. 填写变更信息：
   - 新单位：袋
   - 转换系数：100（1袋=100kg）
   - 变更原因：业务需要
5. 预览变更结果：
   - 当前库存：1000kg → 10袋
   - 当前单价：0.5元/kg → 50元/袋
   - 安全库存：500kg → 5袋
6. 确认变更

**验证：**
- 检查库存数量是否正确
- 检查单价是否正确
- 检查历史记录是否保存

### 3.3 使用包装单位采购

**场景**：采购10袋水泥

**步骤：**
1. 创建采购任务
2. 选择物料：水泥
3. 选择单位：袋（从下拉框选择）
4. 输入数量：10
5. 输入单价：50（元/袋）
6. 系统自动：
   - 存储数量：1000kg
   - 存储单价：0.5元/kg
   - 显示数量：10袋

---

## 四、常见问题

### Q1: 转换系数如何理解？

**A:** 转换系数表示：1个包装单位 = 转换系数 个基础单位

**示例：**
- 水泥：1袋 = 100kg，转换系数 = 100
- 石灰石粉：1袋 = 50kg，转换系数 = 50

### Q2: 单位变更后，历史数据会变化吗？

**A:** 不会。历史数据（如StockTransaction、PurchaseTaskItem）保持原单位不变，这是历史快照。

### Q3: BOM配方需要手动更新吗？

**A:** 建议手动更新。单位变更后，系统会提示检查BOM配方，但不会自动转换，因为配方是技术规格，需要人工确认。

### Q4: 可以同时使用多个包装单位吗？

**A:** 可以。一个物料可以定义多个包装单位，但需要指定一个默认的。

### Q5: 单位变更失败怎么办？

**A:** 
1. 检查是否有未完成的业务（生产任务、采购任务等）
2. 如有必要，选择"强制变更"（需谨慎）
3. 联系系统管理员

---

## 五、故障排查

### 5.1 单位转换失败

**症状：** 提示"无法转换单位"

**排查步骤：**
1. 检查物料是否定义了包装单位
2. 检查包装单位是否启用（is_active=True）
3. 检查转换系数是否正确
4. 检查基础单位是否匹配

**解决方案：**
- 为物料添加包装单位定义
- 检查并修正转换系数

### 5.2 数据不一致

**症状：** 库存数量或单价异常

**排查步骤：**
1. 运行数据一致性检查脚本
2. 查看单位变更历史记录
3. 检查是否有异常的单位变更操作

**解决方案：**
- 使用数据修复脚本
- 如有必要，回滚到变更前状态

### 5.3 单位变更被阻止

**症状：** 提示"无法变更单位，存在业务冲突"

**排查步骤：**
1. 检查是否有进行中的生产任务
2. 检查是否有未完成的采购任务
3. 检查是否有未完成的销售订单

**解决方案：**
- 等待业务完成后变更
- 或选择"强制变更"（需审批）

---

## 六、最佳实践

1. **包装单位定义**
   - 转换系数要准确
   - 定期检查包装单位定义是否正确
   - 避免重复定义相同的包装单位

2. **单位变更**
   - 变更前充分检查业务影响
   - 记录详细的变更原因
   - 变更后验证数据正确性

3. **数据维护**
   - 定期运行数据一致性检查
   - 保留完整的变更历史
   - 定期备份数据

---

## 七、技术支持

如遇到问题，请联系：
- 技术支持邮箱：support@example.com
- 技术文档：`factory_system/doc/unit-management-architecture.md`
