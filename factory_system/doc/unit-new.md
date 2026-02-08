# 双单位体系重构设计方案

> **版本**：v1.0  
> **日期**：2026-02-07  
> **状态**：设计评审稿（未开始实施）  
> **范围**：inventory / production / purchase / sales / logistics 全模块

---

## 一、现状问题分析

### 1.1 当前数据模型摘要

| 模型 | 单位相关字段 | 问题 |
|------|-------------|------|
| `Material` | `unit`(CharField, 默认 kg)、`base_unit`(FK→Unit, 可空) | `unit` 同时充当显示和计算，`base_unit` 可空导致语义模糊 |
| `Product` | `unit`(CharField, 默认 件)、`base_unit`(FK→Unit, 可空) | 同上 |
| `MaterialPackagingUnit` | `packaging_unit_name`、`base_unit`、`conversion_factor` | 只支持"包装"概念，不支持同量纲换算（如 kg↔吨） |
| `ProductPackagingUnit` | 同上 | 同上，且与 Material 侧完全对称复制 |
| `BOM` | 无 unit 字段 | 靠隐含约定"成品基础单位→原料基础单位"，阅读 BOM 时不知道原料用量的单位是什么 |
| `Inventory` | `unit`(CharField) | 单位变更时会修改此字段和 quantity，历史记录与当前记录不在同一口径 |
| `Batch` | 无独立 unit | 继承 Inventory.unit，同样面临变更问题 |
| `StockTransaction` | `unit`(CharField) | 每条记录各自存了当时的 unit，变更后新旧记录单位不一致 |
| `MaterialRequisitionItem` | `unit`(CharField) | 领料单的单位可能与当前物料单位不一致 |
| `PurchaseTaskItem` | `unit`(CharField) | 采购单位可能与库存单位不同 |
| `SalesOrderItem` | 无 unit 字段 | 隐式使用成品当前单位 |
| `FinishedProductInbound` | `unit`(CharField) | 入库单位可能与当前成品单位不一致 |

### 1.2 核心矛盾

1. **显示单位与计算单位合一**：修改"显示单位"会导致库存数量、批次数量、单价等全部跟着换算，容易出错且不可逆。
2. **BOM 无单位**：用户看到 `quantity=5` 无法直观知道是 5 kg 还是 5 吨，只能靠"去查原料的基础单位"。
3. **换算表不够通用**：`PackagingUnit` 只处理"包装换算"（如 1 袋=100kg），无法处理同量纲标准换算（如 1 吨=1000kg）。
4. **Material 和 Product 的单位体系完全对称复制**：`MaterialPackagingUnit` / `ProductPackagingUnit` / `MaterialUnitChangeHistory` / `ProductUnitChangeHistory` / `MaterialUnitChangeService` / `ProductUnitChangeService` 各一套，维护成本高。

---

## 二、设计目标

| 目标 | 说明 |
|------|------|
| **计算与展示分离** | 系统内部所有数量一律使用「基础单位」存储和计算，UI 层按「显示单位」呈现，两者通过换算表连接 |
| **基础单位不可变** | 一旦物料/成品被创建并录入数据（有库存/BOM/订单），其基础单位不可修改，保证历史数据口径一致 |
| **显示单位随时可改** | 仓库管理员可随时切换显示单位，不影响任何存储数据 |
| **BOM 有明确单位** | BOM 每行存储「单位」，且该单位必须在原料的换算表中有定义（含基础单位） |
| **统一换算表** | 每个物料/成品有一张「单位换算表」，涵盖标准换算和包装换算，不再区分两种表 |
| **减少重复** | Material 和 Product 共用一套换算机制，消除代码对称复制 |

---

## 三、新数据模型设计

### 3.1 模型总览（ER 概要）

```
Unit（单位字典 - 保留）
  │
  ├──→ Material.base_unit  (NOT NULL, 不可变)
  ├──→ Product.base_unit   (NOT NULL, 不可变)
  │
  ├──→ ItemUnitConversion.base_unit  (换算基准)
  └──→ ItemUnitConversion.target_unit (换算目标)

Material ──1:N──→ ItemUnitConversion (content_type='material')
Product  ──1:N──→ ItemUnitConversion (content_type='product')

BOM
  ├── product (FK→Product)
  ├── material (FK→Material)
  ├── quantity (用量数值)
  └── unit (FK→Unit)  ← 新增，必须在 material 的换算表中有定义
```

### 3.2 Unit（单位字典表）— 保留，微调

