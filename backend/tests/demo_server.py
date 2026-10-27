"""Run the app with a stubbed translator, to try the UI without an API key.

    .venv/Scripts/python tests/demo_server.py

Every sentence "translates" to a fixed Chinese sentence after a short delay.
"""

import asyncio
import itertools
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import main, translate  # noqa: E402

LINES = itertools.cycle(
    [
        "他慢慢地走进银行，看了看手表。",
        "我们一起去长城吧！",
        "每个灯笼都需要一个故事。",
        "她觉得时间过得很快。",
        "雨停了，街上的人越来越多。",
    ]
)


async def fake_call(self, batch):
    await asyncio.sleep(0.6)
    return {u.id: next(LINES) for u in batch}


async def fake_check(client):
    return True, ""


translate.Translator._call = fake_call
main.check_credentials = fake_check

if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=8001)
