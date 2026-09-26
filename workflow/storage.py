"""Atomic checkpoints and a conservative single-writer lock per batch."""
from contextlib import contextmanager
import ctypes
import ctypes.wintypes
from pathlib import Path
import json
import os
import tempfile
import time


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def lock_owner_is_alive(path):
    """Return whether a PID-backed marker still belongs to a live process.

    ``batch_lock`` is intentionally a visible marker so interrupted work can
    be diagnosed, but a marker left by a crashed process must not make a task
    permanently unrecoverable after restart.  Malformed or unreadable markers
    remain conservative and are treated as active.
    """
    try:
        owner = int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    if owner <= 0:
        return True
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, owner)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        if ctypes.get_last_error() in (87, 1168):
            return False
        return True
    try:
        os.kill(owner, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        # Windows reports a missing/invalid process for os.kill(pid, 0) as
        # ERROR_INVALID_PARAMETER instead of ProcessLookupError.
        if getattr(exc, "winerror", None) in (87, 128):
            return False
        return True
    return True


def lock_is_active(path):
    """Read-only lock status used by recovery inspection."""
    return Path(path).exists() and lock_owner_is_alive(path)


@contextmanager
def batch_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if not lock_owner_is_alive(path):
            # The marker is not task history; reclaiming an ownerless marker
            # lets the durable per-student checkpoint drive recovery.
            try:
                path.unlink()
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except (FileNotFoundError, PermissionError, OSError):
                raise RuntimeError(f"Batch locked: {path}. If a process crashed, verify it has stopped before removing this lock.") from None
        else:
            raise RuntimeError(f"Batch locked: {path}. If a process crashed, verify it has stopped before removing this lock.") from None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def exclusive_lock(path):
    """Wait for an OS-released advisory lock that survives app restarts safely."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
