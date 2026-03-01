# 工厂系统 — 业务领域建模与业务架构审计报告

**角色**：资深领域建模专家 + 业务架构审计专家  
**范围**：仅业务层（不涉及代码重构、技术架构、性能优化）  
**输入**：系统功能、核心模块、关键代码与数据结构  
**输出**：业务目标、角色、流程、领域模型、规则、边界与风险

---

## 1. 系统核心业务目标（它真正解决什么问题？）

系统本质上是一个**「订单驱动 + 库存与生产联动」的轻量 ERP**，解决：

- **接单到履约的闭环**：从销售接单 → 两级审批（销售经理 + 总经理）→ 库存研判（有货则待发货，缺货则下生产）→ 生产领料/质检/入库 → 发货 → 回执，全链路可追溯。
- **库存与批次一致性**：成品/原料/其它统一用「基础单位 + 显示单位」双口径；库存按批次管理，支持锁定（订单占用）、FIFO 扣减与终结回滚。
- **生产与采购的可控性**：生产任务可来自订单或备货；领料需仓库审批后按批次锁定/扣减；采购任务审批后一次「完成」即入库，无多批次部分收货的明细持久化。
- **权责与审计**：按角色（销售/销售经理/仓管/生产/质检/物流/总经理）控制操作与审批，关键动作有操作人、单号、变动类型与备注。

**隐含业务假设**：

- 销售侧：订单以「成品 + 数量」为主，支持按批次预占库存；审批通过后由系统自动决定「直接发货」或「下生产」。
- 生产侧：按 BOM 算料，支持任务级用量覆盖；领料审批后即占批次，发料与入库有记录。
- 采购侧：采购任务以「一次完成」为主（表单内可填各明细收货量，但完成后不保留「已收/未收」进度）。
- 物流侧：发货与订单强绑定，从订单批次分配中扣减锁定库存；回执可选图片。

---

## 2. 用户角色模型

| 角色 code   | 角色名称     | 主要职责边界 |
|------------|--------------|----------------|
| sales      | 销售员       | 创建/编辑（仅被退回）订单，查看自己的订单；客户信息查看/创建/编辑/删除（受权限控制） |
| sales_mgr  | 销售经理     | 订单审批（pending→ceo_pending）、退回；客户管理；查看全部订单 |
| warehouse  | 仓库管理员   | 成品/原料/其它库存查看与调整申请；领料单审批；成品入库；采购任务完成（收货入库）；产品/原料/BOM 在 product 或 inventory 的维护 |
| production | 生产管理员   | 生产任务接收、领料单创建、任务用量覆盖；查看 BOM |
| qc         | 质检员       | 创建质检记录（合格/不合格/返工） |
| logistics  | 物流管理员   | 发货单创建、发货确认、收货回执、司机与车辆管理 |
| ceo        | 总经理       | 订单总经理审批、订单终结、库存调整审批、客户编辑/删除审批；拥有全部权限 |

**权限体系**：`Permission` 按模块（sales/inventory/production/logistics/system）细粒度配置；`UserProfile` 通过角色默认权限 + 额外权限赋予能力；CEO 在代码中直接视为拥有所有权限。

**边界说明**：客户（Customer）模型在 **sales** 应用，但权限码为 `inventory.customer.*`，业务上属于「销售主数据」，权限归类存在命名与归属不一致。

---

## 3. 核心业务流程（流程图式文字）

### 3.1 销售订单全流程

