# 库存调整统一设计建议：单位调整与数量/单价调整并列，审批与记录统一

## 一、现状梳理

### 1.1 当前三类“调整”的差异

| 维度 | 数量调整 + 单价调整 | 单位调整（原料/成品） |
|------|---------------------|------------------------|
| **入口** | 库存 → 某条库存 → 创建调整申请 | 物料/成品 → 单位变更、单位变更历史 |
| **主模型** | `InventoryAdjustmentRequest`（关联 Inventory） | `MaterialUnitChangeHistory` / `ProductUnitChangeHistory`（关联 Material/Product） |
| **是否经审批** | 是，需总经理审批 | 当前多为直接执行（无统一审批） |
| **记录落点** | 审批通过后写 `StockTransaction(transaction_type='adjustment')`，并在库存列表/详情中展示 | 只写各自 History 表，**不**写 StockTransaction，**不**在库存变动记录中展示 |
| **影响范围** | 单条 Inventory + 关联 Material/Product 单价 + 批次 | Material/Product + 对应 Inventory + 所有批次（含数量、单价换算） |
| **权限** | inventory.adjustment.create / approve | 角色：warehouse、ceo 等，无单独“单位调整”权限 |

### 1.2 “库存记录”在当前系统中的含义

- **库存列表页**：展示每条 Inventory 的汇总信息，以及一条「统一记录」列表。
- **统一记录**：来自 `StockTransaction`，按时间排序，包含：
  - 出入库（sale_out, production_out, production_in, purchase_in）
  - 库存调整（adjustment）：对应「数量/单价调整」审批通过后写入的那条。
- **单位变更**：目前**不在**上述“库存记录”中出现，只在物料/成品的「单位变更历史」中可见。

因此，“把调整记录都放到库存记录”在当前语境下可以理解为：  
**所有调整类操作（数量、单价、单位）都在“库存维度”可查，且最好在同一个列表或同一套记录体系中展示。**

---

## 二、统一是否可行？结论与前提

**结论：可以统一，且建议统一。**  
统一的核心是：**以库存（Inventory）为统一维度，把“单位调整”也视为一种库存相关调整，与数量/单价调整并列；审批流程统一；结果记录统一进入库存可查的“库存记录”。**

**前提：**

- 单位调整**必须能对应到唯一一条 Inventory**：  
  原料对应「原料类型 + 某 Material」的 Inventory，成品对应「成品类型 + 某 Product」的 Inventory。当前模型满足（每个 Material/Product 最多一条对应 Inventory）。
- 单位调整的**执行结果**除了改 Material/Product，也会改 Inventory.quantity、Inventory.unit 和批次，因此从业务上就是“对这条库存的调整”，归入库存记录是合理的。

---

## 三、统一设计建议（不涉及具体改代码）

### 3.1 功能并列：三种调整类型

建议在**概念和入口**上把“库存相关调整”归纳为三种，且并列：

| 调整类型 | 说明 | 当前实现 | 统一后建议 |
|----------|------|----------|------------|
| **数量调整** | 盘盈/盘亏，改库存数量 | InventoryAdjustmentRequest（adjustment_type=quantity） | 保持，作为“库存调整”的一种子类型 |
| **单价调整** | 改该库存对应的主数据单价（及可选批次单价） | InventoryAdjustmentRequest（adjustment_type=price/both） | 保持，与数量并列 |
| **单位调整** | 改计量单位，并按系数换算数量、单价、安全库存等 | MaterialUnitChangeHistory / ProductUnitChangeHistory | 与数量/单价调整并列，视为“库存调整”的第三种类型 |

并列的含义：

- 在**库存模块**下，对“某条库存”可进行的操作包括：**数量调整、单价调整、单位调整**（以及现有的出入库等）。
- 入口可以统一为：  
  **库存列表/库存详情 → 选择某条库存 → 选择“调整” → 再选择类型：数量 / 单价 / 单位**。  
  这样三种调整在入口上并列，而不是单位调整只从物料/成品进。

（实现上可以是同一个“调整申请”模型扩展类型，也可以是三个入口共用一个“调整中心”列表，见下。）

### 3.2 审批统一

当前：

- 数量/单价：走 `InventoryAdjustmentRequest`，状态 pending → approved/rejected，需审批人（如总经理）。
- 单位：多为直接执行，无统一审批表。

建议：

