# main.py
# ErisPulse 主程序文件
# 本文件由 SDK 自动创建，您可随意修改
import asyncio
from ErisPulse import sdk

async def main():
    try:
        isInit = await sdk.init_task()
        
        if not isInit:
            sdk.logger.error("ErisPulse 初始化失败，请检查日志")
            return
        
        await sdk.adapter.startup()

        # 等待适配器完全启动
        await asyncio.sleep(3)
        
        user_id = "2694611137"
        
        # 1. 发送文本消息
        print("1. 发送文本消息:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Text("Hello, 这是一条测试消息！")
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 2. 发送@消息
        print("2. 发送@消息:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).At(user_id, "用户名")
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 3. 发送表情
        print("3. 发送表情:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Face(1)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 4. 发送猜拳
        print("4. 发送猜拳:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Rps()
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 5. 发送掷骰子
        print("5. 发送掷骰子:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Dice()
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 6. 发送图片 (如果文件存在)
        print("6. 发送图片:")
        try:
            result = await sdk.adapter.onebot11.Send.To("user", user_id).Image("https://http.cat/200")
            print(f"发送结果: {result}")
        except Exception as e:
            print(f"发送图片失败: {e}")
        await asyncio.sleep(1)
        
        # 7. 发送视频 (如果文件存在)
        print("7. 发送视频:")
        try:
            result = await sdk.adapter.onebot11.Send.To("user", user_id).Video("D:/devs/Python/ErisPulse-devs/SDK/ErisPulse-OneBotAdapter/dev/test_files/test.mp4")
            print(f"发送结果: {result}")
        except Exception as e:
            print(f"发送视频失败: {e}")
        await asyncio.sleep(1)
        
        # 8. 发送语音 (示例使用网络资源)
        print("8. 发送语音:")
        try:
            result = await sdk.adapter.onebot11.Send.To("user", user_id).Voice("https://example.com/test.amr")
            print(f"发送结果: {result}")
        except Exception as e:
            print(f"发送语音失败: {e}")
        await asyncio.sleep(1)
        
        # 9. 发送位置
        print("9. 发送位置:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Location(
            lat=39.9042, 
            lon=116.4074, 
            title="北京市", 
            content="中华人民共和国首都"
        )
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 10. 发送名片分享
        print("10. 发送名片分享:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Contact("qq", user_id)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 11. 发送XML消息
        print("11. 发送XML消息:")
        xml_data = '''<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
            <msg serviceID="1" templateID="1" action="web" brief="测试XML" 
                 sourceName="ErisPulse" url="https://github.com">
                <item layout="2">
                    <picture cover="https://http.cat/200"/>
                    <title>XML消息测试</title>
                    <summary>这是一条XML格式的消息</summary>
                </item>
            </msg>'''
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Xml(xml_data)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 12. 发送JSON消息
        print("12. 发送JSON消息:")
        json_data = '{"app":"com.tencent.miniapp","desc":"ErisPulse测试","view":"notification","ver":"0.0.1","prompt":"[ErisPulse JSON消息]","appID":"","sourceName":"ErisPulse","actionData":"{\"type\":\"jump\",\"url\":\"https://github.com\"}","content":"[\\"ErisPulse测试JSON消息\\"]","sourceUrl":"","meta":{"notification":{"appInfo.icon":10001,"appInfo.name":"ErisPulse","data":[{"title":"JSON消息测试","value":"这是一条JSON格式的消息"}],"title":"ErisPulse通知","button":[{"name":"查看详情"}],"emphasis_keyword":""}},"text":"","extra":""}'
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Json(json_data)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 13. 发送戳一戳
        print("13. 发送戳一戳:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Poke("poke", user_id)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 14. 发送组合消息
        print("14. 发送组合消息:")
        # 构造一个包含文本、表情和@的消息
        message_segments = [
            {"type": "text", "data": {"text": "你好 "}},
            {"type": "at", "data": {"qq": user_id}},
            {"type": "text", "data": {"text": " "}},
            {"type": "face", "data": {"id": "1"}},
            {"type": "text", "data": {"text": " 这是一条组合消息"}}
        ]
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Raw(message_segments)
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        # 15. 测试音乐分享 (使用自定义音乐)
        print("15. 发送音乐分享:")
        result = await sdk.adapter.onebot11.Send.To("user", user_id).Music(
            type="custom",
            url="https://music.163.com/#/song?id=123456",
            audio="https://music.163.com/song/media/outer/url?id=123456.mp3",
            title="测试音乐",
            content="ErisPulse测试",
            image="https://http.cat/200"
        )
        print(f"发送结果: {result}")
        await asyncio.sleep(1)
        
        print("所有示例发送完成！")
        
        # 保持程序运行(不建议修改)
        await asyncio.Event().wait()
    except Exception as e:
        sdk.logger.error(f"发生错误: {e}", exc_info=True)
    except KeyboardInterrupt:
        sdk.logger.info("正在停止程序")
    finally:
        await sdk.adapter.shutdown()

if __name__ == "__main__":
    asyncio.run(main())