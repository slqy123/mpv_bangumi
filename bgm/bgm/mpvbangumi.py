import json
import socket
from typing import Any, Awaitable
import logging
from bgm import logger, NOTIFY_LEVEL_NUM
from bgm.danmaku import convert_dandanplay_json2danmaku_events, get_style_config
from bgm.niconico import niconico_fetch_danmaku
from bgm.source import get_sources
from bgm.utils import AsyncWorker
from bgm.dandanplay import match_video
from bgm.dandanplay import fetch_danmaku as dandanplay_fetch_danmaku
from bgm.bangumi import (
    bangumi_fetch_episodes,
    bangumi_update_collection,
    bangumi_update_episode,
)
from pathlib import Path
from itertools import chain
from threading import Lock


class MPVLogHandler(logging.Handler):
    def __init__(self, sender, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.level_mapping = {
            logging.DEBUG: "verbose",
            logging.INFO: "info",
            logging.WARNING: "warn",
            logging.ERROR: "error",
            NOTIFY_LEVEL_NUM: "notify",
        }
        self.sender = sender

    def emit(self, record):
        try:
            if record.levelno not in self.level_mapping:
                return
            level = self.level_mapping[record.levelno]
            msg = self.format(record)
            self.sender("log", {"level": level, "msg": msg})
        except Exception:
            self.handleError(record)


class MPVBangumi:
    def __init__(self, ipc_path: str) -> None:
        self.ipc_path = ipc_path
        # self.mpv = MPV(start_mpv=False, ipc_socket=ipc_path)
        self.worker = AsyncWorker()
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.connect(ipc_path)
        self.rid = 0
        self.ipc_command_lock = Lock()
        self.mpv_log_handler = MPVLogHandler(sender=self.resp_message)
        logger.addHandler(self.mpv_log_handler)

        self.__comments: dict[str, list[Any]] = {}
        # self.command_lock = Lock()

    def close(self):
        self.worker.stop()
        logger.removeHandler(self.mpv_log_handler)
        self.socket.close()

    def update_comments(self, source: str, comments: Any):
        """comments in dandanplay style"""
        self.__comments[source] = comments

        events = convert_dandanplay_json2danmaku_events(
            list(chain(*self.__comments.values()))
        )
        self.resp_message(
            "set-danmaku",
            {
                "sources": list(self.__comments.keys()),
                "events": [e.model_dump() for e in events],
                "style": get_style_config(),
            },
        )

    def add_task(self, task: Awaitable):
        self.worker.submit_task(task)

    def resp_message(self, action: str, data: Any):
        with self.ipc_command_lock:
            self.rid += 1
            self.socket.send(
                json.dumps(
                    {
                        "command": [
                            "script-message",
                            "mpvbangumi-action",
                            json.dumps(
                                {"action": action, "data": data},
                                ensure_ascii=True,
                            ),
                        ],
                        "request_id": self.rid,
                    },
                ).encode("utf-8")
                + b"\n"
            )
            self.socket.recv(1024)

    def send_action(self, action: str, data: Any):
        if action == "match":
            self.add_task(
                match_video(self, Path(data["path"]), force_id=data.get("force_id"))
            )
        elif action == "sources":
            self.add_task(get_sources(self, data["episode_info"]))
        elif action == "fetch-danmaku":
            source = data["source"]
            if source == "main":
                self.add_task(
                    dandanplay_fetch_danmaku(self, data["episode_info"].episodeId)
                )
            elif source == "niconico":
                self.add_task(
                        niconico_fetch_danmaku(
                            self, data["episode_id"], data["options"], data["context"]
                        )
                )

        elif action == "update-bangumi-metadata":
            self.add_task(bangumi_update_collection(self, data["bgm_id"]))
            self.add_task(
                bangumi_fetch_episodes(self, data["bgm_id"], data["episode_id"])
            )
            self.resp_message("set-bangumi-id", {"bgm_id": data["bgm_id"]})
        elif action == "update-bangumi-episode":
            self.add_task(
                bangumi_update_episode(self, data["bgm_id"], data["episode_id"])
            )
        elif action == "open-bangumi-url":
            import webbrowser

            webbrowser.open(f"https://bgm.tv/subject/{int(data['bgm_id'])}")