```
[销售员] 创建订单(pending)
    → [销售经理] 审批 → 通过 → ceo_pending
    → 退回 → rejected → [销售员] 可编辑再提交 → pending

[总经理] 审批(ceo_pending)
    → 通过 → 锁定订单批次库存(batch.locked_quantity)
         → check_inventory_and_create_tasks()
              → 若所有行「批次分配≥订单数量」→ 建发货通知单 → 订单 ready_to_ship
              → 若有缺口 → 按行建生产任务(pending/material_insufficient) → 订单 in_production
    → 退回 → rejected

[生产中] 生产任务完成、入库满足订单
    → 若订单所需全部满足 → 建发货通知单 → 订单 ready_to_ship

[物流] 创建发货单 → 确认发货
    → 按订单批次分配从 batch 扣减(quantity 与 locked_quantity)
    → 写 StockTransaction(sale_out)
    → 订单 shipped

[物流] 全部发货单录入回执(delivered)
    → 订单 completed

[总经理] 终结订单(可对 in_production / ready_to_ship / shipped)
    → terminate_order_chain：已发货退回入库、已入库成品扣减、已发料原料回库、释放锁定、任务/领料单终结
    → 订单 terminated
```

### 3.2 生产任务与领料

```
任务创建(来自订单或备货)
    → pending 或 material_insufficient

[生产] 接收任务
    → 检查原料是否充足
    → 不足 → material_insufficient
    → 充足 → 自动创建领料单(pending) → 任务 in_production

[仓库] 审批领料单
    → 按批次 FIFO 占用可用量(batch.locked_quantity)，写 MaterialRequisitionItemBatch
    → 领料单 approved，任务 material_preparing（旋即 in_production）

[生产] 生产完成 → 任务 qc_checking

[质检] 录入质检(qualified/unqualified/rework)
    → 仅 qualified 有明确后续：可入库

[仓库] 成品入库
    → 建 FinishedProductInbound、Batch、StockTransaction(production_in)
    → 更新任务 completed_quantity；若 ≥ required_quantity → 任务 completed
    → 若为订单生产，检查订单是否可 ready_to_ship
```

### 3.3 采购任务

```
[创建人] 创建采购任务(pending) → [CEO] 审批 → approved
    → [仓库/CEO] 完成采购：填写本次各明细收货量、批次信息
    → 创建 Batch、更新 Inventory、写 StockTransaction(purchase_in)
    → 任务 status=completed（一次性完成，无持久化「已收/未收」进度）
```

### 3.4 库存调整

```
[仓库/有权限] 创建库存调整申请(数量)
    → 当前仅支持数量调整；单价/单位在「产品管理」维护
    → status=pending

[总经理/有审批权] 审批
    → 通过 → 更新 Inventory.quantity、写 StockTransaction(adjustment)、申请 completed
    → 拒绝 → rejected
```

---

## 4. 领域模型抽象（实体 + 属性）

### 4.1 主数据与基础数据

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| Unit | code, name, symbol, category(weight/length/volume/quantity/area), is_active | 单位字典，物料/成品可引用 |
| MaterialCategory | name | 原料分类 |
| ProductCategory | name | 成品分类 |
| Material | sku, name, category, material_type(raw/auxiliary/tool/office), base_unit, display_unit, unit_price, safety_stock | 原料；单价/安全库存为基础单位口径 |
| Product | sku, name, category, specification, base_unit, display_unit, unit_price, sale_price, safety_stock | 成品 |
| ItemUnitConversion | content_type(material/product), material/product, base_unit, target_unit, factor, is_active | 1 target = factor × base_unit |
| BOM | product, material, quantity, unit | 每 1 基础单位成品所需原料用量；unit 须为物料合法单位 |
| Customer | name, contact_person, phone, address, credit_level, created_by, 编辑/删除审批字段, is_deleted | 客户；软删与审批流程 |
| Supplier | name, contact_person, contact_phone, address, created_by | 供应商 |

### 4.2 库存与批次

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| Inventory | inventory_type(product/material/other), product/material/other_name, other_unit, other_unit_price, quantity | 实时库存；quantity 恒为基础单位 |
| Batch | batch_no, inventory, batch_date, quantity, locked_quantity, unit_price, expiry_date, supplier | 批次；数量与锁定均为基础单位 |
| StockTransaction | transaction_type(sale_out/production_out|in/production_in/purchase_in/adjustment/unit_change), inventory, batch, quantity, unit, base_quantity, reference_no, operator | 变动记录；base_quantity 用于库存增减 |
| InventoryAdjustmentRequest | request_no, inventory, adjustment_type(quantity/price/both), current/new quantity & unit_price, reason, status, applicant, approved_by | 调整申请与审批 |

