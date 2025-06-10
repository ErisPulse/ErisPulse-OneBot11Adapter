# OneBotAdapter 模块文档

## 简介
OneBotAdapter 是基于 [ErisPulse](https://github.com/ErisPulse/ErisPulse/) 架构开发的 **OneBot V11 协议适配器模块**。它提供统一的事件处理机制、连接管理功能，并支持 Server 和 Connect 两种运行模式。

---

## 使用示例

### 初始化与事件处理

```python
from ErisPulse import sdk

async def main():
    # 初始化 SDK
    sdk.init()

    # 获取适配器实例
    onebot = sdk.adapter.QQ

    # 注册事件处理器
    @onebot.on("message")
    async def handle_message(data):
        print(f"收到消息: {data}")
        await onebot.Send.To("user", data["user_id"]).Text("已收到您的消息！")

    @onebot.on("notice")
    async def handle_notice(data):
        print(f"收到通知: {data}")

    @onebot.on("request")
    async def handle_request(data):
        print(f"收到请求: {data}")

    # 启动适配器
    await sdk.adapter.startup()

    # 保持程序运行
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

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

#### 发送原生 CQ 消息
```python
await onebot.Send.To("user", 123456).Raw([
    {"type": "text", "data": {"text": "你好"}},
    {"type": "image", "data": {"file": "http://example.com/image.png"}}
])
```

---

## 支持的消息类型及对应方法

| 方法名   | 参数说明 | 用途 |
|----------|----------|------|
| `.Text(text: str)` | 发送纯文本消息 | 基础消息类型 |
| `.Image(file: str)` | 发送图片消息（URL 或 Base64） | 支持 CQ 格式 |
| `.Voice(file: str)` | 发送语音消息 | 支持 CQ 格式 |
| `.Video(file: str)` | 发送视频消息 | 支持 CQ 格式 |
| `.Raw(message_list: List[Dict])` | 发送原始 OneBot 消息结构 | 自定义消息内容 |

---

## 配置说明

在 `env.py` 中进行如下配置：

```python
sdk.env.set("OneBotAdapter", {
    "mode": "client",  # 可选 server 或 client
    "server": {
        "host": "127.0.0.1",      # WebSocket 监听地址
        "port": 8080,             # WebSocket 监听端口
        "path": "/",              # WebSocket 路径
        "token": "your_token"     # 认证 Token（可选）
    },
    "client": {
        "url": "ws://127.0.0.1:3001",  # 连接的目标地址
        "token": "your_token"         # 请求头或查询参数中的 Token
    }
})
```

---

## 事件类型

支持以下 OneBot 标准事件类型：

| 事件类型       | 映射名称 | 说明 |
|----------------|----------|------|
| `message`      | `message` | 消息事件 |
| `notice`       | `notice`  | 通知类事件（如群成员变动） |
| `request`      | `request` | 请求类事件（如加群请求） |
| `meta_event`   | `meta_event` | 元事件（如心跳包） |

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

## 运行模式说明

### Server 模式（作为服务端监听连接）

- 启动一个 WebSocket 服务器等待 OneBot 客户端连接。
- 适用于部署多个 bot 客户端连接至同一服务端的场景。

### Client 模式（主动连接 OneBot）

- 主动连接到 OneBot 服务（如 go-cqhttp）。
- 更适合单个 bot 实例直接连接的情况。

---

## 生命周期管理

### 启动适配器
```python
await sdk.adapter.startup()
```
此方法会根据配置启动 Server 或连接到 OneBot 客户端。

### 关闭适配器
```python
await sdk.adapter.shutdown()
```
确保资源释放，关闭 WebSocket 连接。

---

## 注意事项

1. 所有 `.Send.*()` 方法返回 `asyncio.Task`，建议使用 `await` 等待执行完成。
2. 确保在调用 `startup()` 前完成所有事件处理器注册。
3. 生产环境建议启用 Token 认证以保证安全性。
4. 若使用 Server 模式，请注意防火墙和端口开放情况。
5. 程序退出时请调用 `shutdown()` 释放资源。

---

## 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [OneBot V11 协议文档](https://github.com/botuniverse/onebot-11)
- [go-cqhttp 项目地址](https://github.com/Mrs4s/go-cqhttp)
- [模块开发指南](https://github.com/ErisPulse/ErisPulse/tree/main/docs/DEVELOPMENT.md)