**改动**：去除 `is_base` 字段（"是否基础单位"不再由字典决定，而是由每个物料/成品自行指定）。新增 `symbol` 用于简洁显示。

```
Unit
├── code         CharField(20, unique)     # 如 'kg', 't', '件', '袋'
├── name         CharField(50)             # 如 '公斤', '吨', '件', '袋'
├── symbol       CharField(10, blank)      # 如 'kg', 't', '个', '袋'（用于紧凑显示）
├── category     CharField(20, choices)    # weight/length/volume/quantity/area
├── display_order IntegerField(default=0)
├── is_active    BooleanField(default=True)
├── created_at   DateTimeField(auto_now_add)
```

**说明**：
- `category` 的 choices 去掉 `packaging`（包装不是物理量纲，而是换算关系）。
- 「袋」「箱」等仍录入 Unit 表，但 category 设为 `quantity`（计数类）。

### 3.3 Material — 改造

```
Material
├── sku            CharField(50, unique)
├── name           CharField(200)
├── category       FK→MaterialCategory
├── material_type  CharField(20, choices)
├── base_unit      FK→Unit (NOT NULL)          # ★ 改为必填、不可变
├── display_unit   FK→Unit (NOT NULL)          # ★ 新增：当前显示单位，可随时修改
├── unit_price     Decimal(10,2)               # ★ 语义变更：始终表示「基础单位」下的单价
├── safety_stock   Decimal(10,2)               # ★ 语义变更：始终表示「基础单位」下的安全库存
├── created_at     DateTimeField
```

**与旧模型对比**：

| 旧字段 | 新字段 | 变化 |
|--------|--------|------|
| `unit` (CharField, 可改) | `display_unit` (FK→Unit, 可改) | 从字符串改为外键；语义从"计算+显示"变为"仅显示" |
| `base_unit` (FK→Unit, 可空) | `base_unit` (FK→Unit, 必填) | 从可空改为必填、不可变 |
| `unit_price` | `unit_price` | 语义锁定为"基础单位下的单价"，不再随显示单位变动 |
| `safety_stock` | `safety_stock` | 语义锁定为"基础单位下的安全库存"，不再随显示单位变动 |

**删除的字段/方法**：
- `unit`（旧 CharField）：被 `display_unit` 取代
- `get_base_unit()` / `get_base_unit_display()`：简化为 `self.base_unit.code` / `self.base_unit.name`
- `get_quantity_in_base_unit()`：不再需要，因为所有存储本身就是基础单位

**新增的方法**：
- `to_display(quantity)` → 将基础单位数量换算为显示单位数量
- `from_display(quantity)` → 将显示单位数量换算为基础单位数量
- `convert(quantity, from_unit, to_unit)` → 通用换算（查换算表）

### 3.4 Product — 改造（与 Material 对称）

```
Product
├── sku            CharField(50, unique)
├── name           CharField(200)
├── category       FK→ProductCategory
├── specification  TextField(blank)
├── base_unit      FK→Unit (NOT NULL)          # ★ 必填、不可变
├── display_unit   FK→Unit (NOT NULL)          # ★ 新增
├── unit_price     Decimal(10,2)               # 基础单位下的成本单价
├── sale_price     Decimal(10,2)               # 基础单位下的售价
├── safety_stock   Decimal(10,2)               # 基础单位下的安全库存
├── created_at / updated_at
```

**变化同 Material**。

### 3.5 ItemUnitConversion（统一换算表）— 新增，替代 PackagingUnit

> 替代原 `MaterialPackagingUnit` + `ProductPackagingUnit`

```
ItemUnitConversion
├── content_type   CharField(20, choices=[('material','原料'),('product','成品')])
├── material       FK→Material (NULL)
├── product        FK→Product  (NULL)
├── base_unit      FK→Unit                    # 换算基准（应与物料/成品的 base_unit 一致）
├── target_unit    FK→Unit                    # 换算目标
├── factor         Decimal(15,6)              # 1 target_unit = factor × base_unit
│                                             # 例：1 吨 = 1000 kg → factor=1000
│                                             # 例：1 袋 = 50 kg   → factor=50
├── is_default     BooleanField(default=False) # 是否为默认显示换算
├── is_active      BooleanField(default=True)
├── remark         TextField(blank)
├── created_at / updated_at
```

**约束**：
- `unique_together = ['material', 'target_unit']`（material 非空时）
- `unique_together = ['product', 'target_unit']`（product 非空时）
- `base_unit` 必须等于关联物料/成品的 `base_unit`（应用层校验）

