# 项目结构分析报告

**分析时间**：2026-01-14  
**项目状态**：半成品（开发中）  
**分析目的**：梳理现有模块职责，识别结构不一致和边界模糊之处

---

## 一、目录结构概览

```
factory_system/
├── accounts/          # 用户认证与权限管理
├── inventory/         # 库存管理
├── sales/             # 销售订单管理
├── production/        # 生产任务管理
├── logistics/         # 物流发货管理
├── purchase/          # 采购任务管理
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
- ✅ 客户信息管理（Customer）- 含编辑/删除审批流程
- ✅ 产品（Product）与原料（Material）基础信息管理
- ✅ BOM配方管理（成品与原料的配比关系）
- ✅ 实时库存（Inventory）管理（支持成品、原料、其它类型）
- ✅ 库存批次（Batch）管理
- ✅ 库存变动记录（StockTransaction）
- ✅ 库存调整申请与审批（InventoryAdjustmentRequest）
- ⚠️ **采购单（PurchaseOrder）管理** - **历史遗留，职责边界模糊**

**核心模型**：
- `Customer`：客户信息（⚠️ 职责边界模糊，主要用于销售）
- `Product`：成品信息
- `Material`：原料信息
- `BOM`：BOM配方
- `Inventory`：实时库存
- `Batch`：库存批次
- `StockTransaction`：库存变动记录
- `InventoryAdjustmentRequest`：库存调整申请
- `PurchaseOrder` / `PurchaseOrderItem`：采购单（⚠️ 历史遗留）

**对外提供**：
- 客户信息（供sales模块使用）
- 产品信息（供sales、production模块使用）
- 原料信息（供production、purchase模块使用）
- BOM配方（供production模块计算领料需求）
- 库存查询与更新接口（供其他模块调用）
- 库存变动记录（供其他模块记录库存变化）

**对外依赖**：
- `auth.User`（操作人、审批人等）

**结构状态**：⚠️ **存在职责边界模糊**

**问题点**：
1. `Customer`模型在inventory模块，但主要用于销售业务，职责归属不清晰
2. `PurchaseOrder`模型在inventory模块，但purchase模块已有`PurchaseTask`，存在功能重复

---

### 2.3 sales（销售模块）

**职责边界**：
- ✅ 销售订单（SalesOrder）创建、编辑、审批
- ✅ 订单明细（SalesOrderItem）管理
- ✅ 订单批次分配（SalesOrderItemBatch）
- ✅ 发货通知单（ShippingNotice）创建
- ✅ 订单状态流转控制
- ✅ 订单审批后触发库存研判与生产任务/发货通知单创建
- ✅ 核心业务函数：`check_inventory_and_create_tasks()`, `terminate_order_chain()`

**核心模型**：
- `SalesOrder`：销售订单
- `SalesOrderItem`：订单明细
- `SalesOrderItemBatch`：订单明细批次分配
- `ShippingNotice`：发货通知单（⚠️ 职责边界模糊，logistics模块也使用）

**对外依赖**：
- `inventory.Customer`（客户信息）
- `inventory.Product`（产品信息）
- `inventory.Inventory`（库存查询）
- `inventory.Batch`（批次分配）
- `inventory.BOM`（检查原材料是否充足）
- `production.ProductionTask`（创建生产任务）
- `auth.User`（销售员、审批人等）

**对外提供**：
- 销售订单信息（供production、logistics模块使用）
- 发货通知单（供logistics模块使用）

**结构状态**：⚠️ **存在职责边界模糊**

**问题点**：
1. `ShippingNotice`在sales模块，但logistics模块也大量使用，职责归属不清晰

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
- `sales.ShippingNotice`（创建发货通知单）
- `sales.views.terminate_order_chain`（终结订单链）

**对外提供**：
- 生产任务信息（供sales模块查询订单生产状态）
- 生产完成触发订单状态更新

**结构状态**：✅ **清晰稳定**

---

### 2.5 logistics（物流模块）

**职责边界**：
- ✅ 发货单（Shipment）创建与管理
- ✅ 司机（Driver）信息管理
- ✅ 车辆（Vehicle）信息管理
- ✅ 发货回执图片（ShipmentImage）管理
- ✅ 发货确认与库存扣减
- ✅ 收货回执录入

**核心模型**：
- `Driver`：司机信息
- `Vehicle`：车辆信息
- `Shipment`：发货单
- `ShipmentImage`：发货回执图片

**对外依赖**：
- `sales.ShippingNotice`（发货通知单）- ⚠️ 跨模块依赖
- `sales.SalesOrder`（关联订单）
- `inventory.Inventory`（扣减成品库存）
- `inventory.Batch`（批次扣减）
- `inventory.StockTransaction`（记录库存变动）
- `sales.SalesOrderItemBatch`（订单批次分配）

**对外提供**：
- 发货单信息（供订单状态查询）

**结构状态**：⚠️ **存在职责边界模糊**

**问题点**：
1. 依赖`sales.ShippingNotice`，但ShippingNotice的创建和管理在sales模块，职责边界不清晰

---

### 2.6 purchase（采购模块）

**职责边界**：
- ✅ 采购任务（PurchaseTask）创建、审批、完成
- ✅ 采购任务明细（PurchaseTaskItem）管理
- ✅ 供应商（Supplier）信息管理
- ✅ 采购收货与库存入库
- ✅ 批次创建与管理

**核心模型**：
- `Supplier`：供应商信息
- `PurchaseTask`：采购任务
- `PurchaseTaskItem`：采购任务明细

**对外依赖**：
- `inventory.Material`（原料信息）
- `inventory.Inventory`（增加库存）
- `inventory.Batch`（创建批次）
- `inventory.StockTransaction`（记录库存变动）
- `auth.User`（操作人、审批人等）

**对外提供**：
- 采购任务信息（供生产模块查询原材料是否充足）

**结构状态**：⚠️ **存在职责边界模糊**

**问题点**：
1. `inventory.PurchaseOrder`与`purchase.PurchaseTask`功能重复，职责边界不清晰
2. `PurchaseTask.supplier`使用字符串字段，而`Supplier`模型存在，数据不一致

---

## 三、结构不一致与模糊之处

### 3.1 采购功能重复 ⚠️ **严重不一致**

**问题描述**：
- `inventory.PurchaseOrder` / `PurchaseOrderItem`：在inventory模块中，有完整的模型、admin、模板文件
- `purchase.PurchaseTask` / `PurchaseTaskItem`：在purchase模块中，是新的采购任务系统

**证据**：
- `inventory/models.py`：定义了`PurchaseOrder`和`PurchaseOrderItem`
- `inventory/admin.py`：注册了`PurchaseOrderAdmin`和`PurchaseOrderItemAdmin`
- `templates/inventory/purchase_order_*.html`：存在4个模板文件
- `purchase/models.py`：定义了`PurchaseTask`和`PurchaseTaskItem`
- `doc/architecture-description.md`：明确标注`PurchaseOrder`为"历史遗留，部分功能"

**影响**：
- 开发人员困惑：应该使用哪个采购系统？
- 数据可能分散在两个模型中
- 维护成本增加

**建议边界**：
- **暂时冻结**：`inventory.PurchaseOrder`相关功能（模型、admin、views、templates）
- **当前使用**：`purchase.PurchaseTask`作为唯一采购系统

---

### 3.2 Customer模型位置 ⚠️ **职责边界模糊**

**问题描述**：
- `Customer`模型在`inventory`模块中
- 但Customer主要用于销售业务（sales模块大量使用）
- 从业务逻辑看，Customer更像是销售模块的基础数据

**证据**：
- `inventory/models.py`：定义了`Customer`模型
- `sales/models.py`：`SalesOrder.customer = ForeignKey(Customer)`
- `sales/views.py`：大量使用Customer
- `inventory/views.py`：也有Customer的CRUD操作

**影响**：
- 职责归属不清晰：Customer是库存管理的一部分还是销售管理的一部分？
- 跨模块依赖增加复杂度

**建议边界**：
- **暂时冻结**：保持现状，Customer继续在inventory模块
- **未来考虑**：如果重构，可考虑迁移到sales模块或创建独立的`common`模块

---

### 3.3 ShippingNotice职责归属 ⚠️ **职责边界模糊**

**问题描述**：
- `ShippingNotice`模型在`sales`模块中
- 但`logistics`模块大量使用ShippingNotice创建发货单
- 从业务逻辑看，ShippingNotice更像是物流模块的输入

**证据**：
- `sales/models.py`：定义了`ShippingNotice`模型
- `logistics/models.py`：`Shipment.shipping_notice = ForeignKey(ShippingNotice)`
- `logistics/views.py`：大量使用ShippingNotice
- `production/views.py`：创建ShippingNotice

**影响**：
- 职责归属不清晰：ShippingNotice是销售流程的一部分还是物流流程的一部分？
- sales模块需要了解物流业务逻辑

**建议边界**：
- **暂时冻结**：保持现状，ShippingNotice继续在sales模块
- **当前理解**：ShippingNotice是销售订单审批后生成的"发货指令"，属于销售流程的输出，物流模块消费

---

### 3.4 Supplier数据不一致 ⚠️ **数据模型不一致**

**问题描述**：
- `purchase.Supplier`：定义了完整的供应商模型（name, contact_person, contact_phone等）
- `purchase.PurchaseTask.supplier`：使用CharField字符串字段
- `inventory.PurchaseOrder.supplier`：也使用CharField字符串字段

**证据**：
- `purchase/models.py`：定义了`Supplier`模型
- `purchase/models.py`：`PurchaseTask.supplier = CharField(max_length=200)`
- `inventory/models.py`：`PurchaseOrder.supplier = CharField(max_length=200)`

**影响**：
- 数据不一致：Supplier模型存在但未使用
- 无法建立供应商与采购任务的关联关系
- 无法统一管理供应商信息

**建议边界**：
- **暂时冻结**：保持现状，PurchaseTask继续使用字符串supplier字段
- **未来考虑**：如果重构，将PurchaseTask.supplier改为ForeignKey(Supplier)

---

### 3.5 跨模块函数调用 ⚠️ **耦合度较高**

**问题描述**：
- `production.views`中直接导入`sales.views.terminate_order_chain`
- 模块间存在视图层直接调用

**证据**：
- `production/views.py`：`from sales.views import terminate_order_chain`
- `production/views.py`：在领料单终结时调用`terminate_order_chain`

**影响**：
- 模块间耦合度高
- 不利于模块独立测试和维护

**建议边界**：
- **暂时冻结**：保持现状，允许跨模块视图调用
- **当前理解**：这是业务流程的需要，production模块需要通知sales模块更新订单状态

---

### 3.6 模板文件组织 ⚠️ **部分不一致**

**问题描述**：
- 大部分模板按模块组织在`templates/{module}/`目录下
- 但`purchase_order`相关模板在`templates/inventory/`目录下（对应历史遗留的PurchaseOrder）

**证据**：
- `templates/inventory/purchase_order_*.html`：4个模板文件
- `templates/purchase/task_*.html`：采购任务相关模板

**影响**：
- 模板文件位置与当前使用的模型不一致

**建议边界**：
- **暂时冻结**：保持现状，purchase_order模板继续在inventory目录
- **当前理解**：这些模板对应历史遗留的PurchaseOrder功能，暂时不使用

---

## 四、"暂时冻结"的结构边界

### 4.1 已明确冻结的功能

1. **`inventory.PurchaseOrder` / `PurchaseOrderItem`**
   - 位置：`inventory/models.py`
   - 状态：历史遗留，功能不完整
   - 冻结范围：
     - 模型定义（保留，不删除）
     - Admin注册（保留，不删除）
     - 模板文件（保留，不删除）
     - **不开发新的views或功能**
     - **不使用此模型进行新开发**

2. **`inventory.PurchaseOrder`相关模板**
   - 位置：`templates/inventory/purchase_order_*.html`
   - 状态：历史遗留
   - 冻结范围：**不修改、不使用**

### 4.2 保持现状但需注意的边界

1. **`inventory.Customer`**
   - 位置：`inventory/models.py`
   - 状态：保持现状，继续在inventory模块
   - 边界：**不迁移，不重构**

2. **`sales.ShippingNotice`**
   - 位置：`sales/models.py`
   - 状态：保持现状，继续在sales模块
   - 边界：**不迁移，不重构**

3. **`purchase.PurchaseTask.supplier`字段**
   - 类型：CharField（字符串）
   - 状态：保持现状，不使用ForeignKey(Supplier)
   - 边界：**不修改为ForeignKey**

4. **跨模块视图调用**
   - 示例：`production.views`调用`sales.views.terminate_order_chain`
   - 状态：允许，但需谨慎
   - 边界：**不增加新的跨模块视图调用，除非业务必需**

---

## 五、模块间依赖关系图

```
accounts (独立)
    ↑ (所有模块依赖，用于权限检查)

