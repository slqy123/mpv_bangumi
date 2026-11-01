import json
import logging
from collections.abc import Awaitable
from contextvars import ContextVar
from itertools import chain
from pathlib import Path
from threading import RLock
from typing import Any

from python_mpv_jsonipc import MPV

from bgm import LOG_LEVEL, logger
from bgm.bangumi import (
    bangumi_set_override,
    bangumi_update_episode,
    bangumi_update_metadata,
    bangumi_validate_subject,
)
from bgm.dandanplay import (
    dandanplay_comment,
    dandanplay_get_episodes,
    dandanplay_search,
    match_video,
)
from bgm.dandanplay import fetch_danmaku as dandanplay_fetch_danmaku
from bgm.danmaku import convert_dandanplay_json2danmaku_events, get_style_config
from bgm.db import EpisodeMatch
from bgm.niconico import niconico_fetch_danmaku
from bgm.source import get_sources, set_source_status
from bgm.utils import AsyncWorker

request_id: ContextVar[int | None] = ContextVar("request_id", default=None)


class MPVLogHandler(logging.Handler):
    def __init__(self, sender, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLevel(LOG_LEVEL)
        self.level_mapping = {
            logging.DEBUG: "verbose",
            logging.INFO: "info",
            logging.WARNING: "warn",
            logging.ERROR: "error",
            logging.CRITICAL: "error",
        }
        self.sender = sender

    def emit(self, record):
        try:
            if record.levelno not in self.level_mapping:
                return
            level = self.level_mapping[record.levelno]
            self.sender("log", {"level": level, "msg": record.getMessage()})
        except Exception:
            self.handleError(record)


class MPVBangumi:
    def __init__(self, mpv: MPV) -> None:
        self.mpv = mpv
        self.worker = AsyncWorker()
        self.rid = 0
        self.ipc_command_lock = RLock()
        self.mpv_log_handler = MPVLogHandler(sender=self.resp_message)
        logger.addHandler(self.mpv_log_handler)

        self.__comments: dict[str, list[Any]] = {}
        # self.command_lock = Lock()

    def close(self):
        self.worker.stop()
        logger.removeHandler(self.mpv_log_handler)

    def clear_comments(self):
        self.__comments = {}

    def update_comments(self, source: str, comments: list[dict], silent: bool = False):
        """comments in dandanplay style"""
        with self.ipc_command_lock:
            if not self.is_current_request():
                return
            self.__comments[source] = comments
            self._publish_comments(source, comments, silent)

    def _publish_comments(self, source: str, comments: list[dict], silent: bool):
        if not silent:
            logger.info(f"source {source}: {len(comments)} danmakus")

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

    def is_current_request(self):
        return request_id.get() in (None, self.rid)

    def add_task(self, task: Awaitable):
        rid = request_id.get()
        if rid is None:
            rid = self.rid

        async def run():
            token = request_id.set(rid)
            try:
                await task
            finally:
                request_id.reset(token)

        self.worker.submit_task(run())

    def resp_message(self, action: str, data: Any):
        if not self.is_current_request():
            return
        self.mpv.command(
            "script-message",
            "mpvbangumi-action",
            json.dumps(
                {"action": action, "data": data, "request_id": request_id.get()},
                ensure_ascii=True,
            ),
        )

    def send_action(self, action: str, data: Any, rid: int | None = None):
        with self.ipc_command_lock:
            if rid is not None:
                if rid < self.rid:
                    return
                if rid != self.rid:
                    self.rid = rid
                    self.clear_comments()
            elif not self.is_current_request():
                return
            token = request_id.set(rid) if rid is not None else None
            try:
                self._send_action(action, data)
            finally:
                if token is not None:
                    request_id.reset(token)

    def _send_action(self, action: str, data: Any):
        if isinstance(data, str):
            data = json.loads(data)

        if action == "match":
            self.add_task(
                match_video(self, Path(data["path"]), force_id=data.get("force_id"))
            )
        elif action == "sources":
            self.clear_comments()
            self._publish_comments("main", [], silent=True)
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
            self.add_task(
                bangumi_update_metadata(self, data["bgm_id"], data["episode_id"], data["source"])
            )
        elif action == "validate-bangumi-id":
            self.add_task(bangumi_validate_subject(self, data["value"]))
        elif action in ("set-bangumi-id", "clear-bangumi-id"):
            self.add_task(
                bangumi_set_override(
                    self, Path(data["path"]), EpisodeMatch(**data["episode_info"]),
                    int(data["bgm_id"]) if action == "set-bangumi-id" else None,
                )
            )
        elif action == "update-bangumi-episode":
            self.add_task(
                bangumi_update_episode(self, data["bgm_id"], data["episode_id"])
            )
        elif action == "open-bangumi-url":
            import webbrowser

            webbrowser.open(f"https://bgm.tv/subject/{int(data['bgm_id'])}")
        elif action == "comment":
            self.add_task(
                dandanplay_comment(
                    self,
                    comment=data["comment"],
                    episode_id=data["episode_id"],
                    color=int(data["color"]),
                    position=int(data["position"]),
                    time=float(data["time"]),
                )
            )
        elif action == "search":
            self.add_task(dandanplay_search(self, data["keyword"]))
        elif action == "get-episodes":
            self.add_task(dandanplay_get_episodes(self, int(data["anime_id"])))
        elif action == "set-source-status":
            self.add_task(
                set_source_status(
                    self, episode_info=EpisodeMatch(**data["episode_info"]), status=data["status"]
                )
            )
            info = data.get("bangumi_info")
            if info and info.get("bgm_id") and not info.get("ready"):
                self.add_task(
                    bangumi_update_metadata(
                        self, info["bgm_id"], data["episode_info"]["episodeId"], info["source"]
                    )
                )
