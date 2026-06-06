import json
from typing import TYPE_CHECKING
from bgm.api import BangumiAPI
from bgm.dandanplay import construct_episode_match
from bgm.db import db
from bgm import logger

if TYPE_CHECKING:
    from bgm.mpvbangumi import MPVBangumi


async def bangumi_update_collection(ctx: "MPVBangumi", subject_id: int):
    """Update Bangumi collection for a given subject ID."""
    async with BangumiAPI() as api:
        info: dict = await api.get_user_collection(subject_id)
        status = info.get("type")
        # ep_status = info.get("ep_status")

        if status is None:
            assert info["status_code"] == 404
            update_message = "条目状态更新：未看 → 在看"
            await api.update_user_collection(subject_id, status=3)
            logger.notify(update_message)
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
            await api.update_user_collection(subject_id, status=3)
            update_message = f"条目状态更新：{update_from} → 在看"
            logger.notify(update_message)


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
        episodes = json.load(f)["data"]

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
        episode = (
            filter(lambda x: x["episode"]["ep"] == ep, episodes).__iter__().__next__()
        )
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
            return
        logger.notify("同步Bangumi追番记录进度成功")


async def bangumi_fetch_episodes(ctx: "MPVBangumi", subject_id: int, episode_id: int):
    """Fetch and update episode information for a given subject ID."""
    episodes_path = db.get_path(episode_id, "episodes")
    async with db.check_update_async(episodes_path) as writer:
        if writer is not None:
            async with BangumiAPI() as api:
                episodes = await api.get_user_episodes(subject_id)
            assert episodes.get("data"), (
                f"Failed to fetch episodes for Bangumi ID {subject_id}"
            )
            writer(json.dumps(episodes, ensure_ascii=False))