**语义**：
- `factor` 的含义：**1 个 target_unit 等于多少个 base_unit**。
- 从 target_unit 转换到 base_unit：`base_qty = target_qty × factor`
- 从 base_unit 转换到 target_unit：`target_qty = base_qty ÷ factor`

**示例**：

| 物料 | base_unit | target_unit | factor | 含义 |
|------|-----------|-------------|--------|------|
| 水泥 | kg | 吨 | 1000 | 1 吨 = 1000 kg |
| 水泥 | kg | 袋 | 50 | 1 袋 = 50 kg |
| 螺丝 | 个 | 箱 | 500 | 1 箱 = 500 个 |
| 油漆 | L | 桶 | 20 | 1 桶 = 20 L |

**与旧模型对比**：

| 旧 | 新 | 变化 |
|----|----|----|
| `MaterialPackagingUnit` | `ItemUnitConversion` (content_type='material') | 合并为统一表 |
| `ProductPackagingUnit` | `ItemUnitConversion` (content_type='product') | 合并为统一表 |
| `packaging_unit_name` (CharField) | `target_unit` (FK→Unit) | 从字符串改为外键，确保单位规范 |
| `conversion_factor` | `factor` | 语义一致，精度提高到 15,6 |

### 3.6 BOM — 改造（恢复 unit 字段）

```
BOM
├── product    FK→Product
├── material   FK→Material
├── quantity   Decimal(10,4)
├── unit       FK→Unit (NOT NULL)            # ★ 新增
├── created_at DateTimeField
```

**语义**：
- **每 1 个「成品基础单位」的成品，需要 `quantity` 个 `unit` 的该原料。**
- `unit` 必须是该 BOM 行所关联的 `material` 的合法单位（即 `material.base_unit` 或 `material` 的换算表中已定义的 target_unit）。

**示例**：

| 成品 | 成品 base_unit | 原料 | BOM.quantity | BOM.unit | 含义 |
|------|---------------|------|-------------|----------|------|
| 防水涂料 A | 桶 | 树脂 | 15 | kg | 每 1 桶成品需要 15 kg 树脂 |
| 防水涂料 A | 桶 | 颜料 | 0.5 | kg | 每 1 桶成品需要 0.5 kg 颜料 |
| 防水涂料 A | 桶 | 桶盖 | 1 | 个 | 每 1 桶成品需要 1 个桶盖 |

**BOM 计算流程**（生产 N 个「成品显示单位」的成品）：

```
1. 成品需求换算：
   base_qty = N × product.get_conversion_factor(product.display_unit)
   （如果 display_unit == base_unit，则 base_qty = N）

2. 对每条 BOM 行：
   raw_need_in_bom_unit = base_qty × bom.quantity
   （此时单位 = bom.unit）

3. 转换为原料基础单位（用于扣库存）：
   raw_need_in_base = raw_need_in_bom_unit × material.get_factor(bom.unit)
   （如 bom.unit 已是原料 base_unit，则 factor=1）

4. 转换为原料显示单位（用于 UI 展示）：
   raw_need_display = material.to_display(raw_need_in_base)
```

**恢复 unit 的好处**：
- BOM 列表直接可读：「15 kg 树脂」而不是「15（去查一下原料的基础单位）」。
- 允许 BOM 用量使用非基础单位：如果原料 base_unit 是 kg，但某 BOM 写「0.5 吨」也合法（因为换算表有 1 吨=1000 kg）。
- 计算时统一换算到 base_unit，不会引起歧义。

### 3.7 Inventory — 改造

```
Inventory
├── inventory_type   CharField(choices)
├── product          FK→Product (NULL)
├── material         FK→Material (NULL)
├── other_name       CharField(200, blank)
├── quantity         Decimal(10,2)           # ★ 始终为「基础单位」下的数量
├── updated_at       DateTimeField
```

**删除 `unit` 字段**：因为单位始终 = 关联物料/成品的 `base_unit`，不再冗余存储。UI 展示时通过 `item.display_unit` + 换算表转换。

### 3.8 Batch — 改造

```
Batch
├── batch_no        CharField
├── inventory       FK→Inventory
├── batch_date      DateField
├── quantity        Decimal(10,2)           # ★ 始终为「基础单位」
├── locked_quantity Decimal(10,2)           # ★ 始终为「基础单位」
├── unit_price      Decimal(10,2)           # ★ 始终为「基础单位」下的单价
├── expiry_date / supplier / remark / created_at / updated_at
```