### 4.3 销售

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| SalesOrder | order_no, customer, salesperson, status(多态), total_amount, delivery_date, reserve_inventory, 审批/终结人及时间 | 订单 |
| SalesOrderItem | order, product, quantity, unit_price, subtotal, display_unit, display_quantity | 明细；数量与单价为基础单位 |
| SalesOrderItemBatch | order_item, batch, quantity | 订单行与批次的分配（总经理审批前分配，审批时锁定） |

### 4.4 生产

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| ProductionTask | task_no, production_type(order/stock), order, product, required_quantity, completed_quantity, status(多态), 时间与终结信息 | 任务；数量为基础单位 |
| TaskMaterialOverride | task, material, quantity, unit, remark | 任务级 BOM 用量覆盖 |
| MaterialRequisition | requisition_no, task, status, requested_by, approved_by, issued_by, 终结信息 | 领料单 |
| MaterialRequisitionItem | requisition, material, required_quantity, issued_quantity | 领料明细；基础单位 |
| MaterialRequisitionItemBatch | requisition_item, batch, quantity_locked | 领料对批次的锁定 |
| QCRecord | task, batch_no, inspected/qualified/unqualified_quantity, qualification_rate, result(qualified/unqualified/rework), inspector | 质检记录 |
| FinishedProductInbound | inbound_no, task, qc_record, quantity, operator | 成品入库单；数量为基础单位 |

### 4.5 采购

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| PurchaseTask | task_no, supplier, total_amount, status, created_by, 审批/终结 | 采购任务 |
| PurchaseTaskItem | task, material, item_name, item_type(material/office/other), quantity, unit_price, subtotal, display_unit, display_quantity | 明细；无持久化 received_quantity |

### 4.6 物流

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| Driver | name, phone, license_no, license_type | 司机 |
| Vehicle | driver, plate_no, vehicle_type, model, capacity | 车辆 |
| ShippingNotice | notice_no, order, status(pending/shipped) | 发货通知单 |
| Shipment | shipment_no, shipping_notice, order, driver, vehicle, freight_cost, status, shipped_by/delivered_by, 回执字段 | 发货单 |
| ShipmentImage | shipment, image, uploaded_by, remark | 回执图片 |

### 4.7 账户与权限

| 实体 | 关键属性 | 说明 |
|------|----------|------|
| User | Django 内置 | 登录与操作人 |
| Permission | code, name, category | 权限定义 |
| UserProfile | user, role, permissions(M2M), phone, department | 角色与额外权限；has_permission(code) |

---

## 5. 业务规则列表（显式 + 隐式）

### 5.1 显式规则（代码或模型约束中明确）

- **单位**：物料/成品有且仅有一个不可变 base_unit（有关联数据后禁止改）；display_unit 须为 base_unit 或 ItemUnitConversion 中已定义；BOM 行的 unit 须为物料合法单位。
- **库存**：Inventory.quantity 与 Batch 数量/锁定均为基础单位；库存总数量由批次汇总更新（update_quantity_from_batches）。
- **订单审批**：销售经理只能审批 pending→ceo_pending；总经理只能审批 ceo_pending，通过后锁定 SalesOrderItemBatch 对应批次的 locked_quantity，并执行 check_inventory_and_create_tasks。
- **库存研判**：每行缺口 = 订单数量 − 该行批次分配总和；缺口>0 则检查 BOM 原料是否充足，建生产任务（pending 或 material_insufficient）；全部满足则建发货通知单，订单 ready_to_ship。
- **领料**：任务接收时创建领料单(pending)；仓库审批时按批次 FIFO 用 get_available_quantity() 分配并增加 batch.locked_quantity，写 MaterialRequisitionItemBatch；任务终结时释放领料锁定。
- **发货**：发货确认时从订单批次分配扣减 batch.quantity 与 batch.locked_quantity，写 sale_out；发货前会校验批次可用量。
- **订单终结**：terminate_order_chain 已发货退回入库、扣减已入库成品、已发料原料回库、释放订单锁定、终结任务与领料单。
- **库存调整**：仅支持数量调整申请；审批后改 Inventory 并写 adjustment 类型流水。
- **客户**：有关联订单则软删除，否则硬删除；编辑/删除走审批字段。

