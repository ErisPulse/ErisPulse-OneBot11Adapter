# OneBotAdapter 模块文档

## 简介
OneBotAdapter 是基于 [ErisPulse](https://github.com/ErisPulse/ErisPulse/) 架构开发的 **OneBot V11 协议适配器模块**。它提供统一的事件处理机制、连接管理功能，并支持 Server 和 Connect 两种运行模式。

---

### 消息发送示例（DSL 链式风格）

#### 文本消息
```python
await onebot.Send.To("group", 123456).Text("Hello World!")
```

#### 图片消息
```python
await onebot.Send.To("user", 123456).Image("http://example.com/image.jpg")
```

#### 语音消息
```python
await onebot.Send.To("user", 123456).Voice("http://example.com/audio.mp3")
```

#### 视频消息
```python
await onebot.Send.To("group", 123456).Video("http://example.com/video.mp4")
```

#### 表情消息
```python
await onebot.Send.To("user", 123456).Face(1)  # 发送ID为1的表情
```

#### @消息
```python
await onebot.Send.To("group", 123456).At(789012, "用户名")
```

#### 猜拳消息
```python
await onebot.Send.To("user", 123456).Rps()
```

#### 掷骰子消息
```python
await onebot.Send.To("user", 123456).Dice()
```

#### 位置消息
```python
await onebot.Send.To("group", 123456).Location(39.9042, 116.4074, "北京市", "中华人民共和国首都")
```

#### 音乐分享
```python
await onebot.Send.To("user", 123456).Music(
    type="custom",
    url="https://music.163.com/#/song?id=123456",
    audio="https://music.163.com/song/media/outer/url?id=123456.mp3",
    title="测试音乐",
    content="ErisPulse测试",
    image="https://http.cat/200"
)
```

#### XML消息
```python
xml_data = '''<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<msg serviceID="1" templateID="1" action="web" brief="测试XML" 
     sourceName="ErisPulse" url="https://github.com">
    <item layout="2">
        <picture cover="https://http.cat/200"/>
        <title>XML消息测试</title>
        <summary>这是一条XML格式的消息</summary>
    </item>
</msg>'''
await onebot.Send.To("user", 123456).Xml(xml_data)
```

#### JSON消息
```python
json_data = '{"app":"com.tencent.miniapp","desc":"ErisPulse测试","view":"notification","ver":"0.0.1","prompt":"[ErisPulse JSON消息]","appID":"","sourceName":"ErisPulse","actionData":"{\"type\":\"jump\",\"url\":\"https://github.com\"}","content":"[\\"ErisPulse测试JSON消息\\"]","sourceUrl":"","meta":{"notification":{"appInfo.icon":10001,"appInfo.name":"ErisPulse","data":[{"title":"JSON消息测试","value":"这是一条JSON格式的消息"}],"title":"ErisPulse通知","button":[{"name":"查看详情"}],"emphasis_keyword":""}},"text":"","extra":""}'
await onebot.Send.To("user", 123456).Json(json_data)
```

#### 戳一戳
```python
await onebot.Send.To("user", 123456).Poke("poke", 789012)
```

#### 发送原生 CQ 消息
```python
await onebot.Send.To("user", 123456).Raw([
    {"type": "text", "data": {"text": "你好"}},
    {"type": "image", "data": {"file": "http://example.com/image.png"}}
])
```

#### 撤回消息
```python
await onebot.Send.To("group", 123456).Recall(123456789)
```

#### 编辑消息
```python
await onebot.Send.To("user", 123456).Edit(123456789, "修改后的内容")
```

#### 批量发送
```python
await onebot.Send.To("user", [123456, 789012, 345678]).Batch(["123456", "789012", "345678"], "批量消息")
```

#### 群组管理：踢人
```python
await onebot.Send.To("group", 123456).Kick(789012)
```

#### 群组管理：禁言
```python
await onebot.Send.To("group", 123456).Ban(789012, duration=1800)  # 禁言30分钟
await onebot.Send.To("group", 123456).Ban(789012, duration=0)     # 解除禁言
```

#### 群组管理：全体禁言
```python
await onebot.Send.To("group", 123456).WholeBan(enable=True)
```

#### 群组管理：设置管理员
```python
await onebot.Send.To("group", 123456).SetAdmin(789012, enable=True)
```

#### 群组管理：设置群名片
```python
await onebot.Send.To("group", 123456).SetCard(789012, "新名片")
```

#### 群组管理：设置群名称
```python
await onebot.Send.To("group", 123456).SetGroupName("新群名")
```

#### 群组管理：退群
```python
await onebot.Send.To("group", 123456).Leave()
```

#### 群组管理：设置头衔
```python
await onebot.Send.To("group", 123456).SetTitle(789012, "专属头衔")
```

#### 群组管理：设置群头像
```python
await onebot.Send.To("group", 123456).SetPortrait("http://example.com/avatar.jpg")
```

#### 获取消息
```python
await onebot.Send.GetMsg(123456789)
```

#### 获取登录信息
```python
await onebot.Send.GetLoginInfo()
```

#### 获取好友列表
```python
await onebot.Send.GetFriendList()
```

#### 获取群信息
```python
await onebot.Send.To("group", 123456).GetGroupInfo()
```

#### 获取群列表
```python
await onebot.Send.GetGroupList()
```

#### 获取群成员信息
```python
await onebot.Send.To("group", 123456).GetGroupMemberInfo(789012)
```

#### 获取群成员列表
```python
await onebot.Send.To("group", 123456).GetGroupMemberList()
```

#### 发送文件
```python
await onebot.Send.To("user", 123456).File("http://example.com/file.pdf")
```

#### 点赞
```python
await onebot.Send.To("user", 123456).Like(789012, times=10)
```

---

## 支持的消息类型及对应方法

| 方法名   | 参数说明 | 用途 |
|----------|----------|------|
| `.Text(text: str)` | 发送纯文本消息 | 基础消息类型 |
| `.Image(file: str/bytes)` | 发送图片消息（URL 或 Base64 或 bytes） | 支持 CQ 格式 |
| `.Voice(file: str/bytes)` | 发送语音消息 | 支持 CQ 格式 |
| `.Video(file: str/bytes)` | 发送视频消息 | 支持 CQ 格式 |
| `.Face(id: Union[str, int])` | 发送表情 | CQ码表情 |
| `.At(user_id: Union[str, int], name: str = None)` | 发送@消息 | 群聊@功能 |
| `.Rps()` | 发送猜拳魔法表情 | 互动表情 |
| `.Dice()` | 发送掷骰子魔法表情 | 互动表情 |
| `.Shake()` | 发送窗口抖动（戳一戳） | 互动功能 |
| `.Location(lat: float, lon: float, title: str = "", content: str = "")` | 发送位置 | 位置分享 |
| `.Music(type: str, ...)` | 发送音乐分享 | 音乐分享 |
| `.Reply(message_id: Union[str, int])` | 发送回复消息 | 消息回复 |
| `.Xml(data: str)` | 发送XML消息 | 富媒体消息 |
| `.Json(data: str)` | 发送JSON消息 | 富媒体消息 |
| `.Poke(type: str, id: Union[str, int] = None, name: str = None)` | 发送戳一戳 | 互动功能 |
| `.Raw(message_list: List[Dict])` | 发送原始 OneBot 消息结构 | 自定义消息内容 |
| `.Recall(message_id: Union[str, int])` | 撤回指定消息 | 消息管理 |
| `.Edit(message_id: Union[str, int], new_text: str)` | 编辑消息（撤回+重发） | 消息管理 |
| `.Batch(target_ids: List[str], text: str)` | 批量发送消息 | 群发功能 |
| `.File(file: Union[str, bytes], filename: str = "file.dat")` | 发送文件 | 文件传输 |
| `.Like(user_id: Union[str, int], times: int = 1)` | 发送好友赞 | 互动功能 |
| `.Kick(user_id: Union[str, int], reject_add_request: bool = False)` | 移除群成员 | 群组管理 |
| `.Ban(user_id: Union[str, int], duration: int = 1800)` | 群组禁言 | 群组管理 |
| `.WholeBan(enable: bool = True)` | 全体禁言 | 群组管理 |
| `.SetAdmin(user_id: Union[str, int], enable: bool = True)` | 设置管理员 | 群组管理 |
| `.SetCard(user_id: Union[str, int], card: str = "")` | 设置群名片 | 群组管理 |
| `.SetGroupName(name: str)` | 设置群名称 | 群组管理 |
| `.Leave(is_dismiss: bool = False)` | 退群/解散群 | 群组管理 |
| `.SetTitle(user_id: Union[str, int], title: str = "")` | 设置群头衔 | 群组管理 |
| `.SetPortrait(file: Union[str, bytes])` | 设置群头像 | 群组管理 |
| `.GetMsg(message_id: Union[str, int])` | 获取消息内容 | API |
| `.GetForwardMsg(id: Union[str, int])` | 获取合并转发消息 | API |
| `.GetLoginInfo()` | 获取登录号信息 | API |
| `.GetFriendList()` | 获取好友列表 | API |
| `.GetGroupInfo()` | 获取群信息（需To） | API |
| `.GetGroupList()` | 获取群列表 | API |
| `.GetGroupMemberInfo(user_id: Union[str, int])` | 获取群成员信息（需To） | API |
| `.GetGroupMemberList()` | 获取群成员列表（需To） | API |

---

## 配置说明

### 多账户配置

OneBot11适配器支持多账户配置，每个 Bot 独立配置：

```toml
# 主账户（Server 模式，被动接收连接）
[OneBotAdapter.bots.main]
bot_id = "123456789"           # 机器人QQ号（必填）
mode = "server"                # server 或 client
server_path = "/onebot"        # WebSocket 路径
token = "your_token_here"      # 认证Token
enabled = true

# 备用账户（Client 模式，主动连接）
[OneBotAdapter.bots.backup]
bot_id = "987654321"
mode = "client"
url = "ws://127.0.0.1:3002"   # 主动连接的WS地址
token = "backup_token_here"
enabled = true

# 测试账户（禁用状态）
[OneBotAdapter.bots.test]
bot_id = "111111111"
mode = "client"
url = "ws://127.0.0.1:3003"
enabled = false
```

### 配置项说明

每个账户独立配置以下选项：

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `bot_id` | string | 是 | 机器人QQ号 |
| `mode` | string | 否 | 运行模式："server"(被动) 或 "client"(主动)，默认 "server" |
| `token` | string | 否 | 认证Token（Server模式验证客户端 / Client模式发送认证头） |
| `server_path` | string | 否 | Server模式下WebSocket路径，默认 "/" |
| `url` | string | 否 | Client模式下要连接的WebSocket地址，默认 "ws://127.0.0.1:3001" |
| `enabled` | bool | 否 | 是否启用该账户，默认 true |

---

## API 调用方式

### 多账户消息发送

```python
from ErisPulse.Core import adapter
onebot = adapter.get("onebot11")

# 使用账户名指定 Bot
await onebot.Send.Using("main").To("group", 123456).Text("来自主账户的消息")

# 使用 bot_id 指定 Bot
await onebot.Send.Using("987654321").To("group", 123456).Text("来自备用Bot的消息")

# 不指定时使用第一个启用的账户
await onebot.Send.To("group", 123456).Text("来自默认账户的消息")
```

---

## 事件处理

推荐使用标准 Event 模块装饰器监听事件：

```python
from ErisPulse.Core.Event import message, notice, request

@message.on_message()
async def handle_message(event):
    if event.get_platform() == "onebot11":
        await event.reply(f"收到消息: {event.get_text()}")

@notice.on_notice()
async def handle_notice(event):
    if event.get_platform() == "onebot11":
        if event.get("detail_type") == "group_member_increase":
            await event.reply(f"欢迎新成员!")

@request.on_friend_request()
async def handle_friend_request(event):
    await event.reply("好友请求已收到")
```

支持的事件类型：`message`、`notice`、`request`、`meta_event`。

---

## 运行模式说明

### 多账户运行模式

OneBot11适配器支持同时运行多个账户，每个账户可以独立配置为 Server 或 Client 模式：

```python
from ErisPulse.Core import adapter
onebot = adapter.get("onebot11")

# 查看所有账户
for name, account in onebot.accounts.items():
    print(f"{name}: bot_id={account.bot_id}, mode={account.mode}, enabled={account.enabled}")
```

### Server 模式（作为服务端监听连接）

- 启动一个 WebSocket 服务器等待 OneBot 客户端连接。
- 适用于部署多个 bot 客户端连接至同一服务端的场景。
- 每个Server账户会注册独立的WebSocket路由路径。

### Client 模式（主动连接 OneBot）

- 主动连接到 OneBot 服务（如 go-cqhttp）。
- 更适合单个 bot 实例直接连接的情况。
- 支持自动重连机制。

---

## 注意事项

1. 生产环境建议启用 Token 认证以保证安全性
2. 二进制内容（图片、语音等）支持 `str`(URL/路径) 和 `bytes` 传入
3. Server 模式下无需公网IP，Client 模式需 OneBot 服务端可被连接
4. 每个 Server 模式账户会注册独立的 WebSocket 路由路径

---

## 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [OneBot V11 协议文档](https://github.com/botuniverse/onebot-11)
- [模块开发指南](https://github.com/ErisPulse/ErisPulse/tree/main/docs/DEVELOPMENT.md)
