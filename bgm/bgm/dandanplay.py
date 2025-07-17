#!/bin/python
import asyncio
import base64
import contextlib
from dataclasses import dataclass
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, List, Literal, NoReturn

from aiohttp import ClientSession, TCPConnector
import click
from pymediainfo import MediaInfo

from bgm import DATA_PATH
from bgm import logger
from bgm.config import config
from bgm.danmaku import (
    convert_dandanplay_json2ass_legacy,
    convert_dandanplay_json2ass_pylib,
    get_style_config,
)
from bgm.db import EpisodeMatch, db
from bgm.utils import extract_info_from_filename


CONFIG = json.loads(os.environ.get("MPV_DANMAKU_CONFIG", "{}"))
logger.debug("CONFIG: %s", CONFIG)


DB_PATH = DATA_PATH / "data.db"

AUTHENTICATION_TOKEN_PATH = DATA_PATH / "authentication_token.json"
AUTHENTICATION_TOKEN: str | None = None
AUTHENTICATION_TOKEN_TIMESTAMP: int | None = None
if AUTHENTICATION_TOKEN_PATH.exists():
    with open(AUTHENTICATION_TOKEN_PATH, "r") as f:
        try:
            _ = json.loads(f.read())
            AUTHENTICATION_TOKEN = _["token"]
            AUTHENTICATION_TOKEN_TIMESTAMP = _["timestamp"]
        except json.JSONDecodeError:
            logger.error("Failed to load authentication token from file.")


# video utils >>> -------------------------------------------------------------


@dataclass
class VideoInfo:
    hash: str
    duration: int
    filename: str
    size: int
    resolution: tuple[int, int]


def check_video(file_path: Path) -> bool:
    if not file_path.exists():
        return False
    try:
        guess = mimetypes.guess_type(file_path)[0]
        return guess.startswith("video") if guess is not None else False
    except FileNotFoundError:
        return False


def get_hash(video_path: Path) -> str:
    assert video_path.exists()
    with open(video_path, "rb") as f:
        # 16 * 1024 * 1024 = 16777216
        return hashlib.md5(f.read(16777216)).hexdigest().upper()


def get_duration(video_path: Path) -> int:
    """path must exist"""
    info = MediaInfo.parse(video_path)
    return int(float(info.video_tracks[0].duration) / 1000)  # type: ignore


def get_resolution(video_path: Path) -> tuple[int, int]:
    info = MediaInfo.parse(video_path)
    return (info.video_tracks[0].width, info.video_tracks[0].height)  # type: ignore


def get_info(video_path: Path):
    """path must exist"""
    return VideoInfo(
        hash=get_hash(video_path),
        duration=get_duration(video_path),
        filename=video_path.stem,
        size=Path(video_path).stat().st_size,
        resolution=get_resolution(video_path),
    )


# api >>> ---------------------------------------------------------------------