### 5.2 隐式规则（无集中文档或易被忽略）

- **订单退回再提交**：保留订单号，状态改回 pending，需重新走完整审批；审批人/时间在重新提交时被清空（代码中编辑 rejected 订单时重置）。
- **生产任务**：received/material_preparing 在实现中几乎不停留，接收后直接 in_production；领料单的 issued 状态未在流程中使用。
- **采购完成**：一次提交即整单 completed，收货数据仅体现在当次创建的 Batch/Transaction，无「每行已收数量」持久化，无法做真正的多批次部分收货追踪。
- **质检**：仅 qualified 可接收入库；unqualified/rework 无后续流程定义，任务可能长期停在 qc_checking。
- **批次**：过期仅 is_expired() 判断，无强制禁止发货或优先使用非过期批次的业务约束；数量为 0 的批次不删除，仅作历史。
- **订单取消**：仅 pending 可取消(cancelled)；其他需走终结。
- **产品/原料维护**：product 应用为 inventory 的 UI 层，成品/原料/BOM/单位换算均在 product 或 inventory 的视图中共存，数据归属在 inventory。

---

## 6. 规则冲突或模糊点

- **质检不合格/返工**：结果有 qualified/unqualified/rework，但只有 qualified 有明确后续；unqualified 与 rework 无状态变更或处理流程，易导致任务卡在 qc_checking。
- **批次分配与订单数量**：业务期望「每行分配总和 ≤ 订单数量」，若前端或接口允许超分配，与「锁定=分配量」的语义可能冲突；需在创建/审批处显式校验。
- **采购「部分收货」**：文档曾提部分收货，当前模型无 received_quantity，完成即整单 completed，与「多次收货、按行跟踪」的常见理解不一致。
- **客户归属**：Customer 在 sales 应用，权限为 inventory.customer.*，职责与命名不统一。
- **状态冗余**：approved/ceo_approved、received/material_preparing、issued、purchasing、loading 等在模型中存在但流程中不停留或未用，易造成报表与状态筛选歧义。

---

## 7. 职责边界是否清晰

- **基本清晰**：销售(sales)、生产(production)、采购(purchase)、物流(logistics)、库存(inventory) 按模块划分；订单→生产→发货的驱动关系明确；库存与批次由 inventory 统一，sales/production/purchase 只读或写库存流水与批次。
- **模糊点**：
  - **product 与 inventory**：product 是 inventory 的展示与维护入口，成品/原料/BOM/单位换算逻辑在 inventory，边界为「product=门面，inventory=数据与规则」；但 inventory 内仍有 product_list 等视图，存在双入口。
  - **客户**：业务上属销售主数据，权限挂在 inventory，职责名与归属不一致。
  - **库存调整**：数量调整在库存模块审批，单价/单位在「产品管理」改，规则分散在两处。
  - **订单终结**：逻辑集中在 sales.views.terminate_order_chain，正确回滚库存/任务/领料单，但跨模块多，耦合在 sales 内。

---

## 8. 是否存在逻辑重复

