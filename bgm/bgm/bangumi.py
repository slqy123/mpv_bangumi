from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import aiohttp

from bgm import logger
from bgm.api import BangumiAPI
from bgm.dandanplay import construct_episode_match, get_bgm_id
from bgm.db import EpisodeMatch, db

if TYPE_CHECKING:
    from bgm.mpvbangumi import MPVBangumi


def parse_bangumi_id(value: str) -> int:
    value = value.strip()
    if not re.fullmatch(r"[0-9]+", value):
        try:
            url = urlsplit(value)
        except ValueError:
            raise ValueError("请输入有效的 Bangumi ID 或条目链接") from None
        if url.scheme not in ("http", "https") or url.netloc.lower() not in (
            "bgm.tv",
            "bangumi.tv",
            "chii.in",
        ):
            raise ValueError("请输入有效的 Bangumi ID 或条目链接")
        match = re.fullmatch(r"/subject/([0-9]+)/?", url.path)
        if match is None:
            raise ValueError("请输入 Bangumi 条目链接，而不是剧集链接")
        value = match[1]
    subject_id = int(value)
    if subject_id <= 0:
        raise ValueError("Bangumi ID 必须是正整数")
    return subject_id


async def bangumi_validate_subject(ctx: MPVBangumi, value: str):
    try:
        subject_id = parse_bangumi_id(value)
    except ValueError as exc:
        ctx.resp_message("bangumi-subject", {"error": str(exc)})
        return
    try:
        async with BangumiAPI() as api:
            subject = await api.get_subject(subject_id)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logger.warning("Failed to validate Bangumi subject", exc_info=True)
        ctx.resp_message(
            "bangumi-subject",
            {"error": "验证 Bangumi 条目失败，请检查网络或服务状态后重试"},
        )
        return
    if subject.get("status_code", 200) != 200 or subject.get("id") != subject_id:
        ctx.resp_message("bangumi-subject", {"error": "Bangumi 条目不存在或无法访问"})
        return
    if subject.get("type") != 2:
        ctx.resp_message("bangumi-subject", {"error": "请选择 Bangumi 动画条目"})
        return
    ctx.resp_message(
        "bangumi-subject",
        {
            "bgm_id": subject_id,
            "title": subject.get("name_cn") or subject.get("name") or str(subject_id),
        },
    )


async def bangumi_set_override(
    ctx: MPVBangumi, video: Path, episode_info: EpisodeMatch, subject_id: int | None
):
    anime_id = episode_info.animeId
    if subject_id is None:
        bgm_id = await get_bgm_id(video, anime_id, use_override=False)
        if not ctx.is_current_request():
            return
        db.clear_bangumi_override(anime_id)
    else:
        if subject_id <= 0 or not ctx.is_current_request():
            return
        db.set_bangumi_override(anime_id, subject_id)
        bgm_id = subject_id
    db.set_anime_bgm_id(anime_id, bgm_id)
    ctx.send_action(
        "update-bangumi-metadata",
        {
            "bgm_id": bgm_id,
            "episode_id": episode_info.episodeId,
            "source": "manual" if subject_id is not None else "auto",
        },
    )


