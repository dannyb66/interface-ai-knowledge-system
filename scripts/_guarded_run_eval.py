#!/usr/bin/env python3
"""Run harness/run_eval.py with every network entry point blocked.

    python scripts/_guarded_run_eval.py <run_eval.py arguments>
    python scripts/_guarded_run_eval.py --self-test

The guard replaces socket.socket, socket.create_connection and socket.getaddrinfo, so a network call
raises RuntimeError("network call during grading") instead of silently working or hanging. The repo
root comes from this file's location, so the script behaves the same from any working directory.
Runs on Python 3.9 and newer.
"""
import runpy
import socket
import sys
from pathlib import Path

MESSAGE = "network call during grading"
RUN_EVAL = Path(__file__).resolve().parent.parent / "harness" / "run_eval.py"


def _blocked(*args, **kwargs):
    raise RuntimeError(MESSAGE)


class _BlockedSocket(socket.socket):
    """Stands in for socket.socket. A class rather than a function because ssl, http.client and
    asyncio subclass socket.socket when they are imported; a function there would raise TypeError
    at import time instead of the guard error."""

    def __new__(cls, *args, **kwargs):
        raise RuntimeError(MESSAGE)


def install_guard():
    socket.socket = _BlockedSocket
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked


def self_test():
    install_guard()
    try:
        socket.create_connection(("example.com", 80))
    except RuntimeError as exc:
        print("RuntimeError: %s" % exc)
        return 0 if str(exc) == MESSAGE else 1
    except Exception as exc:  # any other error means the guard did not intercept the call
        print("guard self-test FAILED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1
    print("guard self-test FAILED: socket.create_connection did not raise", file=sys.stderr)
    return 1


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    install_guard()
    runpy.run_path(str(RUN_EVAL), run_name="__main__")  # sys.argv[1:] is already the harness arguments
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
