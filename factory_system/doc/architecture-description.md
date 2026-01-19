# 工厂管理系统架构描述

## 一、工程结构概览

本项目是一个基于Django 5.2的工厂销售和生产流程管理系统，采用标准的Django应用（App）模块化架构。

### 技术栈
- **框架**：Django 5.2.9
- **数据库**：SQLite（开发）/ PostgreSQL（生产）
- **前端**：Bootstrap 5 + Django模板
- **权限系统**：基于角色的访问控制（RBAC）

### 应用模块列表
1. `accounts` - 用户认证与权限管理
2. `inventory` - 库存管理
3. `sales` - 销售订单管理
4. `production` - 生产任务管理
5. `logistics` - 物流发货管理
6. `purchase` - 采购任务管理

---

## 二、模块边界与职责

### 2.1 accounts（账户模块）

**职责边界**：
- 用户登录/登出认证
- 用户角色定义（销售员、销售经理、仓库管理员、生产管理员、质检员、物流管理员、总经理）
- 权限代码定义与管理
- 用户角色与权限的关联
- 仪表板（Dashboard）展示

**核心模型**：
- `Permission`：系统权限定义表
- `UserProfile`：用户角色扩展表（与Django User一对一关联）

**对外依赖**：
- 依赖Django内置的`auth.User`模型
- 其他模块通过装饰器`@role_required`或`@role_or_permission_required`调用权限检查

**对外提供**：
- 权限检查装饰器（供其他模块使用）
- 用户角色信息（供其他模块查询）

---

### 2.2 inventory（库存模块）

**职责边界**：
- 产品（Product）与原料（Material）基础信息管理
- BOM配方管理（成品与原料的配比关系）
- 实时库存（Inventory）管理
- 库存批次（Batch）管理（支持锁定数量）
- 库存变动记录（StockTransaction）
- 库存调整申请与审批

**核心模型**：
- `Product`：成品信息
- `Material`：原料信息
- `BOM`：BOM配方（成品→原料配比）
- `Inventory`：实时库存（支持成品、原料、其它类型）
- `Batch`：库存批次（含锁定数量字段）
- `StockTransaction`：库存变动记录
- `InventoryAdjustmentRequest`：库存调整申请

**对外依赖**：
- 依赖`auth.User`（操作人、审批人等）

**对外提供**：
- 产品信息（供sales、production模块使用）
- 原料信息（供production、purchase模块使用）
- BOM配方（供production模块计算领料需求）
- 库存查询与更新接口（供其他模块调用）
- 批次管理（含锁定数量功能，供sales模块锁定库存）
- 库存变动记录（供其他模块记录库存变化）

**关键业务逻辑**：
- 库存支持批次管理（FIFO原则）
- 批次支持锁定数量（`locked_quantity`字段），用于订单审批时锁定库存
- 批次可用数量 = 总数量 - 锁定数量（`get_available_quantity()`方法）
- 库存数量从批次汇总计算
- 库存类型分为：成品（product）、原料（material）、其它（other）

---

### 2.3 sales（销售模块）

**职责边界**：
- 客户信息管理（Customer，含编辑/删除审批流程、客户转移）
- 销售订单（SalesOrder）创建、编辑、审批
- 订单明细（SalesOrderItem）管理
- 订单批次分配（SalesOrderItemBatch）
- 订单状态流转控制
- 订单审批后触发库存研判与生产任务/发货通知单创建
- 订单批次库存锁定（通过`Batch.locked_quantity`）

**核心模型**：
- `Customer`：客户信息（含软删除、编辑/删除审批流程）
- `CustomerTransfer`：客户转移记录
- `SalesOrder`：销售订单
- `SalesOrderItem`：订单明细
- `SalesOrderItemBatch`：订单明细批次分配

**对外依赖**：
- 依赖`inventory.Product`（产品信息）
- 依赖`inventory.Inventory`（库存查询）
- 依赖`inventory.Batch`（批次分配与锁定）
- 依赖`inventory.BOM`（检查原材料是否充足）
- 依赖`production.ProductionTask`（创建生产任务）
- 依赖`logistics.ShippingNotice`（创建发货通知单）
- 依赖`auth.User`（销售员、审批人等）

**对外提供**：
- 客户信息（供订单创建使用）
- 销售订单信息（供production、logistics模块使用）
- 订单批次分配信息（供logistics模块发货时使用）

