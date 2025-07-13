import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any, Type
from ErisPulse import sdk
from ErisPulse.Core import adapter_server

class OneBotAdapter(sdk.BaseAdapter):
    class Send(sdk.BaseAdapter.Send):
        def Text(self, text: str):
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=self._target_id if self._target_type == "user" else None,
                    group_id=self._target_id if self._target_type == "group" else None,
                    message=text
                )
            )

        def Image(self, file: str):
            return self._send("image", {"file": file})

        def Voice(self, file: str):
            return self._send("voice", {"file": file})

        def Video(self, file: str):
            return self._send("video", {"file": file})

        def Raw(self, message_list):
            """
            发送原生OneBot消息列表格式
            :param message_list: List[Dict], 例如：
                [{"type": "text", "data": {"text": "Hello"}}, {"type": "image", "data": {"file": "http://..."}}
            """
            raw_message = ''.join([
                f"[CQ:{msg['type']},{','.join([f'{k}={v}' for k, v in msg['data'].items()])}]"
                for msg in message_list
            ])
            return self._send_raw(raw_message)

        def Recall(self, message_id: int):
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    message_id=message_id
                )
            )

        async def Edit(self, message_id: int, new_text: str):
            await self.Recall(message_id)
            return self.Text(new_text)

        def Batch(self, target_ids: List[str], text: str, target_type: str = "user"):
            tasks = []
            for target_id in target_ids:
                task = asyncio.create_task(
                    self._adapter.call_api(
                        endpoint="send_msg",
                        message_type=target_type,
                        user_id=target_id if target_type == "user" else None,
                        group_id=target_id if target_type == "group" else None,
                        message=text
                    )
                )
                tasks.append(task)
            return tasks

        def _send(self, msg_type: str, data: dict):
            message = f"[CQ:{msg_type},{','.join([f'{k}={v}' for k, v in data.items()])}]"
            return self._send_raw(message)

        def _send_raw(self, message: str):
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=self._target_id if self._target_type == "user" else None,
                    group_id=self._target_id if self._target_type == "group" else None,
                    message=message
                )
            )

    def __init__(self, sdk):
        super().__init__()
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = self.sdk.adapter

        self.config = self._load_config()
        self._api_response_futures = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.connection: Optional[aiohttp.ClientWebSocketResponse] = None
        self._setup_event_mapping()
        self.logger.info("OneBot适配器初始化完成")

        self.convert = self._setup_coverter()

    def _setup_coverter(self):
        from .Converter import OneBot11Converter
        convert = OneBot11Converter()
        return convert.convert

    def _load_config(self) -> Dict:
        config = self.sdk.env.getConfig("OneBotv11_Adapter")
        self.logger.debug(f"读取配置: {config}")
        if not config:
            default_config = {
                "mode": "server",
                "server": {
                    "path": "/",
                    "token": ""
                },
                "client": {
                    "url": "ws://127.0.0.1:3001",
                    "token": ""
                }
            }
            try:
                sdk.logger.warning("配置文件不存在，已创建默认配置文件")
                self.sdk.env.setConfig("OneBotv11_Adapter", default_config)
                return default_config
            except Exception as e:
                self.logger.error(f"保存默认配置失败: {str(e)}")
                return default_config
        return config

    def _setup_event_mapping(self):
        self.event_map = {
            "message": "message",
            "notice": "notice",
            "request": "request",
            "meta_event": "meta_event"
        }
        self.logger.debug("事件映射已设置")

    async def call_api(self, endpoint: str, **params):
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
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except asyncio.TimeoutError:
            future.cancel()
            self.logger.error(f"API调用超时: {endpoint}")
            raise TimeoutError(f"API调用超时: {endpoint}")
            return None
        finally:
            if echo in self._api_response_futures:
                del self._api_response_futures[echo]
                self.logger.debug(f"已删除API响应Future: {echo}")
    async def connect(self, retry_interval=30):
        if self.config.get("mode") != "client":
            return

        self.session = aiohttp.ClientSession()
        headers = {}
        if token := self.config.get("client", {}).get("token"):
            headers["Authorization"] = f"Bearer {token}"

        url = self.config["client"]["url"]
        retry_count = 0

        while True:
            try:
                self.connection = await self.session.ws_connect(url, headers=headers)
                self.logger.info(f"成功连接到OneBot服务器: {url}")
                asyncio.create_task(self._listen())
                return
            except Exception as e:
                retry_count += 1
                self.logger.error(f"第 {retry_count} 次连接失败: {str(e)}")
                self.logger.info(f"将在 {retry_interval} 秒后重试...")
                await asyncio.sleep(retry_interval)

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
            if hasattr(self.adapter, "emit"):
                onebot_event = self.convert(data)
                self.logger.debug(f"OneBot12事件数据: {json.dumps(onebot_event, ensure_ascii=False)}")
                if onebot_event:
                    await self.adapter.emit(onebot_event)

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")
    async def _ws_handler(self, websocket: WebSocket):
        self.connection = websocket
        self.logger.info("新的OneBot客户端已连接")

        try:
            while True:
                data = await websocket.receive_text()
                await self._handle_message(data)
        except WebSocketDisconnect:
            self.logger.info("OneBot客户端断开连接")
        except Exception as e:
            self.logger.error(f"WebSocket处理异常: {str(e)}")
        finally:
            self.connection = None
    
    async def _auth_handler(self, websocket: WebSocket):
        if token := self.config["server"].get("token"):
            client_token = websocket.headers.get("Authorization", "").replace("Bearer ", "")
            if not client_token:
                query = dict(websocket.query_params)
                client_token = query.get("token", "")

            if client_token != token:
                self.logger.warning("客户端提供的Token无效")
                await websocket.close(code=1008)
                return False
        return True
    async def start(self):
        mode = self.config.get("mode")
        if mode == "server":
            self.logger.info("正在注册Server模式WebSocket路由")
            adapter_server.register_websocket(
                adapter_name="onebot",
                path="/ws",
                handler=self._ws_handler,
                auth_handler=self._auth_handler
            )
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