class DanDanAPI:
    BASE_API = "https://api.dandanplay.net/api/v2/"

    def __init__(self, limit: int = 4) -> None:
        self.limit = limit
        self.appid = os.environ["DANDANPLAY_APPID"]
        self.secret = os.environ["DANDANPLAY_APPSECRET"]
        self.has_auth = bool(AUTHENTICATION_TOKEN)
        self.auth_header = (
            {
                "Authorization": f"Bearer {AUTHENTICATION_TOKEN}",
            }
            if self.has_auth
            else {}
        )

    async def __aenter__(self):
        self.client = ClientSession(connector=TCPConnector(limit=self.limit))

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.close()

    def generate_signature(self, timestamp, path):
        data = f"{self.appid}{timestamp}{path}{self.secret}"
        sha256_hash = hashlib.sha256(data.encode()).digest()
        return base64.b64encode(sha256_hash).decode()

    def generate_login_signature(self, username, password, timestamp):
        data = f"{self.appid}{password}{timestamp}{username}{self.secret}"
        logger.info(data)
        sig = hashlib.md5(data.encode()).hexdigest()

        logger.info(f"login sig: {sig}")
        return sig

    async def post(self, uri: str, data: dict, timestamp: int | None = None) -> Any:
        timestamp = int(time.time()) if timestamp is None else timestamp
        path = "/api/v2/" + uri
        sig = self.generate_signature(timestamp, path)
        async with self.client.post(
            self.BASE_API + uri,
            data=data,
            headers={
                "Accept": "application/json",
                "X-AppId": self.appid,
                "X-signature": sig,
                "X-Timestamp": str(timestamp),
            }
            | self.auth_header,
        ) as resp:
            return await resp.json()

    async def get(self, uri: str, params: dict | None = None) -> Any:
        timestamp = int(time.time())
        path = "/api/v2/" + uri
        sig = self.generate_signature(timestamp, path)
        async with self.client.get(
            self.BASE_API + uri,
            params=params,
            headers={
                "Accept": "application/json",
                "X-AppId": self.appid,
                "X-signature": sig,
                "X-Timestamp": str(timestamp),
            }
            | self.auth_header,
        ) as resp:
            return await resp.json()

    async def match(self, video_info: VideoInfo) -> List[EpisodeMatch]:
        data = {
            "fileName": video_info.filename,
            "fileHash": video_info.hash,
            "fileSize": video_info.size,
            "videoDuration": video_info.duration,
            "matchMode": "hashAndFileName",
        }
        logger.debug("match data: %s", data)
        j = await self.post("match", data)
        logger.debug("match: %s", j)
        assert j["success"]
        episodes = [EpisodeMatch.model_validate(info) for info in j["matches"]]
        return episodes

    async def get_comment(
        self, episode_id: int, related: bool, convert: Literal["no", "chs", "cht"]
    ):
        chConvert = {"no": 0, "chs": 1, "cht": 2}[convert]
        withRelated = "true" if related else "false"
        j = await self.get(
            f"comment/{episode_id}",
            {
                "from": 0,
                "withRelated": withRelated,
                "chConvert": chConvert,
            },
        )
        return j

    async def login(self, username: str, password: str):
        timestamp = int(time.time())
        sig = self.generate_login_signature(username, password, timestamp)
        return await self.post(
            "login",
            data={
                "appId": self.appid,
                "userName": username,
                "password": password,
                "unixTimestamp": timestamp,
                "hash": sig,
            },
            timestamp=timestamp,
        )

    async def renew_token(self):
        if not AUTHENTICATION_TOKEN:
            logger.error("No authentication token found.")
            exit(-1)
        return await self.get("login/renew")

    async def comment(
        self, comment: str, episode_id: int, color: int, position: int, time: float
    ):
        data = {
            "mode": position,
            "time": time,
            "color": color,
            "comment": comment,
        }
        j = await self.post(f"comment/{episode_id}", data)
        return j

    async def get_anime_info(self, anime_id: int):
        j = await self.get(f"bangumi/{anime_id}")
        if not j["success"]:
            logger.error("Failed to get anime info: %s", j["errorMessage"])
            exit(-1)
        return j["bangumi"]

    async def search_anime(self, keyword: str, type_: str | None = None):
        """
        type:[ tvseries, tvspecial, ova, movie, musicvideo, web, other, jpmovie, jpdrama, unknown, tmdbtv, tmdbmovie ]
        """
        params = {"keyword": keyword}
        if type_:
            params["type"] = type_
        j = await self.get("search/anime", params)
        return j["animes"]

    def run(self, *tasks):
        async def __run(*tasks):
            async with self:
                return await asyncio.gather(*tasks)

        return asyncio.run(__run(*tasks))


# cli >>> ---------------------------------------------------------------------


@click.group("dandanplay")
def main(): ...


def get_match_info(
    video_path: Path,
) -> list[EpisodeMatch]:
    """Get match info from video path."""
    video_path = video_path.absolute()
    if not check_video(video_path):
        logger.error(f"Not a video file: {video_path}")
        exit(-1)

    api = DanDanAPI()
    info = get_info(video_path)
    match_results: list[EpisodeMatch] = api.run(api.match(info))[0]
    if not match_results:
        logger.error(f"No match found for: {info.filename}")
        exit(-1)

    if len(match_results) > 1:
        logger.warning(f"Multiple results for: {info.filename}")
    return match_results