inventory (核心数据模块)
    ↑
    ├── sales (依赖Customer, Product, Inventory, Batch, BOM)
    ├── production (依赖Product, Material, BOM, Inventory, Batch)
    ├── purchase (依赖Material, Inventory, Batch)
    └── logistics (依赖Inventory, Batch)

sales
    ├── → production (创建ProductionTask)
    └── → logistics (提供ShippingNotice)

production
    ├── → sales (更新订单状态, 创建ShippingNotice)
    └── → sales.views (调用terminate_order_chain)

logistics
    └── → sales (依赖ShippingNotice, SalesOrder)

purchase
    └── (独立，只依赖inventory)
```

---

## 六、总结

### 6.1 结构清晰的部分 ✅

1. **accounts模块**：职责清晰，边界明确
2. **production模块**：职责清晰，边界明确
3. **模块划分原则**：按业务领域划分，符合Django最佳实践

### 6.2 需要关注的不一致 ⚠️

1. **采购功能重复**：PurchaseOrder vs PurchaseTask
2. **Customer位置**：在inventory但主要用于sales
3. **ShippingNotice位置**：在sales但logistics大量使用
4. **Supplier数据不一致**：模型存在但未使用
5. **跨模块视图调用**：耦合度较高

### 6.3 建议的冻结边界

1. **明确冻结**：`inventory.PurchaseOrder`相关功能
2. **保持现状**：Customer、ShippingNotice、PurchaseTask.supplier字段
3. **谨慎使用**：跨模块视图调用

### 6.4 架构评价

**优点**：
- 模块划分基本合理，按业务领域组织
- 权限系统设计清晰
- 数据模型关系明确

**待改进**：
- 部分职责边界需要进一步明确
- 历史遗留代码需要清理或文档化
- 跨模块依赖需要更好的抽象

---

**文档生成时间**：2026-01-14  
**分析人员**：AI Assistant  
**文档状态**：分析报告，供开发参考
