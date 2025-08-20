# OneBotAdapter/Core.py
import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any, Union
from ErisPulse import sdk
from ErisPulse.Core import router  # 使用新的router模块

class OneBotAdapter(sdk.BaseAdapter):
    class Send(sdk.BaseAdapter.Send):
        def Text(self, text: str):
            """发送纯文本消息"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=self._target_id if self._target_type == "user" else None,
                    group_id=self._target_id if self._target_type == "group" else None,
                    message=text
                )
            )
        
        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            """发送图片消息"""
            return self._send_media("image", file, filename)

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            """发送语音消息"""
            return self._send_media("record", file, filename)

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            """发送视频消息"""
            return self._send_media("video", file, filename)

        def _send_media(self, msg_type: str, file: Union[str, bytes], filename: str):
            """发送媒体文件"""
            if isinstance(file, bytes):
                return self._send_bytes(msg_type, file, filename)
            else:
                return self._send(msg_type, {"file": file})

        def _send_bytes(self, msg_type: str, data: bytes, filename: str):
            """发送字节数据"""
            if msg_type in ["image", "record"]:
                try:
                    import base64
                    b64_data = base64.b64encode(data).decode('utf-8')
                    return self._send(msg_type, {"file": f"base64://{b64_data}"})
                except Exception as e:
                    self._adapter.logger.warning(f"Base64发送失败，回退到临时文件方式: {str(e)}")
            
            import tempfile
            import os
            import uuid
            
            temp_dir = os.path.join(tempfile.gettempdir(), "onebot_media")
            os.makedirs(temp_dir, exist_ok=True)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            filepath = os.path.join(temp_dir, unique_filename)
            
            with open(filepath, "wb") as f:
                f.write(data)
            
            try:
                return self._send(msg_type, {"file": filepath})
            finally:
                try:
                    os.remove(filepath)
                except:
                    pass

        def Raw(self, message_list: List[Dict]):
            """
            发送原生OneBot消息列表格式
            :param message_list: List[Dict], 例如：
                [{"type": "text", "data": {"text": "Hello"}}, {"type": "image", "data": {"file": "http://..."}}
            """
            # 构造CQ码字符串
            raw_message = ''.join([
                f"[CQ:{msg['type']},{','.join([f'{k}={v}' for k, v in msg['data'].items()])}]"
                for msg in message_list
            ])
            return self._send_raw(raw_message)

        def Recall(self, message_id: Union[str, int]):
            """撤回消息"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    message_id=message_id
                )
            )

        async def Edit(self, message_id: Union[str, int], new_text: str):
            """编辑消息（通过撤回+重新发送实现）"""
            await self.Recall(message_id)
            return self.Text(new_text)

        def Batch(self, target_ids: List[str], text: str, target_type: str = "user"):
            """批量发送消息"""
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
            """发送CQ码消息"""
            message = f"[CQ:{msg_type},{','.join([f'{k}={v}' for k, v in data.items()])}]"
            return self._send_raw(message)

        def _send_raw(self, message: str):
            """发送原始消息"""
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
        self.logger.info("OneBot11适配器初始化完成")

        self.convert = self._setup_coverter()

    def _setup_coverter(self):
        from .Converter import OneBot11Converter
        convert = OneBot11Converter()
        return convert.convert

    def _load_config(self) -> Dict:
        """加载配置，使用新的config模块"""
        config = self.sdk.config.get("OneBotv11_Adapter")
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
                self.sdk.config.set("OneBotv11_Adapter", default_config)
                return default_config
            except Exception as e:
                self.logger.error(f"保存默认配置失败: {str(e)}")
                return default_config
        return config

    def _setup_event_mapping(self):
        """设置事件映射"""
        self.event_map = {
            "message": "message",
            "notice": "notice",
            "request": "request",
            "meta_event": "meta_event"
        }
        self.logger.debug("事件映射已设置")

    async def call_api(self, endpoint: str, **params):
        """调用OneBot API"""
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
            raw_response = await asyncio.wait_for(future, timeout=30)
            self.logger.debug(f"API响应: {raw_response}")

            status = "ok"
            retcode = 0
            message = ""
            message_id = ""
            data = None

            if raw_response is not None:
                message_id = str(raw_response.get("message_id", ""))
                if "status" in raw_response:
                    status = raw_response["status"]
                retcode = raw_response.get("retcode", 0)
                message = raw_response.get("message", "")
                data = raw_response.get("data")

                if retcode != 0:
                    status = "failed"

            standardized_response = {
                "status": status,
                "retcode": retcode,
                "data": data,
                "message_id": message_id,
                "message": message,
                "onebot_raw": raw_response,
            }

            if "echo" in params:
                standardized_response["echo"] = params["echo"]

            return standardized_response

        except asyncio.TimeoutError:
            future.cancel()
            self.logger.error(f"API调用超时: {endpoint}")
            
            timeout_response = {
                "status": "failed",
                "retcode": 33001,
                "data": None,
                "message_id": "",
                "message": f"API调用超时: {endpoint}",
                "onebot_raw": None
            }
            
            if "echo" in params:
                timeout_response["echo"] = params["echo"]
                
            return timeout_response
            
        finally:
            if echo in self._api_response_futures:
                del self._api_response_futures[echo]
                self.logger.debug(f"已删除API响应Future: {echo}")

    async def connect(self, retry_interval=30):
        """连接到OneBot服务端（Client模式）"""
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
                self.logger.info(f"成功连接到OneBotV11服务器: {url}")
                asyncio.create_task(self._listen())
                return
            except Exception as e:
                retry_count += 1
                self.logger.error(f"第 {retry_count} 次连接失败: {str(e)}")
                self.logger.info(f"将在 {retry_interval} 秒后重试...")
                await asyncio.sleep(retry_interval)

    async def _listen(self):
        """监听WebSocket消息"""
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
        """处理接收到的消息"""
        try:
            data = json.loads(raw_msg)
            if "echo" in data:
                echo = data["echo"]
                future = self._api_response_futures.get(echo)
                if future and not future.done():
                    future.set_result(data)
                return

            post_type = data.get("post_type")
            event_type = self.event_map.get(post_type, "unknown")
            
            # 触发原始事件名
            await self.emit(post_type, data)
            
            # 触发映射后的事件名
            await self.emit(event_type, data)
            
            self.logger.debug(f"处理OneBotV11事件: {event_type}")
            
            # 转换为OneBot12事件并提交
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
        """WebSocket处理器（Server模式）"""
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
        """WebSocket认证处理器"""
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

    async def register_websocket(self):
        """注册WebSocket路由，使用新的router模块"""
        if self.config.get("mode") != "server":
            return

        server_config = self.config.get("server", {})
        path = server_config.get("path", "/")

        # 使用新的router模块注册WebSocket
        router.register_websocket(
            "onebot",  # 适配器名
            path,      # 路由路径
            self._ws_handler,  # 处理器
            auth_handler=self._auth_handler  # 认证处理器
        )

    async def start(self):
        """启动适配器"""
        mode = self.config.get("mode")
        if mode == "server":
            self.logger.info("正在注册Server模式WebSocket路由")
            await self.register_websocket()
        elif mode == "client":
            self.logger.info("正在启动Client模式")
            await self.connect()
        else:
            self.logger.error("无效的模式配置")
            raise ValueError("模式配置错误")

    async def shutdown(self):
        """关闭适配器"""
        if self.connection and not self.connection.closed:
            await self.connection.close()
        if self.session:
            await self.session.close()
        self.logger.info("OneBot适配器已关闭")