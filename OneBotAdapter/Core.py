# OneBotAdapter/Core.py
import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any, Union
from ErisPulse import sdk
from ErisPulse.Core import router

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
        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            return self._send_media("image", file, filename)
        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            return self._send_media("record", file, filename)
        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            return self._send_media("video", file, filename)
        def Face(self, id: Union[str, int]):
            return self._send("face", {"id": str(id)})
        def At(self, user_id: Union[str, int], name: str = None):
            data = {"qq": str(user_id)}
            if name:
                data["name"] = name
            return self._send("at", data)
        def Rps(self):
            return self._send("rps", {})
        def Dice(self):
            return self._send("dice", {})
        def Shake(self):
            return self._send("shake", {})
        def Anonymous(self, ignore: bool = False):
            return self._send("anonymous", {"ignore": ignore})
        def Contact(self, type: str, id: Union[str, int]):
            return self._send("contact", {"type": type, "id": str(id)})
        def Location(self, lat: float, lon: float, title: str = "", content: str = ""):
            return self._send("location", {
                "lat": str(lat),
                "lon": str(lon),
                "title": title,
                "content": content
            })
        def Music(self, type: str, id: Union[str, int] = None, url: str = None, 
                  audio: str = None, title: str = None, content: str = None, 
                  image: str = None):
            data = {"type": type}
            if id:
                data["id"] = str(id)
            if url:
                data["url"] = url
            if audio:
                data["audio"] = audio
            if title:
                data["title"] = title
            if content:
                data["content"] = content
            if image:
                data["image"] = image
            return self._send("music", data)
        def Reply(self, message_id: Union[str, int]):
            return self._send("reply", {"id": str(message_id)})
        def Forward(self, id: Union[str, int]):
            return self._send("forward", {"id": str(id)})
        def Node(self, user_id: Union[str, int], nickname: str, content: str):
            return self._send("node", {
                "user_id": str(user_id),
                "nickname": nickname,
                "content": content
            })
        def Xml(self, data: str):
            return self._send("xml", {"data": data})
        def Json(self, data: str):
            return self._send("json", {"data": data})
        def Poke(self, type: str, id: Union[str, int] = None, name: str = None):
            data = {"type": type}
            if id:
                data["id"] = str(id)
            if name:
                data["name"] = name
            return self._send("poke", data)
        def Gift(self, user_id: Union[str, int], gift_id: Union[str, int]):
            return self._send("gift", {
                "qq": str(user_id),
                "id": str(gift_id)
            })
        def MarketFace(self, face_id: str):
            return self._send("market_face", {"id": face_id})
        def _send_media(self, msg_type: str, file: Union[str, bytes], filename: str):
            if isinstance(file, bytes):
                return self._send_bytes(msg_type, file, filename)
            else:
                return self._send(msg_type, {"file": file})
        def _send_bytes(self, msg_type: str, data: bytes, filename: str):
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
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    message_id=message_id
                )
            )

        async def Edit(self, message_id: Union[str, int], new_text: str):
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
        self.logger.info("OneBot11适配器初始化完成")

        self.convert = self._setup_coverter()

    def _setup_coverter(self):
        from .Converter import OneBot11Converter
        convert = OneBot11Converter()
        return convert.convert

    def _load_config(self) -> Dict:
        config = self.sdk.config.getConfig("OneBotv11_Adapter")
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
                self.sdk.config.setConfig("OneBotv11_Adapter", default_config)
                return default_config
            except Exception as e:
                self.logger.error(f"保存默认配置失败: {str(e)}")
                return default_config
        return config
    
    async def call_api(self, endpoint: str, **params):
        if not self.connection:
            raise ConnectionError("尚未连接到OneBot")
        
        # 检查连接是否仍然活跃
        if self.connection.closed:
            raise ConnectionError("WebSocket连接已关闭")

        echo = str(hash(str(params)))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[echo] = future
        self.logger.debug(f"创建API调用Future: {echo}")

        payload = {
            "action": endpoint,
            "params": params,
            "echo": echo
        }

        # 记录发送的payload
        self.logger.debug(f"准备发送API请求: {payload}")
        
        try:
            await self.connection.send_str(json.dumps(payload))
            self.logger.debug(f"调用OneBot API: {endpoint}")
        except Exception as e:
            self.logger.error(f"发送API请求失败: {str(e)}")
            # 清理Future
            if echo in self._api_response_futures:
                del self._api_response_futures[echo]
            raise

        try:
            self.logger.debug(f"开始等待Future: {echo}")
            # 使用较长的超时时间
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
            self.logger.error(f"API调用超时: {endpoint}")
            if not future.done():
                future.cancel()
            
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
            # 延迟清理Future，给可能的响应一些处理时间
            async def delayed_cleanup():
                await asyncio.sleep(0.1)  # 给一点时间处理可能的响应
                if echo in self._api_response_futures:
                    del self._api_response_futures[echo]
                    self.logger.debug(f"已删除API响应Future: {echo}")
            
            asyncio.create_task(delayed_cleanup())

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
            self.logger.debug("开始监听WebSocket消息")
            async for msg in self.connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self.logger.debug(f"收到WebSocket消息: {msg.data[:100]}...")  # 只显示前100个字符
                    # 在新的任务中处理消息，避免阻塞
                    asyncio.create_task(self._handle_message(msg.data))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info("WebSocket连接已关闭")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket错误: {self.connection.exception()}")
        except Exception as e:
            self.logger.error(f"WebSocket监听异常: {str(e)}")
        finally:
            self.logger.debug("退出WebSocket监听")

    async def _handle_api_response(self, data: Dict):
        echo = data["echo"]
        self.logger.debug(f"收到API响应, echo: {echo}")
        future = self._api_response_futures.get(echo)
        
        if future:
            self.logger.debug(f"Future状态 - 已完成: {future.done()}, 已取消: {future.cancelled()}")
            if not future.done():
                self.logger.debug(f"正在设置Future结果: {echo}")
                # 直接设置结果，避免使用call_soon_threadsafe
                future.set_result(data)
                self.logger.debug(f"Future结果设置完成: {echo}")
            else:
                self.logger.warning(f"Future已经完成，无法设置结果: {echo}")
        else:
            self.logger.warning(f"未找到对应的Future: {echo}")

    async def _handle_message(self, raw_msg: str):
        try:
            data = json.loads(raw_msg)
            # API响应优先处理
            if "echo" in data:
                self.logger.debug(f"识别为API响应消息: {data.get('echo')}")
                await self._handle_api_response(data)
                return

            post_type = data.get("post_type")
            
            await self.emit(post_type, data)
            
            self.logger.debug(f"处理OneBotV11事件: {post_type}")
            
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
        self.connection = websocket
        self.logger.info("新的OneBot客户端已连接")

        try:
            while True:
                data = await websocket.receive_text()
                # 在新的任务中处理消息，避免阻塞
                asyncio.create_task(self._handle_message(data))
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

    async def register_websocket(self):
        if self.config.get("mode") != "server":
            return

        server_config = self.config.get("server", {})
        path = server_config.get("path", "/")

        router.register_websocket(
            "onebot11",  # 适配器名
            path,      # 路由路径
            self._ws_handler,  # 处理器
            auth_handler=self._auth_handler  # 认证处理器
        )

    async def start(self):
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
        if self.connection and not self.connection.closed:
            await self.connection.close()
        if self.session:
            await self.session.close()
        self.logger.info("OneBot适配器已关闭")