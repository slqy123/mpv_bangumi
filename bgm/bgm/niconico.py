import asyncio
import html
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import portalocker
from bs4 import BeautifulSoup

from bgm import logger
from bgm.config import config
from bgm.source import DanmakuSource

if TYPE_CHECKING:
    from bgm.mpvbangumi import MPVBangumi

NiconicoColorMap = {
    "red": 0xFF0000,
    "pink": 0xFF8080,
    "orange": 0xFFCC00,
    "yellow": 0xFFFF00,
    "green": 0x00FF00,
    "cyan": 0x00FFFF,
    "blue": 0x0000FF,
    "purple": 0xC000FF,
    "black": 0x000000,
    "niconicowhite": 0xCCCC99,
    "white2": 0xCCCC99,
    "truered": 0xCC0033,
    "red2": 0xCC0033,
    "passionorange": 0xFF6600,
    "orange2": 0xFF6600,
    "madyellow": 0x999900,
    "yellow2": 0x999900,
    "elementalgreen": 0x00CC66,
    "green2": 0x00CC66,
    "marineblue": 0x33FFCC,
    "blue2": 0x33FFCC,
    "nobleviolet": 0x6633CC,
    "purple2": 0x6633CC,
}

BASE_URL = 'https://www.nicovideo.jp'
HEADERS = {
    'X-Frontend-ID': '6',
    'X-Frontend-Version': '0',
}
WATCH_RE = re.compile(r'https?://(?:(?:embed|sp|www)\.)?nicovideo\.jp/watch/(?P<id>(?:[a-z]{2})?\d+)')
ID_RE = re.compile(r'^(?:[a-z]{2})?\d+$')
WATCH_PATH_RE = re.compile(r'(?:https?://(?:(?:embed|sp|www)\.)?nicovideo\.jp)?/watch/(?P<id>(?:[a-z]{2})?\d+)')
SERIES_RE = re.compile(r'https?://(?:(?:sp|www)\.)?nicovideo\.jp/series/(?P<id>\d+)')
DETAIL_RE = re.compile(r'https?://anime\.nicovideo\.jp/detail/(?P<id>[A-Za-z0-9_-]+)(?:/index\.html)?/?(?:\?.*)?$')

_FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
_KANJI_NUMERALS = {
    '〇': 0,
    '零': 0,
    '一': 1,
    '二': 2,
    '三': 3,
    '四': 4,
    '五': 5,
    '六': 6,
    '七': 7,
    '八': 8,
    '九': 9,
    '壱': 1,
    '弐': 2,
    '参': 3,
    '肆': 4,
    '伍': 5,
    '陸': 6,
    '漆': 7,
    '柒': 7,
    '捌': 8,
    '玖': 9,
}
_KANJI_UNITS = {'十': 10, '拾': 10, '百': 100, '佰': 100, '陌': 100, '千': 1000, '仟': 1000, '阡': 1000}

_KANJI_NUMBER_CHARS = '〇零一二三四五六七八九壱弐参肆伍陸漆柒捌玖十拾百佰陌千仟阡'


class _NiconicoSeriesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self._current_video_id = None
        self._capture_depth = 0
        self._title_text = []
        self._title_candidates = []

    def _start_item(self, href: str):
        mobj = WATCH_PATH_RE.search(href or '')
        if not mobj:
            return
        self._current_video_id = mobj.group('id')
        self._capture_depth = 0
        self._title_text = []
        self._title_candidates = []

    def _finalize_item(self):
        if not self._current_video_id:
            return

        title = ' '.join(self._title_text)
        title = re.sub(r'\s+', ' ', title).strip()
        if not title:
            for candidate in self._title_candidates:
                normalized = re.sub(r'\s+', ' ', candidate).strip()
                if normalized:
                    title = normalized
                    break

        self.items.append({'title': html.unescape(title), 'video_id': self._current_video_id})
        self._current_video_id = None
        self._capture_depth = 0
        self._title_text = []
        self._title_candidates = []

    def handle_starttag(self, tag: str, attrs):
        attrs_dict = dict(attrs)

        if tag == 'a':
            href = attrs_dict.get('href') or attrs_dict.get('data-href')
            if self._current_video_id:
                self._finalize_item()
            if href:
                self._start_item(html.unescape(href))
            return

        if not self._current_video_id:
            return

        class_name = attrs_dict.get('class') or ''
        if (
            tag in {'h1', 'h2', 'h3', 'h4'}
            or 'data-title' in attrs_dict
            or 'MediaObjectTitle' in class_name
            or 'VideoMediaObject-title' in class_name
        ):
            self._capture_depth += 1

        for attr in ('aria-label', 'title'):
            value = attrs_dict.get(attr)
            if value:
                self._title_candidates.append(html.unescape(value))

    def handle_endtag(self, tag: str):
        if tag == 'a':
            self._finalize_item()
            return

        if self._current_video_id and self._capture_depth and tag in {'h1', 'h2', 'h3', 'h4'}:
            self._capture_depth -= 1

    def handle_data(self, data: str):
        if self._current_video_id and self._capture_depth:
            text = data.strip()
            if text:
                self._title_text.append(text)


