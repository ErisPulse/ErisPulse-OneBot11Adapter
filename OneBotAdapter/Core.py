# OneBotAdapter/Core.py
import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from typing import Any, Dict, List, Optional, Union
from collections.abc import Awaitable
from dataclasses import dataclass
from ErisPulse import sdk
from ErisPulse.Core import router
from ErisPulse.Core.Bases.adapter import RequestDSL


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

    {!--< tips >!--}
    1. 支持多账户管理，每个账户有独立的 bot_id
    2. 支持 self_id → account_name 自动映射，event.reply() 无需关心账户配置
    3. 提供 WebSocket Server/Client 混合运行模式
    4. 完整的 DSL 消息发送和请求操作接口
    {!--< /tips >!--}
    """

    class Send(sdk.BaseAdapter.Send):
        """消息发送DSL实现

        {!--< tips >!--}
        1. 支持 Text/Image/Voice/Video/Face/File 发送方法
        2. At/AtAll/Reply 修饰器自动转换为 OneBot11 消息段
        3. Raw_ob12 自动将 OneBot12 消息段转换为 OneBot11 格式
        {!--< /tips >!--}
        """

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None):
            super().__init__(adapter, target_type, target_id, account_id)
            self._at_user_ids = []
            self._reply_message_id = None
            self._at_all = False

        def _reset_modifiers(self):
            self._at_user_ids = []
            self._reply_message_id = None
            self._at_all = False

        def _build_ob11_message(self, message: Union[str, List[Dict]]) -> List[Dict]:
            """构建完整的 OneBot11 消息段数组（含修饰器）"""
            message_list = []

            # 修饰器按顺序添加到消息段前
            if self._reply_message_id:
                message_list.append(
                    {"type": "reply", "data": {"id": str(self._reply_message_id)}}
                )

            if self._at_all:
                message_list.append({"type": "at", "data": {"qq": "all"}})

            for user_info in self._at_user_ids:
                at_data = {"qq": user_info["qq"]}
                if user_info.get("name"):
                    at_data["name"] = user_info["name"]
                message_list.append({"type": "at", "data": at_data})

            # 消息内容
            if isinstance(message, str):
                message_list.append({"type": "text", "data": {"text": message}})
            else:
                message_list.extend(message)

            self._insert_text_separators(message_list)
            return message_list

        def _insert_text_separators(self, message_list: List[Dict]):
            """在 at/text 段之间自动插入空格"""
            result = []
            for i, segment in enumerate(message_list):
                seg_type = segment.get("type", "")
                result.append(segment)

                if i < len(message_list) - 1:
                    next_seg = message_list[i + 1]
                    next_type = next_seg.get("type", "")

                    if seg_type == "text" and next_type == "text":
                        result.append({"type": "text", "data": {"text": " "}})
                    elif seg_type == "at" and next_type == "text":
                        next_text = next_seg.get("data", {}).get("text", "")
                        if next_text and not next_text.startswith(" "):
                            result.append({"type": "text", "data": {"text": " "}})
                    elif seg_type == "text" and next_type == "at":
                        current_text = segment.get("data", {}).get("text", "")
                        if current_text and not current_text.endswith(" "):
                            result.append({"type": "text", "data": {"text": " "}})

            message_list.clear()
            message_list.extend(result)

        # ============ 标准发送方法（委托给 Raw_ob12） ============

        def Text(self, text: str):
            """发送文本消息"""
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            """发送图片消息"""
            return self.Raw_ob12(
                [{"type": "image", "data": {"file": file, "file_name": filename}}]
            )

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            """发送语音消息"""
            return self.Raw_ob12(
                [{"type": "audio", "data": {"file": file, "file_name": filename}}]
            )

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            """发送视频消息"""
            return self.Raw_ob12(
                [{"type": "video", "data": {"file": file, "file_name": filename}}]
            )

        def Face(self, id: Union[str, int]):
            """发送表情消息"""
            return self.Raw_ob12([{"type": "face", "data": {"id": str(id)}}])

        def File(self, file: Union[str, bytes], filename: str = "file.dat"):
            """发送文件消息"""
            return self.Raw_ob12(
                [{"type": "file", "data": {"file": file, "file_name": filename}}]
            )

        # ============ Raw_ob12（反向转换核心） ============

        def Raw_ob12(self, message, **kwargs):
            """
            发送 OneBot12 格式消息段，自动转换为 OneBot11 格式

            :param message: OneBot12 消息段（dict 或 list[dict]）
            :param kwargs: 额外参数
            :return: asyncio.Task
            """
            if isinstance(message, dict):
                message = [message]

            # OneBot12 → OneBot11 格式转换
            ob11_segments = self._convert_ob12_to_ob11(message)

            # 合并修饰器
            has_modifiers = self._at_user_ids or self._at_all or self._reply_message_id
            if has_modifiers:
                ob11_message = self._build_ob11_message(ob11_segments)
            else:
                self._insert_text_separators(ob11_segments)
                ob11_message = ob11_segments

            self._reset_modifiers()

            async def _do_send():
                params = {
                    "endpoint": "send_msg",
                    "account_id": self._account_id,
                    "message_type": "private"
                    if self._target_type == "user"
                    else "group",
                    "message": ob11_message,
                }
                if self._target_type == "user":
                    params["user_id"] = self._target_id
                else:
                    params["group_id"] = self._target_id
                params.update(kwargs)
                return await self._adapter.call_api(**params)

            return asyncio.create_task(_do_send())

        # ============ 修饰器方法 ============

        def At(self, user_id: Union[str, int], name: str = None):
            """@指定用户"""
            self._at_user_ids.append({"qq": str(user_id), "name": name})
            return self

        def AtAll(self):
            """@全体成员"""
            self._at_all = True
            return self

        def Reply(self, message_id: Union[str, int]):
            """回复指定消息"""
            self._reply_message_id = str(message_id)
            return self

        # ============ 其他操作方法 ============

        def Recall(self, message_id: Union[str, int]):
            """撤回消息"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    account_id=self._account_id,
                    message_id=str(message_id),
                )
            )

        # ============ 内部转换方法 ============

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

                if seg_type == "text":
                    ob11_message.append(
                        {"type": "text", "data": {"text": seg_data.get("text", "")}}
                    )
                elif seg_type == "image":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({"type": "image", "data": {"file": file}})
                elif seg_type in ("audio", "record"):
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({"type": "record", "data": {"file": file}})
                elif seg_type == "video":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    ob11_message.append({"type": "video", "data": {"file": file}})
                elif seg_type == "file":
                    file = seg_data.get("file") or seg_data.get("url", "")
                    file_name = seg_data.get("file_name", "")
                    data = {"file": file}
                    if file_name:
                        data["name"] = file_name
                    ob11_message.append({"type": "file", "data": data})
                elif seg_type == "face":
                    ob11_message.append(
                        {"type": "face", "data": {"id": seg_data.get("id", "")}}
                    )
                elif seg_type == "mention":
                    ob11_message.append(
                        {"type": "at", "data": {"qq": str(seg_data.get("user_id", ""))}}
                    )
                elif seg_type == "reply":
                    ob11_message.append(
                        {
                            "type": "reply",
                            "data": {"id": seg_data.get("message_id", "")},
                        }
                    )
                elif seg_type.startswith("onebot11_"):
                    cq_type = seg_type[10:]
                    ob11_message.append({"type": cq_type, "data": seg_data})
                else:
                    ob11_message.append({"type": seg_type, "data": seg_data})

            return ob11_message

    class Request(RequestDSL):
        """请求操作实现（好友请求、群邀请等）

        {!--< tips >!--}
        1. 使用 adapter.Request("flag").accept() 同意请求
        2. 使用 adapter.Request("flag").reject() 拒绝请求
        3. 通过 event.approve() / event.reject() 便捷操作
        {!--< /tips >!--}
        """

        def accept(self, **kwargs):
            """同意请求"""
            return self._create_task(self._do_action(approve=True, **kwargs))

        def reject(self, **kwargs):
            """拒绝请求"""
            return self._create_task(self._do_action(approve=False, **kwargs))

        async def _do_action(self, approve: bool, **kwargs) -> dict[str, Any]:
            """
            执行请求操作

            :param approve: 是否同意
            :param kwargs: 额外参数（如 comment 备注）
            :return: 标准响应格式
            """
            try:
                result = await self._adapter.call_api(
                    endpoint="set_friend_add_request"
                    if kwargs.get("_request_type") != "group"
                    else "set_group_add_request",
                    account_id=self._account_id,
                    flag=self._request_id,
                    approve=approve,
                    **{k: v for k, v in kwargs.items() if not k.startswith("_")},
                )

                return {
                    "status": result.get("status", "ok"),
                    "retcode": result.get("retcode", 0),
                    "data": result.get("data"),
                    "message_id": "",
                    "message": result.get("message", ""),
                    "onebot11_raw": result.get("onebot11_raw", result),
                }
            except Exception as e:
                return {
                    "status": "failed",
                    "retcode": 34000,
                    "data": None,
                    "message_id": "",
                    "message": str(e),
                    "onebot11_raw": None,
                }

    def __init__(self, sdk):
        super().__init__()
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = self.sdk.adapter

        # 加载配置
        self.accounts: Dict[str, OneBotAccountConfig] = self._load_account_configs()

        # 映射: raw self_id (OneBot事件中的真实ID) → account_name
        # 收到事件时自动填充，call_api 据此解析 account_id
        self._self_id_map: Dict[str, str] = {}

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

        # 转换器
        self.convert = self._setup_converter()

        # 注册平台事件扩展方法
        self._register_event_methods()

    def _setup_converter(self):
        """设置转换器"""
        from .Converter import OneBot11Converter

        converter = OneBot11Converter()
        return converter.convert

    def _register_event_methods(self):
        """注册 OneBot11 平台特有的 Event 方法"""
        try:
            from ErisPulse.Core.Event import register_event_mixin

            class OneBot11EventMixin:
                """OneBot11 平台事件扩展方法"""

                def get_raw_self_id(self) -> str:
                    """获取 OneBot 原始 self_id（机器人真实 QQ 号）"""
                    return self.get("self", {}).get("user_id", "")

                def get_sender_info(self) -> dict:
                    """获取完整发送者信息"""
                    return self.get("onebot11_raw", {}).get("sender", {})

                def get_sender_role(self) -> str:
                    """获取发送者在群中的角色（owner/admin/member）"""
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("role", "")
                    )

                def get_sender_level(self) -> int:
                    """获取发送者等级"""
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("level", 0)
                    )

                def get_sender_title(self) -> str:
                    """获取发送者群头衔"""
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("title", "")
                    )

                def is_system_message(self) -> bool:
                    """判断是否为系统消息"""
                    return self.get("sub_type") == "system"

            register_event_mixin("onebot11", OneBot11EventMixin)
        except Exception as e:
            self.logger.warning(f"注册 OneBot11 事件扩展方法失败: {e}")

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
                        "enabled": True,
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
                        "enabled": True,
                    }
                }

                try:
                    self.sdk.config.setConfig(
                        "OneBotv11_Adapter.accounts", default_config
                    )
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
                bot_id=str(config["bot_id"]),
                mode=config.get("mode", "server"),
                server_path=config.get("server_path", "/"),
                server_token=config.get("server_token", ""),
                client_url=config.get("client_url", "ws://127.0.0.1:3001"),
                client_token=config.get("client_token", ""),
                enabled=config.get("enabled", True),
                name=account_name,
            )

        self.logger.info(f"OneBot11适配器初始化完成，加载 {len(accounts)} 个账户")
        return accounts

    def _resolve_account(self, account_id: str = None) -> tuple:
        """
        解析账户，返回 (account_config, account_name)

        查找顺序：
        1. 账户名精确匹配
        2. self_id 映射匹配（OneBot 事件中的真实 ID）
        3. bot_id 匹配
        4. 回退到第一个可用账户（仅当 account_id 为 None 时）

        :param account_id: 账户标识（账户名 / self_id / bot_id）
        :return: (OneBotAccountConfig, account_name)
        :raises ValueError: 找不到匹配的账户
        """
        if account_id is None:
            if not self.accounts:
                raise ValueError("没有配置任何OneBot账户")
            account_name = next(iter(self.accounts.keys()))
            return self.accounts[account_name], account_name

        # 1. 账户名精确匹配
        if account_id in self.accounts:
            return self.accounts[account_id], account_id

        # 2. self_id 映射匹配
        if str(account_id) in self._self_id_map:
            account_name = self._self_id_map[str(account_id)]
            return self.accounts[account_name], account_name

        # 3. bot_id 匹配
        for account_name, acc_config in self.accounts.items():
            if str(acc_config.bot_id) == str(account_id):
                return acc_config, account_name

        raise ValueError(f"找不到账户 {account_id}")

    async def call_api(self, endpoint: str, account_id: str = None, **params):
        """
        调用 OneBot API

        :param endpoint: API端点
        :param account_id: 账户名 / self_id / bot_id（可选）
        :param params: 其他参数
        :return: 标准化响应
        """
        account, account_name = self._resolve_account(account_id)

        if not account.enabled:
            raise ValueError(f"账户 {account_name} 已禁用")

        connection = self.connections.get(account_name)
        if not connection:
            raise ConnectionError(f"账户 {account_name} 尚未连接")

        if hasattr(connection, "closed") and connection.closed:
            raise ConnectionError(f"账户 {account_name} 的连接已关闭")

        # 创建响应Future
        if account_name not in self._api_response_futures:
            self._api_response_futures[account_name] = {}

        echo = str(hash((str(params), account_name, endpoint)))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[account_name][echo] = future

        payload = {"action": endpoint, "params": params, "echo": echo}

        try:
            await connection.send_str(json.dumps(payload))
        except Exception as e:
            self.logger.error(
                f"账户 {account_name} (bot_id: {account.bot_id}) 发送请求失败: {str(e)}"
            )
            if echo in self._api_response_futures[account_name]:
                del self._api_response_futures[account_name][echo]
            raise

        try:
            self.logger.debug(
                f"账户 {account_name} (bot_id: {account.bot_id}) 请求: {payload}"
            )

            raw_response = await asyncio.wait_for(future, timeout=self.default_timeout)

            self.logger.debug(
                f"账户 {account_name} (bot_id: {account.bot_id}) 响应: {raw_response}"
            )

            # 从 data 中提取 message_id（OneBot11 标准）
            message_id = ""
            if isinstance(raw_response.get("data"), dict):
                message_id = str(raw_response["data"].get("message_id", ""))

            # 标准化响应
            status = "ok"
            retcode = raw_response.get("retcode", 0)
            if retcode != 0:
                status = "failed"

            standardized_response = {
                "status": status,
                "retcode": retcode,
                "data": raw_response.get("data"),
                "message_id": message_id,
                "message": raw_response.get("message", ""),
                "onebot11_raw": raw_response,
                "self": {"user_id": account.bot_id},
            }

            if "echo" in params:
                standardized_response["echo"] = params["echo"]

            return standardized_response

        except asyncio.TimeoutError:
            self.logger.error(
                f"账户 {account_name} (bot_id: {account.bot_id}) API调用超时: {endpoint}"
            )
            if not future.done():
                future.cancel()

            timeout_response = {
                "status": "failed",
                "retcode": 33001,
                "data": None,
                "message_id": "",
                "message": f"账户 {account_name} (bot_id: {account.bot_id}) API调用超时: {endpoint}",
                "onebot11_raw": None,
                "self": {"user_id": account.bot_id},
            }

            if "echo" in params:
                timeout_response["echo"] = params["echo"]

            return timeout_response

        finally:

            async def cleanup():
                await asyncio.sleep(0.1)
                if (
                    account_name in self._api_response_futures
                    and echo in self._api_response_futures[account_name]
                ):
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
                self.connections[account_name] = await self.sessions[
                    account_name
                ].ws_connect(url, headers=headers)
                self.logger.info(
                    f"账户 {account_name} (bot_id: {account.bot_id}) 连接成功"
                )
                await self.adapter.emit(
                    {
                        "type": "meta",
                        "detail_type": "connect",
                        "platform": "onebot11",
                        "self": {"platform": "onebot11", "user_id": account.bot_id},
                    }
                )
                asyncio.create_task(self._listen(account_name))
                return
            except Exception as e:
                self.logger.error(
                    f"账户 {account_name} (bot_id: {account.bot_id}) 连接失败: {str(e)}"
                )
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
                    self.logger.info(
                        f"账户 {account_name} (bot_id: {account.bot_id}) 连接已关闭"
                    )
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(
                        f"账户 {account_name} (bot_id: {account.bot_id}) WebSocket错误"
                    )
        except Exception as e:
            self.logger.error(
                f"账户 {account_name} (bot_id: {account.bot_id}) 监听异常: {str(e)}"
            )
        finally:
            try:
                await self.adapter.emit(
                    {
                        "type": "meta",
                        "detail_type": "disconnect",
                        "platform": "onebot11",
                        "self": {
                            "platform": "onebot11",
                            "user_id": account.bot_id if account else "",
                        },
                    }
                )
            except Exception:
                pass
            if account_name in self.connections:
                del self.connections[account_name]

            if self._is_running and account.enabled and account.mode == "client":
                self.logger.info(
                    f"账户 {account_name} (bot_id: {account.bot_id}) 开始重连..."
                )
                self.reconnect_tasks[account_name] = asyncio.create_task(
                    self.connect(account_name)
                )

    async def _handle_message(self, raw_msg: str, account_name: str):
        """处理WebSocket消息"""
        try:
            data = json.loads(raw_msg)
            account = self.accounts.get(account_name)
            if not account:
                return

            # 处理API响应
            if "echo" in data:
                future = self._api_response_futures.get(account_name, {}).get(
                    data["echo"]
                )
                if future and not future.done():
                    future.set_result(data)
                return

            # 处理事件
            if hasattr(self.adapter, "emit"):
                onebot_event = self.convert(data)
                if onebot_event:
                    # 记录 self_id → account_name 映射（用于 event.reply() 回路）
                    raw_self_id = onebot_event.get("self", {}).get("user_id", "")
                    if raw_self_id and str(raw_self_id) not in self._self_id_map:
                        self._self_id_map[str(raw_self_id)] = account_name
                        self.logger.info(
                            f"映射 self_id {raw_self_id} → 账户 {account_name}"
                        )
                    await self.adapter.emit(onebot_event)

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")

    async def _ws_handler(self, websocket: WebSocket, account_name: str = "default"):
        """WebSocket连接处理器"""
        account = self.accounts.get(account_name)
        if account:
            self.logger.info(
                f"账户 {account_name} (bot_id: {account.bot_id}) 客户端已连接"
            )

        self.connections[account_name] = websocket

        await self.adapter.emit(
            {
                "type": "meta",
                "detail_type": "connect",
                "platform": "onebot11",
                "self": {
                    "platform": "onebot11",
                    "user_id": account.bot_id if account else "",
                },
            }
        )

        try:
            while True:
                data = await websocket.receive_text()
                asyncio.create_task(self._handle_message(data, account_name))
        except WebSocketDisconnect:
            self.logger.info(
                f"账户 {account_name} (bot_id: {account.bot_id}) 客户端断开连接"
            )
        except Exception as e:
            self.logger.error(
                f"账户 {account_name} (bot_id: {account.bot_id}) WebSocket处理异常: {str(e)}"
            )
        finally:
            try:
                await self.adapter.emit(
                    {
                        "type": "meta",
                        "detail_type": "disconnect",
                        "platform": "onebot11",
                        "self": {
                            "platform": "onebot11",
                            "user_id": account.bot_id if account else "",
                        },
                    }
                )
            except Exception:
                pass
            if account_name in self.connections:
                del self.connections[account_name]

    async def _auth_handler(self, websocket: WebSocket, account_name: str = "default"):
        """WebSocket认证处理器"""
        if account_name not in self.accounts:
            await websocket.close(code=1008)
            return False

        account = self.accounts[account_name]
        if account.server_token:
            client_token = websocket.headers.get("Authorization", "").replace(
                "Bearer ", ""
            )
            if not client_token:
                query = dict(websocket.query_params)
                client_token = query.get("token", "")

            if client_token != account.server_token:
                self.logger.warning(
                    f"账户 {account_name} (bot_id: {account.bot_id}) Token无效"
                )
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
                    auth_handler=make_auth_handler(account_name),
                )
                self.logger.info(
                    f"已注册账户 {account_name} (bot_id: {account.bot_id}) 的Server路由: {path}"
                )

    async def start(self):
        """启动适配器"""
        self._is_running = True

        server_accounts = [
            name
            for name, acc in self.accounts.items()
            if acc.mode == "server" and acc.enabled
        ]
        client_accounts = [
            name
            for name, acc in self.accounts.items()
            if acc.mode == "client" and acc.enabled
        ]

        if server_accounts:
            await self.register_websocket()

        for account_name in client_accounts:
            account = self.accounts[account_name]
            self.logger.info(
                f"启动Client模式账户: {account_name} (bot_id: {account.bot_id})"
            )
            self.reconnect_tasks[account_name] = asyncio.create_task(
                self.connect(account_name)
            )

        enabled_count = len(server_accounts) + len(client_accounts)
        self.logger.info(f"OneBot11适配器启动完成，共 {enabled_count} 个账户")

    async def shutdown(self):
        """关闭适配器"""
        self._is_running = False

        # 取消重连任务
        for task in self.reconnect_tasks.values():
            if not task.done():
                task.cancel()
        self.reconnect_tasks.clear()

        # 关闭所有连接
        for account_name, connection in self.connections.items():
            account = self.accounts.get(account_name)
            try:
                if hasattr(connection, "closed") and not connection.closed:
                    await connection.close()
            except Exception as e:
                self.logger.error(
                    f"关闭账户 {account_name} (bot_id: {account.bot_id}) 连接失败: {str(e)}"
                )
        self.connections.clear()

        # 关闭所有 session
        for account_name, session in self.sessions.items():
            account = self.accounts.get(account_name)
            try:
                await session.close()
            except Exception as e:
                self.logger.error(
                    f"关闭账户 {account_name} (bot_id: {account.bot_id}) session失败: {str(e)}"
                )
        self.sessions.clear()

        # 清理平台事件方法注册
        try:
            from ErisPulse.Core.Event import unregister_platform_event_methods

            unregister_platform_event_methods("onebot11")
        except Exception:
            pass

        self.logger.info("OneBot11适配器已关闭")
