moduleInfo = {
    "meta": {
        "name": "OneBotAdapter",
        "version": "2.2.3",
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

# build_hash="4d10d7c31005bb7dc546a08b635effbcb73faa8885d6fd289b71293229c1933b"

# build_hash="321046625e5172a4be7978cc5a9ebe6c4d76008f37fd88f23535f30e20aa9c52"

# build_hash="c55153c63fe5e126dc99174f40b354d8078cb506e565ce70a23da7b4f2c6ba79"
