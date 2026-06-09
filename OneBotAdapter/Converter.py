"""
OneBot11 事件转换器

将 OneBot11 协议事件转换为 ErisPulse 统一的事件格式（兼容 OneBot12 结构），
支持消息、通知、请求、元事件四种事件类型的转换

{!--< tips >!--}
1. 转换后的事件保留原始数据在 onebot11_raw 字段中
2. CQ 码和数组格式消息均支持解析
3. 未识别的 CQ 码类型会以 onebot11_ 前缀透传
{!--< /tips >!--}
"""

import time
import uuid
from typing import Dict, Optional, List, Any


class OneBot11Converter:
    """
    OneBot11 → ErisPulse 事件转换器

    {!--< tips >!--}
    1. 消息事件会解析 CQ 码并转换为 OB12 消息段格式
    2. 通知事件会映射到统一的 detail_type 命名
    {!--< /tips >!--}
    """

    def __init__(self):
        self._setup_event_mapping()

    def _setup_event_mapping(self):
        """
        初始化事件类型映射表

        建立 OB11 post_type/notice_type 到 OB12 detail_type 的映射关系

        {!--< internal-use >!--}
        """
        self.event_map = {
            "message": "message",
            "notice": "notice",
            "request": "request",
            "meta_event": "meta_event",
        }

        self.notice_subtypes = {
            "group_upload": "group_file_upload",
            "group_admin": "group_admin_change",
            "group_decrease": "group_member_decrease",
            "group_increase": "group_member_increase",
            "group_ban": "group_ban",
            "friend_add": "friend_increase",
            "friend_delete": "friend_decrease",
            "group_recall": "message_recall",
            "friend_recall": "message_recall",
            "notify": "notify",
        }

    def convert(self, raw_event: Dict) -> Optional[Dict]:
        """
        将 OneBot11 事件转换为 OneBot12 格式

        根据事件类型（message/notice/request/meta_event）分发到对应处理器，
        转换后的事件保留原始数据在 onebot11_raw 字段中

        :param raw_event: [Dict] 原始 OneBot11 事件数据
        :return: [Optional[Dict]] 转换后的事件字典，不支持的事件类型返回 None

        :raises ValueError: 当 raw_event 不是字典类型时抛出
        """
        if not isinstance(raw_event, dict):
            raise ValueError("事件数据必须是字典类型")

        post_type = raw_event.get("post_type")
        if post_type not in self.event_map:
            return None

        # 基础事件结构
        onebot_event = {
            "id": str(raw_event.get("echo", str(uuid.uuid4()))),
            "time": self._convert_timestamp(raw_event.get("time", int(time.time()))),
            "platform": "onebot11",
            "self": {
                "platform": "onebot11",
                "user_id": str(raw_event.get("self_id", "")),
            },
            "onebot11_raw": raw_event,  # 保留原始数据
            "onebot11_raw_type": post_type,  # 原始事件类型字段
        }

        # 根据事件类型分发处理
        handler = getattr(self, f"_handle_{post_type}", None)
        if handler:
            return handler(raw_event, onebot_event)

        return None

    def _convert_timestamp(self, ts) -> int:
        """
        转换时间戳为 10 位秒级格式

        自动处理毫秒级（13位）和秒级（10位）时间戳

        :param ts: [Union[str, int, float]] 原始时间戳
        :return: [int] 10 位秒级时间戳

        {!--< internal-use >!--}
        """
        if isinstance(ts, str):
            if len(ts) == 13:  # 毫秒级
                return int(ts) // 1000
            return int(ts)
        elif isinstance(ts, (int, float)):
            if ts > 9999999999:  # 毫秒级
                return int(ts // 1000)
            return int(ts)
        return int(time.time())  # 默认当前时间

    def _handle_message(self, raw_event: Dict, base_event: Dict) -> Dict:
        """
        处理消息事件

        解析消息内容（支持 CQ 码和数组格式），生成 OB12 结构的事件数据，
        包含消息段列表、纯文本替代消息、发送者信息等

        :param raw_event: [Dict] 原始 OB11 消息事件
        :param base_event: [Dict] 基础事件结构
        :return: [Dict] 转换后的消息事件

        {!--< internal-use >!--}
        """
        message_type = raw_event["message_type"]
        detail_type = "private" if message_type == "private" else "group"

        # 解析CQ码消息
        message_segments = self._parse_cq_code(raw_event["message"])
        alt_message = self._generate_alt_message(message_segments)

        base_event.update(
            {
                "type": "message",
                "detail_type": detail_type,
                "message_id": str(raw_event.get("message_id", "")),
                "message": message_segments,
                "alt_message": alt_message,
                "user_id": str(
                    raw_event.get("sender", {}).get(
                        "user_id", raw_event.get("user_id", "")
                    )
                ),
            }
        )

        # 添加发送者信息
        sender = raw_event.get("sender", {})
        if "nickname" in sender:
            base_event["user_nickname"] = sender["nickname"]
        if "card" in sender and sender["card"]:
            base_event["user_nickname"] = sender["card"]

        if detail_type == "group":
            base_event["group_id"] = str(raw_event.get("group_id", ""))
            # 添加群组信息
            if "group_name" in raw_event:
                base_event["group_name"] = raw_event["group_name"]

        # 处理子类型
        if raw_event.get("sub_type"):
            base_event["sub_type"] = raw_event["sub_type"]

        return base_event

    def _parse_cq_code(self, message: Any) -> List[Dict]:
        """
        解析消息内容为 OB12 消息段列表

        支持三种输入格式: 纯文本字符串、CQ 码字符串、OB11 数组格式

        :param message: [Any] 消息内容（str、List[Dict] 或其他）
        :return: [List[Dict]] OB12 消息段列表

        {!--< internal-use >!--}
        """
        if isinstance(message, str):
            # 简单文本消息
            if "[CQ:" not in message:
                return [{"type": "text", "data": {"text": message}}]

            # 包含CQ码的复杂消息
            segments = []
            last_pos = 0

            while True:
                cq_start = message.find("[CQ:", last_pos)
                if cq_start == -1:
                    # 添加剩余文本
                    if last_pos < len(message):
                        text = message[last_pos:]
                        if text:
                            segments.append({"type": "text", "data": {"text": text}})
                    break

                # 添加CQ码前的文本
                if cq_start > last_pos:
                    text = message[last_pos:cq_start]
                    if text:
                        segments.append({"type": "text", "data": {"text": text}})

                # 解析CQ码
                cq_end = message.find("]", cq_start)
                if cq_end == -1:
                    # 格式错误，当作普通文本处理
                    segments.append(
                        {"type": "text", "data": {"text": message[cq_start:]}}
                    )
                    break

                cq_content = message[cq_start + 4 : cq_end]  # 去掉[CQ:和]
                parts = cq_content.split(",", 1)
                cq_type = parts[0]
                cq_data = {}

                if len(parts) > 1:
                    data_str = parts[1]
                    # 简单解析参数（注意：实际CQ码参数可能包含转义字符）
                    data_parts = data_str.split(",")
                    for part in data_parts:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            cq_data[key] = value

                # 转换CQ码类型
                if cq_type == "text":
                    segments.append(
                        {"type": "text", "data": {"text": cq_data.get("text", "")}}
                    )
                elif cq_type == "image":
                    segments.append(
                        {
                            "type": "image",
                            "data": {
                                "file": cq_data.get("file"),
                                "url": cq_data.get("url"),
                                "cache": cq_data.get("cache", "1"),
                            },
                        }
                    )
                elif cq_type == "record":
                    segments.append(
                        {
                            "type": "audio",
                            "data": {
                                "file": cq_data.get("file"),
                                "url": cq_data.get("url"),
                                "magic": cq_data.get("magic", "0"),
                            },
                        }
                    )
                elif cq_type == "at":
                    segments.append(
                        {
                            "type": "mention",
                            "data": {
                                "user_id": cq_data.get("qq"),
                                "user_name": cq_data.get("name", ""),
                            },
                        }
                    )
                elif cq_type == "face":
                    segments.append(
                        {
                            "type": "face",
                            "data": {
                                "id": cq_data.get("id"),
                            },
                        }
                    )
                elif cq_type == "reply":
                    segments.append(
                        {
                            "type": "reply",
                            "data": {
                                "message_id": cq_data.get("id"),
                                "user_id": cq_data.get("qq", ""),
                            },
                        }
                    )
                else:
                    # 保留原始CQ码类型
                    segments.append({"type": f"onebot11_{cq_type}", "data": cq_data})

                last_pos = cq_end + 1

            return segments

        # 处理数组格式的消息
        elif isinstance(message, list):
            segments = []
            for segment in message:
                if isinstance(segment, str):
                    segments.append({"type": "text", "data": {"text": segment}})
                elif isinstance(segment, dict):
                    cq_type = segment.get("type", "")
                    cq_data = segment.get("data", {})

                    if cq_type == "text":
                        segments.append(
                            {"type": "text", "data": {"text": cq_data.get("text", "")}}
                        )
                    elif cq_type == "image":
                        segments.append(
                            {
                                "type": "image",
                                "data": {
                                    "file": cq_data.get("file"),
                                    "url": cq_data.get("url"),
                                    "cache": cq_data.get("cache", "1"),
                                },
                            }
                        )
                    elif cq_type == "record":
                        segments.append(
                            {
                                "type": "audio",
                                "data": {
                                    "file": cq_data.get("file"),
                                    "url": cq_data.get("url"),
                                    "magic": cq_data.get("magic", "0"),
                                },
                            }
                        )
                    elif cq_type == "at":
                        segments.append(
                            {
                                "type": "mention",
                                "data": {
                                    "user_id": cq_data.get("qq"),
                                    "user_name": cq_data.get("name", ""),
                                },
                            }
                        )
                    elif cq_type == "face":
                        segments.append(
                            {
                                "type": "face",
                                "data": {
                                    "id": cq_data.get("id"),
                                },
                            }
                        )
                    elif cq_type == "reply":
                        segments.append(
                            {
                                "type": "reply",
                                "data": {
                                    "message_id": cq_data.get("id"),
                                    "user_id": cq_data.get("qq", ""),
                                },
                            }
                        )
                    else:
                        # 保留原始CQ码类型
                        segments.append(
                            {"type": f"onebot11_{cq_type}", "data": cq_data}
                        )
            return segments

        # 其他情况当作纯文本处理
        return [{"type": "text", "data": {"text": str(message)}}]

    def _generate_alt_message(self, segments: List[Dict]) -> str:
        """
        从消息段列表生成纯文本替代消息

        图片替换为 [图片]、语音替换为 [语音]、@ 用户替换为 @name 等

        :param segments: [List[Dict]] 消息段列表
        :return: [str] 纯文本替代消息

        {!--< internal-use >!--}
        """
        parts = []
        for seg in segments:
            if seg["type"] == "text":
                parts.append(seg["data"]["text"])
            elif seg["type"] == "image":
                parts.append("[图片]")
            elif seg["type"] == "audio":
                parts.append("[语音]")
            elif seg["type"] == "mention":
                parts.append(
                    f"@{seg['data'].get('user_name', seg['data'].get('user_id', ''))}"
                )
            elif seg["type"] == "face":
                parts.append(f"[表情:{seg['data'].get('id', '')}]")
            elif seg["type"] == "reply":
                parts.append("[回复]")
            elif seg["type"].startswith("onebot11_"):
                parts.append(f"[{seg['type'][9:]}]")
        return "".join(parts)

    def _handle_notice(self, raw_event: Dict, base_event: Dict) -> Dict:
        """
        处理通知事件

        处理群文件上传、群管理员变动、群成员增减、群禁言、好友增减、
        消息撤回、群荣誉/戳一戳/运气王等通知类型

        :param raw_event: [Dict] 原始 OB11 通知事件
        :param base_event: [Dict] 基础事件结构
        :return: [Dict] 转换后的通知事件

        {!--< internal-use >!--}
        """
        notice_type = raw_event["notice_type"]
        sub_type = raw_event.get("sub_type", "")

        # 映射通知子类型
        detail_type = self.notice_subtypes.get(notice_type, notice_type)

        base_event.update(
            {"type": "notice", "detail_type": detail_type, "onebot11_notice": raw_event}
        )

        # 处理不同类型的通知
        if notice_type == "group_upload":
            base_event.update(
                {
                    "group_id": str(raw_event.get("group_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "onebot11_file": raw_event.get("file"),
                }
            )
        elif notice_type == "group_admin":
            base_event.update(
                {
                    "group_id": str(raw_event.get("group_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "sub_type": "set" if sub_type == "set" else "unset",
                }
            )
        elif notice_type in ["group_increase", "group_decrease"]:
            base_event.update(
                {
                    "group_id": str(raw_event.get("group_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "operator_id": str(raw_event.get("operator_id", "")),
                    "sub_type": sub_type,
                }
            )
        elif notice_type == "group_ban":
            base_event.update(
                {
                    "group_id": str(raw_event.get("group_id")),
                    "operator_id": str(raw_event.get("operator_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "duration": raw_event.get("duration", 0),
                }
            )
        elif notice_type in ["friend_add", "friend_delete"]:
            base_event.update({"user_id": str(raw_event.get("user_id"))})
        elif notice_type in ["group_recall", "friend_recall"]:
            base_event.update(
                {
                    "message_id": str(raw_event.get("message_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "group_id": str(raw_event.get("group_id", ""))
                    if notice_type == "group_recall"
                    else None,
                }
            )
        elif notice_type == "notify":
            if sub_type == "honor":
                base_event["detail_type"] = "onebot11_honor"
                base_event.update(
                    {
                        "group_id": str(raw_event.get("group_id")),
                        "user_id": str(raw_event.get("user_id")),
                        "honor_type": raw_event.get("honor_type"),
                    }
                )
            elif sub_type == "poke":
                base_event["detail_type"] = "onebot11_poke"
                base_event.update(
                    {
                        "group_id": str(raw_event.get("group_id", "")),
                        "user_id": str(raw_event.get("user_id")),
                        "target_id": str(raw_event.get("target_id")),
                    }
                )
            elif sub_type == "lucky_king":
                base_event["detail_type"] = "onebot11_lucky_king"
                base_event.update(
                    {
                        "group_id": str(raw_event.get("group_id")),
                        "user_id": str(raw_event.get("user_id")),
                        "target_id": str(raw_event.get("target_id")),
                    }
                )

        return base_event

    def _handle_request(self, raw_event: Dict, base_event: Dict) -> Dict:
        """
        处理请求事件

        处理好友请求和群请求（加群/邀请），提取 user_id、comment、flag 等关键字段

        :param raw_event: [Dict] 原始 OB11 请求事件
        :param base_event: [Dict] 基础事件结构
        :return: [Dict] 转换后的请求事件

        {!--< internal-use >!--}
        """
        request_type = raw_event["request_type"]

        base_event.update(
            {
                "type": "request",
                "detail_type": request_type,
                "onebot11_request": raw_event,
            }
        )

        if request_type == "friend":
            base_event.update(
                {
                    "user_id": str(raw_event.get("user_id")),
                    "comment": raw_event.get("comment"),
                    "flag": raw_event.get("flag"),
                    "request_id": raw_event.get("flag"),
                }
            )
        elif request_type == "group":
            base_event.update(
                {
                    "group_id": str(raw_event.get("group_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "comment": raw_event.get("comment"),
                    "sub_type": raw_event.get("sub_type"),
                    "flag": raw_event.get("flag"),
                    "request_id": raw_event.get("flag"),
                }
            )

        return base_event

    def _handle_meta_event(self, raw_event: Dict, base_event: Dict) -> Dict:
        """
        处理元事件

        处理生命周期事件（connect/disable）和心跳事件

        :param raw_event: [Dict] 原始 OB11 元事件
        :param base_event: [Dict] 基础事件结构
        :return: [Dict] 转换后的元事件

        {!--< internal-use >!--}
        """
        meta_type = raw_event["meta_event_type"]

        if meta_type == "heartbeat":
            detail_type = "heartbeat"
        else:
            detail_type = f"onebot11_{meta_type}"

        base_event.update(
            {
                "type": "meta_event",
                "detail_type": detail_type,
                "onebot11_meta": raw_event,
            }
        )

        if meta_type == "lifecycle":
            base_event["sub_type"] = raw_event.get("sub_type", "")
        elif meta_type == "heartbeat":
            base_event["interval"] = raw_event.get("interval", 0)
            base_event["status"] = raw_event.get("status", {})

        return base_event
