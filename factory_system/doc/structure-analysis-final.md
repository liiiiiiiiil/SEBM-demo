# 项目结构分析报告（最终版）

**分析时间**：2026-01-17  
**项目状态**：半成品（开发中，已完成重要重构）  
**分析目的**：梳理当前模块职责，识别结构不一致和边界模糊之处

---

## 一、目录结构概览

```
factory_system/
├── accounts/          # 用户认证与权限管理
├── inventory/         # 库存管理（核心数据模块）
├── sales/             # 销售订单管理（含Customer管理）
├── production/        # 生产任务管理
├── logistics/         # 物流发货管理（含ShippingNotice）
├── purchase/          # 采购任务管理（含Supplier管理）
├── templates/         # 模板文件（统一管理）
├── media/             # 媒体文件（上传文件）
└── factory_system/    # 项目配置（settings, urls）
```

---

## 二、模块职责总结

### 2.1 accounts（账户模块）

**职责边界**：
- ✅ 用户登录/登出认证
- ✅ 用户角色定义（7种角色：sales, sales_mgr, warehouse, production, qc, logistics, ceo）
- ✅ 权限代码定义与管理（29个权限，5个分类）
- ✅ 权限检查装饰器（`@role_required`, `@permission_required`, `@role_or_permission_required`）
- ✅ 模板标签（`has_permission`）
- ✅ 仪表板（Dashboard）展示

**核心模型**：
- `Permission`：系统权限定义表
- `UserProfile`：用户角色扩展表（与Django User一对一关联）

**对外提供**：
- 权限检查装饰器（供其他模块使用）
- 用户角色信息查询接口

**对外依赖**：
- Django内置的`auth.User`模型

**结构状态**：✅ **清晰稳定**

---

### 2.2 inventory（库存模块）

**职责边界**：
- ✅ 产品（Product）与原料（Material）基础信息管理
- ✅ BOM配方管理（成品与原料的配比关系）
- ✅ 实时库存（Inventory）管理（支持成品、原料、其它类型）
- ✅ 库存批次（Batch）管理（含锁定数量功能）
- ✅ 库存变动记录（StockTransaction）
- ✅ 库存调整申请与审批（InventoryAdjustmentRequest）

**核心模型**：
- `MaterialCategory`：原料分类
- `Material`：原料信息
- `ProductCategory`：成品分类
- `Product`：成品信息
- `BOM`：BOM配方
- `Inventory`：实时库存
- `Batch`：库存批次（含`locked_quantity`字段）
- `StockTransaction`：库存变动记录
- `InventoryAdjustmentRequest`：库存调整申请

**对外提供**：
- 产品信息（供sales、production模块使用）
- 原料信息（供production、purchase模块使用）
- BOM配方（供production模块计算领料需求）
- 库存查询与更新接口（供其他模块调用）
- 库存变动记录（供其他模块记录库存变化）

**对外依赖**：
- `auth.User`（操作人、审批人等）

**结构状态**：✅ **清晰稳定**

**注意点**：
- ⚠️ `Batch.supplier`仍使用CharField字符串字段（见下文"结构不一致"部分）

---

### 2.3 sales（销售模块）

**职责边界**：
- ✅ 客户信息管理（Customer）- 含编辑/删除审批流程、客户转移
- ✅ 销售订单（SalesOrder）创建、编辑、审批
- ✅ 订单明细（SalesOrderItem）管理
- ✅ 订单批次分配（SalesOrderItemBatch）
- ✅ 订单状态流转控制
- ✅ 订单审批后触发库存研判与生产任务创建
- ✅ 核心业务函数：`check_inventory_and_create_tasks()`, `terminate_order_chain()`

**核心模型**：
- `Customer`：客户信息（✅ **已从inventory迁移**）
- `CustomerTransfer`：客户转移记录（✅ **已从inventory迁移**）
- `SalesOrder`：销售订单
- `SalesOrderItem`：订单明细
- `SalesOrderItemBatch`：订单明细批次分配

**对外依赖**：
- `inventory.Product`（产品信息）
- `inventory.Inventory`（库存查询）
- `inventory.Batch`（批次分配）
- `inventory.BOM`（检查原材料是否充足）
- `production.ProductionTask`（创建生产任务）
- `auth.User`（销售员、审批人等）

