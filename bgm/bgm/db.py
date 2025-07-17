import sqlite3
from typing import Any, Callable, Literal, NamedTuple, TypedDict, Unpack, NotRequired
from bgm import DATA_PATH
from pydantic import BaseModel
import json
import datetime
from bgm import logger
from pathlib import Path

from bgm.utils import extract_info_from_filename


class EpisodeMatch(BaseModel):
    episodeId: int
    animeId: int
    animeTitle: str
    episodeTitle: str
    type: str
    typeDescription: str
    shift: float


class QueryDict(TypedDict):
    path: NotRequired[str | None]
    bgm_id: NotRequired[int | None]
    dandanplay_id: NotRequired[int | None]


class IDS(NamedTuple):
    path: str
    bgm_id: int | None
    dandanplay_id: int | None


class DB:
    TABLE_NAME = "bgm"

    def __init__(self):
        self.db_path = DATA_PATH / "data.db"
        self.metadata_path = DATA_PATH / "metadata"
        self.metadata_path.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

    def __del__(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.commit()
            self.conn.close()

    def create_table(self):
        self.cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                path TEXT PRIMARY KEY,
                bgm_id INTEGER,
                dandanplay_id INTEGER
            )
            """
        )

    def get(self, **query: Unpack[QueryDict]):
        query_str = " AND ".join(f"{k}=?" for k in query.keys())
        sql = f"SELECT path, bgm_id, dandanplay_id FROM {self.TABLE_NAME} WHERE {query_str}"
        self.cursor.execute(sql, tuple(query.values()))
        result = self.cursor.fetchone()
        if result:
            return IDS(*result)
        return None

    def get_autoload_source(self, dir_: str, filename: str) -> int | None:
        self.cursor.execute(
            f"SELECT DISTINCT dandanplay_id / 10000 FROM {self.TABLE_NAME} WHERE path like ? and dandanplay_id IS NOT NULL",
            (dir_ + "%",),
        )
        results = [r[0] for r in self.cursor.fetchall()]
        if len(results) != 1:
            return None
        anime_id = results[0]
        ep = extract_info_from_filename(filename).episode
        if not ep:
            return None
        return anime_id * 10000 + ep

    def set_bgm_id(self, path: str, id_: int):
        self.cursor.execute(
            f"INSERT INTO {self.TABLE_NAME} (path, bgm_id) VALUES (?, ?) "
            "ON CONFLICT(path) DO UPDATE SET bgm_id = ?",
            (path, id_, id_),
        )

    def set_dandanplay_id(self, path: str, id_: int):
        self.cursor.execute(
            f"INSERT INTO {self.TABLE_NAME} (path, dandanplay_id) VALUES (?, ?) "
            "ON CONFLICT(path) DO UPDATE SET dandanplay_id = ?",
            (path, id_, id_),
        )

    def get_episode_info(self, episode_id: int):
        info = self.metadata_path / f"{episode_id // 10000}" / f"{episode_id}.json"
        if not info.exists():
            return None
        with open(info, "r", encoding="utf-8") as f:
            return EpisodeMatch.model_validate(json.load(f))

    def set_episode_info(self, episode_id: int, data: EpisodeMatch):
        info = self.metadata_path / f"{episode_id // 10000}" / f"{episode_id}.json"
        info.parent.mkdir(parents=True, exist_ok=True)
        with open(info, "w", encoding="utf-8") as f:
            json.dump(data.model_dump(), f, ensure_ascii=False)

    def update_comment(self, episode_id: int, update_cb: Callable[[], dict]) -> Path:
        comment_path = (
            self.metadata_path / f"{episode_id // 10000}" / f"{episode_id}-comment.json"
        )

        if not self.is_outdated(comment_path):
            logger.info(
                f"Comment file {comment_path} exists and is not outdated, skipping update."
            )
            return comment_path
        comment = update_cb()
        with open(comment_path, "w", encoding="utf-8") as f:
            json.dump(comment, f)
        return comment_path

    def append_user_comment(
        self, comment: str, episode_id: int, color: int, position: int, time: float
    ):
        comment_path = (
            self.metadata_path / f"{episode_id // 10000}" / f"{episode_id}-comment.json"
        )
        with open(comment_path, "r", encoding="utf-8") as f:
            comments = json.load(f)
        comments["comments"].append(
            {
                "cid": 114514,
                "p": f"{time:.2f},{position},{color},-1",
                "m": comment,
            }
        )
        comments["count"] += 1
        with open(comment_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, ensure_ascii=False)

    @staticmethod
    def is_outdated(path: Path, max_age: int = 3600 * 4) -> bool:
        if not path.exists():
            return True
        if datetime.datetime.now().timestamp() - path.stat().st_mtime > max_age:
            return True
        return False

    def get_path(
        self,
        episode_id: int,
        type_: Literal["comment", "ass", "metadata", "info", "episodes"],
    ):
        path = self.metadata_path / f"{episode_id // 10000}"
        if type_ == "comment":
            path /= f"{episode_id}-comment.json"
        elif type_ == "ass":
            path /= f"{episode_id}-comment.ass"
        elif type_ == "info":
            path /= f"{episode_id // 10000}-info.json"
        elif type_ == "metadata":
            path /= f"{episode_id}.json"
        elif type_ == "episodes":
            path /= "episodes.json"
        else:
            raise ValueError(f"Unknown type: {type_}")
        return path

    def get_or_update(
        self,
        episode_id: int,
        type_: Literal["comment", "ass", "metadata", "info", "episodes"],
        update_cb: Callable[[], Any],
        max_age: int = 3600 * 4,
    ) -> Any:
        path = self.get_path(episode_id, type_)
        if not self.is_outdated(path, max_age):
            logger.info(
                f"Metadata file {path} exists and is not outdated, skipping update."
            )
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        data = update_cb()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data


db = DB()