**无 unit 字段**：同 Inventory，单位隐含为 base_unit。

### 3.9 StockTransaction — 改造

```
StockTransaction
├── transaction_type  CharField(choices)
├── inventory         FK→Inventory
├── batch             FK→Batch (NULL)
├── quantity          Decimal(10,2)          # ★ 始终为「基础单位」
├── unit              FK→Unit (NOT NULL)     # ★ 改为外键，记录操作时的「操作单位」（用于审计追溯）
├── base_quantity     Decimal(10,2)          # ★ 新增：基础单位下的实际变动量（冗余但便于查询）
├── reference_no      CharField
├── remark            TextField
├── operator          FK→User
├── created_at        DateTimeField
```

**说明**：
- `quantity` + `unit`：记录操作人当时输入的「量 + 单位」（如"入库 2 吨"）。
- `base_quantity`：系统自动换算后的基础单位量（如 2000 kg），用于库存增减。
- 保留 `unit` 而不是只存 base_quantity，是为了审计时能还原操作人的原始意图。
- 删除旧的 `old_unit_price` / `new_unit_price`（单价调整走 InventoryAdjustmentRequest）。

### 3.10 其他受影响模型

#### MaterialRequisitionItem（领料单明细）

```
MaterialRequisitionItem
├── requisition        FK→MaterialRequisition
├── material           FK→Material
├── required_quantity  Decimal(10,2)          # ★ 基础单位
├── issued_quantity    Decimal(10,2)          # ★ 基础单位
├── （删除 unit 字段）
```

**说明**：单位恒为 `material.base_unit`，不冗余存储。展示时换算。

#### PurchaseTaskItem（采购明细）

```
PurchaseTaskItem
├── task         FK→PurchaseTask
├── material     FK→Material (NULL)
├── item_name    CharField(blank)
├── item_type    CharField(choices)
├── quantity     Decimal(10,2)               # ★ 基础单位
├── unit_price   Decimal(10,2)               # ★ 基础单位下的单价
├── subtotal     Decimal(12,2)
├── display_unit FK→Unit (NULL)              # ★ 新增：采购时使用的业务单位（如"吨"）
├── display_quantity Decimal(10,2) (NULL)     # ★ 新增：业务单位下的数量（如 2 吨）
```

**说明**：
- `quantity` / `unit_price` 始终是基础单位口径。
- `display_unit` / `display_quantity` 记录采购人填写时的原始单位和数量，便于打印采购单和与供应商沟通。
- `subtotal = display_quantity × 业务单位单价`（或 `quantity × unit_price`，两者等价）。

#### SalesOrderItem（销售订单明细）

```
SalesOrderItem
├── order        FK→SalesOrder
├── product      FK→Product
├── quantity     Decimal(10,2)               # ★ 基础单位
├── unit_price   Decimal(10,2)               # ★ 基础单位下的单价
├── subtotal     Decimal(12,2)
├── display_unit FK→Unit (NULL)              # ★ 新增：销售时使用的业务单位
├── display_quantity Decimal(10,2) (NULL)     # ★ 新增：业务单位下的数量
```

#### FinishedProductInbound（成品入库单）

```
FinishedProductInbound
├── inbound_no   CharField
├── task         FK→ProductionTask
├── qc_record    FK→QCRecord (NULL)
├── quantity     Decimal(10,2)               # ★ 基础单位
├── operator     FK→User
├── created_at   DateTimeField
├── （删除 unit 字段）
```

#### ProductionTask（生产任务）

```
ProductionTask
├── ...
├── required_quantity   Decimal(10,2)        # ★ 基础单位
├── completed_quantity  Decimal(10,2)        # ★ 基础单位
├── ...
```

**说明**：原本无 unit 字段，只需确认 quantity 语义为基础单位。

---

## 四、可删除 / 废弃的模型与服务

重构后以下模型和服务可以**删除**：

| 待删除 | 替代方案 |
|--------|---------|
| `MaterialPackagingUnit` | `ItemUnitConversion` (content_type='material') |
| `ProductPackagingUnit` | `ItemUnitConversion` (content_type='product') |
| `MaterialUnitChangeHistory` | **不再需要**。基础单位不可变，显示单位变更不影响数据，无需记录历史 |
| `ProductUnitChangeHistory` | 同上 |
| `inventory/services/unit_change.py` (`MaterialUnitChangeService`) | 删除。显示单位修改只改 `display_unit` 字段 |
| `inventory/services/product_unit_change.py` (`ProductUnitChangeService`) | 同上 |
| `inventory/views/unit_change.py` | 删除或简化为只修改 display_unit |
| `inventory/views/product_unit_change.py` | 同上 |
| `InventoryAdjustmentRequest` 的 `unit` 调整类型 | 删除。显示单位可直接改，不需走审批；基础单位不允许改 |