**对外提供**：
- 客户信息（供其他模块查询）
- 销售订单信息（供production、logistics模块使用）
- 订单终结函数（`terminate_order_chain`供production模块调用）

**结构状态**：✅ **职责边界已明确**

---

### 2.4 production（生产模块）

**职责边界**：
- ✅ 生产任务（ProductionTask）管理（订单生产、备货生产）
- ✅ 领料单（MaterialRequisition）创建与审批
- ✅ 领料单明细（MaterialRequisitionItem）管理
- ✅ 质检记录（QCRecord）管理
- ✅ 成品入库单（FinishedProductInbound）管理
- ✅ 根据BOM自动计算领料需求
- ✅ 生产任务接收时自动创建领料单
- ✅ 生产完成后检查订单是否可发货

**核心模型**：
- `ProductionTask`：生产任务单
- `MaterialRequisition`：领料单
- `MaterialRequisitionItem`：领料单明细
- `QCRecord`：质检记录
- `FinishedProductInbound`：成品入库单

**对外依赖**：
- `sales.SalesOrder`（关联订单）
- `inventory.Product`（产品信息）
- `inventory.Material`（原料信息）
- `inventory.BOM`（计算领料需求）
- `inventory.Inventory`（查询与更新库存）
- `inventory.Batch`（批次扣减）
- `inventory.StockTransaction`（记录库存变动）
- `logistics.ShippingNotice`（创建发货通知单）
- `sales.views.terminate_order_chain`（终结订单链）- ⚠️ **跨模块视图调用**

**对外提供**：
- 生产任务信息（供sales模块查询订单生产状态）
- 生产完成触发订单状态更新

**结构状态**：⚠️ **存在跨模块视图调用**

---

### 2.5 logistics（物流模块）

**职责边界**：
- ✅ 发货通知单（ShippingNotice）管理（✅ **已从sales迁移**）
- ✅ 发货单（Shipment）创建与管理
- ✅ 司机（Driver）信息管理
- ✅ 车辆（Vehicle）信息管理
- ✅ 发货回执图片（ShipmentImage）管理
- ✅ 发货确认与库存扣减
- ✅ 收货回执录入

**核心模型**：
- `ShippingNotice`：发货通知单（✅ **已从sales迁移**）
- `Driver`：司机信息
- `Vehicle`：车辆信息
- `Shipment`：发货单
- `ShipmentImage`：发货回执图片

**对外依赖**：
- `sales.SalesOrder`（关联订单）
- `inventory.Inventory`（扣减成品库存）
- `inventory.Batch`（批次扣减）
- `inventory.StockTransaction`（记录库存变动）
- `sales.SalesOrderItemBatch`（订单批次分配）
- `auth.User`（操作人）

**对外提供**：
- 发货通知单（供production模块创建）
- 发货单信息（供订单状态查询）

**结构状态**：✅ **职责边界已明确**

---

### 2.6 purchase（采购模块）

**职责边界**：
- ✅ 采购任务（PurchaseTask）创建、审批、完成
- ✅ 采购任务明细（PurchaseTaskItem）管理
- ✅ 供应商（Supplier）信息管理
- ✅ 采购收货与库存入库
- ✅ 批次创建与管理
- ✅ 从生产任务跳转创建采购任务（支持预填原料）

**核心模型**：
- `Supplier`：供应商信息
- `PurchaseTask`：采购任务（✅ **supplier已改为ForeignKey**）
- `PurchaseTaskItem`：采购任务明细

**对外依赖**：
- `inventory.Material`（原料信息）
- `inventory.Inventory`（增加库存）
- `inventory.Batch`（创建批次）
- `inventory.StockTransaction`（记录库存变动）
- `production.ProductionTask`（从生产任务跳转）
- `inventory.BOM`（计算原料需求）
- `auth.User`（操作人、审批人等）

**对外提供**：
- 采购任务信息（供生产模块查询原材料是否充足）

**结构状态**：✅ **职责边界已明确，supplier问题已解决**

**重构变化**：
- ✅ `PurchaseTask.supplier`已从CharField改为ForeignKey(Supplier)
- ✅ `PurchaseTask.contact_person`和`contact_phone`字段已移除
- ✅ 迁移文件`0004_remove_purchasetask_contact_person_and_more.py`完成了数据迁移

---

