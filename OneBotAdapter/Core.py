import asyncio
import json
import aiohttp
from typing import Dict, List, Optional, Any
from ErisPulse import sdk
from abc import ABC, abstractmethod


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

    def register_adapters(self):
        return {
            "QQ": OneBotAdapter
        }


class OneBotAdapter(sdk.BaseAdapter):
    """
    OneBot协议适配器
    支持两种模式:
    1. Server模式: 作为WebSocket服务器接收OneBot实现端的连接
    2. Client模式: 作为WebSocket客户端连接OneBot实现端
    """

    def __init__(self, sdk):
        super().__init__()
        self.sdk = sdk
        self.logger = sdk.logger
        self.config = self._load_config()
        self._api_response_futures = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.connection: Optional[aiohttp.ClientWebSocketResponse] = None
        self._setup_event_mapping()
        self.logger.info("OneBot适配器初始化完成")

    def _load_config(self) -> Dict:
        config = self.sdk.env.get("OneBotAdapter", {})
        if not config:
            self.logger.warning("""
            OneBot配置缺失，请在env.py中添加配置:
            sdk.env.set("OneBotAdapter", {
                "mode": "connect|server",
                "server": {
                    "host": "127.0.0.1",
                    "port": 8080,
                    "path": "/",
                    "token": ""
                },
                "client": {
                    "url": "ws://127.0.0.1:3001",
                    "token": ""
                }
            })
            """)
        return config

    def _setup_event_mapping(self):
        self.event_map = {
            "message": "message",
            "notice": "notice",
            "request": "request",
            "meta_event": "meta_event"
        }
        self.logger.debug("事件映射已设置")

    async def send(self, conversation_type: str, target_id: int, message: Any, **kwargs) -> dict:
        if not isinstance(message, str):
            message = str(message)

        echo = str(hash(f"{conversation_type}_{target_id}_{message}"))

        payload = {
            "action": "send_msg",
            "params": {
                "message_type": conversation_type,
                f"{conversation_type}_id": target_id,
                "message": message
            },
            "echo": echo
        }

        if not self.connection or self.connection.closed:
            raise ConnectionError("OneBot连接未建立")

        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[echo] = future

        await self.connection.send_str(json.dumps(payload))
        self.logger.debug(f"发送OneBot消息: {payload}")

        try:
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except asyncio.TimeoutError:
            future.cancel()
            self.logger.error("发送消息超时，未收到 OneBot 响应")
            return {"error": "timeout"}
        finally:
            if echo in self._api_response_futures:
                del self._api_response_futures[echo]

    async def send_action(self, action: str, **params) -> Any:
        if not self.connection or self.connection.closed:
            raise ConnectionError("OneBot连接未建立")

        payload = {
            "action": action,
            "params": params,
            "echo": str(hash(f"{action}_{params}"))
        }

        await self.connection.send_str(json.dumps(payload))
        self.logger.debug(f"发送OneBot动作: {payload}")

    async def connect(self):
        if self.config.get("mode") != "client":
            return

        self.session = aiohttp.ClientSession()
        headers = {}
        if token := self.config.get("client", {}).get("token"):
            headers["Authorization"] = f"Bearer {token}"

        try:
            self.connection = await self.session.ws_connect(
                self.config["client"]["url"],
                headers=headers
            )
            self.logger.info(f"成功连接到OneBot服务器: {self.config['client']['url']}")
            asyncio.create_task(self._listen())
        except Exception as e:
            self.logger.error(f"OneBot连接失败: {str(e)}")
            raise

    async def start_server(self):
        if self.config.get("mode") != "server":
            return

        app = aiohttp.web.Application()
        app.router.add_route('GET', self.config["server"].get("path", "/"), self._handle_ws)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()

        server_config = self.config["server"]
        site = aiohttp.web.TCPSite(
            runner,
            server_config.get("host", "127.0.0.1"),
            server_config.get("port", 8080)
        )
        await site.start()
        self.logger.info(f"OneBot服务器启动于 ws://{site.name}")

    async def _handle_ws(self, request):
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        # 验证Token
        if token := self.config["server"].get("token"):
            client_token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not client_token:
                client_token = request.query.get("token", "")

            if client_token != token:
                self.logger.warning("客户端提供的Token无效")
                await ws.close()
                return ws

        self.connection = ws
        self.logger.info("新的OneBot客户端已连接")

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
        finally:
            self.logger.info("OneBot客户端断开连接")
            await ws.close()

        return ws

    async def _listen(self):
        try:
            async for msg in self.connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket错误: {self.connection.exception()}")
        except Exception as e:
            self.logger.error(f"WebSocket监听异常: {str(e)}")

    async def _handle_message(self, raw_msg: str):
        try:
            data = json.loads(raw_msg)
            if "echo" in data:
                echo = data["echo"]
                future = self._api_response_futures.get(echo)
                if future and not future.done():
                    future.set_result(data.get("data"))
                return

            post_type = data.get("post_type")
            event_type = self.event_map.get(post_type, "unknown")
            await self.emit(event_type, data)
            self.logger.debug(f"处理OneBot事件: {event_type}")

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")

    async def call_api(self, endpoint: str, **params) -> Any:
        if not self.connection:
            raise ConnectionError("尚未连接到OneBot")

        echo = str(hash(str(params)))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[echo] = future

        payload = {
            "action": endpoint,
            "params": params,
            "echo": echo
        }

        await self.connection.send_str(json.dumps(payload))
        self.logger.debug(f"调用OneBot API: {endpoint}")

        try:
            # 等待响应（最长30秒）
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except asyncio.TimeoutError:
            future.cancel()
            self.logger.error(f"API调用超时: {endpoint}")
            raise TimeoutError(f"API调用超时: {endpoint}")
        finally:
            if echo in self._api_response_futures:
                del self._api_response_futures[echo]

    async def start(self):
        mode = self.config.get("mode")
        if mode == "server":
            self.logger.info("正在启动Server模式")
            await self.start_server()
        elif mode == "client":
            self.logger.info("正在启动Client模式")
            await self.connect()
        else:
            self.logger.error("无效的模式配置")
            raise ValueError("模式配置错误")

    async def shutdown(self):
        if self.connection and not self.connection.closed:
            await self.connection.close()
        if self.session:
            await self.session.close()
        self.logger.info("OneBot适配器已关闭")
