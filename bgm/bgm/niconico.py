#!/usr/bin/env python3

import json
import re
import time
from pathlib import Path
from html.parser import HTMLParser
import html
from typing import Any

from bgm import logger
from bgm.source import DanmakuSource

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
_KANJI_NUMERALS = {'〇': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_KANJI_UNITS = {'十': 10, '百': 100, '千': 1000}


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
        re.search(r'第\s*([0-9]{1,4}|[〇零一二三四五六七八九十百千]+)\s*(?:話|回|集|章)', normalized),
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


def get_series_data(series: str) -> dict[str, str]:
    import urllib.request
    series_id = parse_series_id(series)
    url = f'{BASE_URL}/series/{series_id}'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        webpage = response.read().decode('utf-8', errors='replace')

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

def _decode_js_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return html.unescape(value)


def _parse_tktk_video_items(source: str, detail_id: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    array_re = re.compile(
        r"window\.TKTK\[\s*['\"](?P<key>[^'\"]+)['\"]\s*\]\s*=\s*\[(?P<body>.*?)\]\s*;",
        flags=re.DOTALL,
    )
    object_re = re.compile(r'\{(?P<object>.*?)\}', flags=re.DOTALL)
    title_re = re.compile(
        r'\btitle\s*:\s*(?:[A-Za-z_]\w*\s*\(\s*)*"(?P<title>(?:\\.|[^"\\])*)"\s*(?:\)\s*)*',
        flags=re.DOTALL,
    )
    watch_re = re.compile(
        r'\bwatchUrl\s*:\s*(?:[A-Za-z_]\w*\s*\(\s*)*"(?P<watch>(?:\\.|[^"\\])*)"\s*(?:\)\s*)*',
        flags=re.DOTALL,
    )

    for array_match in array_re.finditer(source):
        key = array_match.group('key')
        if not key.startswith(f'{detail_id}_'):
            continue
        if not key.endswith(('_ch_video', '_d_video')):
            continue

        body = array_match.group('body')
        for object_match in object_re.finditer(body):
            obj = object_match.group('object')
            title_match = title_re.search(obj)
            watch_match = watch_re.search(obj)
            if not title_match or not watch_match:
                continue

            title = _decode_js_string(title_match.group('title')).strip()
            watch_url = _decode_js_string(watch_match.group('watch')).strip()
            mobj = WATCH_PATH_RE.search(watch_url)
            if not mobj:
                continue

            items.append({'title': title, 'video_id': mobj.group('id')})

    return items


def get_detail_data(detail: str) -> dict[str, str]:
    import urllib.request
    import urllib.parse

    detail_id = parse_detail_id(detail)
    url = f'https://anime.nicovideo.jp/detail/{detail_id}/index.html'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        webpage = response.read().decode('utf-8', errors='replace')

    sources = [webpage]
    script_src_re = re.compile(r'<script[^>]+src=["\'](?P<src>[^"\']+)["\']', flags=re.IGNORECASE)
    for match in script_src_re.finditer(webpage):
        src = match.group('src')
        if f'/detail/{detail_id}/' not in src:
            continue
        if not src.endswith(('/state.js', '/payload.js')):
            continue

        script_url = urllib.parse.urljoin(url, src)
        try:
            script_req = urllib.request.Request(script_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(script_req, timeout=30) as script_response:
                script_body = script_response.read().decode('utf-8', errors='replace')
            sources.append(script_body)
        except Exception:
            continue

    parsed_items: list[dict[str, str]] = []
    for source in sources:
        parsed_items.extend(_parse_tktk_video_items(source, detail_id))

    episode_map = {}
    for idx, item in enumerate(parsed_items, start=1):
        episode_key = _extract_episode_key(item.get('title', ''), idx)
        if episode_key not in episode_map:
            episode_map[episode_key] = item['video_id']

    if not episode_map:
        raise RuntimeError(f'Unable to parse episodes from detail page: {url}')
    return episode_map

def parse_video_id(value: str) -> str:
    mobj = WATCH_RE.match(value)
    if mobj:
        return mobj.group('id')
    if ID_RE.match(value):
        return value
    raise ValueError(f'Invalid niconico URL or ID: {value}')


def http_json(url: str, *, headers=None, query=None, data=None) -> dict:
    import urllib.error
    import urllib.parse
    import urllib.request

    if query:
        url = f'{url}?{urllib.parse.urlencode(query)}'
    req_headers = {'User-Agent': 'Mozilla/5.0', **(headers or {})}
    request = urllib.request.Request(url, headers=req_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            body = '<unreadable>'
        if exc.code in {400, 404}:
            return json.loads(body)
        raise RuntimeError(f'HTTP {exc.code} for {url}: {body}') from exc
    return json.loads(raw.decode('utf-8'))


def fetch_api_data(video_id: str) -> dict:
    return http_json(
        f'{BASE_URL}/api/watch/v3_guest/{video_id}',
        headers=HEADERS,
        query={'actionTrackId': f'AAAAAAAAAA_{round(time.time() * 1000)}'},
    )


def fetch_page_data(video_id: str) -> dict:
    import urllib.request

    url = f'{BASE_URL}/watch/{video_id}'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        webpage = response.read().decode('utf-8', errors='replace')

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


def fetch_comments(api_data: dict, *, flatten: bool = True) -> list[dict]:
    comments_info = (((api_data.get('data') or {}).get('comment') or {}).get('nvComment') or {})
    server = comments_info.get('server')
    if not server:
        raise RuntimeError('No nvComment server in API response; comments may be unavailable')

    payload = {
        'additionals': {},
        'params': comments_info.get('params'),
        'threadKey': comments_info.get('threadKey'),
    }
    threads_resp = http_json(
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
        # logger.debug("context: %s", self.context)
        self.series_info_path = self.context.data_path.joinpath("series_info.json")
        self.series: int|None = options.get("series")
        self.offset: int = options.get("offset", 0)

    def _update_series_info(self) -> dict:
        if self.series is not None:
            _series_map = get_series_data(str(self.series))
        else:
            if self.context.ids is None or self.context.ids.bgm_id is None:
                logger.error("Failed to get bgm id")
                exit(-1)
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
                exit(-1)
            logger.debug("Found anime, title: %s", item["title"])

            sites = [site["site"] for site in item["sites"]]
            if "nicovideo" not in sites:
                logger.error("No nicovideo source found")
                exit(-1)
            nico_anime_id = item["sites"][sites.index("nicovideo")]["id"]
            logger.debug("Get nico_anime_id: %s", nico_anime_id)
            _series_map = get_detail_data(nico_anime_id)

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


    def map_ep(self, ep: int):
        info = self._get_series_info()
        if (
            info.get("series") != self.series
            or info.get("offset") != self.offset
            or info.get(str(ep)) is None
        ):
            info = self._update_series_info()
        return info.get(str(ep))

    def convert_format(self, danmaku: list[dict]) -> list[dict]:
        danmaku_new = []
        for d in danmaku:
            user = d["userId"]
            timestamp = f"{d['vposMs'] / 1000:.2f}"
            comment = d["body"]
            pos = 1
            color = 0xFFFFFF
            for c in d["commands"]:
                if c == "ue":
                    pos = 1
                elif c == "shita":
                    pos = 2
                elif c in NiconicoColorMap:
                    color = NiconicoColorMap[c]
            danmaku_new.append({"p": f"{timestamp},{pos},{color},{user}", "m": comment})
        return danmaku_new

    def fetch(self, ep: int) -> tuple[list[dict], str] | None:
        ep += self.offset
        video_id = self.map_ep(ep)
        if video_id is None:
            return
        logger.debug("NicoNico video_id: %s", video_id)

        out_path = self.context.data_path / f'{video_id}.comments.json'

        if self.context.db.is_outdated(out_path):
            api_data = fetch_page_data(video_id)
            result = fetch_comments(api_data, flatten=True)
            desc = api_data["data"]["video"]["title"]
            out_path.write_text(json.dumps({"result": result, "desc": desc}, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            _ = json.loads(out_path.read_text())
            result, desc = _["result"], _["desc"]

        return self.convert_format(result), desc


def main() -> int:
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
        api_data = fetch_api_data(video_id)

        status = ((api_data.get('meta') or {}).get('status'))
        if status and status != 200:
            reason = ((api_data.get('data') or {}).get('reasonCode')) or 'UNKNOWN'
            # The API may still include comment metadata for member-only videos.
            print(f'Warning: API status={status}, reason={reason}. Trying comments endpoint anyway...')

        comments_info = (((api_data.get('data') or {}).get('comment') or {}).get('nvComment') or {})
        if not comments_info.get('server'):
            print('Info: nvComment data missing from guest API response; falling back to watch page metadata...')
            api_data = fetch_page_data(video_id)

        result = fetch_comments(api_data, flatten=not args.raw_threads)
        out_path = Path(args.output or f'{video_id}.comments.json')
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Wrote {len(result)} {"threads" if args.raw_threads else "comments"} to {out_path}')
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