def parse_series_id(value: str) -> str:
    mobj = SERIES_RE.match(value)
    if mobj:
        return mobj.group('id')
    if value.isdigit():
        return value
    raise ValueError(f'Invalid niconico series URL or ID: {value}')

def parse_detail_id(value: str) -> str:
    mobj = DETAIL_RE.match(value)
    if mobj:
        return mobj.group('id')
    if re.match(r'^[A-Za-z0-9_-]+$', value):
        return value
    raise ValueError(f'Invalid niconico detail URL or ID: {value}')


def _kanji_to_int(value: str) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)

    total = 0
    current = 0
    for ch in value:
        if ch in _KANJI_NUMERALS:
            current = _KANJI_NUMERALS[ch]
            continue
        if ch in _KANJI_UNITS:
            unit = _KANJI_UNITS[ch]
            total += (current or 1) * unit
            current = 0
            continue
        return None
    return total + current


def _extract_episode_key(title: str, index: int) -> str:
    normalized = html.unescape(title or '').translate(_FULLWIDTH_DIGITS)

    # Heuristics for common title formats: #01, 第1話, EP1, Episode 1, 1話, S1E01
    matchers = (
        re.search(r'(?<!\w)#\s*0*(\d{1,4})(?!\d)', normalized, flags=re.IGNORECASE),
        re.search(r'(?<!\w)ep(?:isode)?\.?\s*0*(\d{1,4})(?!\d)', normalized, flags=re.IGNORECASE),
        re.search(r'(?<!\w)s\d{1,3}\s*e\s*0*(\d{1,4})(?!\d)', normalized, flags=re.IGNORECASE),
        re.search(rf'第\s*([0-9]{{1,4}}|[{_KANJI_NUMBER_CHARS}]+)\s*(?:話|回|集|章)', normalized),
        re.search(r'(?<!\d)(\d{1,4})\s*(?:話|回|集|章)(?!\d)', normalized),
        re.search(r'^\s*0*(\d{1,4})\s*(?:[-:：\.、]|\s)', normalized),
    )

    for mobj in matchers:
        if not mobj:
            continue
        raw = mobj.group(1)
        value = _kanji_to_int(raw)
        if value is None:
            continue
        if 0 < value < 10000:
            return str(value)

    # Fall back to sequence index if title has no recognizable episode marker.
    return str(index)


async def get_series_data(series: str) -> dict[str, str]:
    series_id = parse_series_id(series)
    url = f'{BASE_URL}/series/{series_id}'
    async with aiohttp.ClientSession() as session, session.get(
        url, headers={'User-Agent': 'Mozilla/5.0'}
    ) as response:
        webpage = await response.text()

    parser = _NiconicoSeriesParser()
    parser.feed(webpage)

    episode_map = {}
    for idx, item in enumerate(parser.items, start=1):
        video_id = item['video_id']
        title = item.get('title', '')
        episode_key = _extract_episode_key(title, idx)
        if episode_key not in episode_map:
            episode_map[episode_key] = video_id

    if not episode_map:
        raise RuntimeError(f'Unable to parse episodes from series page: {url}')
    return episode_map



async def get_detail_data(detail: str) -> dict[str, str]:
    detail_id = parse_detail_id(detail)
    url = f'https://ch.nicovideo.jp/{detail_id}'
    try:
        async with aiohttp.ClientSession() as session, session.get(
            url, headers={'User-Agent': 'Mozilla/5.0'}
        ) as response:
            webpage = await response.text()
    except Exception:
        return {}

    soup = BeautifulSoup(webpage, 'html.parser')
    items: list[dict[str, str]] = []
    for video in soup.select('.g-video'):
        link = video.select_one('a.g-video-link')
        if not link:
            continue
        href = link.get('href', '')
        assert isinstance(href, str)
        mobj = WATCH_PATH_RE.search(href)
        if not mobj:
            continue
        title_elem = video.select_one('.g-video-title a') or link
        title = title_elem.get_text(strip=True)
        items.append({'title': title, 'video_id': mobj.group('id')})

    episode_map = {}
    for idx, item in enumerate(items, start=1):
        episode_key = _extract_episode_key(item.get('title', ''), idx)
        if episode_key not in episode_map:
            episode_map[episode_key] = item['video_id']

    if not episode_map:
        raise RuntimeError(f'Unable to parse episodes from channel page: {url}')
    return episode_map