**关键业务逻辑**：
- 客户管理支持软删除（`is_deleted`字段）
- 客户编辑/删除需要审批流程
- 订单审批流程：销售员创建 → 销售经理审批 → 总经理审批
- 总经理审批时：
  - 按批次FIFO分配库存，记录到`SalesOrderItemBatch`
  - 锁定批次库存（`batch.locked_quantity += 分配数量`）
  - 自动进行库存研判：
    - 如果库存充足：创建发货通知单，订单状态→待发货
    - 如果库存不足：计算缺口，检查原材料是否充足，创建生产任务，订单状态→生产中
- 订单状态包括：待审批、已审批、待总经理审批、总经理已审批、已退回、生产中、待发货、已发货、已完成、已取消、已终结

---

### 2.4 production（生产模块）

**职责边界**：
- 生产任务（ProductionTask）管理（订单生产、备货生产）
- 领料单（MaterialRequisition）创建与审批
- 领料单明细（MaterialRequisitionItem）管理
- 质检记录（QCRecord）管理
- 成品入库单（FinishedProductInbound）管理
- 根据BOM自动计算领料需求
- 生产任务接收时自动创建领料单
- 生产完成后检查订单是否可发货

**核心模型**：
- `ProductionTask`：生产任务单
- `MaterialRequisition`：领料单
- `MaterialRequisitionItem`：领料单明细
- `QCRecord`：质检记录
- `FinishedProductInbound`：成品入库单

**对外依赖**：
- 依赖`sales.SalesOrder`（关联订单）
- 依赖`inventory.Product`（产品信息）
- 依赖`inventory.Material`（原料信息）
- 依赖`inventory.BOM`（计算领料需求）
- 依赖`inventory.Inventory`（查询与更新库存）
- 依赖`inventory.Batch`（批次扣减）
- 依赖`inventory.StockTransaction`（记录库存变动）
- 依赖`logistics.ShippingNotice`（创建发货通知单）
- 依赖`auth.User`（操作人、审批人等）

**对外提供**：
- 生产任务信息（供sales模块查询订单生产状态）
- 生产完成触发订单状态更新

**关键业务逻辑**：
- 生产任务类型：订单生产（order）、备货生产（stock）
- 生产任务接收时：
  - 检查原材料库存是否充足
  - 根据BOM自动创建领料单
  - 自动批准领料单并扣减原料库存（按批次FIFO）
- 领料单审批流程：待审核 → 已批准 → 已发料
- 成品入库时：
  - 创建批次
  - 增加成品库存
  - 记录库存变动
  - 检查关联订单是否可发货（如果所有产品库存充足，创建发货通知单）
- 生产任务状态包括：待接收、原料不足、已接收、备料中、生产中、质检中、已完成、已取消、已终结

---

### 2.5 logistics（物流模块）

**职责边界**：
- 发货通知单（ShippingNotice）管理
- 发货单（Shipment）创建与管理
- 司机（Driver）信息管理
- 车辆（Vehicle）信息管理
- 发货回执图片（ShipmentImage）管理
- 发货确认与库存扣减（从锁定数量中扣减）
- 收货回执录入

**核心模型**：
- `ShippingNotice`：发货通知单
- `Driver`：司机信息
- `Vehicle`：车辆信息
- `Shipment`：发货单
- `ShipmentImage`：发货回执图片

**对外依赖**：
- 依赖`sales.SalesOrder`（关联订单）
- 依赖`inventory.Inventory`（扣减成品库存）
- 依赖`inventory.Batch`（批次扣减，从锁定数量中扣减）
- 依赖`inventory.StockTransaction`（记录库存变动）
- 依赖`sales.SalesOrderItemBatch`（订单批次分配）
- 依赖`auth.User`（操作人）

**对外提供**：
- 发货通知单（供sales、production模块查询）
- 发货单信息（供订单状态查询）

**关键业务逻辑**：
- 发货通知单由sales模块或production模块创建
- 根据发货通知单创建发货单
- 分配司机和车辆
- 确认发货时：
  - 按订单批次分配扣减库存（从`Batch.locked_quantity`中扣减，然后扣减`Batch.quantity`）
  - 记录库存变动
  - 更新订单状态为已发货
- 发货单状态包括：待发货、装车中、已发货、已送达

---

### 2.6 purchase（采购模块）

