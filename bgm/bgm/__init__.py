from appdirs import user_config_dir, user_data_dir
from pathlib import Path
import logging
from rich.logging import RichHandler
from rich.console import Console
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

CONFIG_PATH = Path(user_config_dir(__name__))
DATA_PATH = Path(user_data_dir(__name__))

CONFIG_PATH.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = (
    logging.INFO if os.environ.get("BGM_DEBUG") in (None, "0") else logging.DEBUG
)
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)
logger.addHandler(RichHandler(LOG_LEVEL, Console(stderr=True), show_path=False))
