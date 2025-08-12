import contextlib
import json
from pathlib import Path
from bgm.config import config
from bgm import DATA_PATH, logger


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
def get_fixed_y(font_size, appear_time, resolution_y, array):
    best_row = 0
    best_bias = -1
    for i in range(array.rows):
        previous_appear_time = array.get_time(i)
        if previous_appear_time < 0:
            array.set_time_length(i, appear_time, 0)
            return font_size * i + 1
        else:
            delta_time = appear_time - previous_appear_time
            if delta_time > 5:
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


def draw_normal_danmaku(
    ass_file,
    root,
    font_size,
    roll_array,
    btm_array,
    resolution_x,
    resolution_y,
    roll_time,
    fix_time,
):
    from dmconvert.utils import format_time, remove_emojis

    with open(ass_file, "a", encoding="utf-8") as f:
        # Convert each danmaku
        all_normal_danmaku = root.findall(".//d")
        for d in all_normal_danmaku:
            # Parse attributes
            p_attrs = d.get("p").split(",")
            appear_time = float(p_attrs[0])
            danmaku_type = int(p_attrs[1])

            # Convert color from decimal to hex
            color = int(p_attrs[3])
            color_hex = hex(color)
            color_reverse = "".join(
                reversed([color_hex[i : i + 2] for i in range(0, len(color_hex), 2)])
            )
            color_hex = color_reverse[:-2].ljust(6, "0").upper()  # Remove 0x
            color_text = f"\\c&H{color_hex}"

            # Format times
            start_time = format_time(appear_time)

            # Format text
            # text = remove_emojis(d.text, ".")
            text = d.text.strip()

            # For rolling danmakus (most common type)
            if danmaku_type == 1:
                layer = 0
                end_time = format_time(appear_time + roll_time)
                style = "R2L"
                text_length = get_str_len(
                    text, font_size
                )  # Estimate the length of the text
                x1 = resolution_x + int(text_length / 2)  # Start from right edge
                x2 = -int(text_length / 2)  # End at left edge
                y = get_position_y(
                    font_size,
                    appear_time,
                    text_length,
                    resolution_x,
                    roll_time,
                    roll_array,
                )
                effect = f"\\move({x1},{y},{x2},{y})"

            # For BTM danmakus
            else:
                layer = 1
                end_time = format_time(appear_time + fix_time)
                style = "TOP"
                x = int(resolution_x / 2)
                y = get_fixed_y(font_size, appear_time, resolution_y, btm_array)
                effect = f"\\pos({x},{y})"

            line = f"Dialogue: {layer},{start_time},{end_time},{style},,0000,0000,0000,,{{{effect}}}{{{color_text}}}{text}\n"
            f.write(line)


def convert_dandanplay_json2ass_pylib(
    dandanplay_json: Path,
    output_file: Path,
    font_size: int,
    resolution: tuple[int, int],
):
    from dmconvert.header.header import draw_ass_header
    from dmconvert.normal.normal_handler import DanmakuArray
    import xml.etree.ElementTree as ET

    with open(dandanplay_json, "r", encoding="utf-8") as f:
        danmaku_data = json.load(f)

        def __get_timestamp(o):
            p = o.get("p")
            if not p:
                return 0
            # timestamp, mode, *_ = p.split(",", 2)
            # return (int(mode), float(timestamp))
            timestamp, *_ = p.split(",", 1)
            return float(timestamp)

        danmaku_data["comments"] = sorted(danmaku_data["comments"], key=__get_timestamp)

    root = ET.Element("i")

    for danmaku in danmaku_data["comments"]:
        p = danmaku.get("p")
        m = danmaku.get("m")
        shift = float(danmaku.get("shift", 0))
        if not (m and p):
            continue

        timestamp, mode, color, uid = p.split(",")
        timestamp = float(timestamp) + shift
        p = f"{timestamp},{mode},25,{color},,,,"
        element = ET.SubElement(
            root, "d", {"p": p, "uid": str(abs(hash(uid))), "user": uid}
        )
        element.text = m

    draw_ass_header(
        output_file,
        resolution_x=resolution[0],
        resolution_y=resolution[1],
        font_size=font_size,
        sc_font_size=font_size,
    )

    # with contextlib.redirect_stdout(None):
    draw_normal_danmaku(
        output_file,
        root=root,
        font_size=font_size,
        roll_array=DanmakuArray(*resolution, font_size),
        btm_array=DanmakuArray(*resolution, font_size),
        resolution_x=resolution[0],
        resolution_y=resolution[1],
        roll_time=config.danmaku.scrolltime,
        fix_time=5,
    )


def convert_dandanplay_json2ass_legacy(
    dandanplay_json: Path,
    ass_output: Path,
):
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


convert_dandanplay_json2ass = (
    convert_dandanplay_json2ass_legacy
    if config.danmaku.danmaku_engine == "DanmakuFactory"
    else lambda i, o: convert_dandanplay_json2ass_pylib(i, o, 36, (1920, 1080))
)


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
    )