def parse_video_id(value: str) -> str:
    mobj = WATCH_RE.match(value)
    if mobj:
        return mobj.group('id')
    if ID_RE.match(value):
        return value
    raise ValueError(f'Invalid niconico URL or ID: {value}')


async def http_json(url: str, *, headers=None, query=None, data=None) -> dict:
    req_headers = {'User-Agent': 'Mozilla/5.0', **(headers or {})}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            if data is not None:
                async with session.post(url, headers=req_headers, data=data) as resp:
                    resp.raise_for_status()
                    raw = await resp.read()
            else:
                async with session.get(url, headers=req_headers, params=query) as resp:
                    resp.raise_for_status()
                    raw = await resp.read()
        except aiohttp.ClientResponseError as exc:
            body = exc.message
            if exc.status in {400, 404}:
                return {}
            raise RuntimeError(f'HTTP {exc.status} for {url}: {body}') from exc

    return json.loads(raw.decode('utf-8'))


async def fetch_api_data(video_id: str) -> dict:
    return await http_json(
        f'{BASE_URL}/api/watch/v3_guest/{video_id}',
        headers=HEADERS,
        query={'actionTrackId': f'AAAAAAAAAA_{round(time.time() * 1000)}'},
    )


async def fetch_page_data(video_id: str) -> dict:
    url = f'{BASE_URL}/watch/{video_id}'
    async with aiohttp.ClientSession() as session, session.get(
        url, headers={'User-Agent': 'Mozilla/5.0'}
    ) as response:
        webpage = await response.text()

    mobj = re.search(
        r'<meta[^>]+name=["\']server-response["\'][^>]+content=(["\'])(?P<content>.+?)\1',
        webpage,
    )
    if not mobj:
        raise RuntimeError('Unable to find server-response metadata on watch page')

    server_response = json.loads(html.unescape(mobj.group('content')))
    return {
        'meta': (server_response.get('meta') or {}),
        'data': (((server_response.get('data') or {}).get('response')) or {}),
    }


async def fetch_comments(api_data: dict, *, flatten: bool = True) -> list[dict]:
    comments_info = (((api_data.get('data') or {}).get('comment') or {}).get('nvComment') or {})
    server = comments_info.get('server')
    if not server:
        raise RuntimeError('No nvComment server in API response; comments may be unavailable')

    payload = {
        'additionals': {},
        'params': comments_info.get('params'),
        'threadKey': comments_info.get('threadKey'),
    }
    threads_resp = await http_json(
        f'{server}/v1/threads',
        headers={
            'Content-Type': 'text/plain;charset=UTF-8',
            'Origin': BASE_URL,
            'Referer': f'{BASE_URL}/',
            'X-Client-Os-Type': 'others',
            **HEADERS,
        },
        data=json.dumps(payload).encode('utf-8'),
    )

    threads = (((threads_resp.get('data') or {}).get('threads')) or [])
    if not flatten:
        return threads

    comments = []
    for thread in threads:
        comments.extend((thread or {}).get('comments') or [])
    return comments

