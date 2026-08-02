import logging
import os
from io import StringIO
from pathlib import Path
from typing import Any

from appdirs import user_config_dir, user_data_dir
from dotenv import load_dotenv

CONFIG_PATH = Path(user_config_dir(__name__))
DATA_PATH = Path(user_data_dir(__name__))

CONFIG_PATH.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)

# Load .env before any bgm.* submodule import: bgm.api reads BGM_ACCESS_TOKEN
# from os.environ at class-definition time, so this must not depend on the
# (alphabetic) import order of bgm submodules.
env_file = CONFIG_PATH / ".env"
if env_file.exists():
    load_dotenv(stream=StringIO(env_file.read_text(encoding="utf-8")), override=False)

LOG_LEVEL = (
    logging.INFO if os.environ.get("BGM_DEBUG") in (None, "0") else logging.DEBUG
)

NOTIFY_LEVEL_NUM = 50
logging.addLevelName(NOTIFY_LEVEL_NUM, "NOTIFY")

class CustomLogger(logging.Logger):
    def notify(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a message with severity 'TRACE'."""
        if self.isEnabledFor(NOTIFY_LEVEL_NUM):
            self._log(NOTIFY_LEVEL_NUM, message, args, **kwargs)

logging.setLoggerClass(CustomLogger)
logger: CustomLogger = logging.getLogger(__name__)  # type: ignore[assignment]
logger.setLevel(LOG_LEVEL)
