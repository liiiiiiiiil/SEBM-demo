# 多账号同时登录使用说明

## 概述

Django系统默认支持在不同浏览器或隐私模式窗口中同时登录不同的账号。每个浏览器实例都有独立的session cookie，因此可以同时保持多个账号的登录状态。

## 使用方法

### 方法1：使用不同浏览器（推荐）

1. **Chrome浏览器** - 登录账号A
2. **Firefox浏览器** - 登录账号B
3. **Edge浏览器** - 登录账号C

每个浏览器都有独立的cookie存储，可以同时登录不同账号。

### 方法2：使用隐私模式窗口

1. **正常窗口** - 登录账号A
2. **Chrome隐私模式** (Ctrl+Shift+N) - 登录账号B
3. **Firefox隐私模式** (Ctrl+Shift+P) - 登录账号C

隐私模式窗口使用独立的cookie存储，不会与正常窗口冲突。

### 方法3：使用不同用户配置文件（Chrome）

1. 打开Chrome设置 → 用户 → 添加新用户
2. 创建不同的用户配置文件
3. 每个配置文件有独立的cookie和session

## 技术说明

### Session机制

- Django使用基于cookie的session机制
- 每个浏览器实例（不同的浏览器或隐私模式）有独立的session cookie
- Session存储在服务器端，通过session ID关联

### 配置说明

在 `settings.py` 中已配置：

- `SESSION_COOKIE_NAME`: session cookie名称
- `SESSION_COOKIE_AGE`: session过期时间（24小时）
- `SESSION_SAVE_EVERY_REQUEST`: 每次请求都保存session
- `SESSION_EXPIRE_AT_BROWSER_CLOSE`: 浏览器关闭后不立即过期

## 注意事项

1. **同一浏览器的不同标签页**会共享session，因此只能登录一个账号
2. **不同浏览器或隐私模式窗口**有独立的session，可以登录不同账号
3. Session过期时间为24小时，超时后需要重新登录
4. 退出登录会清除当前浏览器的session，不影响其他浏览器

## 测试步骤

1. 在Chrome浏览器中登录账号A（如：销售员）
2. 打开Firefox浏览器，登录账号B（如：仓库管理员）
3. 两个浏览器可以同时保持登录状态，互不干扰
4. 在Chrome中退出登录，Firefox中的登录状态不受影响

## 常见问题

**Q: 为什么同一浏览器的不同标签页不能登录不同账号？**

A: 因为同一浏览器的所有标签页共享相同的cookie存储空间，session cookie是共享的。

**Q: 如何在同一浏览器中切换账号？**

A: 需要先退出当前账号，然后登录新账号。或者使用隐私模式窗口。

**Q: Session会过期吗？**

A: 是的，默认24小时后session会过期，需要重新登录。可以在settings.py中修改`SESSION_COOKIE_AGE`来调整过期时间。

