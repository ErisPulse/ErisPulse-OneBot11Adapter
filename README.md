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

---

## 配置说明
```toml
[OneBotv11_Adapter]
mode = "server"  # 或 "client"

[OneBotv11_Adapter.server]
path = "/"
token = ""

[OneBotv11_Adapter.client]
url = "ws://127.0.0.1:3001"
token = ""
```

### 配置项说明

- `mode`: 运行模式，可选 "server"（服务端）或 "client"（客户端）
- `server.path`: Server模式下的WebSocket路径
- `server.token`: Server模式下的认证Token（可选）
- `client.url`: Client模式下要连接的WebSocket地址
- `client.token`: Client模式下的认证Token（可选）

---

## API 调用方式

通过 `call_api` 方法调用 OneBot 提供的任意 API 接口：

```python
response = await onebot.call_api(
    endpoint="send_msg",
    message_type="group",
    group_id=123456,
    message="Hello!"
)
```

该方法会自动处理响应结果并返回，若超时将抛出异常。

---

## 事件处理

OneBot适配器支持两种方式监听事件：

```python
# 使用原始事件名
@sdk.adapter.OneBot.on("message")
async def handle_message(event):
    pass

# 使用映射后的事件名
@sdk.adapter.OneBot.on("message")
async def handle_message(event):
    pass
```

支持的事件类型包括：
- `message`: 消息事件
- `notice`: 通知事件
- `request`: 请求事件
- `meta_event`: 元事件

---

## 运行模式说明

### Server 模式（作为服务端监听连接）

- 启动一个 WebSocket 服务器等待 OneBot 客户端连接。
- 适用于部署多个 bot 客户端连接至同一服务端的场景。

### Client 模式（主动连接 OneBot）

- 主动连接到 OneBot 服务（如 go-cqhttp）。
- 更适合单个 bot 实例直接连接的情况。

---

## 注意事项

1. 生产环境建议启用 Token 认证以保证安全性。
2. 对于二进制内容（如图片、语音等），支持直接传入 bytes 数据。

---

## 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [OneBot V11 协议文档](https://github.com/botuniverse/onebot-11)
- [go-cqhttp 项目地址](https://github.com/Mrs4s/go-cqhttp)
- [模块开发指南](https://github.com/ErisPulse/ErisPulse/tree/main/docs/DEVELOPMENT.md)