## 三、结构不一致与模糊之处

### 3.1 Batch.supplier数据不一致 ⚠️ **轻微不一致**

**问题描述**：
- `purchase.PurchaseTask.supplier`：已改为`ForeignKey(Supplier)` ✅
- `inventory.Batch.supplier`：仍使用`CharField`字符串字段 ⚠️

**证据**：
- `inventory/models.py`：`Batch.supplier = CharField(max_length=200, blank=True)`
- `purchase/views.py`：创建Batch时使用`supplier=task.supplier.name`（第354行）

**影响**：
- 数据不一致：Batch中的supplier是字符串，无法建立与Supplier的关联
- 无法统计：无法直接统计供应商的批次信息
- 信息可能不同步：如果Supplier名称更新，Batch中的字符串不会自动更新

**建议边界**：
- **暂时冻结**：保持现状，Batch.supplier继续使用字符串字段
- **当前理解**：Batch是历史记录，supplier字段主要用于记录，不需要关联查询
- **未来考虑**：如果需要统计供应商的批次信息，可以考虑改为ForeignKey或添加supplier_name字段

---

### 3.2 跨模块视图调用 ⚠️ **耦合度较高**

**问题描述**：
- `production.views`中直接导入`sales.views.terminate_order_chain`
- 模块间存在视图层直接调用

**证据**：
- `production/views.py`：`from sales.views import terminate_order_chain`
- `production/views.py`：在领料单终结时调用`terminate_order_chain`

**影响**：
- 模块间耦合度高
- 不利于模块独立测试和维护
- 违反模块化设计原则

**建议边界**：
- **暂时冻结**：保持现状，允许跨模块视图调用
- **当前理解**：这是业务流程的需要，production模块需要通知sales模块更新订单状态
- **未来考虑**：可以考虑将`terminate_order_chain`移到服务层（如`factory_system/services/`）或使用信号机制

---

### 3.3 Batch.locked_quantity新功能 ⚠️ **新功能，需关注**

**问题描述**：
- `inventory.Batch`模型新增了`locked_quantity`字段（锁定数量）
- 新增了`get_available_quantity()`方法（获取可用数量 = 总数量 - 锁定数量）

**证据**：
- `inventory/models.py`：`Batch.locked_quantity = DecimalField(...)`
- `inventory/models.py`：`Batch.get_available_quantity()`方法

**影响**：
- 这是新功能，需要确保所有使用Batch的地方都考虑锁定数量
- 需要确保库存扣减时使用可用数量而不是总数量

**建议边界**：
- **当前状态**：新功能，需要全面测试
- **关注点**：确保库存扣减逻辑正确处理锁定数量
- **暂时冻结**：保持现状，不修改锁定数量的逻辑

---

## 四、"暂时冻结"的结构边界

### 4.1 已明确冻结的功能

**无** - 所有历史遗留问题已解决

### 4.2 保持现状但需注意的边界

1. **`inventory.Batch.supplier`字段**
   - 类型：CharField（字符串）
   - 状态：保持现状，不使用ForeignKey(Supplier)
   - 边界：**不修改为ForeignKey**

2. **跨模块视图调用**
   - 示例：`production.views`调用`sales.views.terminate_order_chain`
   - 状态：允许，但需谨慎
   - 边界：**不增加新的跨模块视图调用，除非业务必需**

3. **`Batch.locked_quantity`字段**
   - 状态：新功能，需要全面测试
   - 边界：**确保所有库存操作正确处理锁定数量**

---

## 五、模块间依赖关系图

```
accounts (独立)
    ↑ (所有模块依赖，用于权限检查)

inventory (核心数据模块)
    ↑
    ├── sales (依赖Product, Inventory, Batch, BOM)
    ├── production (依赖Product, Material, BOM, Inventory, Batch)
    ├── purchase (依赖Material, Inventory, Batch, BOM)
    └── logistics (依赖Inventory, Batch)

sales
    ├── → production (创建ProductionTask)
    └── → production.views (提供terminate_order_chain函数)

production
    ├── → sales (更新订单状态)
    ├── → sales.views (调用terminate_order_chain) ⚠️
    ├── → logistics (创建ShippingNotice)
    └── → purchase (跳转到采购任务创建)

logistics
    └── → sales (依赖SalesOrder, SalesOrderItemBatch)

purchase
    ├── → inventory (依赖Material, Inventory, Batch)
    └── → production (从生产任务跳转)
```

