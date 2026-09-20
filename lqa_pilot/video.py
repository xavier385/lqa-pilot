"""Native Android recording, one MP4 per case; no LQA model calls."""
import json
import shlex
import shutil
import subprocess
import threading
import time
import uuid
import queue
from pathlib import Path

from .util import PilotError, executable, now, process, write_json


class CaseRecorder:
    def __init__(self, driver, folder, case_id, frame, config=None):
        self.driver, self.folder, self.case_id = driver, Path(folder), case_id
        self.config = config or {}
        self.ffmpeg = executable("ffmpeg", self.config.get("ffmpeg"))
        self.target = self.folder/"videos"/(case_id+".mp4")
        self.parts = self.folder/"videos"/"segments"/(case_id+"-"+uuid.uuid4().hex[:10])
        self.parts.mkdir(parents=True, exist_ok=True)
        longest = int(self.config.get("max_dimension", 1920))
        if (longest != 0 and longest < 320) or int(self.config.get("bit_rate", 8000000)) <= 0:
            raise PilotError("Video: max_dimension deve essere 0 o almeno 320; bit_rate deve essere positivo")
        scale = min(1, longest/max(frame["width"], frame["height"])) if longest else 1
        self.size = tuple(max(2, int(frame[k]*scale)//2*2) for k in ("width", "height"))
        self.lock = threading.RLock()
        self.ready, self.halt = threading.Event(), threading.Event()
        self.error, self.proc, self.remote_pid, self.remote = None, None, None, None
        self.segments, self.gaps = [], []
        self.started_at, self.begun = now(), 0
        self.thread = None

    def start(self):
        # Fail before sending game input if the old codec/size cannot be reused.
        prior = self.target.with_suffix(".json")
        if self.target.exists():
            if not prior.is_file():
                raise PilotError("Video esistente senza manifest: usare una nuova run")
            previous = json.loads(prior.read_text(encoding="utf-8"))
            self.size = tuple(previous["size"])
        self.thread = threading.Thread(target=self._worker, daemon=True, name="lqa-screenrecord")
        self.thread.start()
        if not self.ready.wait(15):
            self.halt.set()
            raise PilotError("Registrazione Android non avviata entro 15 secondi")
        if self.error:
            raise PilotError(self.error)

    def _signal(self):
        if self.proc and self.proc.poll() is None and self.remote_pid:
            # Signal only our known recorder, never another screenrecord process.
            cmd = self.driver.adb("shell", "cat", f"/proc/{self.remote_pid}/cmdline", timeout=5)
            if b"screenrecord" in cmd and self.remote.encode() in cmd:
                self.driver.adb("shell", "kill", "-2", str(self.remote_pid), timeout=5)

    def _begin(self, number):
        self.remote = f"/sdcard/lqa-{uuid.uuid4().hex}.mp4"
        args = ["screenrecord", "--time-limit", "180", "--bit-rate", str(int(self.config.get("bit_rate", 8000000))),
                "--size", f"{self.size[0]}x{self.size[1]}", self.remote]
        # $$ belongs to this shell, preserved by exec. No PID guessing/pidof.
        command = "echo $$; exec " + shlex.join(args)
        self.proc = subprocess.Popen([self.driver.exe, "-s", self.driver.serial, "shell", command],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = queue.Queue()
        def read_pid():
            try:
                output.put(self.proc.stdout.readline())
            except OSError:
                output.put(b"")
        threading.Thread(target=read_pid, daemon=True).start()
        try:
            line = output.get(timeout=10).decode("ascii", "replace").strip()
        except queue.Empty:
            self.proc.terminate()
            raise PilotError("Android recorder did not return its PID within 10 seconds")
        if not line.isdigit():
            raise PilotError("Impossibile identificare il processo di registrazione Android")
        self.remote_pid = int(line)
        time.sleep(.7)
        if self.proc.poll() is not None:
            raise PilotError("screenrecord non supportato o dimensione video non valida")
        self.begun = time.monotonic()
        self.ready.set()

    def _finish_segment(self, number):
        self._signal()
        try:
            self.proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            raise PilotError("screenrecord non si è chiuso correttamente; segmento conservato sul dispositivo")
        local = self.parts/f"{number:04d}.mp4"
        self.driver.adb("pull", self.remote, str(local), timeout=60)
        if not local.exists() or local.stat().st_size < 1024:
            raise PilotError("Segmento video vuoto o incompleto")
        self.segments.append({"path": str(local), "started_offset_seconds": self.begun-self.origin,
                              "ended_offset_seconds": time.monotonic()-self.origin})
        # Remove only this generated temporary file after a successful pull.
        self.driver.adb("shell", "rm", "-f", self.remote, timeout=5)
        self.remote_pid = None
        self.proc.stdout.close()

    def _worker(self):
        self.origin = time.monotonic()
        try:
            number = 1
            with self.lock:
                self._begin(number)
            while True:
                while not self.halt.wait(.2) and time.monotonic()-self.begun < 90:
                    if self.proc.poll() is not None:
                        raise PilotError("Registrazione Android terminata inaspettatamente")
                with self.lock:
                    self.ready.clear()
                    gap_start = time.monotonic()-self.origin
                    self._finish_segment(number)
                    if self.halt.is_set():
                        break
                    number += 1
                    self._begin(number)
                    self.gaps.append({"start_seconds": gap_start, "end_seconds": time.monotonic()-self.origin})
        except (PilotError, OSError, ValueError) as error:
            self.error = str(error)
            self.halt.set()
            try:
                self._signal()
            except (PilotError, OSError):
                pass
        finally:
            self.ready.set()

    def perform(self, operation):
        with self.lock:
            if self.error or not self.ready.is_set() or self.halt.is_set() or self.proc.poll() is not None:
                raise PilotError(self.error or "Recording is not active; no game input sent")
            return operation()

    def stop(self):
        self.halt.set()
        if self.thread:
            self.thread.join(timeout=85)
            if self.thread.is_alive():
                raise PilotError("Recorder shutdown timed out; no complete video claimed")
        if not self.segments:
            raise PilotError(self.error or "No video segment saved")
        inputs = [Path(s["path"]) for s in self.segments]
        previous = None
        if self.target.exists():
            previous = self.parts/"previous.mp4"
            shutil.copy2(self.target, previous)
            inputs.insert(0, previous)
        listing = self.parts/"concat.txt"
        listing.write_text("".join("file '"+p.resolve().as_posix().replace("'", "'\\''")+"'\n" for p in inputs), encoding="utf-8")
        staged = self.parts/"joined.mp4"
        process([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                 "-map", "0:v:0", "-c:v", "copy", "-an", "-movflags", "+faststart", staged], timeout=120)
        if not staged.is_file() or staged.stat().st_size < 1024:
            raise PilotError("No playable merged video produced")
        staged.replace(self.target)
        result = {"path": self.target.relative_to(self.folder).as_posix(), "size": list(self.size),
                  "started_at": self.started_at, "finished_at": now(), "audio": False,
                  "resumed_previous_video": bool(previous), "segment_count": len(self.segments),
                  "recording_gaps": self.gaps, "error": self.error,
                  "note": "Short encoder rollover gaps are logged; game inputs are paused during rollover. No LQA analysis."}
        if self.error:
            # Keep the playable partial result, but never certify completion.
            result["partial"] = True
        write_json(self.target.with_suffix(".json"), result)
        return result


def export_manifest(folder, run):
    records = []
    for case in run["project"]["cases"]:
        r = run["cases"].get(case["id"], {})
        records.append({"case_id": case["id"], "objective": case["objective"], "journey": case["journey"],
                        "status": r.get("status", "INCOMPLETE"), "video": r.get("video"), "reason": r.get("blocker", "")})
    target = Path(folder)/"videos.json"
    write_json(target, {"mode": "video", "lqa_performed": False, "cases": records})
    return target