---

## 五、UnitConversionService 重写

### 5.1 核心接口

```python
class UnitConversionService:
    """统一单位换算服务"""

    @staticmethod
    def get_factor(item, unit) -> Decimal:
        """
        获取 unit 相对于 item.base_unit 的换算系数。
        返回值含义：1 unit = factor × base_unit

        - item: Material 或 Product 实例
        - unit: Unit 实例或 unit code 字符串

        如果 unit == item.base_unit，返回 Decimal('1')。
        如果 unit 在 item 的 ItemUnitConversion 中，返回 factor。
        否则抛出 ValueError。
        """

    @staticmethod
    def to_base(item, quantity, from_unit) -> Decimal:
        """将任意单位数量转换为基础单位数量"""
        # base_qty = quantity × get_factor(item, from_unit)

    @staticmethod
    def from_base(item, base_quantity, to_unit) -> Decimal:
        """将基础单位数量转换为目标单位数量"""
        # target_qty = base_quantity ÷ get_factor(item, to_unit)

    @staticmethod
    def convert(item, quantity, from_unit, to_unit) -> Decimal:
        """任意两个合法单位之间互转"""
        # base_qty = to_base(item, quantity, from_unit)
        # return from_base(item, base_qty, to_unit)

    @staticmethod
    def to_display(item, base_quantity) -> (Decimal, Unit):
        """将基础单位数量转换为该物料/成品的当前显示单位数量"""
        # return from_base(item, base_quantity, item.display_unit), item.display_unit

    @staticmethod
    def from_display(item, display_quantity) -> Decimal:
        """将显示单位数量转换为基础单位数量"""
        # return to_base(item, display_quantity, item.display_unit)

    @staticmethod
    def get_available_units(item) -> list[dict]:
        """
        获取物料/成品的所有可用单位列表。
        返回: [
            {'unit': Unit实例, 'factor': Decimal, 'is_base': True/False},
            ...
        ]
        包含 base_unit (factor=1) + 所有 ItemUnitConversion 中的 target_unit。
        """

    @staticmethod
    def validate_bom_unit(bom_item) -> bool:
        """
        校验 BOM 行的 unit 是否合法：
        必须是 bom_item.material 的 base_unit 或其换算表中已定义的 target_unit。
        """
```

### 5.2 Material / Product 便捷方法

在 Material 和 Product 上提供快捷代理（可通过 Mixin 或抽象基类统一）：

```python
class UnitMixin:
    """Material 和 Product 共享的单位方法"""

    def to_base(self, quantity, from_unit):
        return UnitConversionService.to_base(self, quantity, from_unit)

    def from_base(self, base_quantity, to_unit):
        return UnitConversionService.from_base(self, base_quantity, to_unit)

    def to_display(self, base_quantity):
        return UnitConversionService.to_display(self, base_quantity)

    def from_display(self, display_quantity):
        return UnitConversionService.from_display(self, display_quantity)

    def convert(self, quantity, from_unit, to_unit):
        return UnitConversionService.convert(self, quantity, from_unit, to_unit)

    def get_available_units(self):
        return UnitConversionService.get_available_units(self)
```

---

## 六、各业务场景的计算流程

### 6.1 BOM 原料需求计算（生产领料）

**场景**：生产任务要求生产 N（基础单位）的成品 P，计算各原料需求。

```
对每条 BOM 行（material=M, quantity=Q, unit=U）：
  1. bom_need = N × Q          # 得到的数量单位是 U
  2. base_need = to_base(M, bom_need, U)   # 换算为原料基础单位
  3. 用 base_need 去扣减 Inventory / Batch
  4. 展示时：display_need = M.to_display(base_need)
```

**示例**：
- 成品 P 的 base_unit = 桶，生产任务 N=100 桶
- BOM 行：原料=树脂, quantity=15, unit=kg
- bom_need = 100 × 15 = 1500，单位 = kg
- 树脂 base_unit = kg，factor = 1，base_need = 1500 kg
- 树脂 display_unit = 吨，factor = 1000，display_need = 1.5 吨

### 6.2 采购入库

**场景**：采购人录入"到货 2 吨水泥"。

