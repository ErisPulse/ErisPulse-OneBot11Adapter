# OneBotAdapter 模块文档

## 简介
OneBotAdapter 是基于全新 [ErisPulse - 1.0.15dev0](https://github.com/ErisPulse/ErisPulse/) 架构设计的 OneBot V11 协议适配器，提供统一的事件处理和连接管理功能。

## 主要特性
- 统一的事件处理机制
- 支持 Server 和 Connect 两种运行模式
- 内置消息、通知、请求等事件处理
- 完善的连接管理和错误处理
- 遵循新架构设计规范

## 使用示例

```python
from ErisPulse import sdk

async def main():
    # 初始化 SDK
    sdk.init()
    
    # 启动适配器
    await sdk.adapter.startup()
    
    # 注册事件处理器
    qq = sdk.adapter.QQ
    
    @qq.on("message")
    async def handle_message(data):
        print(f"收到消息: {data}")
    
    @qq.on("notice")
    async def handle_notice(data):
        print(f"收到通知: {data}")
    
    @qq.on("request")
    async def handle_request(data):
        print(f"收到请求: {data}")

    # 发送消息示例
    await qq.send("group", 123456, "Hello World!")
    
    # 保持程序运行
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## 配置说明
在 `env.py` 中进行如下配置：

```python
sdk.env.set("OneBotAdapter", {
    "mode": "client",  # 或 "server"
    "server": {
        "host": "127.0.0.1",
        "port": 8080,
        "path": "/",
        "token": "your_token"
    },
    "client": {
        "url": "ws://127.0.0.1:3001/",
        "token": "your_token"
    }
})
```

## 事件处理
通过 `@adapter.on(event_type)` 装饰器注册事件处理器：
```python
@qq.on("message")
async def handler(data):
    # 处理逻辑
```

## API 调用
使用 `call_api` 方法调用 OneBot API：
```python
await qq.call_api("send_msg", message_type="group", group_id=123456, message="Hello!")
```

## 注意事项
- 确保在调用 `startup()` 前完成所有处理器的注册
- 在程序结束时调用 `shutdown()` 进行清理
- 根据实际需求选择合适的运行模式（Server/Connect）

# 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [ErisPulse 模块开发指南](https://github.com/ErisPulse/ErisPulse/tree/main/docs/DEVELOPMENT.md)
