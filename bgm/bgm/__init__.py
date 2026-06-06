from appdirs import user_config_dir, user_data_dir
from pathlib import Path
import logging
from typing import Any
import os

CONFIG_PATH = Path(user_config_dir(__name__))
DATA_PATH = Path(user_data_dir(__name__))

CONFIG_PATH.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)

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