---

## 六、重构总结

### 6.1 已解决的结构问题 ✅

1. **Customer模型位置** ✅
   - **重构前**：在inventory模块，但主要用于sales业务
   - **重构后**：已迁移到sales模块，职责归属清晰

2. **ShippingNotice职责归属** ✅
   - **重构前**：在sales模块，但logistics大量使用
   - **重构后**：已迁移到logistics模块，职责归属清晰

3. **PurchaseOrder功能重复** ✅
   - **重构前**：inventory.PurchaseOrder与purchase.PurchaseTask功能重复
   - **重构后**：PurchaseOrder已完全删除，只保留PurchaseTask

4. **PurchaseTask.supplier数据不一致** ✅
   - **重构前**：使用CharField字符串字段，Supplier模型存在但不使用
   - **重构后**：已改为ForeignKey(Supplier)，contact_person和contact_phone字段已移除

### 6.2 仍需关注的问题 ⚠️

1. **Batch.supplier数据不一致**
   - Batch.supplier仍使用字符串字段
   - 影响较小，因为Batch是历史记录，主要用于追溯

2. **跨模块视图调用**
   - production.views直接调用sales.views.terminate_order_chain
   - 耦合度较高，但符合当前业务需求

3. **Batch.locked_quantity新功能**
   - 需要确保所有库存操作正确处理锁定数量

### 6.3 架构评价（最终版）

**优点**：
- ✅ 模块职责清晰（Customer在sales，ShippingNotice在logistics，Supplier在purchase）
- ✅ 消除了功能重复（PurchaseOrder已删除）
- ✅ 解决了数据不一致（PurchaseTask.supplier已改为ForeignKey）
- ✅ 模块划分基本合理，按业务领域组织
- ✅ 权限系统设计清晰

**待改进**：
- ⚠️ Batch.supplier仍使用字符串（影响较小）
- ⚠️ 跨模块视图调用需要更好的抽象（可考虑服务层或信号机制）
- ⚠️ Batch.locked_quantity新功能需要全面测试

---

## 七、重构前后对比

| 问题项 | 重构前 | 重构后 | 状态 |
|--------|--------|--------|------|
| Customer模型位置 | inventory模块 | sales模块 | ✅ 已解决 |
| ShippingNotice位置 | sales模块 | logistics模块 | ✅ 已解决 |
| PurchaseOrder重复 | 存在重复 | 已删除 | ✅ 已解决 |
| PurchaseTask.supplier | CharField | ForeignKey(Supplier) | ✅ 已解决 |
| Batch.supplier | CharField | CharField | ⚠️ 仍存在（影响较小） |
| 跨模块视图调用 | 存在 | 仍存在 | ⚠️ 仍存在 |
| Batch.locked_quantity | 不存在 | 新增 | ⚠️ 新功能 |

---

## 八、总结

### 8.1 当前状态

项目结构已经过重要重构，主要结构问题已解决：
- ✅ Customer已迁移到sales模块
- ✅ ShippingNotice已迁移到logistics模块
- ✅ PurchaseOrder已删除
- ✅ PurchaseTask.supplier已改为ForeignKey

### 8.2 剩余问题

剩余问题影响较小：
- ⚠️ Batch.supplier使用字符串（历史记录，影响较小）
- ⚠️ 跨模块视图调用（业务需要，可接受）
- ⚠️ Batch.locked_quantity新功能（需要测试）

### 8.3 建议

**短期（保持现状）**：
- ✅ 保持当前结构，不进行大规模重构
- ✅ 关注Batch.locked_quantity新功能的测试
- ✅ 确保库存操作正确处理锁定数量

**长期（可选优化）**：
- ⚠️ 考虑将跨模块视图调用移到服务层
- ⚠️ 如果需要统计供应商批次信息，可考虑Batch.supplier改为ForeignKey

**暂时冻结**：
- ⚠️ Batch.supplier保持字符串字段
- ⚠️ 不增加新的跨模块视图调用
- ⚠️ 不修改Batch.locked_quantity的逻辑

---

**文档生成时间**：2026-01-17  
**分析人员**：AI Assistant  
**文档状态**：最终分析报告，反映最新重构状态