```
1. 用户输入：display_quantity=2, display_unit=吨
2. base_quantity = to_base(水泥, 2, 吨) = 2 × 1000 = 2000 kg
3. Inventory.quantity += 2000
4. 新建 Batch：quantity=2000
5. StockTransaction：quantity=2, unit=吨, base_quantity=2000
```

### 6.3 销售出库

**场景**：销售订单明细"防水涂料 A × 10 桶"。

```
1. 用户输入：display_quantity=10, display_unit=桶
2. base_quantity = to_base(涂料A, 10, 桶)
   如果 base_unit=桶 → base_quantity=10
   如果 base_unit=kg, 1桶=20kg → base_quantity=200
3. Inventory.quantity -= base_quantity
4. StockTransaction 记录
```

### 6.4 库存展示

**场景**：仓库管理员查看库存列表。

```
对每条 Inventory 记录：
  item = inv.product 或 inv.material
  display_qty = item.to_display(inv.quantity)   # 如 2000kg → 2吨
  display_unit = item.display_unit.name         # "吨"
  显示："{item.name} | {display_qty} {display_unit}"
```

### 6.5 修改显示单位

**场景**：仓库管理员将水泥的显示单位从"kg"改为"吨"。

```
1. 修改 material.display_unit = Unit(code='t')
2. 保存。完成。
   
   不修改：
   - Inventory.quantity（仍为 2000，单位 kg 不变）
   - Batch.quantity
   - unit_price
   - safety_stock
   - 历史 StockTransaction
   - BOM.quantity / BOM.unit
```

**这就是双单位体系的核心价值：改显示单位 = 改一个字段，零风险。**

---

## 七、UI / 模板层修改指南

### 7.1 总体原则

| 位置 | 显示什么 | 数据来源 |
|------|---------|---------|
| 库存列表 | 显示单位下的数量 + 显示单位名称 | `item.to_display(inv.quantity)` + `item.display_unit.name` |
| BOM 列表 | BOM 行的 quantity + BOM 行的 unit | `bom.quantity` + `bom.unit.name` |
| 领料单 | 显示单位下的数量 | `material.to_display(item.required_quantity)` |
| 采购单 | 采购时使用的业务单位 | `task_item.display_quantity` + `task_item.display_unit.name` |
| 销售订单 | 销售时使用的业务单位 | `order_item.display_quantity` + `order_item.display_unit.name` |
| 入库表单 | 用户选择单位 + 输入数量 | 表单提供单位下拉（来自 `get_available_units()`） |
| 库存变动记录 | 操作时的原始单位 + 基础单位量 | `tx.quantity` + `tx.unit.name`（辅助显示 `tx.base_quantity` + `base_unit`） |

### 7.2 表单处理模式

所有涉及「数量输入」的表单（采购入库、销售下单、生产入库、库存调整等）统一采用：

```
[ 数量输入框 ] [ 单位下拉选择 ]
```

- 单位下拉由 `item.get_available_units()` 填充，默认选中 `display_unit`。
- 后端接收 `(quantity, unit_code)` 后，统一调用 `to_base()` 换算为基础单位再入库/扣减。

### 7.3 受影响的模板清单

| 模板文件 | 影响点 |
|---------|--------|
| `templates/inventory/bom_list.html` | BOM 用量列新增单位显示 |
| `templates/inventory/inventory_list.html` | 数量和单位改为从 display_unit 换算 |
| `templates/inventory/inventory_detail.html` | 同上 |
| `templates/inventory/adjustment_form.html` | 数量展示用 display_unit，提交用 base_unit |
| `templates/inventory/adjustment_approve.html` | 同上 |
| `templates/inventory/adjustment_list.html` | 同上 |
| `templates/production/task_list.html` | 数量展示用成品 display_unit |
| `templates/production/task_detail.html` | 同上 + 领料清单用原料 display_unit |
| `templates/production/requisition_list.html` | 领料数量用 display_unit |
| `templates/production/inbound_form.html` | 入库表单加单位选择 |
| `templates/purchase/task_list.html` | 显示采购业务单位 |
| `templates/purchase/task_form.html` | 采购表单加单位选择 |
| `templates/purchase/task_detail.html` | 同上 |
| `templates/sales/order_list.html` | 显示销售业务单位 |
| `templates/sales/order_form.html` | 下单表单加单位选择 |
| `templates/sales/order_detail.html` | 同上 |
| `templates/logistics/shipment_list.html` | 发货数量用 display_unit |

---

## 八、数据迁移策略

