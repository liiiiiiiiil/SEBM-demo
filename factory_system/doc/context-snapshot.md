# 权限系统技术总结

## 一、系统架构概述

### 1.1 设计理念

本系统采用**基于角色的访问控制（RBAC）** + **灵活权限配置**的混合模式：

- **预定义角色**：每个角色有默认权限集合，满足常规业务需求
- **灵活配置**：可以为用户额外配置权限，叠加在角色默认权限之上
- **权限检查**：支持角色检查、权限检查、或两者结合

### 1.2 核心组件

```
Permission（权限模型）
    ↓
UserProfile（用户角色扩展）
    ├── role（角色）
    └── permissions（额外权限，ManyToMany）
        ↓
权限检查装饰器 + 模板标签
```

## 二、数据模型设计

### 2.1 Permission模型

**位置**：`accounts/models.py`

**字段**：
- `code`：权限代码（唯一标识，如：`inventory.view_product`）
- `name`：权限名称（显示用）
- `category`：权限分类（sales/inventory/production/logistics/system）
- `description`：权限描述

**特点**：
- 系统预定义29个权限，分为5个类别
- 权限代码采用点分命名（`模块.功能.操作`）
- 通过管理命令 `init_permissions` 初始化

### 2.2 UserProfile模型

**位置**：`accounts/models.py`

**核心字段**：
- `role`：角色（sales/sales_mgr/warehouse/production/qc/logistics/ceo）
- `permissions`：额外权限（ManyToMany关联到Permission）

**关键方法**：

```python
def has_permission(self, permission_code):
    """检查用户是否有指定权限"""
    # 1. CEO拥有所有权限
    # 2. 检查角色默认权限
    # 3. 检查额外配置的权限

def get_role_default_permissions(self):
    """获取角色默认权限列表"""
    # 返回该角色预定义的权限代码列表

def get_all_permissions(self):
    """获取用户所有权限（角色默认 + 额外权限）"""
```

### 2.3 角色默认权限映射

| 角色 | 默认权限 |
|------|---------|
| sales | sales.order.create, sales.order.view, sales.order.edit |
| sales_mgr | sales所有权限 + sales.order.approve, sales.order.view_all |
| warehouse | inventory.view, inventory.transaction.view, production.requisition.approve等 |
| production | production.task.view, production.task.receive, production.requisition.create |
| qc | production.qc.create, production.task.view |
| logistics | logistics.shipment.*, logistics.driver.manage, logistics.vehicle.manage |
| ceo | 所有权限（通过has_permission直接返回True） |

## 三、权限检查机制

### 3.1 装饰器

**位置**：`accounts/decorators.py`

**三种装饰器**：

1. **`@role_required(*roles)`**（向后兼容）
   - 只检查角色
   - 示例：`@role_required('sales', 'sales_mgr', 'ceo')`

2. **`@permission_required(permission_code)`**
   - 只检查权限
   - 示例：`@permission_required('inventory.view_product')`

3. **`@role_or_permission_required(*roles, permission_code=None)`**（推荐）
   - 检查角色或权限，满足任一即可
   - 示例：`@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.view_product')`

**使用示例**：

```python
from accounts.decorators import role_or_permission_required

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.view_product')
def inventory_list(request):
    # 仓库管理员、CEO或有inventory.view_product权限的用户可访问
    pass
```

### 3.2 模板标签

**位置**：`accounts/templatetags/permission_tags.py`

**过滤器**：`has_permission`

**使用示例**：

```django
{% load permission_tags %}

{% if user|has_permission:'inventory.view_product' %}
    <a href="{% url 'inventory:inventory_list' %}">查看库存</a>
{% endif %}
```

**在菜单中的应用**：

```django
{% if user.profile.role == 'warehouse' or user.profile.role == 'ceo' or user|has_permission:'inventory.view_product' %}
    <li class="nav-item">
        <a href="{% url 'inventory:inventory_list' %}">库存管理</a>
    </li>
{% endif %}
```

## 四、权限配置界面

### 4.1 管理后台

**位置**：`accounts/admin.py`

**特点**：
- 移除了Django默认的权限和组字段
- 统一在"用户角色和权限"inline中配置
- 支持多选权限（filter_horizontal）

