# 灵活权限系统使用说明

## 概述

系统实现了基于角色的权限控制（RBAC），支持：
1. **预定义角色**：每个角色有默认权限
2. **灵活配置**：可以为用户额外配置权限，叠加在角色默认权限之上

## 权限系统架构

### 1. 权限模型（Permission）

系统定义了29个权限，分为5个类别：
- **销售权限**：订单创建、查看、编辑、审批等
- **库存权限**：查看库存、管理产品、管理客户等
- **生产权限**：查看任务、接收任务、创建领料单等
- **物流权限**：创建发货单、管理司机车辆等
- **系统权限**：查看仪表板、管理用户等

### 2. 角色默认权限

每个角色都有预定义的默认权限：

- **销售员（sales）**：
  - sales.order.create（创建订单）
  - sales.order.view（查看订单）
  - sales.order.edit（编辑订单）

- **销售经理（sales_mgr）**：
  - 销售员的所有权限 +
  - sales.order.approve（审批订单）
  - sales.order.view_all（查看所有订单）

- **仓库管理员（warehouse）**：
  - inventory.view（查看库存）
  - inventory.transaction.view（查看库存变动）
  - inventory.customer.view（查看客户）
  - inventory.product.view（查看产品）
  - production.requisition.approve（审核领料单）
  - production.inbound.create（创建入库单）

- **生产管理员（production）**：
  - production.task.view（查看生产任务）
  - production.task.receive（接收生产任务）
  - production.requisition.create（创建领料单）

- **质检员（qc）**：
  - production.qc.create（创建质检记录）
  - production.task.view（查看生产任务）

- **物流管理员（logistics）**：
  - logistics.shipment.create（创建发货单）
  - logistics.shipment.view（查看发货单）
  - logistics.driver.manage（管理司机）
  - logistics.vehicle.manage（管理车辆）

- **总经理（ceo）**：
  - 拥有所有权限（无需配置）

## 使用方法

### 1. 为用户配置额外权限

#### 方法1：通过Django管理后台

1. 访问 `/admin/`
2. 进入 **用户（Users）** → 选择要配置的用户
3. 在 **用户角色和权限** 部分：
   - 选择角色（如：销售员）
   - 在 **额外权限** 中选择要添加的权限（如：查看成品库存）
4. 保存

#### 方法2：通过代码配置

```python
from accounts.models import UserProfile, Permission

# 获取用户
user = User.objects.get(username='sales01')
profile = user.profile

# 获取权限
permission = Permission.objects.get(code='inventory.view_product')

# 添加权限
profile.permissions.add(permission)
```

### 2. 在视图中使用权限检查

#### 使用权限装饰器

```python
from accounts.decorators import permission_required, role_or_permission_required

# 方式1：只检查权限
@permission_required('inventory.view_product')
def view_product_inventory(request):
    # 只有拥有该权限的用户可以访问
    pass

# 方式2：检查角色或权限（推荐）
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.view_product')
def inventory_list(request):
    # 仓库管理员、CEO或有该权限的用户可以访问
    pass
```

### 3. 在模板中检查权限

```django
{% if user.profile.has_permission('inventory.view_product') %}
    <a href="{% url 'inventory:inventory_list' %}">查看库存</a>
{% endif %}
```

## 实际应用示例

### 示例：为销售员添加查看成品库存权限

**场景**：销售员需要查看成品库存，以便在创建订单时了解库存情况。

**步骤**：

1. **在管理后台配置**：
   - 进入 `/admin/auth/user/` → 选择销售员用户
   - 在 **用户角色和权限** → **额外权限** 中
   - 勾选 `inventory.view_product`（查看成品库存）
   - 保存

2. **验证权限**：
   - 销售员登录后，访问 `/accounts/my-permissions/` 查看自己的权限
   - 应该能看到 `inventory.view_product` 在"额外配置的权限"列表中

3. **使用权限**：
   - 销售员现在可以访问库存列表页面
   - 因为 `inventory_list` 视图使用了 `@role_or_permission_required` 装饰器

## 权限代码列表

### 销售权限
- `sales.order.create` - 创建订单
- `sales.order.view` - 查看订单
- `sales.order.view_all` - 查看所有订单
- `sales.order.edit` - 编辑订单
- `sales.order.approve` - 审批订单
- `sales.order.delete` - 删除订单

### 库存权限
- `inventory.view` - 查看库存
- `inventory.view_product` - 查看成品库存
- `inventory.view_material` - 查看原料库存
- `inventory.transaction.view` - 查看库存变动
- `inventory.customer.view` - 查看客户
- `inventory.customer.manage` - 管理客户
- `inventory.product.view` - 查看产品
- `inventory.product.manage` - 管理产品
- `inventory.material.manage` - 管理原料
- `inventory.bom.manage` - 管理BOM配方

### 生产权限
- `production.task.view` - 查看生产任务
- `production.task.receive` - 接收生产任务
- `production.requisition.create` - 创建领料单
- `production.requisition.approve` - 审核领料单
- `production.qc.create` - 创建质检记录
- `production.inbound.create` - 创建入库单

### 物流权限
- `logistics.shipment.view` - 查看发货单
- `logistics.shipment.create` - 创建发货单
- `logistics.shipment.ship` - 确认发货
- `logistics.driver.manage` - 管理司机
- `logistics.vehicle.manage` - 管理车辆

### 系统权限
- `system.dashboard.view` - 查看仪表板
- `system.user.manage` - 管理用户

## 权限检查逻辑

系统按以下顺序检查权限：

1. **CEO检查**：如果是CEO，直接通过（拥有所有权限）
2. **角色默认权限**：检查用户的角色是否有该权限
3. **额外配置权限**：检查用户是否被额外配置了该权限

只要满足以上任一条件，用户就可以访问。

## 查看我的权限

用户可以访问 `/accounts/my-permissions/` 查看：
- 角色默认权限
- 额外配置的权限
- 所有权限代码列表

## 注意事项

1. **权限叠加**：额外权限会叠加在角色默认权限之上，不会覆盖
2. **CEO特权**：CEO拥有所有权限，无需配置
3. **权限代码**：权限代码是唯一的标识符，用于权限检查
4. **向后兼容**：旧的 `@role_required` 装饰器仍然可用

## 初始化权限

如果权限数据丢失，可以运行：

```bash
python manage.py init_permissions
```

这会创建所有29个系统权限。