### 8.1 迁移步骤

```
Phase 1：新增字段（向后兼容）
  1. Material 新增 display_unit (FK, NULL 暂允许)
  2. Product 新增 display_unit (FK, NULL 暂允许)
  3. 新建 ItemUnitConversion 表
  4. BOM 新增 unit (FK, NULL 暂允许)

Phase 2：数据填充
  1. 遍历所有 Material：
     - 若 base_unit 已有值 → 保留
     - 若 base_unit 为空 → 根据 material.unit 字符串查 Unit 表，设为 base_unit
     - display_unit = base_unit（初始状态，显示单位=基础单位）
  2. 遍历所有 Product：同上
  3. 迁移 MaterialPackagingUnit → ItemUnitConversion：
     - content_type='material'
     - material=原记录.material
     - base_unit=原记录.base_unit
     - target_unit=查 Unit 表匹配 packaging_unit_name（若不存在则创建）
     - factor=原记录.conversion_factor
  4. 迁移 ProductPackagingUnit → ItemUnitConversion：同上
  5. 遍历所有 BOM：
     - bom.unit = bom.material.base_unit（当前 BOM 无单位，默认用原料基础单位）

Phase 3：设为必填 + 删除旧字段
  1. Material.base_unit → NOT NULL
  2. Material.display_unit → NOT NULL
  3. Product.base_unit → NOT NULL
  4. Product.display_unit → NOT NULL
  5. BOM.unit → NOT NULL
  6. 删除 Material.unit (旧 CharField)
  7. 删除 Inventory.unit
  8. 删除 MaterialRequisitionItem.unit
  9. 删除 FinishedProductInbound.unit
  10. 删除 MaterialPackagingUnit 表
  11. 删除 ProductPackagingUnit 表
  12. 删除 MaterialUnitChangeHistory 表
  13. 删除 ProductUnitChangeHistory 表
```

### 8.2 Inventory / Batch 数据校验

迁移前需确认：当前 `Inventory.unit` / `Batch` 中的数量是否已经与 `material.base_unit`（或 `material.unit`）一致。

- **若一致**（大多数情况）：无需数值转换，直接去掉 `Inventory.unit` 字段。
- **若不一致**（曾做过"单位变更"）：需要逐条换算为 base_unit 口径，写迁移脚本处理。

### 8.3 StockTransaction 历史数据

历史 `StockTransaction` 已有 `unit` (CharField) 和 `quantity`。迁移策略：

1. 新增 `base_quantity` 字段（允许 NULL）。
2. 遍历历史记录：
   - 若 `unit` == 关联物料/成品的当前 base_unit → `base_quantity = quantity`
   - 若不一致 → 通过换算表或历史变更记录计算 `base_quantity`
3. 将 `unit` 从 CharField 改为 FK→Unit（需要先确保所有历史 unit 字符串在 Unit 表中有对应记录）。

---

## 九、关键业务规则

### 9.1 基础单位不可变

- 规则：Material / Product 一旦存在关联数据（Inventory / BOM / Order / Task），`base_unit` 字段不允许修改。
- 实现：在 `Material.save()` / `Product.save()` 中，如果 `pk` 已存在且 `base_unit` 发生变化，检查是否有关联数据，有则抛出 `ValidationError`。
- 特殊情况：如果物料刚创建、尚无任何关联数据，允许修正 `base_unit`。

### 9.2 显示单位必须在换算表中

- 规则：`display_unit` 必须是 `base_unit` 本身，或者在 `ItemUnitConversion` 中已定义。
- 实现：在 `Material.save()` / `Product.save()` 中校验。

### 9.3 BOM 单位必须合法

- 规则：`BOM.unit` 必须是 `bom.material` 的合法单位（base_unit 或换算表中的 target_unit）。
- 实现：在 `BOM.clean()` / `BOM.save()` 中校验。

### 9.4 换算表的 base_unit 必须一致

- 规则：`ItemUnitConversion.base_unit` 必须等于所关联物料/成品的 `base_unit`。
- 实现：在 `ItemUnitConversion.clean()` 中校验。

### 9.5 数量精度

- 规则：所有基础单位下的数量保留 2 位小数（`Decimal(10,2)`），换算系数保留 6 位小数（`Decimal(15,6)`）。
- BOM 用量保留 4 位小数（`Decimal(10,4)`），因为可能出现"每件需要 0.0015 吨"等场景。

---

## 十、实施优先级建议

