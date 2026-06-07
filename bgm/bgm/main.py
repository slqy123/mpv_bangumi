import logging
import sys
from python_mpv_jsonipc import MPV
from bgm.mpvbangumi import MPVBangumi
from bgm import LOG_LEVEL
import json
import threading
import traceback
import portalocker


def exception_hook(args):
    if LOG_LEVEL <= logging.DEBUG:
        traceback.print_exception(
            args.exc_type, args.exc_value, args.exc_traceback, file=sys.stdout
        )
    exit(0)
threading.excepthook = exception_hook

if LOG_LEVEL > logging.DEBUG:
    import os

    sys.stderr = open(os.devnull, "w")

ipc_socket = sys.argv[1]
if sys.platform == "win32":
    portalocker.portalocker.LOCKER = portalocker.portalocker.Win32Locker
    assert ipc_socket.startswith("\\\\.\\pipe\\")
    ipc_socket = ipc_socket.replace("\\\\.\\pipe\\", "", count=1)

mpv = MPV(start_mpv=False, ipc_socket=ipc_socket, quit_callback=lambda *_: exit(0))
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
    try:
        while True:
            mpv.wait_for_property("duration")
    except Exception:
        if LOG_LEVEL <= logging.DEBUG:
            traceback.print_exc()
        exit(0)
