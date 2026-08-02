import json
import logging
import os
import sys
import threading
import traceback

import portalocker
from python_mpv_jsonipc import MPV

from bgm import LOG_LEVEL
from bgm.mpvbangumi import MPVBangumi


def exception_hook(args):
    if LOG_LEVEL <= logging.DEBUG:
        traceback.print_exception(
            args.exc_type, args.exc_value, args.exc_traceback, file=sys.stdout
        )
    sys.exit(0)
threading.excepthook = exception_hook

if LOG_LEVEL > logging.DEBUG:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115 -- process-lifetime redirect

ipc_socket = sys.argv[1]
if sys.platform == "win32":
    portalocker.portalocker.LOCKER = portalocker.portalocker.Win32Locker
    assert ipc_socket.startswith("\\\\.\\pipe\\")
    ipc_socket = ipc_socket.replace("\\\\.\\pipe\\", "", count=1)

# Set when the mpv side disconnects (mpv exited / crashed / closed the IPC socket).
# The library invokes quit_callback from its socket-reader thread; we must not
# exit() there because SystemExit in a non-main thread only kills that thread.
shutdown_event = threading.Event()

mpv = MPV(
    start_mpv=False,
    ipc_socket=ipc_socket,
    quit_callback=lambda *_: shutdown_event.set(),
)
bgm = MPVBangumi(mpv)


@mpv.property_observer("user-data/mpv_bangumi/dispatch")
def dispatch(name: str, value: str):
    if not value:
        return
    info = json.loads(value)
    action = info["action"]
    data = info["data"]
    del value, info

    bgm.send_action(action, data)


def main():
    bgm.resp_message("ready", {"ok": True})
    shutdown_event.wait()
    bgm.close()
    if sys.platform != "win32":
        try:
            # mpv exits without running Lua's shutdown handler (e.g. SIGKILL),
            # leaving the IPC socket file behind; clean it up here.
            os.remove(ipc_socket)
        except OSError:
            pass
