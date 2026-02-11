# OneBotAdapter/Core.py
import asyncio
import json
import aiohttp
import base64
import os
import tempfile
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from ErisPulse import sdk
from ErisPulse.Core import router


@dataclass
class OneBotAccountConfig:
    """OneBot11 账户配置"""
    bot_id: str  # 机器人ID（必填，用于SDK路由）
    mode: str  # "server" or "client"
    server_path: Optional[str] = "/"
    server_token: Optional[str] = ""
    client_url: Optional[str] = "ws://127.0.0.1:3001"
    client_token: Optional[str] = ""
    enabled: bool = True
    name: str = ""  # 账户名称


class OneBotAdapter(sdk.BaseAdapter):
    """
    OneBot11 平台适配器实现

    使用 OneBot11 消息段数组格式，避免 CQ 码字符串拼接
    """

    class Send(sdk.BaseAdapter.Send):
        """消息发送DSL实现"""

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None):
            super().__init__(adapter, target_type, target_id, account_id)
            self._at_user_ids = []       # @的用户列表
            self._reply_message_id = None # 回复的消息ID
            self._at_all = False         # 是否@全体
            
        def __getattr__(self, name):
            """
            处理未定义的发送方法
            
            当调用不存在的消息类型方法时，发送文本提示
            """
            def unsupported_method(*args, **kwargs):
                # 格式化参数信息
                params_info = []
                for i, arg in enumerate(args):
                    if isinstance(arg, bytes):
                        params_info.append(f"args[{i}]: <bytes: {len(arg)} bytes>")
                    else:
                        params_info.append(f"args[{i}]: {repr(arg)[:100]}")
                
                for k, v in kwargs.items():
                    if isinstance(v, bytes):
                        params_info.append(f"{k}: <bytes: {len(v)} bytes>")
                    else:
                        params_info.append(f"{k}: {repr(v)[:100]}")
                
                params_str = ", ".join(params_info)
                error_msg = f"[不支持的发送类型] 方法名: {name}, 参数: [{params_str}]"
                
                return self.Text(error_msg)
            
            return unsupported_method

        def _build_message_array(self, message: Union[str, List[Dict]]) -> List[Dict]:
            """
            构建消息数组，包含链式修饰
            
            :param message: 消息内容（字符串或消息段数组）
            :return: 完整的消息段数组
            """
            message_list = []
            
            # 添加回复
            if self._reply_message_id:
                message_list.append({
                    "type": "reply",
                    "data": {"id": str(self._reply_message_id)}
                })
            
            # 添加@全体
            if self._at_all:
                message_list.append({
                    "type": "at",
                    "data": {"qq": "all"}
                })
            
            # 添加@用户
            for user_info in self._at_user_ids:
                user_id = user_info["qq"]
                name = user_info.get("name")
                at_data = {"qq": user_id}
                if name:
                    at_data["name"] = name
                message_list.append({
                    "type": "at",
                    "data": at_data
                })
            
            # 添加消息内容
            if isinstance(message, str):
                message_list.append({
                    "type": "text",
                    "data": {"text": message}
                })
            else:
                message_list.extend(message)
            
            return message_list

        def _send(self, message_array: List[Dict]):
            """
            发送消息（使用数组格式）
            
            :param message_array: OneBot11 消息段数组
            :return: asyncio.Task
            """
            # 添加链式修饰
            if self._at_user_ids or self._at_all or self._reply_message_id:
                message_array = self._build_message_array(message_array)
            
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    account_id=self._account_id,
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=self._target_id if self._target_type == "user" else None,
                    group_id=self._target_id if self._target_type == "group" else None,
                    message=message_array
                )
            )

        def Text(self, text: str):
            """发送文本消息"""
            return self._send([{"type": "text", "data": {"text": text}}])

        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            """发送图片"""
            return self._send_media("image", file, filename)

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            """发送语音"""
            return self._send_media("record", file, filename)

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            """发送视频"""
            return self._send_media("video", file, filename)

        def Face(self, id: Union[str, int]):
            """发送表情"""
            return self._send([{"type": "face", "data": {"id": str(id)}}])

        def Raw_ob12(self, message, **kwargs):
            """
            发送原始 OneBot12 格式消息
            
            将 OneBot12 格式转换为 OneBot11 格式发送
            
            :param message: OneBot12 消息段或消息段数组
            :param kwargs: 额外参数
            :return: asyncio.Task
            """
            # 处理单条消息段的情况
            if isinstance(message, dict):
                message = [message]
            
            # 转换为 OneBot11 格式
            ob11_message = self._convert_ob12_to_ob11(message)
            
            # 添加链式修饰
            if self._at_user_ids or self._at_all or self._reply_message_id:
                ob11_message = self._build_message_array(ob11_message)
            
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_msg",
                    account_id=self._account_id,
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=self._target_id if self._target_type == "user" else None,
                    group_id=self._target_id if self._target_type == "group" else None,
                    message=ob11_message,
                    **kwargs
                )
            )

        def At(self, user_id: Union[str, int], name: str = None):
            """
            @用户（可多次调用）
            :param user_id: 用户ID
            :param name: 自定义@名称（可选）
            :return: self，支持链式调用
            """
            self._at_user_ids.append({"qq": str(user_id), "name": name})
            return self

        def AtAll(self):
            """
            @全体成员
            :return: self，支持链式调用
            """
            self._at_all = True
            return self

        def Reply(self, message_id: Union[str, int]):
            """
            回复消息
            :param message_id: 消息ID
            :return: self，支持链式调用
            """
            self._reply_message_id = str(message_id)
            return self

        def Recall(self, message_id: Union[str, int]):
            """撤回消息"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    account_id=self._account_id,
                    message_id=message_id
                )
            )

        def File(self, file: Union[str, bytes], filename: str = "file.dat"):
            """
            发送文件（通用接口）
            
            注意：OneBot11 标准没有独立的文件消息段类型
            此方法会根据文件类型自动选择合适的发送方式：
            - 图片文件：使用 Image
            - 音频文件：使用 Voice
            - 视频文件：使用 Video
            - 其他文件：尝试发送（可能不被支持）
            
            :param file: 文件内容（bytes）或 URL（str）
            :param filename: 文件名
            :return: asyncio.Task
            """
            # 判断文件类型
            if isinstance(file, str):
                # URL 方式，无法判断类型，尝试作为普通文本发送
                return self._send([{"type": "text", "data": {"text": f"[文件] {file}"}}])
            
            # 根据 filename 判断类型
            filename_lower = filename.lower()
            if any(ext in filename_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                return self.Image(file, filename)
            elif any(ext in filename_lower for ext in ['.mp3', '.amr', '.wav', '.ogg', '.flac', '.m4a']):
                return self.Voice(file, filename)
            elif any(ext in filename_lower for ext in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']):
                return self.Video(file, filename)
            else:
                # 其他类型，尝试发送
                return self._send([{"type": "text", "data": {"text": f"[文件] {filename}"}}])

        def _convert_ob12_to_ob11(self, message: List[Dict]) -> List[Dict]:
            """
            将 OneBot12 消息段数组转换为 OneBot11 格式
            
            :param message: OneBot12 消息段数组
            :return: OneBot11 消息段数组
            """
            ob11_message = []
            
            for segment in message:
                seg_type = segment.get("type", "")
                seg_data = segment.get("data", {})
                
                # 文本消息
                if seg_type == "text":
                    ob11_message.append({
                        "type": "text",
                        "data": {"text": seg_data.get("text", "")}
                    })
                
                # 图片
                elif seg_type == "image":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({
                        "type": "image",
                        "data": {"file": file}
                    })
                
                # 语音/音频
                elif seg_type == "audio" or seg_type == "record":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({
                        "type": "record",
                        "data": {"file": file}
                    })
                
                # 视频
                elif seg_type == "video":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({
                        "type": "video",
                        "data": {"file": file}
                    })
                
                # 表情
                elif seg_type == "face":
                    face_id = seg_data.get("id", "")
                    ob11_message.append({
                        "type": "face",
                        "data": {"id": face_id}
                    })
                
                # @用户（mention）
                elif seg_type == "mention":
                    user_id = seg_data.get("user_id", "")
                    ob11_message.append({
                        "type": "at",
                        "data": {"qq": str(user_id)}
                    })
                
                # 回复
                elif seg_type == "reply":
                    msg_id = seg_data.get("message_id", "")
                    ob11_message.append({
                        "type": "reply",
                        "data": {"id": msg_id}
                    })
                
                # OneBot11 扩展消息段（直接保留）
                elif seg_type.startswith("onebot11_"):
                    cq_type = seg_type[10:]  # 去掉 onebot11_ 前缀
                    ob11_message.append({
                        "type": cq_type,
                        "data": seg_data
                    })
                
                # 其他未知类型，直接保留
                else:
                    ob11_message.append({
                        "type": seg_type,
                        "data": seg_data
                    })
            
            return ob11_message

        def _send_media(self, msg_type: str, file: Union[str, bytes], filename: str):
            """
            发送媒体文件
            
            :param msg_type: 消息类型（image/record/video）
            :param file: 文件内容（bytes）或 URL（str）
            :param filename: 文件名
            :return: asyncio.Task
            """
            if isinstance(file, bytes):
                return self._send_bytes(msg_type, file, filename)
            else:
                return self._send([{"type": msg_type, "data": {"file": file}}])

        def _send_bytes(self, msg_type: str, data: bytes, filename: str):
            """
            发送二进制文件
            
            :param msg_type: 消息类型
            :param data: 二进制数据
            :param filename: 文件名
            :return: asyncio.Task
            """
            # 优先尝试 base64 方式
            if msg_type in ["image", "record"]:
                try:
                    b64_data = base64.b64encode(data).decode('utf-8')
                    return self._send([{
                        "type": msg_type,
                        "data": {"file": f"base64://{b64_data}"}
                    }])
                except Exception as e:
                    self._adapter.logger.warning(f"Base64发送失败: {str(e)}")
            
            # 创建临时文件
            temp_dir = os.path.join(tempfile.gettempdir(), "onebot_media")
            os.makedirs(temp_dir, exist_ok=True)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            filepath = os.path.join(temp_dir, unique_filename)
            
            try:
                with open(filepath, "wb") as f:
                    f.write(data)
                
                return self._send([{
                    "type": msg_type,
                    "data": {"file": filepath}
                }])
            finally:
                try:
                    # 延迟删除，确保发送完成
                    async def delayed_cleanup():
                        await asyncio.sleep(1)
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
                    asyncio.create_task(delayed_cleanup())
                except Exception:
                    pass

    def __init__(self, sdk):
        super().__init__()
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = self.sdk.adapter

        # 加载配置
        self.accounts: Dict[str, OneBotAccountConfig] = self._load_account_configs()
        
        # 连接池 - 每个账户一个连接
        self._api_response_futures: Dict[str, Dict[str, asyncio.Future]] = {}
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.connections: Dict[str, aiohttp.ClientWebSocketResponse] = {}
        
        # 重连任务
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        
        # 初始化状态
        self._is_running = False
        
        # 默认配置
        self.default_retry_interval = 30
        self.default_timeout = 30

        self.convert = self._setup_converter()

    def _setup_converter(self):
        """设置转换器"""
        from .Converter import OneBot11Converter
        converter = OneBot11Converter()
        return converter.convert

    def _load_account_configs(self) -> Dict[str, OneBotAccountConfig]:
        """加载多账户配置"""
        accounts = {}
        
        # 检查新格式配置
        account_configs = self.sdk.config.getConfig("OneBotv11_Adapter.accounts", {})
        
        if not account_configs:
            # 检查旧格式配置
            old_config = self.sdk.config.getConfig("OneBotv11_Adapter")
            if old_config:
                self.logger.warning("检测到旧格式配置，正在迁移...")
                mode = old_config.get("mode", "server")
                server_config = old_config.get("server", {})
                client_config = old_config.get("client", {})
                
                account_configs = {
                    "default": {
                        "bot_id": "default",
                        "mode": mode,
                        "server_path": server_config.get("path", "/"),
                        "server_token": server_config.get("token", ""),
                        "client_url": client_config.get("url", "ws://127.0.0.1:3001"),
                        "client_token": client_config.get("token", ""),
                        "enabled": True
                    }
                }
            else:
                # 创建默认配置
                self.logger.info("创建默认账户配置")
                default_config = {
                    "default": {
                        "bot_id": "机器人ID/QQ号",
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
                    self.logger.error(f"保存默认配置失败: {str(e)}")
                    account_configs = default_config

        # 创建账户配置对象
        for account_name, config in account_configs.items():
            if "bot_id" not in config or not config["bot_id"]:
                self.logger.error(f"账户 {account_name} 缺少bot_id，已跳过")
                continue
            
            accounts[account_name] = OneBotAccountConfig(
                bot_id=config["bot_id"],
                mode=config.get("mode", "server"),
                server_path=config.get("server_path", "/"),
                server_token=config.get("server_token", ""),
                client_url=config.get("client_url", "ws://127.0.0.1:3001"),
                client_token=config.get("client_token", ""),
                enabled=config.get("enabled", True),
                name=account_name
            )
        
        self.logger.info(f"OneBot11适配器初始化完成，加载 {len(accounts)} 个账户")
        return accounts

    async def call_api(self, endpoint: str, account_id: str = None, **params):
        """
        调用 OneBot API
        
        :param endpoint: API端点
        :param account_id: 账户名或bot_id
        :param params: 其他参数
        :return: 标准化响应
        """
        # 确定使用的账户
        if account_id is None:
            if not self.accounts:
                raise ValueError("没有配置任何OneBot账户")
            account = next(iter(self.accounts.values()))
            account_name = next(iter(self.accounts.keys()))
        else:
            if account_id in self.accounts:
                account = self.accounts[account_id]
                account_name = account_id
            else:
                for account_name, acc_config in self.accounts.items():
                    if acc_config.bot_id == account_id:
                        account = acc_config
                        break
                else:
                    raise ValueError(f"找不到账户 {account_id}")
        
        if not account.enabled:
            raise ValueError(f"账户 {account_name} 已禁用")

        connection = self.connections.get(account_name)
        if not connection:
            raise ConnectionError(f"账户 {account_name} 尚未连接")

        if connection.closed:
            raise ConnectionError(f"账户 {account_name} 的连接已关闭")

        # 创建响应Future
        if account_name not in self._api_response_futures:
            self._api_response_futures[account_name] = {}

        echo = str(hash((str(params), account_name)))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[account_name][echo] = future

        payload = {
            "action": endpoint,
            "params": params,
            "echo": echo
        }

        try:
            await connection.send_str(json.dumps(payload))
        except Exception as e:
            self.logger.error(f"账户 {account_name} 发送请求失败: {str(e)}")
            if echo in self._api_response_futures[account_name]:
                del self._api_response_futures[account_name][echo]
            raise

        try:
            raw_response = await asyncio.wait_for(future, timeout=self.default_timeout)

            # 标准化响应
            status = "ok"
            retcode = raw_response.get("retcode", 0)
            if retcode != 0:
                status = "failed"

            standardized_response = {
                "status": status,
                "retcode": retcode,
                "data": raw_response.get("data"),
                "message_id": str(raw_response.get("message_id", "")),
                "message": raw_response.get("message", ""),
                "onebot_raw": raw_response,
                "self": {"user_id": account.bot_id}
            }

            if "echo" in params:
                standardized_response["echo"] = params["echo"]

            return standardized_response

        except asyncio.TimeoutError:
            self.logger.error(f"账户 {account_name} API调用超时: {endpoint}")
            if not future.done():
                future.cancel()

            timeout_response = {
                "status": "failed",
                "retcode": 33001,
                "data": None,
                "message_id": "",
                "message": f"账户 {account_name} API调用超时: {endpoint}",
                "onebot_raw": None,
                "self": {"user_id": account.bot_id}
            }

            if "echo" in params:
                timeout_response["echo"] = params["echo"]

            return timeout_response

        finally:
            async def cleanup():
                await asyncio.sleep(0.1)
                if account_name in self._api_response_futures and echo in self._api_response_futures[account_name]:
                    del self._api_response_futures[account_name][echo]

            asyncio.create_task(cleanup())

    async def connect(self, account_name: str, retry_interval=None):
        """连接指定账户的OneBot服务"""
        if account_name not in self.accounts:
            raise ValueError(f"账户 {account_name} 不存在")

        account = self.accounts[account_name]
        if account.mode != "client":
            return

        if account_name not in self.sessions:
            self.sessions[account_name] = aiohttp.ClientSession()

        headers = {}
        if account.client_token:
            headers["Authorization"] = f"Bearer {account.client_token}"

        url = account.client_url
        retry_interval = retry_interval or self.default_retry_interval

        while self._is_running:
            try:
                self.connections[account_name] = await self.sessions[account_name].ws_connect(url, headers=headers)
                self.logger.info(f"账户 {account_name} (bot_id: {account.bot_id}) 连接成功")
                asyncio.create_task(self._listen(account_name))
                return
            except Exception as e:
                self.logger.error(f"账户 {account_name} 连接失败: {str(e)}")
                await asyncio.sleep(retry_interval)

    async def _listen(self, account_name: str):
        """监听指定账户的WebSocket消息"""
        connection = self.connections.get(account_name)
        if not connection:
            return

        account = self.accounts.get(account_name)

        try:
            async for msg in connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    asyncio.create_task(self._handle_message(msg.data, account_name))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info(f"账户 {account_name} 连接已关闭")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"账户 {account_name} WebSocket错误")
        except Exception as e:
            self.logger.error(f"账户 {account_name} 监听异常: {str(e)}")
        finally:
            if account_name in self.connections:
                del self.connections[account_name]

            if self._is_running and account.enabled and account.mode == "client":
                self.logger.info(f"账户 {account_name} 开始重连...")
                self.reconnect_tasks[account_name] = asyncio.create_task(self.connect(account_name))

    async def _handle_message(self, raw_msg: str, account_name: str):
        """处理WebSocket消息"""
        try:
            data = json.loads(raw_msg)
            account = self.accounts.get(account_name)
            if not account:
                return

            # 处理API响应
            if "echo" in data:
                future = self._api_response_futures.get(account_name, {}).get(data["echo"])
                if future and not future.done():
                    future.set_result(data)
                return

            # 处理事件
            if hasattr(self.adapter, "emit"):
                onebot_event = self.convert(data)
                if onebot_event:
                    if "self" not in onebot_event or not onebot_event.get("self", {}).get("user_id"):
                        onebot_event["self"] = {"user_id": account.bot_id}
                    await self.adapter.emit(onebot_event)

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")

    async def _ws_handler(self, websocket: WebSocket, account_name: str = "default"):
        """WebSocket连接处理器"""
        account = self.accounts.get(account_name)
        if account:
            self.logger.info(f"账户 {account_name} (bot_id: {account.bot_id}) 客户端已连接")

        self.connections[account_name] = websocket

        try:
            while True:
                data = await websocket.receive_text()
                asyncio.create_task(self._handle_message(data, account_name))
        except WebSocketDisconnect:
            self.logger.info(f"账户 {account_name} 客户端断开连接")
        except Exception as e:
            self.logger.error(f"账户 {account_name} WebSocket处理异常: {str(e)}")
        finally:
            if account_name in self.connections:
                del self.connections[account_name]

    async def _auth_handler(self, websocket: WebSocket, account_name: str = "default"):
        """WebSocket认证处理器"""
        if account_name not in self.accounts:
            await websocket.close(code=1008)
            return False

        account = self.accounts[account_name]
        if account.server_token:
            client_token = websocket.headers.get("Authorization", "").replace("Bearer ", "")
            if not client_token:
                query = dict(websocket.query_params)
                client_token = query.get("token", "")

            if client_token != account.server_token:
                self.logger.warning(f"账户 {account_name} Token无效")
                await websocket.close(code=1008)
                return False
        return True

    async def register_websocket(self):
        """注册WebSocket路由"""
        for account_name, account in self.accounts.items():
            if account.mode == "server" and account.enabled:
                path = account.server_path

                def make_ws_handler(name):
                    async def handler(ws):
                        await self._ws_handler(ws, name)
                    return handler

                def make_auth_handler(name):
                    async def handler(ws):
                        return await self._auth_handler(ws, name)
                    return handler

                router.register_websocket(
                    f"onebot11_{account_name}",
                    path,
                    make_ws_handler(account_name),
                    auth_handler=make_auth_handler(account_name)
                )
                self.logger.info(f"已注册账户 {account_name} 的Server路由: {path}")

    async def start(self):
        """启动适配器"""
        self._is_running = True

        server_accounts = [name for name, acc in self.accounts.items() if acc.mode == "server" and acc.enabled]
        client_accounts = [name for name, acc in self.accounts.items() if acc.mode == "client" and acc.enabled]

        if server_accounts:
            await self.register_websocket()

        for account_name in client_accounts:
            self.reconnect_tasks[account_name] = asyncio.create_task(self.connect(account_name))

        enabled_count = len(server_accounts) + len(client_accounts)
        self.logger.info(f"OneBot11适配器启动完成，共 {enabled_count} 个账户")

    async def shutdown(self):
        """关闭适配器"""
        self._is_running = False

        for task in self.reconnect_tasks.values():
            if not task.done():
                task.cancel()
        self.reconnect_tasks.clear()

        for account_name, connection in self.connections.items():
            try:
                if not connection.closed:
                    await connection.close()
            except Exception as e:
                self.logger.error(f"关闭连接失败: {str(e)}")
        self.connections.clear()

        for session in self.sessions.values():
            try:
                await session.close()
            except Exception as e:
                self.logger.error(f"关闭session失败: {str(e)}")
        self.sessions.clear()

        self.logger.info("OneBot11适配器已关闭")
