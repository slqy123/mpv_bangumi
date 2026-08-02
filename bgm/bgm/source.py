import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import portalocker

from bgm import DATA_PATH
from bgm.db import DB, IDS, EpisodeMatch, db

if TYPE_CHECKING:
    from bgm.mpvbangumi import MPVBangumi

class DanmakuSource(Protocol):
    @dataclass
    class Context:
        data_path: Path
        bangumi_data: list[dict]
        ids: IDS | None = None
        db: DB = db

    def __init__(self, options: dict, context: Context): ...

    async def fetch(self, ep: int) -> tuple[list[dict], str, str] | None: ...


async def get_sources(ctx: "MPVBangumi", episode_info: 'EpisodeMatch') -> None:
    source_path = db.get_path(episode_info.episodeId, "source")

    if source_path.exists():
        sources = json.loads(source_path.read_text(encoding="utf-8"))
    else:
        sources = {"main": {"enabled": True}}

    ctx.resp_message("sources", sources)

    for source, info in sources.items():
        if not (info and info.get("enabled")):
            continue

        if source == "main":
            ctx.send_action("fetch-danmaku", {"source": source, "episode_info": episode_info})
            continue

        data_path = DATA_PATH / f"metadata/{episode_info.animeId}/cache_{source}"
        data_path.mkdir(exist_ok=True, parents=True)

        ctx.send_action(
            "fetch-danmaku",
            {
                "source": source,
                "episode_id": episode_info.episodeId,
                "options": info,
                "context": DanmakuSource.Context(
                    data_path=data_path,
                    bangumi_data=(await get_or_update_bangumi_data())["items"],
                    ids=db.get(
                        dandanplay_id=episode_info.episodeId,
                    ),
                    db=db,
                ),
            },
        )

async def set_source_status(ctx: "MPVBangumi", episode_info: EpisodeMatch, status: dict):
    source_path = db.get_path(episode_info.episodeId, "source")
    with portalocker.Lock(
        source_path, mode="w", flags=portalocker.LockFlags.EXCLUSIVE
    ) as f:
        f.write(json.dumps(status))

    ctx.send_action("sources", {"episode_info": episode_info})


# --- bangumi data ---
def get_bangumi_data():
    bangumi_data_path = DATA_PATH.joinpath("bangumi-data.json")
    if bangumi_data_path.exists():
        try:
            return json.loads(bangumi_data_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return None
    return None

async def _get_or_update_bangumi_data() -> dict:
    import io
    import tarfile

    import aiohttp

    with db.check_update(
        DATA_PATH.joinpath("bangumi-data.json"), 1 * 12 * 3600
    ) as writer:
        if writer is not None:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://registry.npmmirror.com/bangumi-data/latest"
                ) as meta_res:
                    meta = await meta_res.json()
                pub_time = meta["publish_time"] / 1000
                bangumi_data_path = DATA_PATH.joinpath("bangumi-data.json")
                if bangumi_data_path.stat().st_mtime >= pub_time:
                    data = get_bangumi_data()
                    assert data is not None
                    return data
                tarball_url = meta["dist"]["tarball"]
                async with session.get(tarball_url) as res:
                    raw = await res.read()
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                f = tar.extractfile("package/dist/data.json")
                assert f is not None
                res_str = f.read().decode()
            writer(res_str)
            return json.loads(res_str)

    data = get_bangumi_data()
    assert data is not None
    return data


async def get_or_update_bangumi_data() -> dict:
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    return await _get_or_update_bangumi_data()

