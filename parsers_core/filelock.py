# -*- coding: utf-8 -*-
import contextlib
import os
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class LockTimeout(Exception):
    pass


def _try_lock(fh):
    if os.name == "nt":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fh):
    if os.name == "nt":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def locked(path, timeout=60.0, poll=0.1):
    """Блокировка файла между процессами через соседний path.lock."""
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    fh = open(lock_path, "a+")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                _try_lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"не удалось получить блокировку {lock_path} за {timeout} с")
                time.sleep(poll)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()