- **审批流程统一**：  
  - 三种调整都走“申请 → 审批 → 通过后执行”的流程（至少对需要管控的环境如此）。  
  - 即：单位调整也先落成一条“申请单”，状态与数量/单价一致（pending/approved/rejected/completed），由同一套审批权限（如 inventory.adjustment.approve）审批。
- **审批数据统一**：  
  - 要么：扩展现有 `InventoryAdjustmentRequest`，增加“单位调整”类型及相关字段（见下）；  
  - 要么：新增一张“库存调整申请”表，统一覆盖数量、单价、单位三种，原 `InventoryAdjustmentRequest` 仅做兼容或迁移。  
  这样审批列表、待办、权限都可以统一（例如一个“库存调整审批”列表包含三种类型）。

可选策略：

- **严格模式**：单位调整也必须提交申请、审批通过后才执行。  
- **宽松模式**：单位调整可配置为“免审”或“仅记录不审批”，但在**记录**上仍与数量/单价一致，都进“库存记录”（见下）。

### 3.3 记录统一到“库存记录”

目标：**所有调整（数量、单价、单位）都在库存维度可查，且尽量在同一套“库存记录”里展示。**

当前：

- 数量/单价：审批通过后写 `StockTransaction(transaction_type='adjustment')`，并在库存列表的“统一记录”中展示。
- 单位：只写在 MaterialUnitChangeHistory / ProductUnitChangeHistory，不写 StockTransaction，因此**不在**库存记录里。

建议：

- **单位调整执行后，也写一条库存变动记录**，且与现有“库存记录”同一数据源、同一列表展示：  
  - 方案 A（推荐）：扩展 `StockTransaction.transaction_type`，增加一种类型，例如 `unit_change`（单位调整）。  
    - 单位调整审批通过并执行后，除写 MaterialUnitChangeHistory/ProductUnitChangeHistory 外，**同时**为对应 Inventory 写一条 `StockTransaction(inventory=..., transaction_type='unit_change', ...)`，数量可为 0 或“换算后数量差”的示意，单位为新单位，备注或扩展字段中可存“单位变更”的简要信息（如旧单位→新单位、转换系数）。  
    - 这样库存列表/详情页的“统一记录”只需在展示逻辑上把 `unit_change` 与 `adjustment` 一起当作“调整类”展示即可，所有调整记录都来自 StockTransaction，都按 inventory 维度查。
  - 方案 B：不新增 transaction_type，单位调整执行后也写一条 `transaction_type='adjustment'`，在 remark 或 reference_no 中区分是“数量/单价调整”还是“单位调整”。  
    - 优点是不改 transaction_type 枚举；缺点是可读性和统计略差，需要依赖备注或关联表区分。
- **“库存记录”的展示**：  
  - 统一记录列表按时间排序，包含：出入库 + 数量/单价调整（adjustment）+ 单位调整（unit_change 或带标识的 adjustment）。  
  - 每条记录都能关联到一条 Inventory，即“都放到库存记录”在展示和查询上成立。
- **历史与审计**：  
  - 单位变更的完整前后快照仍可保留在 MaterialUnitChangeHistory/ProductUnitChangeHistory 中；  
  - 库存侧只需“有迹可循”：通过 StockTransaction 能看到某日某库存发生了单位调整、操作人、单号等，必要时再通过 reference_no 或类型反查到详细历史表。

这样既满足“调整记录都放到库存记录”，又不丢失单位变更的详细审计信息。

### 3.4 数据模型层面的统一思路（仅建议，不写具体代码）

- **申请单统一**  
  - 思路一：在现有 `InventoryAdjustmentRequest` 上增加“调整类型”枚举，例如：quantity / price / quantity_and_price / **unit**。  
    - 类型为 unit 时，使用或扩展字段：旧单位、新单位、转换系数、变更前后数量/单价快照等（可与现有单位变更历史字段对齐）。  
  - 思路二：新建通用表，如 `InventoryAdjustment`，字段覆盖：inventory、调整类型（数量/单价/单位）、类型相关参数（数量差、新单价、单位与系数等）、状态、申请人、审批人、单号等，原 InventoryAdjustmentRequest 迁移或兼容。  
  这样“申请 + 审批”的数据结构统一，便于做统一待办、统一权限。

- **执行结果记录统一**  
  - 无论采用思路一还是二，执行阶段都：  
    - 更新 Inventory（及 Material/Product、Batch 等）；  
    - **写一条 StockTransaction**，且与当前库存列表使用的“库存记录”数据源一致（见上）；  
    - 单位调整时，可继续写 MaterialUnitChangeHistory/ProductUnitChangeHistory 作为明细审计。

