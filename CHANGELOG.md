# 更新日志

所有版本更新遵循 [语义化版本控制](https://semver.org/lang/zh-CN/) 规范。

> **如何阅读本日志**
> 每个版本分为 "新增"/"变更"/"修复"/"移除"/"废弃" 等部分。建议开发者在升级前先阅读对应版本的 Breaking Change 和修复内容。

> **贡献日志**
> 如需为新版本添加日志，请在对应版本号下补充内容，并注明日期和主要贡献者。

---

## 规则

### 必须包含的信息
1. **贡献者信息**：每项变更必须标明贡献者，格式为 `@Github用户名`
2. **变更类型**：明确标识变更类型（新增/变更/修复/移除/废弃等）
3. **日期信息**：版本发布日期采用 `YYYY/MM/DD` 格式

### 示例格式

```markdown
## [version] - 2025/08/20
> 开发版本

### 新增

- By [贡献者](https://github.com/贡献者)
  - `模块名` 模块新增功能描述：
    - 具体功能点1
    - 具体功能点2
```

---

## [3.6.0] - 2026/02/11
> 重构消息发送架构，支持 OneBot12 格式兼容

### 新增
- By @wsu2059q
  - `Core.py` 消息发送 DSL 全面重构：
    - 支持链式调用（At/AtAll/Reply 等修饰符）
    - 新增 `Raw_ob12()` 方法支持 OneBot12 格式消息发送
    - 新增 `File()` 通用文件发送接口
    - 新增 `__getattr__` 处理不支持的消息类型
  - 消息数组格式支持（替代 CQ 码字符串拼接）
  - `_build_message_array()` 方法统一构建消息段
  - `_convert_ob12_to_ob11()` 方法实现 OB12 到 OB11 格式转换
  - 支持 `base64://` 协议发送媒体文件

### 变更
- By @wsu2059q
  - 消息发送从 CQ 码字符串改为 OneBot11 消息段数组格式
  - `Text()`/`Image()`/`Voice()`/`Video()`/`Face()` 等方法内部实现重构
  - 媒体文件发送优化：优先 base64，失败回退临时文件
  - 临时文件延迟清理机制（1秒后删除）
  - 移除 `Raw()` 方法（被 `Raw_ob12()` 替代）
  - 移除 `Edit()` 方法（撤回+重发逻辑移除）
  - 移除 `Batch()` 方法（批量发送逻辑简化）
  - 移除 `Rps()`/`Dice()`/`Shake()`/`Anonymous()`/`Contact()`/`Location()`/`Music()`/`Forward()`/`Node()`/`Xml()`/`Json()`/`Poke()`/`Gift()`/`MarketFace()` 等非常用方法

### 修复
- By @wsu2059q
  - 修复 `_send_bytes()` 中临时文件过早删除问题
  - 修复消息段数组构建时的链式修饰逻辑

---

## [3.5.1] - 2025/08/22
> 添加 bot_id 支持，改进多账户管理

### 新增
- By @wsu2059q
  - `OneBotAccountConfig` 新增 `bot_id` 必填字段
  - 支持通过 bot_id 查找账户
  - 所有日志输出增加 bot_id 标识

### 变更
- By @wsu2059q
  - `call_api()` 支持通过 bot_id 或账户名定位账户
  - 事件 `self.user_id` 使用 bot_id 而非账户名
  - 旧配置迁移提示优化

---

## [3.5.0] - 2025/08/22
> 支持多账户配置与管理

### 新增
- By @wsu2059q
  - 多账户架构：支持同时配置和运行多个 OneBot 账户
  - `OneBotAccountConfig` 数据类定义账户配置
  - `_load_account_configs()` 加载多账户配置
  - 每个账户独立的 WebSocket 连接管理
  - `accounts` / `connections` / `sessions` / `reconnect_tasks` 分账户存储
  - 支持混合运行模式（Server/Client 同时运行）
  - `Send` 类新增 `Account()` 方法指定发送账户
  - 事件自动添加 `account_id` 字段标识来源账户

### 变更
- By @wsu2059q
  - 配置结构改为 `OneBotv11_Adapter.accounts.{account_name}`
  - 完全兼容旧配置格式（自动迁移，不强制保存新配置）
  - `call_api()` 新增 `account_id` 参数
  - `connect()` / `_listen()` / `_handle_message()` 等改为按账户处理
  - 每个账户独立注册 WebSocket 路由

### 修复
- By @wsu2059q
  - 修复多账户下 API 响应 Future 冲突问题
  - 修复账户连接状态管理问题

---

## [3.4.0] - 2025/08/21

### 变更
- 向 `convert` 模块添加 `onebot11_raw_type` 字段
- 删除提交原始数据的接口（交由ErisPulse处理原生事件分发）
