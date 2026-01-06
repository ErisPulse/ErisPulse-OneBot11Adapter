# OneBotAdapter/Core.py
import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from ErisPulse import sdk
from ErisPulse.Core import router

@dataclass
class OneBotAccountConfig:
    mode: str  # "server" or "client"
    server_path: Optional[str] = "/"
    server_token: Optional[str] = ""
    client_url: Optional[str] = "ws://127.0.0.1:3001"
    client_token: Optional[str] = ""
    enabled: bool = True
    name: str = ""

class OneBotAdapter(sdk.BaseAdapter):
    class Send(sdk.BaseAdapter.Send):
        def Text(self, text: str):
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    account_id=self._account_id,
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
                except Exception:
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
                    account_id=self._account_id,
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
                        account_id=self._account_id,
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
                    account_id=self._account_id,
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

        # 加载配置
        self.accounts: Dict[str, OneBotAccountConfig] = self._load_account_configs()
        
        # 连接池 - 每个账户一个连接
        self._api_response_futures: Dict[str, Dict[str, asyncio.Future]] = {}  # account_id -> {echo: future}
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.connections: Dict[str, aiohttp.ClientWebSocketResponse] = {}
        
        # 轮询任务
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        
        # 初始化状态
        self._is_running = False
        
        # 默认配置值
        self.default_retry_interval = 30
        self.default_timeout = 30
        self.default_max_retries = 3
        
        self.logger.info(f"OneBot11适配器初始化完成，共加载 {len(self.accounts)} 个账户")

        self.convert = self._setup_coverter()

    def _setup_coverter(self):
        from .Converter import OneBot11Converter
        convert = OneBot11Converter()
        return convert.convert

    def _load_account_configs(self) -> Dict[str, OneBotAccountConfig]:
        accounts = {}
        
        # 检查新格式的账户配置
        account_configs = self.sdk.config.getConfig("OneBotv11_Adapter.accounts", {})
        
        if not account_configs:
            # 检查旧配置格式，进行兼容性处理
            old_config = self.sdk.config.getConfig("OneBotv11_Adapter")
            if old_config:
                self.logger.warning("检测到旧格式配置，正在临时兼容处理...")
                self.logger.warning("建议迁移到新配置格式以获得更好的多账户支持。")
                self.logger.warning("迁移方法：将现有配置移动到 OneBotv11_Adapter.accounts.default 下")
                
                # 临时使用旧配置，创建默认账户
                mode = old_config.get("mode", "server")
                server_config = old_config.get("server", {})
                client_config = old_config.get("client", {})
                
                # 不自动保存新配置，只在内存中创建
                temp_config = {
                    "default": {
                        "mode": mode,
                        "server_path": server_config.get("path", "/"),
                        "server_token": server_config.get("token", ""),
                        "client_url": client_config.get("url", "ws://127.0.0.1:3001"),
                        "client_token": client_config.get("token", ""),
                        "enabled": True
                    }
                }
                account_configs = temp_config
                
                self.logger.warning(f"已临时加载旧配置为默认账户，请尽快迁移到新格式")
                
            else:
                # 创建默认账户配置
                self.logger.info("未找到配置文件，创建默认账户配置")
                default_config = {
                    "default": {
                        "mode": "server",
                        "server_path": "/",
                        "server_token": "",
                        "client_url": "ws://127.0.0.1:3001",
                        "client_token": "",
                        "enabled": True
                    }
                }
                
                try:
                    self.sdk.config.setConfig("OneBotv11_Adapter.accounts", default_config)
                    account_configs = default_config
                except Exception as e:
                    self.logger.error(f"保存默认账户配置失败: {str(e)}")
                    # 即使保存失败也使用内存中的配置
                    account_configs = default_config

        # 创建账户配置对象
        for account_name, config in account_configs.items():
            # 使用内置默认值
            merged_config = {
                "mode": config.get("mode", "server"),
                "server_path": config.get("server_path", "/"),
                "server_token": config.get("server_token", ""),
                "client_url": config.get("client_url", "ws://127.0.0.1:3001"),
                "client_token": config.get("client_token", ""),
                "enabled": config.get("enabled", True),
                "name": account_name
            }
            
            accounts[account_name] = OneBotAccountConfig(**merged_config)
        
        return accounts
    
    async def call_api(self, endpoint: str, account_id: str = None, **params):
        # 确定使用的账户ID
        if account_id is None:
            if not self.accounts:
                raise ValueError("没有配置任何OneBot账户")
            account_id = next(iter(self.accounts.keys()))
        
        if account_id not in self.accounts:
            raise ValueError(f"账户 {account_id} 不存在")
        
        account = self.accounts[account_id]
        if not account.enabled:
            raise ValueError(f"账户 {account_id} 已禁用")
        
        connection = self.connections.get(account_id)
        if not connection:
            raise ConnectionError(f"账户 {account_id} 尚未连接到OneBot")
        
        # 检查连接是否仍然活跃
        if connection.closed:
            raise ConnectionError(f"账户 {account_id} 的WebSocket连接已关闭")

        # 确保该账户的响应Future字典存在
        if account_id not in self._api_response_futures:
            self._api_response_futures[account_id] = {}

        echo = str(hash(str(params + (account_id,))))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[account_id][echo] = future
        self.logger.debug(f"账户 {account_id} 创建API调用Future: {echo}")

        payload = {
            "action": endpoint,
            "params": params,
            "echo": echo
        }

        # 记录发送的payload
        self.logger.debug(f"账户 {account_id} 准备发送API请求: {payload}")
        
        try:
            await connection.send_str(json.dumps(payload))
            self.logger.debug(f"账户 {account_id} 调用OneBot API: {endpoint}")
        except Exception as e:
            self.logger.error(f"账户 {account_id} 发送API请求失败: {str(e)}")
            # 清理Future
            if echo in self._api_response_futures[account_id]:
                del self._api_response_futures[account_id][echo]
            raise

        try:
            self.logger.debug(f"账户 {account_id} 开始等待Future: {echo}")
            # 使用较长的超时时间
            raw_response = await asyncio.wait_for(future, timeout=self.default_timeout)
            self.logger.debug(f"账户 {account_id} API响应: {raw_response}")

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
                "self": {"user_id": account_id}  # 使用标准字段标识机器人账号
            }

            if "echo" in params:
                standardized_response["echo"] = params["echo"]

            return standardized_response

        except asyncio.TimeoutError:
            self.logger.error(f"账户 {account_id} API调用超时: {endpoint}")
            if not future.done():
                future.cancel()
            
            timeout_response = {
                "status": "failed",
                "retcode": 33001,
                "data": None,
                "message_id": "",
                "message": f"账户 {account_id} API调用超时: {endpoint}",
                "onebot_raw": None,
                "self": {"user_id": account_id}  # 使用标准字段标识机器人账号
            }
            
            if "echo" in params:
                timeout_response["echo"] = params["echo"]
                
            return timeout_response
            
        finally:
            # 延迟清理Future，给可能的响应一些处理时间
            async def delayed_cleanup():
                await asyncio.sleep(0.1)  # 给一点时间处理可能的响应
                if account_id in self._api_response_futures and echo in self._api_response_futures[account_id]:
                    del self._api_response_futures[account_id][echo]
                    self.logger.debug(f"账户 {account_id} 已删除API响应Future: {echo}")
            
            asyncio.create_task(delayed_cleanup())

    async def connect(self, account_id: str, retry_interval=None):
        """连接指定账户的OneBot服务"""
        if account_id not in self.accounts:
            raise ValueError(f"账户 {account_id} 不存在")
        
        account = self.accounts[account_id]
        if account.mode != "client":
            return

        # 创建该账户的session
        if account_id not in self.sessions:
            self.sessions[account_id] = aiohttp.ClientSession()
        
        headers = {}
        if account.client_token:
            headers["Authorization"] = f"Bearer {account.client_token}"

        url = account.client_url
        retry_count = 0
        retry_interval = retry_interval or self.default_retry_interval

        while self._is_running:
            try:
                self.connections[account_id] = await self.sessions[account_id].ws_connect(url, headers=headers)
                self.logger.info(f"账户 {account_id} 成功连接到OneBotV11服务器: {url}")
                asyncio.create_task(self._listen(account_id))
                return
            except Exception as e:
                retry_count += 1
                self.logger.error(f"账户 {account_id} 第 {retry_count} 次连接失败: {str(e)}")
                self.logger.info(f"账户 {account_id} 将在 {retry_interval} 秒后重试...")
                await asyncio.sleep(retry_interval)

    async def _listen(self, account_id: str):
        """监听指定账户的WebSocket消息"""
        connection = self.connections.get(account_id)
        if not connection:
            return
            
        try:
            self.logger.debug(f"账户 {account_id} 开始监听WebSocket消息")
            async for msg in connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self.logger.debug(f"账户 {account_id} 收到WebSocket消息: {msg.data[:100]}...")  # 只显示前100个字符
                    # 在新的任务中处理消息，避免阻塞
                    asyncio.create_task(self._handle_message(msg.data, account_id))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info(f"账户 {account_id} WebSocket连接已关闭")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"账户 {account_id} WebSocket错误: {connection.exception()}")
        except Exception as e:
            self.logger.error(f"账户 {account_id} WebSocket监听异常: {str(e)}")
        finally:
            self.logger.debug(f"账户 {account_id} 退出WebSocket监听")
            # 清理连接
            if account_id in self.connections:
                del self.connections[account_id]
            
            # 如果仍在运行，尝试重连
            if self._is_running and self.accounts[account_id].enabled and self.accounts[account_id].mode == "client":
                self.logger.info(f"账户 {account_id} 开始重连...")
                self.reconnect_tasks[account_id] = asyncio.create_task(self.connect(account_id))

    async def _handle_api_response(self, data: Dict, account_id: str):
        echo = data["echo"]
        self.logger.debug(f"账户 {account_id} 收到API响应, echo: {echo}")
        
        if account_id not in self._api_response_futures:
            self.logger.warning(f"账户 {account_id} 不存在响应Future字典")
            return
            
        future = self._api_response_futures[account_id].get(echo)
        
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
            self.logger.warning(f"账户 {account_id} 未找到对应的Future: {echo}")

    async def _handle_message(self, raw_msg: str, account_id: str):
        try:
            data = json.loads(raw_msg)
            # API响应优先处理
            if "echo" in data:
                self.logger.debug(f"账户 {account_id} 识别为API响应消息: {data.get('echo')}")
                await self._handle_api_response(data, account_id)
                return
            
            self.logger.debug(f"账户 {account_id} 处理OneBotV11事件: {data.get('post_type')}")
            
            # 转换为OneBot12事件并提交
            if hasattr(self.adapter, "emit"):
                onebot_event = self.convert(data)
                # 检查转换后的事件是否包含self.user_id，如果没有则添加配置中的账户ID
                if onebot_event:
                    if "self" not in onebot_event or not onebot_event.get("self", {}).get("user_id"):
                        onebot_event["self"] = {"user_id": account_id}
                        self.logger.debug(f"账户 {account_id} 添加配置中的账户ID")
                    
                    self.logger.debug(f"账户 {account_id} OneBot12事件数据: {json.dumps(onebot_event, ensure_ascii=False)}")
                    await self.adapter.emit(onebot_event)

        except json.JSONDecodeError:
            self.logger.error(f"账户 {account_id} JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"账户 {account_id} 消息处理异常: {str(e)}")

    async def _ws_handler(self, websocket: WebSocket, account_id: str = "default"):
        self.connections[account_id] = websocket
        self.logger.info(f"账户 {account_id} 的OneBot客户端已连接")

        try:
            while True:
                data = await websocket.receive_text()
                # 在新的任务中处理消息，避免阻塞
                asyncio.create_task(self._handle_message(data, account_id))
        except WebSocketDisconnect:
            self.logger.info(f"账户 {account_id} 的OneBot客户端断开连接")
        except Exception as e:
            self.logger.error(f"账户 {account_id} WebSocket处理异常: {str(e)}")
        finally:
            if account_id in self.connections:
                del self.connections[account_id]
    
    async def _auth_handler(self, websocket: WebSocket, account_id: str = "default"):
        if account_id not in self.accounts:
            self.logger.warning(f"账户 {account_id} 不存在")
            await websocket.close(code=1008)
            return False
            
        account = self.accounts[account_id]
        if account.server_token:
            client_token = websocket.headers.get("Authorization", "").replace("Bearer ", "")
            if not client_token:
                query = dict(websocket.query_params)
                client_token = query.get("token", "")

            if client_token != account.server_token:
                self.logger.warning(f"账户 {account_id} 客户端提供的Token无效")
                await websocket.close(code=1008)
                return False
        return True

    async def register_websocket(self):
        # 注册所有server模式的账户
        for account_id, account in self.accounts.items():
            if account.mode == "server" and account.enabled:
                path = account.server_path
                
                # 为每个账户创建专用的处理器
                def make_ws_handler(account_id):
                    async def ws_handler(websocket):
                        await self._ws_handler(websocket, account_id)
                    return ws_handler
                
                def make_auth_handler(account_id):
                    async def auth_handler(websocket):
                        return await self._auth_handler(websocket, account_id)
                    return auth_handler
                
                router.register_websocket(
                    f"onebot11_{account_id}",  # 使用账户ID作为适配器名
                    path,                      # 路由路径
                    make_ws_handler(account_id),  # 处理器
                    auth_handler=make_auth_handler(account_id)  # 认证处理器
                )
                self.logger.info(f"已注册账户 {account_id} 的Server模式WebSocket路由: {path}")

    async def start(self):
        self._is_running = True
        
        # 注册所有server模式的账户WebSocket路由
        server_accounts = [aid for aid, acc in self.accounts.items() if acc.mode == "server" and acc.enabled]
        client_accounts = [aid for aid, acc in self.accounts.items() if acc.mode == "client" and acc.enabled]
        
        if server_accounts:
            self.logger.info(f"正在注册 {len(server_accounts)} 个Server模式账户的WebSocket路由")
            await self.register_websocket()
        
        if client_accounts:
            self.logger.info(f"正在启动 {len(client_accounts)} 个Client模式账户")
            for account_id in client_accounts:
                self.reconnect_tasks[account_id] = asyncio.create_task(self.connect(account_id))
        
        if not server_accounts and not client_accounts:
            self.logger.warning("没有启用任何账户")
        
        self.logger.info("OneBot11适配器启动完成")

    async def shutdown(self):
        self._is_running = False
        
        # 取消所有重连任务
        for task in self.reconnect_tasks.values():
            if not task.done():
                task.cancel()
        self.reconnect_tasks.clear()
        
        # 关闭所有连接
        for account_id, connection in self.connections.items():
            try:
                if not connection.closed:
                    await connection.close()
            except Exception as e:
                self.logger.error(f"关闭账户 {account_id} 连接失败: {str(e)}")
        self.connections.clear()
        
        # 关闭所有session
        for account_id, session in self.sessions.items():
            try:
                await session.close()
            except Exception as e:
                self.logger.error(f"关闭账户 {account_id} session失败: {str(e)}")
        self.sessions.clear()
        
        self.logger.info("OneBot11适配器已关闭")