**职责边界**：
- 采购任务（PurchaseTask）创建、审批、完成
- 采购任务明细（PurchaseTaskItem）管理
- 供应商（Supplier）信息管理
- 采购收货与库存入库
- 批次创建与管理

**核心模型**：
- `Supplier`：供应商信息
- `PurchaseTask`：采购任务（supplier字段为ForeignKey关联Supplier）
- `PurchaseTaskItem`：采购任务明细

**对外依赖**：
- 依赖`inventory.Material`（原料信息）
- 依赖`inventory.Inventory`（增加库存）
- 依赖`inventory.Batch`（创建批次）
- 依赖`inventory.StockTransaction`（记录库存变动）
- 依赖`auth.User`（操作人、审批人等）

**对外提供**：
- 采购任务信息（供生产模块查询原材料是否充足）
- 供应商信息（供采购任务关联）

**关键业务逻辑**：
- 采购任务通过ForeignKey关联Supplier（不再使用CharField）
- 采购任务审批流程：待审批 → 已审批 → 采购中 → 已完成
- 采购任务完成时：
  - 创建批次（支持批次号、批次日期、单价、过期日期）
  - 增加原料库存（或其它类型库存）
  - 更新库存总数量（从批次汇总）
  - 记录库存变动（purchase_in类型）
- 支持采购原料、办公用品、其它物品

---

## 三、模块间交互关系

### 3.1 数据流向图

```
销售订单审批
    ↓
库存研判（inventory模块）
    ├─→ 库存充足 → 创建发货通知单 → 物流发货
    └─→ 库存不足 → 创建生产任务
                      ↓
                  生产任务接收（production模块）
                      ↓
                  根据BOM创建领料单
                      ↓
                  领料单审批 → 扣减原料库存（inventory模块）
                      ↓
                  生产完成 → 成品入库 → 增加成品库存（inventory模块）
                      ↓
                  检查订单是否可发货 → 创建发货通知单
                      ↓
                  物流发货 → 扣减成品库存（inventory模块）
```

### 3.2 模块间调用关系

**sales → inventory**：
- 查询产品信息（Product）
- 查询成品库存（Inventory）
- 查询批次信息（Batch）
- 进行批次分配（SalesOrderItemBatch）
- 锁定批次库存（Batch.locked_quantity）
- 查询BOM检查原材料是否充足

**sales → production**：
- 创建生产任务（ProductionTask）

**sales → logistics**：
- 创建发货通知单（ShippingNotice）

**production → inventory**：
- 查询产品信息（Product）
- 查询原料信息（Material）
- 查询BOM配方（BOM）
- 查询原料库存（Inventory）
- 扣减原料库存（Inventory、Batch）
- 增加成品库存（Inventory、Batch）
- 记录库存变动（StockTransaction）

**production → sales**：
- 查询关联订单（SalesOrder）
- 更新订单状态

**production → logistics**：
- 创建发货通知单（ShippingNotice）

**logistics → sales**：
- 查询订单信息（SalesOrder）
- 查询订单批次分配（SalesOrderItemBatch）

**logistics → inventory**：
- 扣减成品库存（Inventory、Batch，从锁定数量中扣减）
- 记录库存变动（StockTransaction）

**purchase → inventory**：
- 查询原料信息（Material）
- 增加原料库存（Inventory、Batch）
- 记录库存变动（StockTransaction）

**所有模块 → accounts**：
- 通过装饰器进行权限检查
- 查询用户角色信息

---

## 四、最小可接受架构描述

### 4.1 架构层次

本系统采用**三层架构**：

1. **表现层（Presentation Layer）**
   - Django模板（HTML + Bootstrap）
   - URL路由配置（各模块的urls.py）
   - 视图函数（views.py）

2. **业务逻辑层（Business Logic Layer）**
   - 视图函数中的业务逻辑
   - 模型方法（models.py中的业务方法）
   - 辅助函数（如`check_inventory_and_create_tasks`、`create_material_requisition`）

3. **数据访问层（Data Access Layer）**
   - Django ORM模型（models.py）
   - 数据库迁移文件（migrations/）

### 4.2 模块划分原则

- **按业务领域划分**：每个Django应用对应一个业务领域（销售、生产、库存、物流、采购）
- **模块独立性**：每个模块管理自己的模型、视图、URL配置
- **共享数据模型**：通过Django ForeignKey/ManyToMany实现模块间数据关联
- **权限控制**：通过accounts模块统一管理，其他模块通过装饰器调用

