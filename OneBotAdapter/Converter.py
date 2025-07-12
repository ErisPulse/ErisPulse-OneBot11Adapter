import time
from typing import Dict, Optional, List, Any

class OneBot11Converter:
    def __init__(self):
        self._setup_event_mapping()
    
    def _setup_event_mapping(self):
        """初始化事件类型映射"""
        self.event_map = {
            "message": "message",
            "notice": "notice",
            "request": "request",
            "meta_event": "meta_event"
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
            "notify": "notify"
        }

    def convert(self, raw_event: Dict) -> Optional[Dict]:
        """
        将OneBot11事件转换为OneBot12格式
        
        :param raw_event: 原始OneBot11事件数据
        :return: 转换后的OneBot12事件，None表示不支持的事件类型
        """
        if not isinstance(raw_event, dict):
            raise ValueError("事件数据必须是字典类型")

        post_type = raw_event.get("post_type")
        if post_type not in self.event_map:
            return None

        # 基础事件结构
        onebot_event = {
            "id": str(raw_event.get("time", int(time.time()))),
            "time": raw_event.get("time", int(time.time())),
            "platform": "onebot11",
            "self": {
                "platform": "onebot11",
                "user_id": str(raw_event.get("self_id", ""))
            },
            "onebot11_raw": raw_event  # 保留原始数据
        }

        # 根据事件类型分发处理
        handler = getattr(self, f"_handle_{post_type}", None)
        if handler:
            return handler(raw_event, onebot_event)
        
        return None

    def _handle_message(self, raw_event: Dict, base_event: Dict) -> Dict:
        """处理消息事件"""
        message_type = raw_event["message_type"]
        detail_type = "private" if message_type == "private" else "group"
        
        # 解析CQ码消息
        message_segments = self._parse_cq_code(raw_event["message"])
        alt_message = self._generate_alt_message(message_segments)
        
        base_event.update({
            "type": "message",
            "detail_type": detail_type,
            "message_id": str(raw_event.get("message_id", "")),
            "message": message_segments,
            "alt_message": alt_message,
            "user_id": str(raw_event.get("user_id", "")),
            "onebot11_message": raw_event["message"]
        })

        if detail_type == "group":
            base_event["group_id"] = str(raw_event.get("group_id", ""))
        
        # 处理子类型
        if raw_event.get("sub_type") == "group":
            base_event["sub_type"] = "group"
        elif raw_event.get("sub_type") == "friend":
            base_event["sub_type"] = "friend"
        
        return base_event

    def _parse_cq_code(self, message: Any) -> List[Dict]:
        """解析CQ码消息为OneBot12消息段"""
        if isinstance(message, str):
            return [{"type": "text", "data": {"text": message}}]
        
        segments = []
        for segment in message:
            if isinstance(segment, str):
                segments.append({"type": "text", "data": {"text": segment}})
            elif isinstance(segment, dict):
                cq_type = segment["type"]
                if cq_type == "text":
                    segments.append({"type": "text", "data": {"text": segment["data"]["text"]}})
                elif cq_type == "image":
                    segments.append({
                        "type": "image",
                        "data": {
                            "file": segment["data"].get("file"),
                            "url": segment["data"].get("url"),
                            "cache": segment["data"].get("cache", 1),
                            "sub_type": segment["data"].get("type", 0)
                        }
                    })
                elif cq_type == "record":
                    segments.append({
                        "type": "audio",
                        "data": {
                            "file": segment["data"].get("file"),
                            "url": segment["data"].get("url"),
                            "magic": segment["data"].get("magic", 0)
                        }
                    })
                elif cq_type == "at":
                    segments.append({
                        "type": "mention",
                        "data": {
                            "user_id": segment["data"].get("qq"),
                            "user_name": segment["data"].get("name", "")
                        }
                    })
                else:
                    segments.append({
                        "type": f"onebot11_{cq_type}",
                        "data": segment["data"]
                    })
        
        return segments

    def _generate_alt_message(self, segments: List[Dict]) -> str:
        """生成替代文本消息"""
        parts = []
        for seg in segments:
            if seg["type"] == "text":
                parts.append(seg["data"]["text"])
            elif seg["type"] == "image":
                parts.append("[图片]")
            elif seg["type"] == "audio":
                parts.append("[语音]")
            elif seg["type"] == "mention":
                parts.append(f"@{seg['data'].get('user_name', seg['data'].get('user_id', ''))}")
        return "".join(parts)

    def _handle_notice(self, raw_event: Dict, base_event: Dict) -> Dict:
        """处理通知事件"""
        notice_type = raw_event["notice_type"]
        sub_type = raw_event.get("sub_type", "")
        
        # 映射通知子类型
        detail_type = self.notice_subtypes.get(notice_type, notice_type)
        
        base_event.update({
            "type": "notice",
            "detail_type": detail_type,
            "onebot11_notice": raw_event
        })
        
        # 处理不同类型的通知
        if notice_type == "group_upload":
            base_event.update({
                "group_id": str(raw_event.get("group_id")),
                "user_id": str(raw_event.get("user_id")),
                "onebot11_file": raw_event.get("file")
            })
        elif notice_type == "group_admin":
            base_event.update({
                "group_id": str(raw_event.get("group_id")),
                "user_id": str(raw_event.get("user_id")),
                "sub_type": "set" if sub_type == "set" else "unset"
            })
        elif notice_type in ["group_increase", "group_decrease"]:
            base_event.update({
                "group_id": str(raw_event.get("group_id")),
                "user_id": str(raw_event.get("user_id")),
                "operator_id": str(raw_event.get("operator_id", "")),
                "sub_type": sub_type
            })
        elif notice_type == "group_ban":
            base_event.update({
                "group_id": str(raw_event.get("group_id")),
                "operator_id": str(raw_event.get("operator_id")),
                "user_id": str(raw_event.get("user_id")),
                "duration": raw_event.get("duration", 0)
            })
        elif notice_type in ["friend_add", "friend_delete"]:
            base_event.update({
                "user_id": str(raw_event.get("user_id"))
            })
        elif notice_type in ["group_recall", "friend_recall"]:
            base_event.update({
                "message_id": str(raw_event.get("message_id")),
                "user_id": str(raw_event.get("user_id")),
                "group_id": str(raw_event.get("group_id", "")) if notice_type == "group_recall" else None
            })
        elif notice_type == "notify":
            if sub_type == "honor":
                base_event.update({
                    "group_id": str(raw_event.get("group_id")),
                    "user_id": str(raw_event.get("user_id")),
                    "honor_type": raw_event.get("honor_type")
                })
            elif sub_type == "poke":
                base_event.update({
                    "group_id": str(raw_event.get("group_id", "")),
                    "user_id": str(raw_event.get("user_id")),
                    "target_id": str(raw_event.get("target_id"))
                })
        
        return base_event

    def _handle_request(self, raw_event: Dict, base_event: Dict) -> Dict:
        """处理请求事件"""
        request_type = raw_event["request_type"]
        
        base_event.update({
            "type": "request",
            "detail_type": f"onebot11_{request_type}",
            "onebot11_request": raw_event
        })
        
        if request_type == "friend":
            base_event.update({
                "user_id": str(raw_event.get("user_id")),
                "comment": raw_event.get("comment"),
                "flag": raw_event.get("flag")
            })
        elif request_type == "group":
            base_event.update({
                "group_id": str(raw_event.get("group_id")),
                "user_id": str(raw_event.get("user_id")),
                "comment": raw_event.get("comment"),
                "sub_type": raw_event.get("sub_type"),
                "flag": raw_event.get("flag")
            })
        
        return base_event

    def _handle_meta_event(self, raw_event: Dict, base_event: Dict) -> Dict:
        """处理元事件"""
        meta_type = raw_event["meta_event_type"]
        
        base_event.update({
            "type": "meta_event",
            "detail_type": f"onebot11_{meta_type}",
            "onebot11_meta": raw_event
        })
        
        if meta_type == "lifecycle":
            base_event["sub_type"] = raw_event.get("sub_type", "")
        elif meta_type == "heartbeat":
            base_event["interval"] = raw_event.get("interval", 0)
            base_event["status"] = raw_event.get("status", {})
        
        return base_event