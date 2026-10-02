import ast
import asyncio
import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import threading
import types
import unittest
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load_definitions(filename, names, namespace):
    path = ROOT / "bgm" / "bgm" / filename
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    future = ast.parse("from __future__ import annotations").body
    module = ast.Module(body=future + nodes, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class RegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_directory_matching(self):
        namespace = load_definitions(
            "db.py",
            {"DB"},
            {
                "Path": Path,
                "os": os,
                "Counter": Counter,
                "contextlib": contextlib,
                "asyncio": asyncio,
                "logger": Mock(),
                "extract_info_from_filename": lambda name: types.SimpleNamespace(
                    episode=1
                ),
            },
        )
        db = namespace["DB"].__new__(namespace["DB"])
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        db.cursor = conn.cursor()
        db.cursor.execute("CREATE TABLE bgm (path TEXT, dandanplay_id INTEGER)")
        for directory in ("/anime/Show", "/anime/Show_100%"):
            db.cursor.execute("DELETE FROM bgm")
            db.cursor.executemany(
                "INSERT INTO bgm VALUES (?, ?)",
                [
                    (directory + "/01.mkv", 10001),
                    (directory + "2/01.mkv", 20001),
                    (directory + "/extras/01.mkv", 30001),
                    ("/anime/ShowX100Z/01.mkv", 40001),
                ],
            )
            self.assertEqual(db.get_autoload_source(directory, "02.mkv"), 10001)

    def test_translation_is_idempotent(self):
        namespace = load_definitions("llm.py", {"DanmakuTranslator"}, {})
        translator = namespace["DanmakuTranslator"]
        comments = [{"p": "1,1,0,0", "m": "原文A"}, {"p": "1,1,0,0", "m": "原文B"}]
        translations = {"1|原文A": "原文B", "1|原文B": "译文B"}
        translator._apply_translations(comments, translations)
        translator._apply_translations(comments, translations)
        self.assertEqual(comments[0]["m"], "原文B")
        self.assertEqual(comments[0]["m_original"], "原文A")
        self.assertEqual(translator._comment_key(comments[0]), "1|原文A")

    async def test_fallback_cache_uses_matched_id(self):
        episode = types.SimpleNamespace(
            episodeId=20002,
            animeId=2,
            animeTitle="title",
            episodeTitle="ep",
            model_dump=dict,
        )
        db = Mock()
        db.get.return_value = None
        db.get_autoload_source.return_value = 10002
        db.get_episode_info.return_value = None
        namespace = load_definitions(
            "dandanplay.py",
            {"match_video"},
            {
                "config": types.SimpleNamespace(storages=[Path("/tmp")]),
                "db": db,
                "logger": Mock(),
                "construct_episode_match": AsyncMock(return_value=None),
                "api_match_danmaku": AsyncMock(return_value=episode),
                "get_bgm_id": AsyncMock(return_value=2),
            },
        )
        await namespace["match_video"](Mock(), Path("/tmp/video.mkv"))
        db.set_episode_info.assert_called_once_with(20002, episode)

    async def test_first_bangumi_data_download(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory)
            payload = {"items": []}
            archive = io.BytesIO()
            content = json.dumps(payload).encode()
            with tarfile.open(fileobj=archive, mode="w:gz") as tar:
                info = tarfile.TarInfo("package/dist/data.json")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            class Response:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def json(self):
                    return {"publish_time": 1000, "dist": {"tarball": "archive"}}

                async def read(self):
                    return archive.getvalue()

            class Session(Response):
                def get(self, url):
                    return Response()

            @contextlib.asynccontextmanager
            async def check_update(path, age):
                yield lambda text: path.write_text(text)

            namespace = load_definitions(
                "source.py",
                {"_get_or_update_bangumi_data"},
                {
                    "DATA_PATH": data_path,
                    "json": json,
                    "db": types.SimpleNamespace(check_update_async=check_update),
                },
            )
            with patch.dict(
                "sys.modules", {"aiohttp": types.SimpleNamespace(ClientSession=Session)}
            ):
                self.assertEqual(
                    await namespace["_get_or_update_bangumi_data"](), payload
                )
            self.assertEqual(
                json.loads((data_path / "bangumi-data.json").read_text()), payload
            )

    async def test_stale_tasks_cannot_publish_or_spawn(self):
        namespace = load_definitions(
            "mpvbangumi.py",
            {"MPVBangumi"},
            {
                "request_id": ContextVar("request_id", default=None),
                "json": json,
                "logger": Mock(),
            },
        )
        cls = namespace["MPVBangumi"]
        ctx = cls.__new__(cls)
        ctx.rid = 1
        ctx.ipc_command_lock = threading.RLock()
        ctx.mpv = Mock()
        ctx.worker = types.SimpleNamespace(submit_task=asyncio.create_task)
        ctx.clear_comments()
        completed = asyncio.Event()

        async def old_task():
            await completed.wait()
            ctx.update_comments("main", [{"m": "old"}])
            ctx.resp_message("match", {})
            ctx.send_action("search", {"keyword": "old"})

        task = ctx.worker.submit_task
        tasks = []
        ctx.worker.submit_task = lambda coro: tasks.append(task(coro))
        ctx.add_task(old_task())
        ctx.send_action("invalidate", {}, rid=2)
        completed.set()
        await asyncio.gather(*tasks)
        ctx.mpv.command.assert_not_called()
        self.assertEqual(ctx._MPVBangumi__comments, {})
        token = namespace["request_id"].set(2)
        try:
            ctx.resp_message("match", {})
        finally:
            namespace["request_id"].reset(token)
        message = json.loads(ctx.mpv.command.call_args.args[-1])
        self.assertEqual(message["request_id"], 2)

    async def test_background_errors_are_logged(self):
        namespace = load_definitions(
            "utils.py",
            {"AsyncWorker"},
            {
                "asyncio": asyncio,
                "threading": threading,
            },
        )
        logger = Mock()
        worker = namespace["AsyncWorker"]()

        def close_worker():
            worker.stop()
            worker.loop.close()

        self.addCleanup(close_worker)

        async def fail():
            raise ValueError("test failure")

        with patch.dict("sys.modules", {"bgm": types.SimpleNamespace(logger=logger)}):
            await worker.submit_task(fail())
            logger.exception.assert_called_once_with("Background task failed")
            logger.reset_mock()
            future = await asyncio.to_thread(worker.submit_task, fail())
            await asyncio.wrap_future(future)
            logger.exception.assert_called_once_with("Background task failed")

    def test_renderer_handles_missing_position(self):
        executable = shutil.which("luajit")
        if executable is None:
            self.skipTest("LuaJIT is unavailable")
        script = """
mp = {get_property_number = function() return nil, "unavailable" end}
package.preload["lib.utils"] = function() return {} end
Delay = 0
local renderer = require "lib.danmaku_render"
renderer.comments = {{}}
renderer:render()
"""
        subprocess.run(
            [executable, "-e", script], cwd=ROOT, check=True, capture_output=True
        )


if __name__ == "__main__":
    unittest.main()