async def bangumi_update_metadata(
    ctx: MPVBangumi, subject_id: int | None, episode_id: int, source: str
):
    data = {"bgm_id": subject_id, "source": source, "ready": False}
    ctx.resp_message("set-bangumi-id", data)
    if subject_id is None:
        logger.info("No Bangumi association found; danmaku is unaffected")
        ctx.resp_message(
            "notify",
            {"message": "未找到 Bangumi 关联，可在 Alt+n 菜单中手动设置 ID；弹幕不受影响"},
        )
        return
    await bangumi_update_collection(ctx, subject_id)
    ids = db.get(dandanplay_id=episode_id)
    if not ctx.is_current_request() or ids is None or ids.bgm_id != subject_id:
        return
    ready = await bangumi_fetch_episodes(ctx, subject_id, episode_id)
    if not ready:
        ctx.resp_message("notify", {"message": "获取 Bangumi 剧集失败，暂未启用进度同步"})
        return
    ids = db.get(dandanplay_id=episode_id)
    if ids is not None and ids.bgm_id == subject_id:
        source = "manual" if db.get_bangumi_override(episode_id // 10000) is not None else "auto"
        ctx.resp_message("set-bangumi-id", data | {"source": source, "ready": True})


async def bangumi_update_collection(ctx: "MPVBangumi", subject_id: int):
    """Update Bangumi collection for a given subject ID."""
    async with BangumiAPI() as api:
        info: dict = await api.get_user_collection(subject_id)
        status = info.get("type")
        # ep_status = info.get("ep_status")

        if status is None:
            assert info["status_code"] == 404
            update_message = "条目状态更新：未看 → 在看"
            result = await api.update_user_collection(subject_id, status=3)
            if result["status_code"] >= 400:
                ctx.resp_message("notify", {"message": "更新 Bangumi 收藏失败，请检查访问令牌或服务状态"})
                raise ValueError(f"Failed to update Bangumi collection: {result}")
            logger.info("Bangumi collection status updated: uncollected -> watching")
            ctx.resp_message("notify", {"message": update_message})
            return

        assert isinstance(status, int) and status in [1, 2, 3, 4, 5], (
            "Invalid status code"
        )
        update_from = (
            "想看",
            None,  # 看过
            None,  # 在看
            "搁置",
            "抛弃",
        )[status - 1]
        if update_from is not None:
            result = await api.update_user_collection(subject_id, status=3)
            if result["status_code"] >= 400:
                ctx.resp_message("notify", {"message": "更新 Bangumi 收藏失败，请检查访问令牌或服务状态"})
                raise ValueError(f"Failed to update Bangumi collection: {result}")
            update_message = f"条目状态更新：{update_from} → 在看"
            logger.info("Bangumi collection status updated: %d -> watching", status)
            ctx.resp_message("notify", {"message": update_message})


def fuzzy_match_title(t1: str, t2: str) -> float:
    """Fuzzy match two titles and return a similarity score."""
    from difflib import SequenceMatcher

    if not t1 or not t2:
        return 0.0

    parts1 = t1.split(" ")
    parts2 = t2.split(" ")
    common_parts = set(parts1) & set(parts2)
    l1 = len("".join(parts1))
    l2 = len("".join(parts2))
    l_common = len("".join(common_parts))
    ratio1 = l_common / min(l1, l2)
    ratio2 = (1 - ratio1) * SequenceMatcher(
        None, list(set(parts1) - common_parts), list(set(parts2) - common_parts)
    ).ratio()

    return max(ratio1 + ratio2, SequenceMatcher(None, t1, t2).ratio())


async def bangumi_update_episode(ctx: "MPVBangumi", subject_id: int, episode_id: int):
    """Update Bangumi episode status for a given subject ID and dandanplay episode ID."""
    ep = episode_id % 10000

    episodes_path = db.get_path(episode_id, "episodes")
    if not episodes_path.exists():
        logger.error(f"Episode file {episodes_path} does not exist.")
        return
    with open(episodes_path, "r", encoding="utf-8") as f:
        cached = json.load(f)
    if cached.get("subject_id") != subject_id:
        logger.error("Bangumi episode cache does not match subject %d", subject_id)
        return
    episodes = cached.get("data", [])
    if not episodes:
        logger.error("No episodes found for Bangumi subject %d", subject_id)
        return

    if ep > 1000:
        logger.warning(
            f"Special Episode ID {episode_id} detected, try matching by episode title"
        )
        episode_info = await construct_episode_match(episode_id)
        if episode_info is None:
            logger.error(f"Failed to match episode info for ID {episode_id}")
            return
        title = episode_info.episodeTitle
        # Fuzzy match the title with the episodes
        confs1 = [
            fuzzy_match_title(title, ep_info["episode"].get("name", ""))
            for ep_info in episodes
        ]
        confs2 = [
            fuzzy_match_title(title, ep_info["episode"].get("name_cn", ""))
            for ep_info in episodes
        ]
        confs = [max(c1, c2) for c1, c2 in zip(confs1, confs2)]
        max_conf = max(confs)
        idx = confs.index(max_conf)
        episode = episodes[idx]
        bgm_episode_id = episode["episode"]["id"]
        if max_conf < 0.8:
            logger.error(
                f"Failed to match episode title {title} with episodes, max confidence {max_conf}: {episode}"
            )
            return
        else:
            logger.info(
                f"Matched episode title {title} with episode {episode} (confidence: {max_conf})"
            )
    else:
        # ep >= sort?, ep starts from 1
        episode = next((item for item in episodes if item["episode"]["ep"] == ep), None)
        if episode is None:
            logger.error("No matching Bangumi episode for DandanPlay episode %d", episode_id)
            return
        bgm_episode_id = episode["episode"]["id"]

    async with BangumiAPI() as api:
        prev_status = await api.get_episode_status(bgm_episode_id)
        if prev_status["type"] == 2:
            logger.info(
                f"Episode {bgm_episode_id} already marked as watched, skip updating."
            )
            return
        res = await api.update_episode_status(bgm_episode_id, status=2)
        if res["status_code"] >= 400:
            logger.error("Failed to update episode status %s", res)
            ctx.resp_message("notify", {"message": "同步 Bangumi 观看进度失败，请检查访问令牌或服务状态"})
            return
        logger.info("Bangumi watch progress synchronized successfully")
        ctx.resp_message("notify", {"message": "同步Bangumi追番记录进度成功"})


async def bangumi_fetch_episodes(ctx: "MPVBangumi", subject_id: int, episode_id: int):
    """Fetch and update episode information for a given subject ID."""
    episodes_path = db.get_path(episode_id, "episodes")
    async with db.update_lock(episodes_path):
        if episodes_path.exists() and not db.is_outdated(episodes_path):
            cached = json.loads(await db.read_locked(episodes_path))
            if cached.get("subject_id") == subject_id and cached.get("data"):
                return True
        async with BangumiAPI() as api:
            episodes = await api.get_user_episodes(subject_id)
        if episodes.get("status_code", 200) >= 400 or not episodes.get("data"):
            logger.error("Failed to fetch episodes for Bangumi ID %d", subject_id)
            return False
        episodes["subject_id"] = subject_id
        episodes_path.parent.mkdir(parents=True, exist_ok=True)
        await db.write_locked(episodes_path, json.dumps(episodes, ensure_ascii=False))
    return True
