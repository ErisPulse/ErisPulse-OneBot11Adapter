"""
OneBot11 适配器核心模块

实现 OneBot11 协议与 ErisPulse 2.7 框架的对接，支持 WebSocket Server/Client 混合运行模式。

{!--< tips >!--}
1. 支持多账户管理
2. 支持 self_id → account_name 自动映射，event.reply() 无需关心账户配置
3. 提供 WebSocket Server/Client 混合运行模式
4. 完整的 ApiDSL 标准动作接口（OB11 动作名映射）
5. 查询类 Send 方法已标注废弃，推荐使用 Api DSL
{!--< /tips >!--}
"""

import asyncio
import base64 as _base64
import json
import os
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import filetype
from ErisPulse.Core import client, router
from ErisPulse.Core.Bases import BaseConfig, BotAccountConfig
from ErisPulse.Core.Bases.adapter import BaseAdapter, RequestDSL
from ErisPulse.Core.Bases.websocket import WSMessage

from .i18n import OneBot11I18n

try:
    from ErisPulse.runtime.tasks import spawn_background
except ImportError:  # pragma: no cover
    spawn_background = None

__version__ = "4.3.0"

# 软依赖的框架最低版本（运行时检测，仅提示不强制）
MIN_FRAMEWORK_VERSION = (2, 7, 1)


@dataclass
class OneBotGlobalConfig(BaseConfig):
    """OneBot11 适配器全局配置"""

    pass


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
            "description": {"i18n": "OneBotAdapter.mode", "default": "连接模式: server(被动) 或 client(主动)"},
            "required": False,
            "ui": {
                "widget": "select",
                "group": "connection",
                "order": 2,
                "options": [
                    {"label": {"i18n": "OneBotAdapter.mode_server", "default": "Server"}, "value": "server"},
                    {"label": {"i18n": "OneBotAdapter.mode_client", "default": "Client"}, "value": "client"},
                ],
            },
        },
    )
    url: Optional[str] = field(
        default="ws://127.0.0.1:3001",
        metadata={
            "description": {"i18n": "OneBotAdapter.url", "default": "Client模式 WebSocket 地址"},
            "required": False,
            "ui": {"widget": "text", "group": "client", "order": 3},
        },
    )
    token: Optional[str] = field(
        default="",
        metadata={
            "description": {"i18n": "OneBotAdapter.token", "default": "认证Token（Client模式连接Token / Server模式验证Token）"},
            "required": False,
            "secret": True,
            "ui": {"widget": "password", "group": "connection", "order": 4},
        },
    )
    server_path: Optional[str] = field(
        default="/",
        metadata={
            "description": {"i18n": "OneBotAdapter.server_path", "default": "Server模式 WebSocket 路径"},
            "required": False,
            "ui": {"widget": "text", "group": "server", "order": 5},
        },
    )


# 分组显示名（WebUI 用）
OneBotGlobalConfig._schema_meta = {
    "group_labels": {
        "connection": {"i18n": "OneBotAdapter.group_connection", "default": "连接设置"},
        "server": {"i18n": "OneBotAdapter.group_server", "default": "服务端模式"},
        "client": {"i18n": "OneBotAdapter.group_client", "default": "客户端模式"},
    }
}


def _deprecation_warning(old_method: str, new_method: str):
    """Send 查询类方法的废弃提示（软提示，不改变行为）"""
    msg = f"Send.{old_method}() 已废弃，推荐使用 {new_method} 替代"
    warnings.warn(msg, DeprecationWarning, stacklevel=3)
    try:
        from ErisPulse.Core import logger

        logger.debug(msg)
    except Exception:
        pass