- **单位换算**：Material/Product 通过 UnitMixin 委托 UnitConversionService；BOM/TaskMaterialOverride 的「用量→基础单位」各自调 to_base/get_base_quantity，规则集中，重复度低。
- **批次可用量**：get_available_quantity() 在 Batch 上定义一处；领料审批与发货处均使用，无重复实现。
- **订单行「显示数量」**：SalesOrderItem 的 get_display_quantity() 与前端多处「用 product.to_display(quantity)」类似逻辑分散在多处，可考虑统一为「行级展示服务」。
- **库存变动记录**：不同模块创建 StockTransaction 时 transaction_type/reference_no/operator 的填写方式类似，可抽象为「库存变动服务」减少重复与错误，但当前未抽象。
- **成品/原料列表**：inventory 的 product_list 与 product 应用的 product_list（成品+原料统一列表）功能重叠，入口不统一。

---

## 9. 是否存在可抽象为通用 Skill 的能力

以下可抽象为与具体业务解耦的「领域能力」，便于在其他项目复用或标准化：

- **双单位体系**：基础单位 + 显示单位 + 换算表 + 校验（BOM/订单/采购行等），可沉淀为「可配置单位与换算」的领域 Skill。
- **审批流**：订单两级审批、客户编辑/删除审批、库存调整审批、领料审批，可抽象为「状态 + 审批人/时间/原因」的轻量审批模式 Skill。
- **批次库存与占用**：批次 quantity/locked_quantity、FIFO 分配、占用释放与回滚，可抽象为「批次占用与回滚」Skill。
- **订单驱动任务创建**：按「缺口」自动创建生产任务或发货通知，可抽象为「订单履约研判（库存/生产）」的决策 Skill。
- **终结与回滚**：订单终结时对发货/入库/领料的回滚策略，可抽象为「订单/任务链终结与库存回滚」的通用模式 Skill。

上述能力在代码中已实现但未以独立服务/Skill 形式暴露，文档化与接口化后可复用。

---

## 10. 风险点与改进建议

### 10.1 业务与数据风险

- **质检结果无闭环**：unqualified/rework 无后续动作，建议明确：不合格需处理单或报废/降级；返工将任务打回 in_production 并允许再次质检与入库。
- **采购无行级收货进度**：若需多次收货与对账，建议在 PurchaseTaskItem 上恢复或新增「已收数量」及多批次入库关联，完成条件改为「每行已收≥应购」。
- **批次过期与可用性**：建议在发货/领料分配时优先非过期批次，并对过期批次做提示或审批；可选在 Batch 或库存列表显式标记 is_expired。
- **订单批次分配校验**：在保存或提交审批前校验「每行分配总和 ≤ 订单数量」，防止超分配与锁定异常。

### 10.2 边界与一致性建议

- **客户归属**：将 Customer 的权限改为 sales.customer.*，或保持 inventory 但在文档中明确「客户为销售主数据，仅权限挂在 inventory」。
- **产品/原料入口**：收敛为单一入口（建议以 product 应用为唯一门面），inventory 仅保留库存、批次、调整、变动记录等「仓管视角」功能。
- **状态精简**：对从不停留或未使用的状态（如 approved、ceo_approved、received、material_preparing、issued、purchasing、loading）在文档中标明「内部/历史」，或从可选状态中隐藏，避免业务误解。

### 10.3 规则显式化建议

- **订单退回后重提**：在业务规则文档中写明「保留订单号与历史，清空当前审批人/时间，状态改为 pending，重新走两级审批」。
- **超产与完成**：明确允许 completed_quantity > required_quantity，任务仍为 completed，超产进入库存；可选记录超产原因。
- **领料单 issued**：若未来不打算使用「已发料」状态，可从流程与 UI 中移除，避免与 approved 混淆。

### 10.4 能力抽象建议

- 将「单位换算与校验」「批次占用与回滚」「订单履约研判」「终结回滚」等抽成领域服务或内部 API，便于测试、复用在备货生产/其他单据类型上，并为后续多租户或扩展留空间。

---

**文档版本**：1.0  
**依据**：factory_system 代码与 doc/business-rules-analysis-final.md、architecture-description.md  
**范围**：业务目标、角色、流程、领域模型、规则、边界、重复、可复用能力与风险建议；不涉及技术架构与性能优化。
