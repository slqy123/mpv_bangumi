import random
import click
import toml
from bgm import CONFIG_PATH, logger
from pathlib import Path
from pydantic import BaseModel, DirectoryPath
from dotenv import load_dotenv
from io import StringIO
import os


class DanmakuConfig(BaseModel):
    danmaku_factory_path: str = "DanmakuFactory"
    scrolltime: int = 15
    fontname: str = "sans-serif"
    fontsize: int = 50
    font_size_strict: bool = False
    shadow: int = 0
    bold: bool = True
    density: float = 0.0
    displayarea: float = 0.85
    outline: float = 1.0
    blockmode: str = ""
    blacklist_path: str = ""
    transparency: int = 0x30


class Config(BaseModel):
    storages: list[DirectoryPath]
    danmaku: DanmakuConfig


def init_config():
    """Initialize the config file."""
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    config_file = CONFIG_PATH / "config.toml"
    access_token = click.prompt(
        "Please enter your access token(You can get a new token from https://next.bgm.tv/demo/access-token)",
        type=str,
    ).strip()
    storage = click.prompt("Please enter your bangumi storage path", type=Path).strip()
    click.echo(
        "You can download DanmakuFactory from https://github.com/hihkm/DanmakuFactory/actions/runs/15092837913"
    )
    danmaku_factory_path = click.prompt(
        "Please enter your danmaku factory path, or skip if you have installed globally",
        default="DanmakuFactory",
        type=str,
    ).strip()

    with open(config_file, "w", encoding="utf-8") as f:
        toml.dump(
            {
                "storages": [str(storage)],
                "danmaku": {"danmaku_factory_path": danmaku_factory_path},
            },
            f,
        )
    with open(CONFIG_PATH / ".env", "w", encoding="utf-8") as f:
        f.write(f"BGM_ACCESS_TOKEN={access_token}\n")


config_file = CONFIG_PATH / "config.toml"
env_file = CONFIG_PATH / ".env"
if not config_file.exists():
    logger.warning(f"Config file {config_file} does not exist.")
    init_config()
    assert config_file.exists()

# Load environment variables from .env file
if env_file.exists():
    env_str = env_file.read_text()
    logger.debug(f"Loading environment variables from {env_file}:\n{env_str}")
    env_stream = StringIO(env_str)

    # Load the environment variables
    load_dotenv(stream=env_stream, override=False)
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