def construct_episode_match(episode_id: int) -> EpisodeMatch | None:
    """Construct an EpisodeMatch object from anime info."""
    api = DanDanAPI()
    anime_info = db.get_or_update(
        episode_id, "info", lambda: api.run(api.get_anime_info(episode_id // 10000))[0]
    )
    try:
        episode_part = (
            filter(lambda x: x["episodeId"] == episode_id, anime_info["episodes"])
            .__iter__()
            .__next__()
        )
    except StopIteration:
        return None
    return EpisodeMatch(
        episodeId=episode_part["episodeId"],
        animeId=anime_info["animeId"],
        animeTitle=anime_info["animeTitle"],
        episodeTitle=episode_part["episodeTitle"],
        type=anime_info["type"],
        typeDescription=anime_info["typeDescription"],
        shift=0.0,
    )


@main.command()
@click.argument("video", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--force-id", type=int, default=None, help="Force use this dandanplay episode ID"
)
def fetch(video: Path, force_id: int | None = None):
    """Fetch danmaku for a video file."""
    video = video.absolute()
    if not any(video.is_relative_to(storage) for storage in config.storages):
        logger.info(f"Skip video {video} not in the storage path {config.storages}.")
        click.echo(
            json.dumps(
                {
                    "error": "VideoPathError",
                    "video": str(video),
                    "storage": str(config.storages),
                },
                ensure_ascii=False,
            )
        )
        return

    res = db.get(path=str(video))

    def fallback_to_match():
        episode_info = get_match_info(video)
        if len(episode_info) > 1:
            click.echo(
                json.dumps(
                    {
                        "info": extract_info_from_filename(video.name).model_dump(),
                        "matches": [
                            {
                                "episodeId": ep.episodeId,
                                "animeTitle": ep.animeTitle,
                                "episodeTitle": ep.episodeTitle,
                            }
                            for ep in episode_info
                        ],
                    },
                    ensure_ascii=False,
                )
            )
            exit(0)
        episode_info = episode_info[0]

        return episode_info

    if force_id is not None:
        # force use this dandanplay episode ID, no need for match
        episode_id = force_id
        episode_info = db.get_episode_info(force_id)
        if episode_info is None:
            episode_info = construct_episode_match(episode_id)
        logger.info("Using forced episode ID: %s for video %s", force_id, video.name)
        logger.info("ForceID episode info: %s", episode_info)
        db.set_dandanplay_id(str(video), episode_info.episodeId)
        db.set_episode_info(episode_info.episodeId, episode_info)
    elif res is not None and res.dandanplay_id is not None:
        # use dandanplay_id from db, no need for match
        episode_id = res.dandanplay_id
        episode_info = db.get_episode_info(episode_id)
        if episode_info is None:
            logger.warning(f"Episode info not found for: {video.name}")
            episode_info = construct_episode_match(episode_id)
            if episode_info is None:
                logger.error(f"Failed to construct episode match for: {video.name}")
                exit(-1)
            db.set_dandanplay_id(str(video), episode_info.episodeId)
            db.set_episode_info(episode_id, episode_info)
    elif _ := db.get_autoload_source(str(video.parent), video.name):
        # should autoload
        episode_id = _
        logger.info("Autoload episode ID: %s for video %s", episode_id, video.name)
        episode_info = db.get_episode_info(episode_id)
        if episode_info is None:
            logger.warning(f"Episode info not found for: {video.name}")
            episode_info = construct_episode_match(episode_id)
            if episode_info is None:
                episode_info = fallback_to_match()
            db.set_episode_info(episode_id, episode_info)
        db.set_dandanplay_id(str(video), episode_info.episodeId)
    else:
        # match video to dandanplay episode
        episode_info = fallback_to_match()
        db.set_dandanplay_id(str(video), episode_info.episodeId)
        db.set_episode_info(episode_info.episodeId, episode_info)

    logger.info("Episode info: %s", episode_info)

    comment_path = db.update_comment(
        episode_info.episodeId,
        lambda: (api := DanDanAPI()).run(
            api.get_comment(episode_info.episodeId, related=True, convert="no")
        )[0],
    )
    ass_path = comment_path.with_suffix(".ass")
    if not (
        ass_path.exists()
        and ass_path.stat().st_mtime_ns < comment_path.stat().st_mtime_ns
    ):
        # convert_dandanplay_json2ass_legacy(comment_path, ass_path)
        convert_dandanplay_json2ass_pylib(comment_path, ass_path, 36, (1920, 1080))

    logger.info("Danmaku fetched successfully.")
    click.echo(
        json.dumps(
            {
                "path": str(ass_path),
                "style": get_style_config(),
                "info": episode_info.model_dump(),
                "desc": episode_info.animeTitle + " " + episode_info.episodeTitle,
                "count": json.loads(comment_path.read_text(encoding="utf-8"))["count"],
            },
            ensure_ascii=False,
        )
    )


@main.command("login-or-update")
def login_or_update():
    if AUTHENTICATION_TOKEN and AUTHENTICATION_TOKEN_TIMESTAMP:
        delta = int(time.time()) - AUTHENTICATION_TOKEN_TIMESTAMP
        if delta < 3600 * 24 * 7:
            logger.info("Authentication token is still valid, skip login.")
            exit(-1)
        if delta < 3600 * 24 * 21:
            logger.info("Try renew authentication token.")
            api = DanDanAPI()
            j = api.run(api.renew_token())[0]
            if j.get("token"):
                logger.info("Renew authentication token successful.")
                with open(AUTHENTICATION_TOKEN_PATH, "w") as f:
                    f.write(
                        json.dumps(
                            {
                                "token": j["token"],
                                "timestamp": j["timestamp"],
                            }
                        )
                    )
            exit(-1)
        logger.info("Authentication token expired, try login.")

    username = CONFIG.get("userName")
    password = CONFIG.get("password")
    if not username or not password:
        logger.error("Username or password not found in config.")
        exit(-1)
    api = DanDanAPI()
    j = api.run(api.login(username, password))[0]
    if j.get("token"):
        logger.info("Login successful.")
        with open(AUTHENTICATION_TOKEN_PATH, "w") as f:
            f.write(
                json.dumps(
                    {
                        "token": j["token"],
                        "timestamp": int(time.time()),
                    }
                )
            )
            exit()
    else:
        logger.error("Login failed, %s", j.get("errorMessage"))
        exit(-1)


@main.command()
@click.argument("comment", type=str)
@click.option("--episode-id", type=int, required=True)
@click.option("--color", type=int, default=0xFFFFFF)
@click.option("--position", type=int, default=1)
@click.option("--time", type=float, default=0.0)
def comment(comment: str, episode_id: int, color: int, position: int, time: float):
    api = DanDanAPI()
    if not api.has_auth:
        logger.error("No authentication token found, please login first.")
        click.echo(json.dumps(dict(path=None, error=True), ensure_ascii=False))
        return
    success = api.run(
        api.comment(
            comment=comment,
            episode_id=episode_id,
            color=color,
            position=position,
            time=time,
        )
    )[0].get("success")
    if not success:
        logger.error("Failed to send comment.")
        exit(-1)
    logger.info("Comment sent successfully.")
    db.append_user_comment(
        comment=comment,
        episode_id=episode_id,
        color=color,
        position=position,
        time=time,
    )
    comment_path = db.get_path(episode_id, "comment")
    ass_path = db.get_path(episode_id, "ass")
    # convert_dandanplay_json2ass_legacy(comment_path, ass_path)
    convert_dandanplay_json2ass_pylib(comment_path, ass_path, 36, (1920, 1080))
    assert ass_path.exists()
    click.echo(json.dumps(dict(path=str(ass_path)), ensure_ascii=False))


@main.command("update-metadata")
@click.pass_context
@click.argument("video", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def update_metadata(ctx: click.Context, video: Path):
    api = DanDanAPI()
    ids = db.get(path=str(video))
    if ids is None or ids.dandanplay_id is None:
        with contextlib.redirect_stdout(None):
            ctx.forward(fetch)
        ids = db.get(path=str(video))
    assert ids and ids.dandanplay_id

    info_path = db.get_path(ids.dandanplay_id, "info")

    if db.is_outdated(info_path, 3600 * 24):
        info = api.run(api.get_anime_info(ids.dandanplay_id // 10000))[0]
        with info_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(info, ensure_ascii=False))
    else:
        logger.info("anime info not outdated, skip requesting info")
        info = json.loads(info_path.read_text(encoding="utf-8"))

    bgm_id = int(info["bangumiUrl"].rsplit("/", 1)[1])
    db.set_bgm_id(str(video), bgm_id)
    logger.info("successfully update anime info")
    click.echo(
        json.dumps({"bgm_id": bgm_id, "bgm_url": f"https://bgm.tv/subject/{bgm_id}"})
    )


@main.command("search")
@click.argument("keyword", type=str)
def search(keyword: str):
    """Search for anime by keyword."""
    api = DanDanAPI()
    results = api.run(api.search_anime(keyword))[0]
    click.echo(
        json.dumps(
            [
                {
                    "id": result["animeId"],
                    "title": result["animeTitle"],
                    "type": result["type"],
                }
                for result in results
            ],
            ensure_ascii=False,
        )
    )


@main.command("get-episodes")
@click.argument("anime_id", type=int)
def get_episodes(anime_id: int):
    """Get episodes of an anime by its ID."""
    api = DanDanAPI()
    info = db.get_or_update(
        anime_id * 10000 + 1, "info", lambda: api.run(api.get_anime_info(anime_id))[0]
    )
    episodes = info["episodes"]
    click.echo(
        json.dumps(
            [
                {"id": episode["episodeId"], "title": episode["episodeTitle"]}
                for episode in episodes
            ],
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
