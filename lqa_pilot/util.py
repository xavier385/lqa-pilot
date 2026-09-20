from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


class PilotError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def digest(data):
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def executable(kind, explicit=None):
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p.resolve())
        raise PilotError(f"Eseguibile {kind} non trovato: {explicit}")
    found = shutil.which(kind)
    if found:
        return found
    if kind == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass
    if kind == "codex":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        candidates = list((root / "OpenAI/Codex/bin").glob("*/codex.exe"))
    elif kind == "adb":
        root = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        candidates = list((root / "Netease/MuMuPlayer").glob("nx_main/adb.exe"))
        if os.name == "nt":
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for keypath in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                    try:
                        with winreg.OpenKey(hive, keypath) as registry:
                            for i in range(winreg.QueryInfoKey(registry)[0]):
                                with winreg.OpenKey(registry, winreg.EnumKey(registry, i)) as product:
                                    try:
                                        name = winreg.QueryValueEx(product, "DisplayName")[0]
                                        location = winreg.QueryValueEx(product, "InstallLocation")[0]
                                        if "mumu" in str(name).lower():
                                            for relative in ("nx_main/adb.exe", "adb.exe"):
                                                candidate = Path(location)/relative
                                                if candidate.is_file():
                                                    candidates.append(candidate)
                                    except OSError:
                                        continue
                    except OSError:
                        continue
    else:
        candidates = []
    if candidates:
        return str(max(candidates, key=lambda p: p.stat().st_mtime))
    raise PilotError(f"{kind} non trovato. Configurare il percorso nel progetto.")


def process(args, *, timeout=30, data=None, env=None, cwd=None):
    """No host shell; UTF-8 and raw PNG bytes survive Windows pipelines."""
    try:
        result = subprocess.run(
            list(map(str, args)), input=data, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, env=env, cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PilotError(f"Processo non riuscito ({Path(str(args[0])).name}): {e}") from e
    if result.returncode:
        # Do not include environment, auth files or entire model prompts in errors.
        error = result.stderr.decode("utf-8", "replace")[-1800:]
        raise PilotError(f"{Path(str(args[0])).name}: codice {result.returncode}: {error}")
    return result


class FileLock:
    """OS advisory lock, automatically released even after a crashed process."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            self.file.close()
            raise PilotError("Un altro bot sta già usando questa macchina/run.") from e
        return self

    def __exit__(self, *args):
        self.file.close()


def resolve_input(root, value):
    p = (Path(root) / value).resolve()
    if not p.is_file():
        raise PilotError(f"Materiale mancante: {p}")
    return p
