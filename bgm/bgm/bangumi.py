import json
from pathlib import Path
import click
from bgm.api import BangumiAPI
from bgm.dandanplay import construct_episode_match
from bgm.db import db
from bgm import logger

bangumi = BangumiAPI()


def update_bangumi_collection(subject_id: int):
    """Update Bangumi collection for a given subject ID."""
    res = {}
    info: dict = bangumi.get_user_collection(subject_id)
    status = info.get("type")
    # ep_status = info.get("ep_status")

    if status is None:
        assert info["status_code"] == 404
        update_message: str | None = "条目状态更新：未看 → 在看"
        bangumi.update_user_collection(subject_id, status=3)
        res["update_message"] = update_message
        return res

    assert isinstance(status, int) and status in [1, 2, 3, 4, 5], "Invalid status code"
    update_from = (
        "想看",
        None,  # 看过
        None,  # 在看
        "搁置",
        "抛弃",
    )[status - 1]
    if update_from is None:
        update_message = None
        res["update_message"] = None
    else:
        update_message = f"条目状态更新：{update_from} → 在看"
        res["update_message"] = update_message
        bangumi.update_user_collection(subject_id, status=3)
    return res


def fuzzy_match_title(t1: str, t2: str) -> float:
    """Fuzzy match two titles and return a similarity score."""
    from difflib import SequenceMatcher

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


def update_bangumi_episode(subject_id: int, episode_id: int):
    """Update Bangumi episode status for a given subject ID and dandanplay episode ID."""
    ep = episode_id % 10000

    episodes_path = db.get_path(episode_id, "episodes")
    if not episodes_path.exists():
        logger.error(f"Episode file {episodes_path} does not exist.")
        exit(-1)
    with open(episodes_path, "r", encoding="utf-8") as f:
        episodes = json.load(f)["data"]

    if ep > 1000:
        logger.warning(
            f"Special Episode ID {episode_id} detected, try matching by episode title"
        )
        episode_info = construct_episode_match(episode_id)
        if episode_info is None:
            logger.error(f"Failed to match episode info for ID {episode_id}")
            exit(-1)
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
            exit(-1)
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

    prev_status = bangumi.get_episode_status(bgm_episode_id)
    if prev_status["type"] == 2:
        logger.info(
            f"Episode {bgm_episode_id} already marked as watched, skip updating."
        )
        return {"progress": ep, "total": len(episodes), "skipped": True}
    res = bangumi.update_episode_status(bgm_episode_id, status=2)
    if res.get("status_code") >= 400:
        logger.error("Failed to update episode status %s", res)
        exit(-1)
    return {"progress": ep, "total": len(episodes)}


@click.group("bangumi")
def main():
    pass


@main.command("update-collection")
@click.argument("subject_id", type=int)
def update_collection(subject_id: int):
    """Update Bangumi collection data for a given subject ID."""
    res = update_bangumi_collection(subject_id)
    click.echo(json.dumps(res, ensure_ascii=False))


@main.command("fetch-episodes")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
def fetch_episodes(video: Path):
    """Fetch and update episode information for a given subject ID."""
    video = video.absolute()
    res = db.get(path=str(video))
    assert res and res.bgm_id and res.dandanplay_id, (
        f"Failed to get Bangumi ID for {video}"
    )
    episodes_path = db.get_path(res.dandanplay_id, "episodes")
    if not db.is_outdated(episodes_path):
        logger.info(
            f"Episode file {episodes_path} exists and is not outdated, skipping update."
        )
        click.echo(json.dumps({"success": True}, ensure_ascii=False))
        return

    episodes = bangumi.get_user_episodes(res.bgm_id)
    assert episodes.get("data"), f"Failed to fetch episodes for Bangumi ID {res.bgm_id}"
    with open(episodes_path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False)
    click.echo(json.dumps({"success": True}, ensure_ascii=False))


@main.command("update-episode")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
def update_episode(video: Path):
    video = video.absolute()
    res = db.get(path=str(video))
    assert res and res.bgm_id and res.dandanplay_id, (
        f"Failed to get Bangumi ID and Dandanplay ID for {video}"
    )
    res = update_bangumi_episode(res.bgm_id, res.dandanplay_id)
    click.echo(json.dumps(res, ensure_ascii=False))
