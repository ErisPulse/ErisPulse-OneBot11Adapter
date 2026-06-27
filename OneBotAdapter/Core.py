"""
OneBot11 适配器核心模块

实现 OneBot11 协议与 ErisPulse 框架的对接，支持 WebSocket Server/Client 混合运行模式

{!--< tips >!--}
1. 支持多账户管理
2. 支持 self_id → account_name 自动映射，event.reply() 无需关心账户配置
3. 提供 WebSocket Server/Client 混合运行模式
4. 完整的 DSL 消息发送和请求操作接口
{!--< /tips >!--}
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ErisPulse.Core import router
from ErisPulse.Core.Bases.adapter import BaseAdapter, RequestDSL
from ErisPulse.runtime.config_schema import BotAccountConfig


@dataclass
class OneBotAccountConfig(BotAccountConfig):
    """
    OneBot11 账户配置

    {!--< tips >!--}
    1. mode 为 client 时使用 url + token 主动连接 OneBot 服务
    2. mode 为 server 时使用 server_path + token 作为被动 WS 路由
    {!--< /tips >!--}
    """

    mode: str = field(
        default="server",
        metadata={
            "description": "连接模式: server(被动) 或 client(主动)",
            "required": False,
            "webui": {
                "widget": "select",
                "group": "connection",
                "order": 2,
                "options": [
                    {"label": "Server", "value": "server"},
                    {"label": "Client", "value": "client"},
                ],
            },
        },
    )
    url: Optional[str] = field(
        default="ws://127.0.0.1:3001",
        metadata={
            "description": "Client模式 WebSocket 地址",
            "required": False,
            "webui": {"widget": "text", "group": "client", "order": 3},
        },
    )
    token: Optional[str] = field(
        default="",
        metadata={
            "description": "认证Token（Client模式连接Token / Server模式验证Token）",
            "required": False,
            "secret": True,
            "webui": {"widget": "password", "group": "connection", "order": 4},
        },
    )
    server_path: Optional[str] = field(
        default="/",
        metadata={
            "description": "Server模式 WebSocket 路径",
            "required": False,
            "webui": {"widget": "text", "group": "server", "order": 5},
        },
    )


class OneBotAdapter(BaseAdapter):
    """
    OneBot11 协议适配器

    实现 OneBot11 标准（基于 OneBot v11 规范）与 ErisPulse 框架的对接，
    支持 WebSocket Server/Client 混合运行模式，提供消息收发、API调用、事件转换等能力

    {!--< tips >!--}
    1. 使用 mode=client 主动连接 OneBot 服务，mode=server 被动接收连接
    2. 支持多账户并行运行，每个账户独立管理连接和状态
    3. 自动建立 self_id → account_name 映射，event.reply() 无需手动指定账户
    {!--< /tips >!--}
    """

    AccountConfigClass = OneBotAccountConfig

    class Send(BaseAdapter.Send):
        """
        OneBot11 消息发送 DSL

        提供文本、图片、语音、视频、表情、文件等消息类型发送能力，
        同时支持消息撤回和原始 OB12 消息段发送

        {!--< tips >!--}
        1. 所有发送方法返回 asyncio.Task 对象
        2. 消息段会自动经过修饰器处理和 OB12→OB11 格式转换
        {!--< /tips >!--}
        """

        def _build_ob11_message(self, message: Union[str, List[Dict]]) -> List[Dict]:
            """
            构建最终的 OB11 消息段列表

            :param message: [Union[str, List[Dict]]] 输入消息，可为纯文本或 OB12 消息段列表
            :return: [List[Dict]] 转换后的 OB11 消息段列表

            {!--< internal-use >!--}
            """
            if isinstance(message, str):
                segments = [{"type": "text", "data": {"text": message}}]
            else:
                segments = list(message)

            segments = self._apply_modifiers(segments)
            segments = self._convert_ob12_to_ob11(segments)
            self._insert_text_separators(segments)
            return segments

        def _insert_text_separators(self, message_list: List[Dict]):
            """
            在相邻消息段之间插入空格分隔符

            处理 text-text、at-text、text-at 等相邻场景，确保消息显示正确

            :param message_list: [List[Dict]] 消息段列表（原地修改）

            {!--< internal-use >!--}
            """
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

        def Text(self, text: str):
            """
            发送纯文本消息

            :param text: [str] 文本内容
            :return: [asyncio.Task] 发送任务
            """
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            """
            发送图片消息

            支持以下三种格式:
            - bytes: 二进制数据，自动转换为 base64
            - str (以 base64:// 开头): base64 编码字符串，直接透传
            - str (其他): 视为文件路径，自动读取并转换为 base64

            :param file: [Union[str, bytes]] 图片文件路径/URL/base64/二进制
            :param filename: [str] 文件名 (默认: "image.png")
            :return: [asyncio.Task] 发送任务
            """
            import base64
            import os

            if isinstance(file, bytes):
                file = "base64://" + base64.b64encode(file).decode("ascii")
            elif isinstance(file, str) and not file.startswith("base64://"):
                file_path = os.path.abspath(file)
                with open(file_path, "rb") as f:
                    file = "base64://" + base64.b64encode(f.read()).decode("ascii")

            return self.Raw_ob12(
                [{"type": "image", "data": {"file": file, "file_name": filename}}]
            )

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            """
            发送语音消息

            支持以下三种格式:
            - bytes: 二进制数据，自动转换为 base64
            - str (以 base64:// 开头): base64 编码字符串，直接透传
            - str (其他): 视为文件路径，自动读取并转换为 base64

            :param file: [Union[str, bytes]] 语音文件路径/URL/base64/二进制
            :param filename: [str] 文件名 (默认: "voice.amr")
            :return: [asyncio.Task] 发送任务
            """
            import base64
            import os

            if isinstance(file, bytes):
                file = "base64://" + base64.b64encode(file).decode("ascii")
            elif isinstance(file, str) and not file.startswith("base64://"):
                file_path = os.path.abspath(file)
                with open(file_path, "rb") as f:
                    file = "base64://" + base64.b64encode(f.read()).decode("ascii")

            return self.Raw_ob12(
                [{"type": "audio", "data": {"file": file, "file_name": filename}}]
            )

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            """
            发送视频消息

            支持以下三种格式:
            - bytes: 二进制数据，自动转换为 base64
            - str (以 base64:// 开头): base64 编码字符串，直接透传
            - str (其他): 视为文件路径，自动读取并转换为 base64

            :param file: [Union[str, bytes]] 视频文件路径/URL/base64/二进制
            :param filename: [str] 文件名 (默认: "video.mp4")
            :return: [asyncio.Task] 发送任务
            """
            import base64
            import os

            if isinstance(file, bytes):
                file = "base64://" + base64.b64encode(file).decode("ascii")
            elif isinstance(file, str) and not file.startswith("base64://"):
                file_path = os.path.abspath(file)
                with open(file_path, "rb") as f:
                    file = "base64://" + base64.b64encode(f.read()).decode("ascii")

            return self.Raw_ob12(
                [{"type": "video", "data": {"file": file, "file_name": filename}}]
            )

        def Face(self, id: Union[str, int]):
            """
            发送 QQ 表情

            :param id: [Union[str, int]] 表情 ID
            :return: [asyncio.Task] 发送任务
            """
            return self.Raw_ob12([{"type": "face", "data": {"id": str(id)}}])

        def File(self, file: Union[str, bytes], filename: str = "file.dat"):
            """
            发送文件

            支持以下三种格式:
            - bytes: 二进制数据，自动转换为 base64
            - str (以 base64:// 开头): base64 编码字符串，直接透传
            - str (其他): 视为文件路径，自动读取并转换为 base64

            :param file: [Union[str, bytes]] 文件路径/URL/base64/二进制
            :param filename: [str] 文件名 (默认: "file.dat")
            :return: [asyncio.Task] 发送任务
            """
            import base64
            import os

            if isinstance(file, bytes):
                file = "base64://" + base64.b64encode(file).decode("ascii")
            elif isinstance(file, str) and not file.startswith("base64://"):
                file_path = os.path.abspath(file)
                with open(file_path, "rb") as f:
                    file = "base64://" + base64.b64encode(f.read()).decode("ascii")

            return self.Raw_ob12(
                [{"type": "file", "data": {"file": file, "file_name": filename}}]
            )

        def Raw_ob12(self, message, **kwargs):
            """
            发送原始 OB12 格式消息段

            消息段会自动经过修饰器处理和 OB12→OB11 格式转换后发送

            :param message: [Union[Dict, List[Dict]]] OB12 消息段（单个或列表）
            :param kwargs: 额外 API 参数
            :return: [asyncio.Task] 发送任务

            {!--< tips >!--} 支持链式调用多个消息段组合
            """
            if isinstance(message, dict):
                message = [message]

            ob11_message = self._build_ob11_message(message)

            async def _do_send():
                ctx = self.send_context
                params = {
                    "endpoint": "send_msg",
                    "message_type": "private"
                    if ctx["target_type"] == "user"
                    else "group",
                    "message": ob11_message,
                    **{k: v for k, v in ctx.items() if k not in ("target_type",)},
                }
                if ctx["target_type"] == "user":
                    params["user_id"] = ctx["target_id"]
                else:
                    params["group_id"] = ctx["target_id"]
                params.update(kwargs)
                params.pop("target_type", None)
                params.pop("target_id", None)
                params.pop("account_id", None)
                account_id = ctx.get("account_id")
                if account_id:
                    params["account_id"] = account_id
                return await self._adapter.call_api(**params)

            return asyncio.create_task(_do_send())

        def Recall(self, message_id: Union[str, int]):
            """
            撤回消息

            :param message_id: [Union[str, int]] 要撤回的消息 ID
            :return: [asyncio.Task] 撤回任务
            """
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    message_id=str(message_id),
                )
            )

        def Like(self, user_id: Union[str, int], times: int = 1):
            """
            发送好友赞

            :param user_id: [Union[str, int]] 目标用户 ID
            :param times: [int] 点赞次数（默认 1 次，最大 10 次）
            :return: [asyncio.Task] 点赞任务
            """
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_like",
                    user_id=int(user_id),
                    times=times,
                )
            )

        def Kick(self, user_id: Union[str, int], reject_add_request: bool = False):
            """
            群组踢人（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 要踢的用户 ID
            :param reject_add_request: [bool] 是否拒绝此人再加群（默认 False）
            :return: [asyncio.Task] 踢人任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_kick",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    reject_add_request=reject_add_request,
                    account_id=ctx.get("account_id"),
                )
            )

        def Ban(self, user_id: Union[str, int], duration: int = 1800):
            """
            群组单人禁言（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 要禁言的用户 ID
            :param duration: [int] 禁言时长（秒），默认 1800（30分钟），0 表示解禁
            :return: [asyncio.Task] 禁言任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_ban",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    duration=duration,
                    account_id=ctx.get("account_id"),
                )
            )

        def WholeBan(self, enable: bool = True):
            """
            群组全员禁言（需通过 To("group", group_id) 指定群）

            :param enable: [bool] 是否开启全员禁言（默认 True）
            :return: [asyncio.Task] 禁言任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_whole_ban",
                    group_id=int(ctx.get("target_id", 0)),
                    enable=enable,
                    account_id=ctx.get("account_id"),
                )
            )

        def SetAdmin(self, user_id: Union[str, int], enable: bool = True):
            """
            设置/取消群管理员（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 要设置的用户 ID
            :param enable: [bool] True 设为管理员，False 取消（默认 True）
            :return: [asyncio.Task] 设置任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_admin",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    enable=enable,
                    account_id=ctx.get("account_id"),
                )
            )

        def SetCard(self, user_id: Union[str, int], card: str = ""):
            """
            设置群名片（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 要设置的用户 ID
            :param card: [str] 群名片内容，空字符串表示清空
            :return: [asyncio.Task] 设置任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_card",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    card=card,
                    account_id=ctx.get("account_id"),
                )
            )

        def SetGroupName(self, name: str):
            """
            设置群名（需通过 To("group", group_id) 指定群）

            :param name: [str] 新的群名称
            :return: [asyncio.Task] 设置任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_name",
                    group_id=int(ctx.get("target_id", 0)),
                    group_name=name,
                    account_id=ctx.get("account_id"),
                )
            )

        def Leave(self, is_dismiss: bool = False):
            """
            退群（需通过 To("group", group_id) 指定群）

            :param is_dismiss: [bool] 是否解散群（仅群主可用，默认 False）
            :return: [asyncio.Task] 退群任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_leave",
                    group_id=int(ctx.get("target_id", 0)),
                    is_dismiss=is_dismiss,
                    account_id=ctx.get("account_id"),
                )
            )

        def SetTitle(self, user_id: Union[str, int], title: str = ""):
            """
            设置群头衔（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 要设置的用户 ID
            :param title: [str] 头衔内容，空字符串表示清空
            :return: [asyncio.Task] 设置任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_special_title",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    special_title=title,
                    account_id=ctx.get("account_id"),
                )
            )

        def SetPortrait(self, file: Union[str, bytes]):
            """
            设置群头像（需通过 To("group", group_id) 指定群）

            :param file: [Union[str, bytes]] 图片文件（URL 或 bytes）
            :return: [asyncio.Task] 设置任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_portrait",
                    group_id=int(ctx.get("target_id", 0)),
                    file=file,
                    account_id=ctx.get("account_id"),
                )
            )

        def GetMsg(self, message_id: Union[str, int]):
            """
            获取消息内容

            :param message_id: [Union[str, int]] 消息 ID
            :return: [asyncio.Task] 获取任务
            """
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_msg",
                    message_id=int(message_id),
                )
            )

        def GetForwardMsg(self, id: Union[str, int]):
            """
            获取合并转发消息内容

            :param id: [Union[str, int]] 合并转发 ID
            :return: [asyncio.Task] 获取任务
            """
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_forward_msg",
                    id=str(id),
                )
            )

        def GetLoginInfo(self):
            """
            获取登录号信息

            :return: [asyncio.Task] 获取任务（包含 user_id、nickname）
            """
            return asyncio.create_task(
                self._adapter.call_api(endpoint="get_login_info")
            )

        def GetFriendList(self):
            """
            获取好友列表

            :return: [asyncio.Task] 获取任务
            """
            return asyncio.create_task(
                self._adapter.call_api(endpoint="get_friend_list")
            )

        def GetGroupInfo(self):
            """
            获取群信息（需通过 To("group", group_id) 指定群）

            :return: [asyncio.Task] 获取任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_info",
                    group_id=int(ctx.get("target_id", 0)),
                    account_id=ctx.get("account_id"),
                )
            )

        def GetGroupList(self):
            """
            获取群列表

            :return: [asyncio.Task] 获取任务
            """
            return asyncio.create_task(
                self._adapter.call_api(endpoint="get_group_list")
            )

        def GetGroupMemberInfo(self, user_id: Union[str, int]):
            """
            获取群成员信息（需通过 To("group", group_id) 指定群）

            :param user_id: [Union[str, int]] 用户 ID
            :return: [asyncio.Task] 获取任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_member_info",
                    group_id=int(ctx.get("target_id", 0)),
                    user_id=int(user_id),
                    account_id=ctx.get("account_id"),
                )
            )

        def GetGroupMemberList(self):
            """
            获取群成员列表（需通过 To("group", group_id) 指定群）

            :return: [asyncio.Task] 获取任务
            """
            ctx = self.send_context
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_member_list",
                    group_id=int(ctx.get("target_id", 0)),
                    account_id=ctx.get("account_id"),
                )
            )

        def _convert_ob12_to_ob11(self, message: List[Dict]) -> List[Dict]:
            """
            将 OB12 消息段转换为 OB11 格式

            支持的类型映射: text→text, image→image, audio→record, video→video,
            file→file, face→face, mention→at, mention_all→at(all), reply→reply,
            onebot11_* 前缀类型直接透传

            :param message: [List[Dict]] OB12 消息段列表
            :return: [List[Dict]] OB11 消息段列表

            {!--< internal-use >!--}
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
                elif seg_type in ("mention", "at"):
                    ob11_message.append(
                        {
                            "type": "at",
                            "data": {
                                "qq": str(
                                    seg_data.get("user_id", seg_data.get("qq", ""))
                                )
                            },
                        }
                    )
                elif seg_type == "mention_all":
                    ob11_message.append({"type": "at", "data": {"qq": "all"}})
                elif seg_type == "reply":
                    ob11_message.append(
                        {
                            "type": "reply",
                            "data": {
                                "id": str(
                                    seg_data.get("message_id", seg_data.get("id", ""))
                                )
                            },
                        }
                    )
                elif seg_type.startswith("onebot11_"):
                    cq_type = seg_type[10:]
                    ob11_message.append({"type": cq_type, "data": seg_data})
                else:
                    ob11_message.append({"type": seg_type, "data": seg_data})

            return ob11_message

    class Request(RequestDSL):
        """
        OneBot11 请求处理 DSL

        用于处理好友请求和群请求（加群/邀请），提供接受和拒绝操作
        """

        async def _do_accept(self, **kwargs) -> dict[str, Any]:
            """
            接受请求

            :param kwargs: 额外参数，可包含 _request_type 用于区分好友/群请求
            :return: [dict] API 调用结果

            {!--< internal-use >!--}
            """
            return await self._do_action(approve=True, **kwargs)

        async def _do_reject(self, **kwargs) -> dict[str, Any]:
            """
            拒绝请求

            :param kwargs: 额外参数，可包含 _request_type 用于区分好友/群请求
            :return: [dict] API 调用结果

            {!--< internal-use >!--}
            """
            return await self._do_action(approve=False, **kwargs)

        async def _do_action(self, approve: bool, **kwargs) -> dict[str, Any]:
            """
            执行请求操作（接受/拒绝）

            根据 _request_type 参数自动选择 set_friend_add_request 或 set_group_add_request API

            :param approve: [bool] 是否接受
            :param kwargs: 额外参数
            :return: [dict] API 调用结果

            {!--< internal-use >!--}
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
                return result
            except Exception as e:
                return self._adapter.make_error(message=str(e))

    def __init__(self, sdk_ref=None):
        """
        初始化 OneBot11 适配器

        :param sdk_ref: [Optional] SDK 引用（通常由框架自动注入）
        """
        super().__init__(sdk_ref)
        self._self_id_map: Dict[str, str] = {}
        self._bot_ids: Dict[str, str] = {}
        self._pending_connect_meta: set = set()
        self.connections: Dict[str, Any] = {}
        self._api_response_futures: Dict[str, Dict[str, asyncio.Future]] = {}
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self.default_timeout = 30
        self.default_retry_interval = 30

        from .Converter import OneBot11Converter

        self._converter = OneBot11Converter()
        self.convert = self._converter.convert

        self._register_event_methods()

    def _get_config_key(self) -> str:
        """
        获取配置文件中对应的 key 名称

        :return: [str] 配置键名 "OneBotAdapter"

        {!--< internal-use >!--}
        """
        return "OneBotAdapter"

    def _get_bot_id(self, account_name: str) -> str:
        return self._bot_ids.get(account_name, "")

    def _bot_id_display(self, account_name: str) -> str:
        return self._bot_ids.get(account_name, "待确认")

    def _update_bot_id(self, account_name: str, self_id: str):
        old = self._bot_ids.get(account_name)
        if not old:
            self._bot_ids[account_name] = self_id
            self.logger.info(f"账户 {account_name} 自动识别 bot_id: {self_id}")
        elif old != self_id:
            self._bot_ids[account_name] = self_id
            self.logger.warning(f"账户 {account_name} bot_id 变更: {old} → {self_id}")

    def _register_event_methods(self):
        """
        注册 OneBot11 平台的事件扩展方法

        为事件对象添加 get_raw_self_id、get_sender_info、get_sender_role 等便捷方法

        {!--< internal-use >!--}
        """
        try:
            from ErisPulse.Core.Event import register_event_mixin

            class OneBot11EventMixin:
                def get_raw_self_id(self) -> str:
                    return self.get("self", {}).get("user_id", "")

                def get_sender_info(self) -> dict:
                    return self.get("onebot11_raw", {}).get("sender", {})

                def get_sender_role(self) -> str:
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("role", "")
                    )

                def get_sender_level(self) -> int:
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("level", 0)
                    )

                def get_sender_title(self) -> str:
                    return (
                        self.get("onebot11_raw", {}).get("sender", {}).get("title", "")
                    )

                def is_system_message(self) -> bool:
                    return self.get("sub_type") == "system"

            register_event_mixin("onebot11", OneBot11EventMixin)
        except Exception as e:
            self._get_logger().warning(f"注册 OneBot11 事件扩展方法失败: {e}")

    async def call_api(self, endpoint: str, **params):
        """
        调用 OneBot11 HTTP API

        通过 WebSocket 连接发送 API 请求并等待响应，支持超时控制和多账户路由

        :param endpoint: [str] API 端点名称（如 send_msg、get_login_info 等）
        :param params: API 参数，可包含 account_id 指定使用的账户
        :return: [dict] API 响应结果，包含 status、retcode、data 等字段

        :raises ConnectionError: 当账户未连接或连接已关闭时抛出
        """
        account_id = params.pop("account_id", None)
        account_name, account = self._resolve_account(account_id)

        connection = self.connections.get(account_name)
        if not connection:
            raise ConnectionError(f"账户 {account_name} 尚未连接")

        if hasattr(connection, "closed") and connection.closed:
            raise ConnectionError(f"账户 {account_name} 的连接已关闭")

        if account_name not in self._api_response_futures:
            self._api_response_futures[account_name] = {}

        echo = str(hash((str(params), account_name, endpoint)))
        future = asyncio.get_event_loop().create_future()
        self._api_response_futures[account_name][echo] = future

        payload = {"action": endpoint, "params": params, "echo": echo}

        try:
            await connection.send_text(json.dumps(payload))
        except Exception as e:
            self.logger.error(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 发送请求失败: {str(e)}"
            )
            if echo in self._api_response_futures[account_name]:
                del self._api_response_futures[account_name][echo]
            raise

        try:
            self.logger.debug(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 请求: {payload}"
            )

            raw_response = await asyncio.wait_for(future, timeout=self.default_timeout)

            self.logger.debug(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 响应: {raw_response}"
            )

            message_id = ""
            if isinstance(raw_response.get("data"), dict):
                message_id = str(raw_response["data"].get("message_id", ""))

            retcode = raw_response.get("retcode", 0)
            status = "ok" if retcode == 0 else "failed"

            return self.make_response(
                status=status,
                retcode=retcode,
                data=raw_response.get("data"),
                message_id=message_id,
                message=raw_response.get("message", ""),
                raw=raw_response,
            )

        except asyncio.TimeoutError:
            self.logger.error(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) API调用超时: {endpoint}"
            )
            if not future.done():
                future.cancel()

            return self.make_error(
                retcode=33001,
                message=f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) API调用超时: {endpoint}",
                raw=None,
            )

        finally:

            async def cleanup():
                await asyncio.sleep(0.1)
                if (
                    account_name in self._api_response_futures
                    and echo in self._api_response_futures[account_name]
                ):
                    del self._api_response_futures[account_name][echo]

            asyncio.create_task(cleanup())

    async def connect(self, account_name: str):
        """
        以 Client 模式连接 OneBot 服务

        启动后会持续监听消息，断开后自动重连直到适配器关闭

        :param account_name: [str] 账户名称

        :raises ValueError: 当账户不存在时抛出
        """
        if account_name not in self.accounts:
            raise ValueError(f"账户 {account_name} 不存在")

        account = self.accounts[account_name]
        if account.mode != "client":
            return

        headers = {}
        if account.token:
            headers["Authorization"] = f"Bearer {account.token}"

        url = account.url

        from ErisPulse.Core import client

        while self._running:
            try:
                self.logger.debug(
                    f"账户 {account_name} 正在连接: url={url}, token={'***' if headers.get('Authorization') else '(none)'}"
                )
                ws = await client.ws_connect(url, headers=headers)
                self.logger.debug(
                    f"账户 {account_name} WS对象: closed={ws.closed}, type={type(ws).__name__}"
                )
                self.connections[account_name] = ws
                self.logger.info(
                    f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 连接成功"
                )
                await self.emit_meta("connect", self._get_bot_id(account_name))
                if not self._get_bot_id(account_name):
                    self._pending_connect_meta.add(account_name)
                await self._listen(account_name)
                if not self._running:
                    return
                self.logger.info(
                    f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) "
                    f"{self.default_retry_interval}秒后重连..."
                )
                await asyncio.sleep(self.default_retry_interval)
            except Exception as e:
                if not self._running:
                    return
                self.logger.error(
                    f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 连接失败: {str(e)}"
                )
                await asyncio.sleep(self.default_retry_interval)

    async def _listen(self, account_name: str):
        """
        监听 WebSocket 连接的消息流

        使用 receive() 逐帧读取，处理 TEXT/BINARY/CLOSE/ERROR 帧类型

        :param account_name: [str] 账户名称

        {!--< internal-use >!--}
        """
        connection = self.connections.get(account_name)
        if not connection:
            return

        account = self.accounts.get(account_name)

        try:
            from ErisPulse.Core.Bases.websocket import WSMessage

            while True:
                msg = await connection.receive()
                if msg.type == WSMessage.TEXT:
                    self.logger.debug(
                        f"账户 {account_name} 收到WS文本: {str(msg.data)[:300]}"
                    )
                    asyncio.create_task(self._handle_message(msg.data, account_name))
                elif msg.type == WSMessage.BINARY:
                    self.logger.debug(f"账户 {account_name} 收到WS二进制数据")
                elif msg.type == WSMessage.CLOSE:
                    self.logger.info(
                        f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 收到CLOSE帧"
                    )
                    break
                elif msg.type == WSMessage.ERROR:
                    self.logger.error(
                        f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 收到ERROR帧"
                    )
                    break
                else:
                    self.logger.warning(
                        f"账户 {account_name} 收到未知消息类型: {msg.type}"
                    )
        except Exception as e:
            self.logger.error(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 监听异常: {str(e)}",
                exc_info=True,
            )
        finally:
            try:
                await self.emit_meta(
                    "disconnect", self._get_bot_id(account_name) if account else ""
                )
            except Exception:
                pass
            self.connections.pop(account_name, None)

    async def _handle_message(self, raw_msg: str, account_name: str):
        """
        处理收到的原始消息

        解析 JSON 数据，区分 API 响应（echo）和事件消息，
        自动维护 self_id → account_name 映射并转发事件到框架

        :param raw_msg: [str] 原始 JSON 字符串
        :param account_name: [str] 账户名称

        {!--< internal-use >!--}
        """
        try:
            data = json.loads(raw_msg)
            account = self.accounts.get(account_name)
            if not account:
                return

            if "echo" in data:
                future = self._api_response_futures.get(account_name, {}).get(
                    data["echo"]
                )
                if future and not future.done():
                    future.set_result(data)
                return

            from ErisPulse.Core import adapter as adapter_mgr

            onebot_event = self.convert(data)
            if onebot_event:
                raw_self_id = onebot_event.get("self", {}).get("user_id", "")
                if raw_self_id:
                    self._update_bot_id(account_name, str(raw_self_id))
                    if str(raw_self_id) not in self._self_id_map:
                        self._self_id_map[str(raw_self_id)] = account_name
                        self.logger.info(
                            f"映射 self_id {raw_self_id} → 账户 {account_name}"
                        )
                    if account_name in self._pending_connect_meta:
                        self._pending_connect_meta.discard(account_name)
                        await self.emit_meta("connect", str(raw_self_id))
                await adapter_mgr.emit(onebot_event)

        except json.JSONDecodeError:
            self.logger.error(f"JSON解析失败: {raw_msg}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")

    async def _ws_handler(self, websocket, account_name: str = "default"):
        """
        Server 模式 WebSocket 连接处理器

        处理被动接入的 WebSocket 连接，持续读取消息直到断开

        :param websocket: WebSocket 连接对象
        :param account_name: [str] 账户名称 (默认: "default")

        {!--< internal-use >!--}
        """
        account = self.accounts.get(account_name)
        if account:
            self.logger.info(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 客户端已连接"
            )

        self.connections[account_name] = websocket

        await self.emit_meta(
            "connect", self._get_bot_id(account_name) if account else ""
        )
        if account and not self._get_bot_id(account_name):
            self._pending_connect_meta.add(account_name)

        try:
            while True:
                data = await websocket.receive_text()
                asyncio.create_task(self._handle_message(data, account_name))
        except Exception:
            self.logger.info(
                f"账户 {account_name} (bot_id: {self._bot_id_display(account_name) if account else ''}) 客户端断开连接"
            )
        finally:
            try:
                await self.emit_meta(
                    "disconnect", self._get_bot_id(account_name) if account else ""
                )
            except Exception:
                pass
            if account_name in self.connections:
                del self.connections[account_name]

    async def _auth_handler(self, websocket, account_name: str = "default"):
        """
        Server 模式 WebSocket 认证处理器

        验证客户端 Token（支持 Authorization 头和 query 参数两种方式）

        :param websocket: WebSocket 连接对象
        :param account_name: [str] 账户名称 (默认: "default")
        :return: [bool] 认证是否通过

        {!--< internal-use >!--}
        """
        if account_name not in self.accounts:
            await websocket.close(code=1008)
            return False

        account = self.accounts[account_name]
        if account.token:
            client_token = websocket.headers.get("Authorization", "").replace(
                "Bearer ", ""
            )
            if not client_token:
                query = dict(websocket.query_params)
                client_token = query.get("token", "")

            if client_token != account.token:
                self.logger.warning(
                    f"账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) Token无效"
                )
                await websocket.close(code=1008)
                return False
        return True

    async def register_websocket(self):
        """
        注册 Server 模式的 WebSocket 路由

        为每个 server 模式账户注册独立的 WebSocket 路由和认证处理器
        """
        for account_name, account in self.enabled_accounts.items():
            if account.mode == "server":
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
                    f"已注册账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 的Server路由: {path}"
                )

    async def start(self):
        """
        启动适配器

        初始化所有已启用的账户，server 模式注册路由，client 模式建立连接
        """
        self._running = True

        server_accounts = [
            name for name, acc in self.enabled_accounts.items() if acc.mode == "server"
        ]
        client_accounts = [
            name for name, acc in self.enabled_accounts.items() if acc.mode == "client"
        ]

        if server_accounts:
            await self.register_websocket()

        for account_name in client_accounts:
            account = self.accounts[account_name]
            self.logger.info(
                f"启动Client模式账户: {account_name} (bot_id: {self._bot_id_display(account_name)})"
            )
            self.reconnect_tasks[account_name] = asyncio.create_task(
                self.connect(account_name)
            )

        enabled_count = len(server_accounts) + len(client_accounts)
        self.logger.info(f"OneBot11适配器启动完成，共 {enabled_count} 个账户")

    async def shutdown(self):
        """
        关闭适配器

        停止所有重连任务，关闭所有 WebSocket 连接，清理注册的事件方法
        """
        self._running = False

        for task in self.reconnect_tasks.values():
            if not task.done():
                task.cancel()
        self.reconnect_tasks.clear()

        for account_name, connection in list(self.connections.items()):
            account = self.accounts.get(account_name)
            try:
                if hasattr(connection, "closed") and not connection.closed:
                    await connection.close()
            except Exception as e:
                self.logger.error(
                    f"关闭账户 {account_name} (bot_id: {self._bot_id_display(account_name) if account else ''}) 连接失败: {str(e)}"
                )
        self.connections.clear()

        try:
            from ErisPulse.Core.Event import unregister_platform_event_methods

            unregister_platform_event_methods("onebot11")
        except Exception:
            pass

        self.logger.info("OneBot11适配器已关闭")
