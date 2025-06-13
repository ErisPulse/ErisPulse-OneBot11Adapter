moduleInfo = {
    "meta": {
        "name": "OneBotAdapter",
        "version": "2.1.0",
        "description": "OneBotV11协议适配模块，异步的OneBot触发器",
        "author": "WSu2059",
        "license": "MIT",
        "homepage": "https://github.com/wsu2059q/ErisPulse-OneBotAdapter"
    },
    "dependencies": {
        "requires": [],
        "optional": [],
        "pip": []
    }
}

from .Core import Main
from .Core import OneBotAdapter

adapterInfo = {
    "qq": OneBotAdapter,
    "QQ": OneBotAdapter,
    "onebot": OneBotAdapter
}


# build_hash="cb8a57cd1c6754a634bb0783f77757f8ad1b2da29b4d9b6467fee2756ef6faa9"
