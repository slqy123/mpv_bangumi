import json
from pathlib import Path
from typing import Literal
from bgm.config import config
from bgm import DATA_PATH, logger
from pydantic import BaseModel


class DanmakuEvent(BaseModel):
    start_time: float
    end_time: float
    style: Literal["R2L", "TOP"]
    text: str
    pos: tuple[int, int] | None
    move: tuple[int, int, int, int] | None
    color: str


# R2L danmaku algorithm
def get_position_y(font_size, appear_time, text_length, resolution_x, roll_time, array):
    velocity = (text_length + resolution_x) / roll_time
    best_row = 0
    max_delta_velocity = 0
    best_bias = float("-inf")
    for i in range(array.rows):
        previous_appear_time = array.get_time(i)
        if previous_appear_time < 0:
            array.set_time_length(i, appear_time, text_length)
            return 1 + i * font_size
        previous_length = array.get_length(i)
        previous_velocity = (previous_length + resolution_x) / roll_time
        delta_velocity = velocity - previous_velocity
        # abs_velocity = abs(delta_velocity)
        # The initial difference length
        delta_x = (
            appear_time - previous_appear_time
        ) * previous_velocity - previous_length
        # if 35 > appear_time > 30:
        #     logger.info(
        #         f"{i=} {delta_x=} {delta_velocity=} {appear_time=} {previous_appear_time=} {text_length=} {previous_length=} {previous_velocity=} {velocity=}"
        #     )
        # If the initial difference length is negative, which means overlapped. Skip.
        if delta_x < 0:
            if abs(delta_velocity) > max_delta_velocity:
                max_delta_velocity = abs(delta_velocity)
                best_row = i
            continue
        if delta_velocity <= 0:
            array.set_time_length(i, appear_time, text_length)
            return 1 + i * font_size
        delta_time = delta_x / delta_velocity
        bias = appear_time - previous_appear_time + delta_time
        if bias > roll_time * resolution_x / (previous_length + resolution_x):
            array.set_time_length(i, appear_time, text_length)
            return 1 + i * font_size
        else:
            if bias > best_bias:
                best_bias = bias
                best_row = i
    array.set_time_length(best_row, appear_time, text_length)
    return 1 + best_row * font_size


# Top danmaku algorithm
def get_fixed_y(font_size, appear_time, array, fix_time):
    best_row = 0
    best_bias = -1
    for i in range(array.rows):
        previous_appear_time = array.get_time(i)
        if previous_appear_time < 0:
            array.set_time_length(i, appear_time, 0)
            return font_size * i + 1
        else:
            delta_time = appear_time - previous_appear_time
            if delta_time > fix_time:
                array.set_time_length(i, appear_time, 0)
                return font_size * i + 1
            else:
                if delta_time > best_bias:
                    best_bias = delta_time
                    best_row = i
    array.set_time_length(best_row, appear_time, 0)
    return font_size * best_row + 1


def get_str_len(text, fontSizeSet):
    from unicodedata import east_asian_width

    width = 0
    for char in text:
        if east_asian_width(char) in "WF":
            width += 2
        else:
            width += 1
    return width * fontSizeSet * 5 / 12


