import os
import random
import sys
from pathlib import Path
from typing import Literal

import click
import toml
from pydantic import BaseModel, DirectoryPath

from bgm import CONFIG_PATH, logger


class DanmakuConfig(BaseModel):
    danmaku_factory_path: str = "DanmakuFactory"
    danmaku_engine: Literal["DanmakuFactory", "dmconvert"] = "dmconvert"
    scrolltime: int = 15
    fixtime: int = 8
    fontname: str = "sans-serif"
    fontsize: int = 36
    shadow: int = 0
    bold: bool = True
    displayarea: float = 0.5
    outline: float = 1.0
    transparency: int = 0x30


class LLMConfig(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


class Config(BaseModel):
    storages: list[DirectoryPath]
    danmaku: DanmakuConfig
    llm: LLMConfig | None = None


def init_config():
    """Initialize the config file."""
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    config_file = CONFIG_PATH / "config.toml"
    access_token = click.prompt(
        "请输入bangumi access token (可从此处获取：https://next.bgm.tv/demo/access-token)",
        type=str,
    ).strip()
    storage: Path = click.prompt(
        "请输入番剧的存储目录（插件仅会在该目录下激活）", type=Path
    )
    # click.echo(
    #     "You can download DanmakuFactory from https://github.com/hihkm/DanmakuFactory/actions/runs/15092837913"
    # )
    # danmaku_factory_path = click.prompt(
    #     "Please enter your danmaku factory path, or skip if you have installed globally",
    #     default="DanmakuFactory",
    #     type=str,
    # ).strip()
    fontname = click.prompt(
        "请输入弹幕字体名称",
        default="sans-serif",
        type=str,
    ).strip()

    with open(config_file, "w", encoding="utf-8") as f:
        toml.dump(
            {
                "storages": [str(storage)],
                "danmaku": {"fontname": fontname},
            },
            f,
        )
    with open(CONFIG_PATH / ".env", "w", encoding="utf-8") as f:
        f.write(f"BGM_ACCESS_TOKEN={access_token}\n")


config_file = CONFIG_PATH / "config.toml"
if not config_file.exists():
    logger.warning(f"Config file {config_file} does not exist.")
    init_config()
    assert config_file.exists()
    sys.exit(0)

assert "BGM_ACCESS_TOKEN" in os.environ
if not ("DANDANPLAY_APPID" in os.environ and "DANDANPLAY_APPSECRET" in os.environ):
    logger.debug("Using default DandanPlay appid and appsecret.")
    os.environ["DANDANPLAY_APPID"] = "3tm7ddc5gh"
    old_seed = random.getstate()
    random.seed(6174)
    b = random.randbytes(32)
    random.setstate(old_seed)
    res = bytes(
        map(
            lambda _, __: _ ^ __,
            "Z¾¶ä§Èþ8¿yì\x8dvëÂ]Ðs^ã£[\x82\x131QÝuÙ\x18Nû".encode("latin-1"),
            b,
        )
    ).decode("utf-8")
    os.environ["DANDANPLAY_APPSECRET"] = res

config = Config.model_validate(
    toml.load(config_file),
)
logger.debug(f"Config loaded: {config}")
