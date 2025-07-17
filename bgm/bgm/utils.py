from functools import reduce
import re
from pydantic import BaseModel


class InfoFromFileName(BaseModel):
    title: str | None
    tags: list[str]
    episode: int | None


def extract_info_from_filename(filename: str):
    filename = filename.strip().rsplit(".", 1)[0]  # Remove file extension
    tags_re = re.compile(r"[\[\(（【第](.+?)[\]\)）】话話]")
    # tags_re = "|".join(
    #     rf"{lb}(.+?){rb}"
    #     for lb, rb in zip(["\\[", "\\(", "（", "【"], ["\\]", "\\)", "）", "】"])
    # )
    tags = tags_re.findall(filename)
    tags = list(map(str.strip, tags))
    _ = re.split(tags_re, filename)[::2]
    _ = reduce(lambda x, y: x + y, [s.split(" ") for s in _], [])
    title_parts = list(filter(bool, map(str.strip, _)))

    for tag in tags:
        if res := re.match(r"^(\d+)(v\d|end)?$", tag, re.IGNORECASE):
            episode = int(res.group(1))
            break
        if res := re.match(r"^ep_?(\d+).*$", tag, re.IGNORECASE):
            episode = int(res.group(1))
            break
    else:
        for i, part in enumerate(title_parts):
            if (
                (res := re.search(r"-?(\d+)-?", part))
                or (res := re.search(r"-?ep(\d+)-?", part, re.IGNORECASE))
                or (res := re.search(r"-?s\d+e(\d+)-?", part, re.IGNORECASE))
            ):
                episode = int(res.group(1))
                title_parts[i] = part[: res.start()] + " " + part[res.end() :]
                if not title_parts[i].strip():
                    title_parts[i] = "-"
                break
        else:
            episode = None

    if not title_parts:
        title = None
    else:
        title_parts = [p for p in title_parts if p != "-"]
        title = " ".join(title_parts)

    return InfoFromFileName(title=title, tags=tags, episode=episode)