class OneBotAdapter(BaseAdapter):
    """
    OneBot11 协议适配器

    实现 OneBot11 标准（基于 OneBot v11 规范）与 ErisPulse 框架的对接，
    支持 WebSocket Server/Client 混合运行模式，提供消息收发、ApiDSL、事件转换等能力。

    {!--< tips >!--}
    1. 使用 mode=client 主动连接 OneBot 服务，mode=server 被动接收连接
    2. 支持多账户并行运行，每个账户独立管理连接和状态
    3. 自动建立 self_id → account_name 映射，event.reply() 无需手动指定账户
    4. ApiDSL 自动将 OB12 标准动作名映射到 OB11 动作名
    {!--< /tips >!--}
    """

    ConfigClass = OneBotGlobalConfig
    AccountConfigClass = OneBotAccountConfig
    I18nClass = OneBot11I18n

    class EventMixin:
        """
        OneBot11 平台事件扩展方法

        注册到事件包装类后，可在事件处理器中直接调用。
        """

        def get_raw_event(self) -> dict:
            """获取 OneBot11 原始事件数据"""
            return self.get("onebot11_raw", {}) or {}

        def get_raw_self_id(self) -> str:
            """获取原始 self_id（Bot 的 QQ 号）"""
            return self.get("self", {}).get("user_id", "")

        def get_sender_info(self) -> dict:
            """获取完整的发送者信息（包含 nickname、role、level 等）"""
            return self.get("onebot11_raw", {}).get("sender", {})

        def get_sender_role(self) -> str:
            """获取发送者在群内的角色（owner/admin/member）"""
            return self.get("onebot11_raw", {}).get("sender", {}).get("role", "")

        def get_sender_level(self) -> int:
            """获取发送者等级"""
            return self.get("onebot11_raw", {}).get("sender", {}).get("level", 0)

        def get_sender_title(self) -> str:
            """获取发送者群头衔"""
            return self.get("onebot11_raw", {}).get("sender", {}).get("title", "")

        def is_system_message(self) -> bool:
            """判断是否为系统消息（sub_type == "system"）"""
            return self.get("sub_type") == "system"

    class Api(BaseAdapter.Api):
        """
        OneBot11 标准 API 动作实现（ApiDSL）

        覆盖 OB12 标准动作名到 OB11 动作名的映射。

        {!--< tips >!--}
        1. get_self_info → get_login_info（字段标准化）
        2. get_user_info → get_stranger_info（字段标准化）
        3. delete_message → delete_msg（动作名映射）
        4. leave_group → set_group_leave（动作名映射）
        5. upload_file 扩展了 group_id/user_id 参数（OB11 文件上传绑定目标）
        6. 其他标准动作（get_friend_list/get_group_info 等）动作名一致，走默认实现
        {!--< /tips >!--}
        """

        async def get_self_info(self) -> dict:
            """获取机器人自身信息（映射到 get_login_info）"""
            raw = await self._adapter.call_api(
                "get_login_info", _account_id=self._account_id
            )
            if raw.get("status") != "ok":
                return raw
            data = raw.get("data", {}) or {}
            user_id = str(data.get("user_id", ""))
            user_name = data.get("nickname", "")
            return self._adapter.make_response(
                data={
                    "user_id": user_id,
                    "user_name": user_name,
                    "user_displayname": user_name,
                },
                raw=raw.get("onebot11_raw", raw),
            )

        async def get_user_info(self, user_id: str) -> dict:
            """获取用户信息（映射到 get_stranger_info）"""
            raw = await self._adapter.call_api(
                "get_stranger_info",
                _account_id=self._account_id,
                user_id=int(user_id),
            )
            if raw.get("status") != "ok":
                return raw
            data = raw.get("data", {}) or {}
            return self._adapter.make_response(
                data={
                    "user_id": str(data.get("user_id", user_id)),
                    "user_name": data.get("nickname", ""),
                    "user_displayname": data.get("nickname", ""),
                    "user_remark": "",
                },
                raw=raw.get("onebot11_raw", raw),
            )

        async def delete_message(self, message_id: str) -> dict:
            """撤回/删除消息（映射到 delete_msg）"""
            return await self._adapter.call_api(
                "delete_msg",
                _account_id=self._account_id,
                message_id=int(message_id),
            )

        async def leave_group(self, group_id: str) -> dict:
            """退出群（映射到 set_group_leave）"""
            return await self._adapter.call_api(
                "set_group_leave",
                _account_id=self._account_id,
                group_id=int(group_id),
            )

        async def upload_file(
            self,
            *,
            type: str,
            name: str,
            url: str | None = None,
            path: str | None = None,
            data: bytes | None = None,
            headers: dict[str, str] | None = None,
            sha256: str | None = None,
            group_id: str | None = None,
            user_id: str | None = None,
        ) -> dict:
            """
            上传文件（OB11 扩展：需指定 group_id 或 user_id）

            :param type: 来源类型（url/path/data）
            :param name: 文件名
            :param group_id: 群 ID（上传群文件）
            :param user_id: 用户 ID（上传私聊文件）
            """
            if not group_id and not user_id:
                return self._adapter.make_error(
                    retcode=10003,
                    message="OneBot11 上传文件需指定 group_id 或 user_id",
                )

            # 1. 读取文件 bytes
            try:
                if type == "data":
                    if data is None:
                        return self._adapter.make_error(
                            retcode=10003, message="type=data 时必须提供 data"
                        )
                    file_bytes = data
                elif type == "path":
                    if not path:
                        return self._adapter.make_error(
                            retcode=10003, message="type=path 时必须提供 path"
                        )
                    with open(path, "rb") as f:
                        file_bytes = f.read()
                elif type == "url":
                    if not url:
                        return self._adapter.make_error(
                            retcode=10003, message="type=url 时必须提供 url"
                        )
                    from urllib.parse import urlparse, unquote

                    resp = await client.get(url, headers=headers or {}, timeout=300)
                    file_bytes = await resp.read()
                else:
                    return self._adapter.make_error(
                        retcode=10003, message=f"不支持的 type: {type}"
                    )
            except Exception as e:
                return self._adapter.make_error(
                    retcode=10003, message=f"读取文件失败: {e}"
                )

            # 2. 用 filetype 检测类型
            try:
                sample = file_bytes[:1024] if file_bytes else b""
                info = filetype.guess(sample) if sample else None
                mime = info.mime if info else ""
            except Exception:
                mime = ""

            self._adapter.logger.debug(
                f"upload_file: name={name}, mime={mime}, size={len(file_bytes)}"
            )

            # 3. base64 编码
            file_b64 = _base64.b64encode(file_bytes).decode("ascii")
            file_param = f"base64://{file_b64}"

            # 4. 路由到目标端点
            if group_id:
                return await self._adapter.call_api(
                    "upload_group_file",
                    _account_id=self._account_id,
                    group_id=int(group_id),
                    file=file_param,
                    name=name,
                )
            else:
                return await self._adapter.call_api(
                    "upload_private_file",
                    _account_id=self._account_id,
                    user_id=int(user_id),
                    file=file_param,
                    name=name,
                )

    class Send(BaseAdapter.Send):
        """
        OneBot11 消息发送 DSL

        {!--< tips >!--}
        1. 所有发送方法返回 asyncio.Task 对象
        2. 消息段会自动经过修饰器处理和 OB12→OB11 格式转换
        3. 查询类方法（GetMsg/GetLoginInfo 等）已废弃，推荐使用 Api DSL
        {!--< /tips >!--}
        """

        def _build_ob11_message(self, message: Union[str, List[Dict]]) -> List[Dict]:
            if isinstance(message, str):
                segments = [{"type": "text", "data": {"text": message}}]
            else:
                segments = list(message)

            segments = self._apply_modifiers(segments)
            segments = self._convert_ob12_to_ob11(segments)
            self._insert_text_separators(segments)
            return segments

        def _insert_text_separators(self, message_list: List[Dict]):
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

        def _file_to_base64(self, file: Union[str, bytes]) -> str:
            """将文件统一转换为 base64:// 格式"""
            if isinstance(file, bytes):
                return "base64://" + _base64.b64encode(file).decode("ascii")
            elif isinstance(file, str) and not file.startswith("base64://"):
                file_path = os.path.abspath(file)
                with open(file_path, "rb") as f:
                    return "base64://" + _base64.b64encode(f.read()).decode("ascii")
            return file

        def Text(self, text: str):
            """发送纯文本消息"""
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            """发送图片消息（支持 URL、Base64 或 bytes）"""
            file = self._file_to_base64(file)
            return self.Raw_ob12(
                [{"type": "image", "data": {"file": file, "file_name": filename}}]
            )

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            """发送语音消息"""
            file = self._file_to_base64(file)
            return self.Raw_ob12(
                [{"type": "audio", "data": {"file": file, "file_name": filename}}]
            )

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            """发送视频消息"""
            file = self._file_to_base64(file)
            return self.Raw_ob12(
                [{"type": "video", "data": {"file": file, "file_name": filename}}]
            )

        def Face(self, id: Union[str, int]):
            """发送 QQ 表情"""
            return self.Raw_ob12([{"type": "face", "data": {"id": str(id)}}])

        def File(self, file: Union[str, bytes], filename: str = "file.dat"):
            """发送文件"""
            file = self._file_to_base64(file)
            return self.Raw_ob12(
                [{"type": "file", "data": {"file": file, "file_name": filename}}]
            )

        def Raw_ob12(self, message, **kwargs):
            """发送原始 OB12 格式消息段（自动转换为 OB11）"""
            if isinstance(message, dict):
                message = [message]

            ob11_message = self._build_ob11_message(message)

            async def _do_send():
                return await self._adapter.call_api(
                    endpoint="send_msg",
                    _account_id=self._account_id,
                    message_type="private" if self._target_type == "user" else "group",
                    user_id=int(self._target_id) if self._target_type == "user" else None,
                    group_id=int(self._target_id) if self._target_type == "group" else None,
                    message=ob11_message,
                    **kwargs,
                )

            return asyncio.create_task(_do_send())

        def Recall(self, message_id: Union[str, int]):
            """撤回消息"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="delete_msg",
                    _account_id=self._account_id,
                    message_id=int(message_id),
                )
            )

        def Like(self, user_id: Union[str, int], times: int = 1):
            """发送好友赞（最大 10 次）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="send_like",
                    _account_id=self._account_id,
                    user_id=int(user_id),
                    times=times,
                )
            )

        def Kick(self, user_id: Union[str, int], reject_add_request: bool = False):
            """群组踢人（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_kick",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                    reject_add_request=reject_add_request,
                )
            )

        def Ban(self, user_id: Union[str, int], duration: int = 1800):
            """群组单人禁言（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_ban",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                    duration=duration,
                )
            )

        def WholeBan(self, enable: bool = True):
            """群组全员禁言（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_whole_ban",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    enable=enable,
                )
            )

        def SetAdmin(self, user_id: Union[str, int], enable: bool = True):
            """设置/取消群管理员（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_admin",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                    enable=enable,
                )
            )

        def SetCard(self, user_id: Union[str, int], card: str = ""):
            """设置群名片（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_card",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                    card=card,
                )
            )

        def SetGroupName(self, name: str):
            """设置群名（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_name",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    group_name=name,
                )
            )

        def Leave(self, is_dismiss: bool = False):
            """退群（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_leave",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    is_dismiss=is_dismiss,
                )
            )

        def SetTitle(self, user_id: Union[str, int], title: str = ""):
            """设置群头衔（需通过 To("group", group_id) 指定群）"""
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_special_title",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                    special_title=title,
                )
            )

        def SetPortrait(self, file: Union[str, bytes]):
            """设置群头像（需通过 To("group", group_id) 指定群）"""
            file = self._file_to_base64(file)
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="set_group_portrait",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    file=file,
                )
            )

        # ==================== 已废弃的查询方法（推荐使用 Api DSL） ====================

        def GetMsg(self, message_id: Union[str, int]):
            """[已废弃] 获取消息内容，推荐使用 Api.call('get_msg', ...)"""
            _deprecation_warning("GetMsg", "Api.call('get_msg', ...)")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_msg",
                    _account_id=self._account_id,
                    message_id=int(message_id),
                )
            )

        def GetForwardMsg(self, id: Union[str, int]):
            """[已废弃] 获取合并转发消息，推荐使用 Api.call('get_forward_msg', ...)"""
            _deprecation_warning("GetForwardMsg", "Api.call('get_forward_msg', ...)")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_forward_msg",
                    _account_id=self._account_id,
                    id=str(id),
                )
            )

        def GetLoginInfo(self):
            """[已废弃] 获取登录号信息，推荐使用 Api.get_self_info()"""
            _deprecation_warning("GetLoginInfo", "Api.get_self_info()")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_login_info",
                    _account_id=self._account_id,
                )
            )

        def GetFriendList(self):
            """[已废弃] 获取好友列表，推荐使用 Api.get_friend_list()"""
            _deprecation_warning("GetFriendList", "Api.get_friend_list()")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_friend_list",
                    _account_id=self._account_id,
                )
            )

        def GetGroupInfo(self):
            """[已废弃] 获取群信息，推荐使用 Api.get_group_info(group_id)"""
            _deprecation_warning("GetGroupInfo", "Api.get_group_info(group_id)")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_info",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                )
            )

        def GetGroupList(self):
            """[已废弃] 获取群列表，推荐使用 Api.get_group_list()"""
            _deprecation_warning("GetGroupList", "Api.get_group_list()")
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_list",
                    _account_id=self._account_id,
                )
            )

        def GetGroupMemberInfo(self, user_id: Union[str, int]):
            """[已废弃] 获取群成员信息，推荐使用 Api.get_group_member_info(group_id, user_id)"""
            _deprecation_warning(
                "GetGroupMemberInfo", "Api.get_group_member_info(group_id, user_id)"
            )
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_member_info",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                    user_id=int(user_id),
                )
            )

        def GetGroupMemberList(self):
            """[已废弃] 获取群成员列表，推荐使用 Api.get_group_member_list(group_id)"""
            _deprecation_warning(
                "GetGroupMemberList", "Api.get_group_member_list(group_id)"
            )
            return asyncio.create_task(
                self._adapter.call_api(
                    endpoint="get_group_member_list",
                    _account_id=self._account_id,
                    group_id=int(self._target_id),
                )
            )

        def _convert_ob12_to_ob11(self, message: List[Dict]) -> List[Dict]:
            """
            将 OB12 消息段转换为 OB11 格式

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

        用于处理好友请求和群请求（加群/邀请），提供接受和拒绝操作。
        """

        async def _do_accept(self, **kwargs) -> dict[str, Any]:
            return await self._do_action(approve=True, **kwargs)

        async def _do_reject(self, **kwargs) -> dict[str, Any]:
            return await self._do_action(approve=False, **kwargs)

        async def _do_action(self, approve: bool, **kwargs) -> dict[str, Any]:
            try:
                result = await self._adapter.call_api(
                    endpoint="set_friend_add_request"
                    if kwargs.get("_request_type") != "group"
                    else "set_group_add_request",
                    _account_id=self._account_id,
                    flag=self._request_id,
                    approve=approve,
                    **{k: v for k, v in kwargs.items() if not k.startswith("_")},
                )
                return result
            except Exception as e:
                return self._adapter.make_error(message=str(e))

    def __init__(self, sdk_ref=None):
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

        platform = self._platform or "onebot11"
        self._converter = OneBot11Converter(platform=platform)
        self.convert = self._converter.convert

        self._check_framework_version()
        self._get_logger().info(f"OneBotAdapter v{__version__} 已加载")

    @staticmethod
    def _parse_version(version_str: str) -> tuple:
        """解析版本号为可比较的三元组（忽略 dev/预发布后缀，如 2.8.0-dev.3 → (2, 8, 0)）"""
        parts = []
        for piece in str(version_str).split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _check_framework_version(self):
        """软依赖检测：框架版本过低时打警告（不阻断加载）"""
        try:
            from importlib.metadata import version as _pkg_version

            raw = _pkg_version("ErisPulse")
        except Exception:
            return
        try:
            if self._parse_version(raw) < MIN_FRAMEWORK_VERSION:
                self._get_logger().warning(
                    f"当前 ErisPulse 版本 {raw} 过低：OneBotAdapter v{__version__} 需要 >= "
                    f"{'.'.join(map(str, MIN_FRAMEWORK_VERSION))}"
                    "（BaseConverter / Api DSL / spawn_background 等特性），"
                    "部分功能可能不可用，建议升级框架"
                )
        except Exception:
            pass

    def _get_config_key(self) -> str:
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

    async def call_api(self, endpoint: str, _account_id: str = None, **params):
        """
        调用 OneBot11 HTTP API

        通过 WebSocket 连接发送 API 请求并等待响应，支持超时控制和多账户路由。

        :param endpoint: API 端点名称（如 send_msg、get_login_info 等）
        :param _account_id: 账户标识
        :param params: API 参数
        :return: 标准响应结果
        """
        account_name, account = self._resolve_account(_account_id)
        # 吸收 ApiDSL._merge_context 传入的 account_id
        params.pop("account_id", None)

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
        """以 Client 模式连接 OneBot 服务"""
        if account_name not in self.accounts:
            raise ValueError(f"账户 {account_name} 不存在")

        account = self.accounts[account_name]
        if account.mode != "client":
            return

        headers = {}
        if account.token:
            headers["Authorization"] = f"Bearer {account.token}"

        url = account.url

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
        """监听 WebSocket 连接的消息流"""
        connection = self.connections.get(account_name)
        if not connection:
            return

        account = self.accounts.get(account_name)

        try:
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
        """处理收到的原始消息"""
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
        """Server 模式 WebSocket 连接处理器"""
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
        """Server 模式 WebSocket 认证处理器"""
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
        """注册 Server 模式的 WebSocket 路由"""
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
                    f"{self._platform}_{account_name}",
                    path,
                    make_ws_handler(account_name),
                    auth_handler=make_auth_handler(account_name),
                )
                self.logger.info(
                    f"已注册账户 {account_name} (bot_id: {self._bot_id_display(account_name)}) 的Server路由: {path}"
                )

    async def start(self):
        """启动适配器"""
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
            coro = self.connect(account_name)
            # 生命周期任务使用 spawn_background（owner 归属，shutdown 自动回收）
            self.reconnect_tasks[account_name] = (
                spawn_background(coro) if spawn_background is not None else asyncio.create_task(coro)
            )

        enabled_count = len(server_accounts) + len(client_accounts)
        self.logger.info(f"OneBot11适配器启动完成，共 {enabled_count} 个账户")

    async def shutdown(self):
        """关闭适配器"""
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

        self.logger.info("OneBot11适配器已关闭")