class NicoNicoSource(DanmakuSource):
    def __init__(self, options: dict, context: DanmakuSource.Context):
        self.context = context
        self.context.data_path.mkdir(parents=True, exist_ok=True)
        self.series_info_path = self.context.data_path.joinpath("series_info.json")
        self.series: int|None = options.get("series")
        self.offset: int = options.get("offset", 0)

    async def _update_series_info(self) -> dict|None:
        if self.series is not None:
            _series_map = await get_series_data(str(self.series))
        else:
            if self.context.ids is None or self.context.ids.bgm_id is None:
                logger.error("Failed to get bgm id")
                return
            bgm_id = self.context.ids.bgm_id
            for item in self.context.bangumi_data:
                if not any(
                    site["site"] == "bangumi" and site["id"] == str(bgm_id)
                    for site in item["sites"]
                ):
                    continue
                break
            else:
                logger.error("bangumi not found in bangumi-data")
                return None
            logger.debug("Found anime, title: %s", item["title"])

            sites = [site["site"] for site in item["sites"]]
            if "nicovideo" not in sites:
                logger.error("No nicovideo source found")
                return None
            nico_anime_id = item["sites"][sites.index("nicovideo")]["id"]
            logger.debug("Get nico_anime_id: %s", nico_anime_id)
            _series_map = await get_detail_data(nico_anime_id)

        series_map: dict[str, Any] = {
            "series": self.series,
            "offset": self.offset,
            "bgm_id": self.context.ids and self.context.ids.bgm_id,
        } | _series_map

        with self.series_info_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(series_map))
        return series_map

    def _get_series_info(self) -> dict:
        if self.series_info_path.exists():
            return json.loads(self.series_info_path.read_text(encoding="utf-8"))
        else:
            return {}


    async def map_ep(self, ep: int):
        ep += self.offset
        info = self._get_series_info()
        if (
            info.get("series") != self.series
            or info.get("offset") != self.offset
            or info.get(str(ep)) is None
        ):
            info = await self._update_series_info()
            if info is None:
                return None
        try:
            min_ep = min([int(k) for k in info if k.isdigit()])
        except ValueError:
            return None
        if min_ep > 1 and self.offset == 0:
            return info.get(str(min_ep - 1 + ep))
            
        return info.get(str(ep))

    def convert_format(self, danmaku: list[dict]) -> list[dict]:
        danmaku_new = []
        for d in danmaku:
            user = d["userId"]
            timestamp = f"{d['vposMs'] / 1000:.2f}"
            comment = d["body"]
            comment = re.sub(r"\n+", "\n", comment)
            pos = 1
            color = 0xFFFFFF
            for c in d["commands"]:
                if c == "ue":
                    pos = 4
                elif c == "shita":
                    pos = 5
                elif c in NiconicoColorMap:
                    color = NiconicoColorMap[c]
            for c in comment.splitlines():
                danmaku_new.append({"p": f"{timestamp},{pos},{color},{user}", "m": c})
        return danmaku_new

    async def fetch(self, ep: int) -> tuple[list[dict], str, str] | None:
        video_id = await self.map_ep(ep)
        if video_id is None:
            return None
        logger.debug("NicoNico video_id: %s", video_id)

        out_path = self.context.data_path / f'{video_id}.comments.json'

        if self.context.db.is_outdated(out_path):
            api_data = await fetch_page_data(video_id)
            result = await fetch_comments(api_data, flatten=True)
            desc = api_data["data"]["video"]["title"]
            out_path.write_text(json.dumps({"result": result, "desc": desc}, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            _ = json.loads(out_path.read_text(encoding="utf-8"))
            result, desc = _["result"], _["desc"]

        return self.convert_format(result), desc, video_id

async def niconico_fetch_danmaku(
    ctx: "MPVBangumi", episode_id: int, options: dict, context: DanmakuSource.Context
):
    with portalocker.Lock(
        context.data_path.joinpath("update.lock"),
        mode="w",
        flags=portalocker.LockFlags.EXCLUSIVE,
    ):
        res = await NicoNicoSource(options, context).fetch(episode_id % 10000)
        if not res:
            logger.warning("Failed to get nicovideo danmaku!")
            return
        danmaku, desc, video_id = res
        logger.info("nicovideo title: %s", desc)

        if config.llm and config.llm.enabled and os.environ.get("LLM_API_KEY"):
            logger.info("Start trasnlation with LLM")
            from bgm.llm import DanmakuTranslator
            translator = DanmakuTranslator(context.data_path, video_id)
            try:
                async def on_translation_update(partial_danmaku, done):
                    ctx.update_comments("niconico", partial_danmaku, silent=not done)

                await translator.translate(danmaku, desc, on_update=on_translation_update)
            except Exception:
                logger.warning("llm: translation failed, using original danmaku")
                ctx.update_comments("niconico", danmaku)
        else:
            ctx.update_comments("niconico", danmaku)

async def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description='Download niconico comments (danmaku) as JSON')
    parser.add_argument('video', help='niconico watch URL or video ID (e.g. so44149446)')
    parser.add_argument('-o', '--output', help='output JSON path (default: <video_id>.comments.json)')
    parser.add_argument(
        '--raw-threads',
        action='store_true',
        help='write raw thread payload instead of flattened comments list',
    )

    args = parser.parse_args()

    try:
        video_id = parse_video_id(args.video)
        api_data = await fetch_api_data(video_id)

        status = ((api_data.get('meta') or {}).get('status'))
        if status and status != 200:
            reason = ((api_data.get('data') or {}).get('reasonCode')) or 'UNKNOWN'
            # The API may still include comment metadata for member-only videos.
            print(f'Warning: API status={status}, reason={reason}. Trying comments endpoint anyway...')

        comments_info = (((api_data.get('data') or {}).get('comment') or {}).get('nvComment') or {})
        if not comments_info.get('server'):
            print('Info: nvComment data missing from guest API response; falling back to watch page metadata...')
            api_data = await fetch_page_data(video_id)

        result = await fetch_comments(api_data, flatten=not args.raw_threads)
        out_path = Path(args.output or f'{video_id}.comments.json')
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Wrote {len(result)} {"threads" if args.raw_threads else "comments"} to {out_path}')
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}')
        return 1

def main() -> int:
    return asyncio.run(_main())


if __name__ == '__main__':
    raise SystemExit(main())