**配置步骤**：
1. 访问 `/admin/auth/user/`
2. 选择用户 → 编辑
3. 在"用户角色和权限"部分：
   - 选择角色
   - 勾选额外权限（多选）

### 4.2 用户权限查看

**URL**：`/accounts/my-permissions/`

**功能**：
- 显示角色默认权限
- 显示额外配置的权限
- 显示所有权限代码列表

## 五、权限系统初始化

### 5.1 初始化命令

**位置**：`accounts/management/commands/init_permissions.py`

**执行**：
```bash
python manage.py init_permissions
```

**功能**：
- 创建29个系统预定义权限
- 按分类组织（销售、库存、生产、物流、系统）

### 5.2 权限列表（29个）

**销售权限（6个）**：
- sales.order.create/view/view_all/edit/approve/delete

**库存权限（10个）**：
- inventory.view/view_product/view_material/transaction.view
- inventory.customer.view/manage
- inventory.product.view/manage
- inventory.material.manage
- inventory.bom.manage

**生产权限（6个）**：
- production.task.view/receive
- production.requisition.create/approve
- production.qc.create
- production.inbound.create

**物流权限（5个）**：
- logistics.shipment.view/create/ship
- logistics.driver.manage
- logistics.vehicle.manage

**系统权限（2个）**：
- system.dashboard.view
- system.user.manage

## 六、实际应用场景

### 6.1 场景：为销售员添加查看库存权限

**需求**：销售员需要查看成品库存，以便在创建订单时了解库存情况。

**配置步骤**：
1. 管理后台 → 用户 → 选择销售员
2. 在"用户角色和权限" → "额外权限"中
3. 勾选 `inventory.view_product`
4. 保存

**效果**：
- 销售员登录后可以看到"库存管理"菜单
- 可以访问库存列表页面
- 仍然保持销售订单的所有权限

### 6.2 权限检查流程

```
用户访问页面
    ↓
检查是否登录
    ↓
获取UserProfile
    ↓
has_permission(permission_code)
    ├── 是CEO？ → 返回True
    ├── 角色默认权限包含？ → 返回True
    └── 额外权限包含？ → 返回True
    ↓
有权限 → 允许访问
无权限 → 重定向到仪表板，显示错误消息
```

## 七、技术要点

### 7.1 权限代码命名规范

采用点分命名：`模块.功能.操作`

- `sales.order.create`：销售模块，订单功能，创建操作
- `inventory.view_product`：库存模块，查看功能，产品对象
- `production.requisition.approve`：生产模块，领料单功能，审批操作

### 7.2 权限叠加机制

- 角色默认权限 + 额外配置权限 = 用户所有权限
- 权限不会覆盖，只会叠加
- CEO拥有所有权限，无需配置

### 7.3 向后兼容

- 保留了 `@role_required` 装饰器
- 旧的基于角色的视图仍然可以正常工作
- 新功能使用 `@role_or_permission_required` 装饰器

## 八、文件清单

### 核心文件

- `accounts/models.py`：Permission和UserProfile模型
- `accounts/decorators.py`：权限检查装饰器
- `accounts/templatetags/permission_tags.py`：模板标签
- `accounts/admin.py`：管理后台配置
- `accounts/management/commands/init_permissions.py`：权限初始化命令

### 模板文件

- `templates/base.html`：使用权限标签控制菜单显示
- `templates/accounts/dashboard.html`：使用权限标签控制按钮显示
- `templates/accounts/my_permissions.html`：用户权限查看页面

### 文档

- `PERMISSION_SYSTEM.md`：详细使用文档
- `doc/context-snapshot.md`：本技术总结

## 九、最佳实践

1. **新视图开发**：使用 `@role_or_permission_required` 装饰器，同时支持角色和权限检查
2. **菜单显示**：使用 `user|has_permission` 过滤器，根据权限动态显示
3. **权限配置**：优先使用角色默认权限，特殊需求再配置额外权限
4. **权限命名**：遵循点分命名规范，保持一致性
5. **测试验证**：配置权限后，通过"我的权限"页面验证配置是否正确

---

**版本**：v1.0  
**最后更新**：2025-12-23  
**维护者**：系统开发团队