- **权限统一**  
  - 三种调整共用：创建权限（如 inventory.adjustment.create）、审批权限（inventory.adjustment.approve）。  
  - 若希望单位调整更严格，可单独增加“单位调整”权限，但审批入口建议仍与数量/单价放在同一“库存调整审批”里，便于管理员一次处理所有待审调整。

---

## 四、业务与展示上的建议

### 4.1 入口与列表

- **入口统一**：在库存列表或库存详情页，为每条 Inventory 提供统一入口，例如“申请调整”，再选择：数量调整 / 单价调整 / 单位调整。  
  单位调整也可以保留从物料/成品详情跳转的入口，但应支持从“库存”发起，这样“按库存看所有调整”的体验一致。
- **审批列表统一**：一个“库存调整审批”列表，包含待审批的：数量调整、单价调整、单位调整。  
  列表字段可包含：单号、库存（物料/成品名）、调整类型、申请时间、申请人等，审批人无需区分入口。

### 4.2 库存“统一记录”列表

- 数据源：仅来自 `StockTransaction`（或你当前展示库存变动的那张表）。  
- 类型包含：现有出入库类型 + adjustment（数量/单价）+ unit_change（或带标识的 adjustment）。  
- 展示时可根据 transaction_type（及必要时 remark/reference_no）区分：  
  - 出入库 / 数量·单价调整 / 单位调整，  
  并做简要文案（如“单位调整：kg → 袋，系数 100”），这样“所有调整记录都在库存记录里”在界面上成立。

### 4.3 单位调整的特殊性

- **前置检查**：单位调整前仍有“进行中生产/采购/销售”等检查，建议保留；可在统一申请单上展示为“风险提示”，审批人可见。  
- **换算与回滚**：单位调整涉及换算，执行逻辑比数量/单价更复杂，建议执行仍沿用现有单位变更服务，仅在“申请、审批、写 StockTransaction”上与数量/单价对齐。  
- **成品售价**：成品单位调整若会改 sale_price，也应在申请单/历史中体现，并在审批通过后一并更新。

---

## 五、实施时需要注意的点

### 5.1 兼容与迁移

- 已有 `MaterialUnitChangeHistory` / `ProductUnitChangeHistory`：  
  - 保留，作为单位调整的明细与审计；  
  - 若希望“库存记录”里也能看到历史单位变更，可考虑：  
    - 仅对新发生的单位调整写 StockTransaction；或  
    - 对历史数据做一次性脚本：为每条单位变更历史补写一条 StockTransaction（需对应到当时 Inventory 与时间），便于统一查询。  
  不修改代码的前提下，至少明确：新逻辑下单位调整执行后要写 StockTransaction，旧数据是否补写由后续实现决定。

### 5.2 权限与角色

- 若单位调整纳入统一审批，需确保：  
  - 有“库存调整审批”权限的角色（如 CEO）也能审批单位调整；  
  - 创建权限与现有 inventory.adjustment.create 对齐，或单独加“单位调整申请”权限但审批入口统一。

### 5.3 报表与统计

- “库存变动报表”“调整统计”等，若按 transaction_type 统计，需把 unit_change（或你选定的单位调整标识）纳入“调整”类，与 quantity/price 调整一起统计，这样分析和审计上也是统一的。

---

## 六、总结表

| 项目 | 建议 |
|------|------|
| **功能并列** | 数量调整、单价调整、单位调整在概念和入口上并列，均可从“某条库存”发起。 |
| **审批统一** | 三种调整都走“申请 → 审批 → 执行”，使用同一套审批列表与权限（或扩展现有 InventoryAdjustmentRequest/权限）。 |
| **记录统一到库存记录** | 单位调整执行后也写一条 StockTransaction（建议新增 transaction_type 如 unit_change），与数量/单价调整一起在库存列表的“统一记录”中展示；单位变更明细仍可保留在 Material/ProductUnitChangeHistory。 |
| **数据模型** | 申请单统一（扩展类型或新表），执行结果统一写 StockTransaction，单位明细保留在现有 History 表。 |
| **入口与列表** | 库存模块统一入口“申请调整”选类型；审批列表统一“库存调整审批”；库存记录列表包含所有调整类型。 |

按上述方式，可以在不修改现有代码的前提下，明确“单位调整与数量/单价调整并列、审批统一、调整记录都放到库存记录”的设计方向与落地要点；具体字段与接口可在开发阶段再细化。