```
阶段一：基础设施（约 2-3 天）
  ├── 1. 修改 Unit 模型（去 is_base，加 symbol）
  ├── 2. 新建 ItemUnitConversion 模型
  ├── 3. 重写 UnitConversionService
  └── 4. 编写数据迁移脚本（Phase 1 + Phase 2）

阶段二：核心模型改造（约 3-4 天）
  ├── 5. 改造 Material（base_unit 必填、display_unit、删旧 unit）
  ├── 6. 改造 Product（同上）
  ├── 7. 改造 BOM（加 unit 字段）
  ├── 8. 改造 Inventory / Batch（去 unit 字段）
  └── 9. 数据迁移 Phase 3

阶段三：业务模块适配（约 3-4 天）
  ├── 10. 改造 production 模块（领料、入库）
  ├── 11. 改造 purchase 模块（采购单）
  ├── 12. 改造 sales 模块（销售订单）
  └── 13. 改造 StockTransaction

阶段四：UI 层适配（约 2-3 天）
  ├── 14. 所有模板加"显示单位换算"
  ├── 15. 所有表单加"单位选择下拉"
  └── 16. 删除旧的"单位变更"页面和服务

阶段五：清理（约 1 天）
  ├── 17. 删除旧模型（PackagingUnit, UnitChangeHistory 等）
  ├── 18. 删除旧服务和视图
  └── 19. 更新管理命令和初始化脚本
```

**预计总工期：约 11-15 天**（单人全职开发）。

---

## 附录 A：新旧模型字段对照速查

### Material

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| `unit` (CharField='kg') | **删除** | 被 display_unit 取代 |
| `base_unit` (FK, NULL) | `base_unit` (FK, NOT NULL) | 改为必填 |
| — | `display_unit` (FK, NOT NULL) | 新增 |
| `unit_price` | `unit_price` | 语义锁定为 base_unit 下的单价 |
| `safety_stock` | `safety_stock` | 语义锁定为 base_unit 下的安全库存 |

### Product

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| `unit` (CharField='件') | **删除** | 被 display_unit 取代 |
| `base_unit` (FK, NULL) | `base_unit` (FK, NOT NULL) | 改为必填 |
| — | `display_unit` (FK, NOT NULL) | 新增 |

### BOM

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| — | `unit` (FK→Unit, NOT NULL) | 新增，BOM 行的用量单位 |

### Inventory

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| `unit` (CharField) | **删除** | 单位 = 关联物料/成品的 base_unit |
| `quantity` | `quantity` | 语义锁定为 base_unit |

### 新增表

| 表 | 替代 |
|----|------|
| `ItemUnitConversion` | `MaterialPackagingUnit` + `ProductPackagingUnit` |

### 删除表

| 表 | 原因 |
|----|------|
| `MaterialPackagingUnit` | 被 ItemUnitConversion 取代 |
| `ProductPackagingUnit` | 被 ItemUnitConversion 取代 |
| `MaterialUnitChangeHistory` | 基础单位不可变，显示单位变更无需历史 |
| `ProductUnitChangeHistory` | 同上 |

---

## 附录 B：完整的换算表示例

### 物料：水泥（base_unit = kg）

| target_unit | factor | 含义 |
|-------------|--------|------|
| 吨 | 1000 | 1 吨 = 1000 kg |
| 袋 | 50 | 1 袋 = 50 kg |

水泥当前 `display_unit = 吨`。

库存实际存储：`quantity = 5000`（单位隐含为 kg）。
UI 展示：`5000 ÷ 1000 = 5 吨`。

BOM 示例：成品"混凝土预制件"(base_unit=件)，BOM 行：水泥, quantity=200, unit=kg。
含义：每 1 件需要 200 kg 水泥。

生产 50 件 → 需要 50 × 200 = 10000 kg 水泥 → 展示为 10 吨。

### 物料：螺丝（base_unit = 个）

| target_unit | factor | 含义 |
|-------------|--------|------|
| 箱 | 500 | 1 箱 = 500 个 |
| 包 | 50 | 1 包 = 50 个 |

### 成品：防水涂料 A（base_unit = kg）

| target_unit | factor | 含义 |
|-------------|--------|------|
| 桶 | 20 | 1 桶 = 20 kg |
| 吨 | 1000 | 1 吨 = 1000 kg |

display_unit = 桶。
BOM 行：树脂, quantity=0.75, unit=kg → 每 1 kg 成品需要 0.75 kg 树脂。
生产 10 桶 = 200 kg 成品 → 需要 200 × 0.75 = 150 kg 树脂。
