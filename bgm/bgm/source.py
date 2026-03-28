from sqlite3.dbapi2 import Time
from typing import Literal, Protocol
import click
import json
from dataclasses import dataclass
from pathlib import Path
import time

from bgm import DATA_PATH, logger
from bgm.db import DB, IDS, db

class DanmakuSource(Protocol):
    @dataclass
    class Context:
        data_path: Path
        bangumi_data: list[dict]
        ids: IDS | None = None
        db: DB = db

    def __init__(self, options: dict, context: Context): ...

    def fetch(self, ep: int) -> tuple[list[dict], str] | None: ...


def get_source_status(anime_id: int) -> dict:
    from bgm.db import db
    source_path = db.get_path(anime_id * 10000, "source")

    if source_path.exists():
        sources = json.loads(source_path.read_text())
    else:
        sources = {"main": {"enabled": True}}

    return sources

def set_source_status(anime_id: int, status: dict):
    from bgm.db import db
    source_path = db.get_path(anime_id * 10000, "source")

    with source_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(status))
    
def get_source_danmaku(episode_id: int, source: Literal["niconico"]) -> tuple[list[dict], str] | None:
    from bgm.db import db
    comment_path = db.get_path(episode_id, "commentEX")

    if comment_path.exists():
        sources = json.loads(comment_path.read_text())
    else:
        sources = {}

    if (danmaku:=sources.get(source)) is not None and not db.is_outdated(comment_path):
        return danmaku

    ids = db.get(dandanplay_id=episode_id)
    if ids is None:
        assert False, "Dandanplay ID should not be None"
    if ids.bgm_id is None:
        info_path = db.get_path(episode_id, "info")
        info = json.loads(info_path.read_text())
        bgm_id = int(info["bangumiUrl"].rsplit("/", 1)[1])
        ids = IDS(ids.path, bgm_id, ids.dandanplay_id)

    match source:
        case "niconico":
            from bgm.niconico import NicoNicoSource
            return NicoNicoSource(
                get_source_status(episode_id // 10000)[source],
                DanmakuSource.Context(DATA_PATH / f"metadata/{episode_id // 10000}/cache_{source}", get_or_update_bangumi_data()["items"], ids)
            ).fetch(episode_id % 10000)
        case _:
            assert False
        


@click.group()
def source():
    pass


# @click.argument("source", type=click.Choice(["niconico"]))
@source.command("set-status")
@click.argument("anime_id", type=int)
@click.argument("options_json", type=str)
def set_status(anime_id: int, options_json: str):
    # sources = get_source_status(anime_id)
    # sources[source] = json.loads(options_json)
    sources = json.loads(options_json)
    set_source_status(anime_id, sources)

    click.echo(json.dumps({"success": True, "sources": sources}))
    
@source.command("get-status")
@click.argument("anime_id", type=int)
def get_status(anime_id: int):
    click.echo(json.dumps(get_source_status(anime_id), ensure_ascii=False))

# --- bangumi data ---
def get_bangumi_data():
    bangumi_data_path = DATA_PATH.joinpath("bangumi-data.json")
    if bangumi_data_path.exists():
        try:
            return json.loads(bangumi_data_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return None
    return None

def update_bangumi_data() -> dict:
    import requests
    res = requests.get("https://unpkg.com/bangumi-data@0.3/dist/data.json")
    res_json = res.json() | {"last_update": time.time()}
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    with DATA_PATH.joinpath("bangumi-data.json").open("w", encoding="utf-8") as f:
        f.write(json.dumps(res_json, ensure_ascii=False))
    return res_json

def get_or_update_bangumi_data() -> dict:
    bangumi_data = get_bangumi_data()
    if bangumi_data is not None and (time.time() - bangumi_data["last_update"]) < 7 * 24 * 3600:
        return bangumi_data
    return update_bangumi_data()

@source.command("get-bangumi-data")
def get_or_update_bangumi_data_():
    click.echo(json.dumps(get_or_update_bangumi_data(), ensure_ascii=False))
