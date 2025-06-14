moduleInfo = {
    "meta": {
        "name": "OneBotAdapter",
        "version": "2.1.1",
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
    "onebot": OneBotAdapter
}


# build_hash="fcb24dd06cd5386dbf27416f20b1f4397d7fa1b910b4346b841a1b42f7b002c6"
