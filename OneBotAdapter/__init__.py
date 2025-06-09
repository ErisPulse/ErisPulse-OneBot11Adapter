moduleInfo = {
    "meta": {
        "name": "OneBotAdapter",
        "version": "2.0.9",
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

# build_hash="f0ccac80fe3e29e0ca054f0c683b36266f1224dffc2f8fcd5a70f19b6ec0707f"

# build_hash="5ec0fa239c5fad571e8e039d8556e59ee243ec982f0661580fb4caa7774ee3e2"