### 4.3 数据流转机制

- **直接模型关联**：通过ForeignKey/ManyToMany实现跨模块数据关联
- **视图层调用**：模块间通过导入模型和调用视图函数实现交互
- **状态驱动**：业务流程通过模型状态字段驱动（如订单状态、生产任务状态）
- **事务保证**：关键操作使用`transaction.atomic()`保证数据一致性

### 4.4 核心业务流程

**销售-生产-物流闭环**：
1. 销售订单创建 → 审批 → 库存研判
2. 库存不足 → 创建生产任务 → 领料 → 生产 → 入库
3. 库存充足或生产完成 → 创建发货通知单 → 发货 → 扣减库存

**采购-库存-生产闭环**：
1. 采购任务创建 → 审批 → 收货 → 入库（增加原料库存）
2. 生产任务接收 → 检查原料库存 → 领料（扣减原料库存）

### 4.5 数据一致性保证

- **库存数量**：通过`Inventory.update_quantity_from_batches()`从批次汇总计算
- **批次管理**：
  - 库存扣减按FIFO原则从批次中扣减
  - 批次支持锁定数量（`locked_quantity`），用于订单审批时锁定库存
  - 批次可用数量 = 总数量 - 锁定数量（`Batch.get_available_quantity()`）
  - 发货时从锁定数量中扣减，然后扣减总数量
- **库存变动记录**：所有库存变化都记录在`StockTransaction`中
- **事务控制**：关键操作使用数据库事务保证原子性

### 4.6 权限控制机制

- **角色定义**：在`accounts.UserProfile`中定义角色
- **权限代码**：在`accounts.Permission`中定义权限代码
- **权限检查**：通过装饰器`@role_required`或`@role_or_permission_required`进行权限检查
- **默认权限**：每个角色有默认权限列表，可通过`UserProfile.permissions`添加额外权限

---

## 五、技术特点

1. **Django标准架构**：遵循Django应用模块化最佳实践
2. **RBAC权限系统**：基于角色的访问控制，支持细粒度权限管理
3. **批次管理**：
   - 库存支持批次管理，实现FIFO出库
   - 批次支持锁定数量，订单审批时锁定库存，发货时从锁定数量中扣减
4. **状态机模式**：业务流程通过状态字段驱动
5. **审批流程**：支持多级审批（销售经理、总经理）
6. **库存自动研判**：订单审批后自动检查库存并创建生产任务或发货通知单
7. **BOM自动计算**：生产任务接收时根据BOM自动计算领料需求
8. **模块职责优化**：
   - Customer模型从inventory迁移到sales模块（客户属于销售领域）
   - ShippingNotice模型从sales迁移到logistics模块（发货通知单属于物流领域）
   - PurchaseTask.supplier从CharField改为ForeignKey(Supplier)（规范化数据关联）

---

## 六、数据模型关系图（简化）

```
User (Django内置)
  └─ UserProfile (accounts)
      └─ Permission (accounts)

Customer (sales)
  └─ SalesOrder (sales)
      ├─ SalesOrderItem (sales)
      │   └─ SalesOrderItemBatch (sales)
      ├─ ProductionTask (production)
      └─ ShippingNotice (logistics)
          └─ Shipment (logistics)

Product (inventory)
  ├─ BOM (inventory)
  │   └─ Material (inventory)
  ├─ Inventory (inventory)
  │   └─ Batch (inventory, 含locked_quantity)
  └─ ProductionTask (production)
      ├─ MaterialRequisition (production)
      │   └─ MaterialRequisitionItem (production)
      ├─ QCRecord (production)
      └─ FinishedProductInbound (production)

Material (inventory)
  ├─ Inventory (inventory)
  │   └─ Batch (inventory, 含locked_quantity)
  └─ PurchaseTaskItem (purchase)
      └─ PurchaseTask (purchase)
          └─ Supplier (purchase)

StockTransaction (inventory) - 记录所有库存变动
```

---

**文档生成时间**：2026-01-17
**系统版本**：Django 5.2.9
**文档更新说明**：
- Customer模型从inventory迁移到sales模块
- ShippingNotice模型从sales迁移到logistics模块
- Batch模型增加locked_quantity字段和get_available_quantity()方法
- PurchaseTask.supplier从CharField改为ForeignKey(Supplier)