def format_time(seconds):
    """Convert seconds to ASS time format (H:MM:SS.cc)"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    centiseconds = int((seconds % 1) * 100)
    seconds = int(seconds)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


class DanmakuArray:
    def __init__(self, solution_x=1920, solution_y=1080, font_size=38):
        """
        Args:
            solution_x (int): resolution_x
            solution_y (int): resolution_y
            font_size (int): font_size
        """
        self.solution_x = solution_x
        self.solution_y = solution_y
        self.font_size = font_size
        self.rows = int(solution_y / font_size)
        self.time_length_array = [[-1, 0] for _ in range(self.rows)]

    def set_time_length(self, row, time, length):
        """Set time and length for a row"""
        if 0 <= row < self.rows:
            self.time_length_array[row] = [time, length]
        else:
            raise IndexError("Array index out of range")

    def get_time(self, row):
        """Get time for a row"""
        if 0 <= row < self.rows:
            return self.time_length_array[row][0]
        else:
            raise IndexError("Array index out of range")

    def get_length(self, row):
        """Get length for a row"""
        if 0 <= row < self.rows:
            return self.time_length_array[row][1]
        else:
            raise IndexError("Array index out of range")


def draw_danmaku(
    events: list[DanmakuEvent],
    resolution: tuple[int, int],
    font_size: int,
    roll_time: int | float,
    fix_time: int | float,
    displayarea: float = 0.5,
) -> list[DanmakuEvent]:
    display_height = int(resolution[1] * displayarea)

    roll_array = DanmakuArray(resolution[0], display_height, font_size)
    btm_array = DanmakuArray(resolution[0], display_height, font_size)

    for event in events:
        if event.style == "R2L":
            event.end_time = event.start_time + roll_time
            text_length = get_str_len(event.text, font_size)
            x1 = resolution[0] + int(text_length / 2)
            x2 = -int(text_length / 2)
            y = get_position_y(
                font_size,
                event.start_time,
                text_length,
                resolution[0],
                roll_time,
                roll_array,
            )
            event.move = (x1, y, x2, y)
        else:
            event.end_time = event.start_time + fix_time
            x = int(resolution[0] / 2)
            y = get_fixed_y(font_size, event.start_time, btm_array, fix_time)
            event.pos = (x, y)
    return events


def convert_dandanplay_json2danmaku_events(
    dandanplay_json: Path | list[dict] | dict,
    resolution: tuple[int, int] = (1920, 1080),
) -> list[DanmakuEvent]:
    def __get_timestamp(o):
        p = o.get("p")
        if not p:
            return 0
        timestamp, *_ = p.split(",", 1)
        return float(timestamp)

    if isinstance(dandanplay_json, Path):
        data = json.loads(dandanplay_json.read_text(encoding="utf-8"))
    else:
        data = dandanplay_json
    if isinstance(data, dict):
        danmaku_data = data["comments"]
    else:
        danmaku_data = data
    assert isinstance(danmaku_data, list)
    danmaku_data = sorted(danmaku_data, key=__get_timestamp)

    danmaku_set = set()
    events = []
    for danmaku in danmaku_data:
        p = danmaku.get("p")
        m = danmaku.get("m")
        if not (m and p):
            continue

        timestamp, mode, color, uid = p.split(",")

        if (m, timestamp) in danmaku_set:
            continue
        danmaku_set.add((m, timestamp))

        shift = float(danmaku.get("shift", 0))
        appear_time = float(timestamp) + shift

        color_hex = hex(int(color))
        color_reverse = "".join(
            reversed([color_hex[i : i + 2] for i in range(0, len(color_hex), 2)])
        )
        color_hex = color_reverse[:-2].ljust(6, "0").upper()
        color_text = f"\\c&H{color_hex}"

        style = "R2L" if mode == "1" else "TOP"

        events.append(
            DanmakuEvent(
                start_time=appear_time,
                end_time=0.0,
                style=style,
                text=m.strip().replace("\n", " "),
                pos=None,
                move=None,
                color=color_text,
            )
        )

    return draw_danmaku(
        events,
        resolution=resolution,
        font_size=config.danmaku.fontsize,
        roll_time=config.danmaku.scrolltime,
        fix_time=config.danmaku.fixtime,
        displayarea=config.danmaku.displayarea,
    )


def convert_dandanplay_json2ass_legacy(
    dandanplay_json: Path,
    ass_output: Path,
):
    raise NotImplementedError
    from sh import Command
    import shutil

    if not shutil.which(config.danmaku.danmaku_factory_path):
        logger.error(
            f"Can not find DanmakuFactory executable: {config.danmaku.danmaku_factory_path}"
        )
        exit(-1)

    danmaku_data_tmp_path = DATA_PATH / "danmaku_data_tmp.json"

    danmaku_factory = Command(config.danmaku.danmaku_factory_path).bake(
        o=str(ass_output),
        i=str(danmaku_data_tmp_path),
        t=0.0,
    )

    with open(dandanplay_json, "r", encoding="utf-8") as f:
        danmaku_data = json.load(f)

    danmaku_data_tmp = []
    for danmaku in danmaku_data["comments"]:
        p = danmaku.get("p")
        m = danmaku.get("m")
        shift = float(danmaku.get("shift", 0))
        if not (m and p):
            continue

        timestamp, mode, color, uid = p.split(",")
        timestamp = float(timestamp) + shift
        p = f"{timestamp},{color},{mode},25,,,"
        element = {"c": p, "m": m}
        danmaku_data_tmp.append(element)
    with danmaku_data_tmp_path.open("w", encoding="utf-8") as f:
        f.write("[\n")
        f.write(
            ",\n".join(
                json.dumps(e, ensure_ascii=False, separators=(",", ":"))
                for e in danmaku_data_tmp
            )
        )
        f.write("\n]" if danmaku_data_tmp else "]")

    danmaku_factory = danmaku_factory.bake(
        "--ignore-warnings",
        s=config.danmaku.scrolltime,
        N=config.danmaku.fontname,
        S=config.danmaku.fontsize,
        D=config.danmaku.shadow,
        B=str(config.danmaku.bold).upper(),
        d=config.danmaku.density,
        L=config.danmaku.outline,
    )
    logger.debug(danmaku_factory)
    danmaku_factory()


def generate_ass_events(ass_input: Path) -> str:
    def override_style(ass_event: str):
        ass_event = ass_event.replace(
            "{\\",
            f"{{\\rDefault\\fn{config.danmaku.fontname}"
            f"\\fs{config.danmaku.fontsize}"
            f"\\c&HFFFFFF&\\alpha&H{config.danmaku.transparency:02X}"
            f"\\bord{config.danmaku.outline}"
            f"\\shad{config.danmaku.shadow}"
            f"\\b{1 if config.danmaku.bold else 0}\\q2}}{{\\",
            count=1,
        )

    res = []
    for line in ass_input.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("Dialogue: "):
            res.append(override_style(line))
    return "\n".join(res)


def get_style_config():
    """style config for danmaku_render.lua"""
    return dict(
        fontname=config.danmaku.fontname,
        fontsize=config.danmaku.fontsize,
        shadow=config.danmaku.shadow,
        bold=config.danmaku.bold,
        displayarea=config.danmaku.displayarea,
        outline=config.danmaku.outline,
        transparency=config.danmaku.transparency,
        scrolltime=config.danmaku.scrolltime,
        fixtime=config.danmaku.fixtime,
    )
