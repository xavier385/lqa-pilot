from __future__ import annotations

import io
import math
import re
import shlex
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .util import PilotError, digest, executable, now, process, read_json


def visual_distance(a, b, region=None):
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return 1.0
        if region:
            ia, ib = ia.crop(region), ib.crop(region)
        ia = ia.convert("RGB").resize((64, 64))
        ib = ib.convert("RGB").resize((64, 64))
        return sum(ImageStat.Stat(ImageChops.difference(ia, ib)).mean) / (3 * 255)


def validate_action(action, allow_game_progress=False, allow_required_terms=False):
    allowed = {"tap", "swipe", "long_press", "back", "wait", "type_text", "inspect", "finish", "blocked"}
    if action.get("kind") not in allowed:
        raise PilotError("Azione non supportata")
    for key in ("x", "y", "x2", "y2"):
        value = action.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise PilotError(f"Coordinata normalizzata fuori intervallo: {key}")
    duration = action.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration <= 5000:
        raise PilotError("Durata azione fuori intervallo (0–5000 ms)")
    allowed_risks = {"navigation"} | ({"required_terms"} if allow_required_terms else set()) | ({"game_progress"} if allow_game_progress else set())
    if action.get('risk')=='required_terms' and (action['kind']!='tap' or re.search(r'optional|marketing|personaliz|personalisi|advertis|werbung|analytics',action.get('target',''),re.I)):
        raise PilotError('Consentiti soltanto i termini obbligatori del gioco; consensi facoltativi esclusi')
    if action["kind"] not in {"blocked", "finish", "inspect"} and action.get("risk") not in allowed_risks:
        raise PilotError(f"Azione non autorizzata dalla policy: {action.get('risk')}")
    if action["kind"] in {"tap", "long_press"} and re.search(r"agree to all|accept all|allen zustimmen|accetta tutto|consenti tutto", action.get("target", ""), re.I):
        raise PilotError("Consenso globale bloccato: selezionare solo condizioni obbligatorie, mantenendo esclusi i consensi facoltativi.")
    if action["kind"] == "type_text":
        # Android input text does not reliably inject Unicode; do not silently lose characters.
        text = action.get("text", "")
        if not text or len(text) > 200 or not text.isascii() or any(ord(c) < 32 for c in text):
            raise PilotError("Inserimento supportato: testo ASCII, massimo 200 caratteri. Unicode richiede un IME dedicato.")
    return action


class Android:
    def __init__(self, config, diagnostics=None):
        self.config = config
        self.trace = diagnostics or (lambda *args, **kwargs: None)
        self.trace('adb.resolve', explicit=bool(config.get('adb')))
        self.exe = executable("adb", config.get("adb"))
        self.trace('adb.executable', path=self.exe)
        self.serial = config.get("serial", "auto")
        self.package = config.get("package", "")
        self.user = None
        if self.package and not re.fullmatch(r"[a-zA-Z][\w]*(?:\.[\w]+)+", self.package):
            raise PilotError("Package Android non valido")

    def adb(self, *args, timeout=30, device=True):
        prefix = [self.exe] + (["-s", self.serial] if device else [])
        return process(prefix + list(args), timeout=timeout).stdout

    def connect(self):
        self.trace('adb.connect.begin', requested_serial=self.serial, endpoint=self.config.get('endpoint','auto'))
        raw = self.adb("devices", "-l", device=False).decode("utf-8", "replace")
        self.trace('adb.devices', output=raw)
        devices = [line.split()[0] for line in raw.splitlines() if re.match(r"^\S+\s+device\b", line)]
        if self.config.get('endpoint'):
            endpoint=self.config['endpoint']
            if not re.fullmatch(r'127\.0\.0\.1:\d{1,5}',endpoint) or not 1<=int(endpoint.rsplit(':',1)[1])<=65535:
                raise PilotError('Indicare una porta ADB locale valida (1–65535)')
            reply=self.adb('connect',endpoint,device=False).decode('utf-8','replace')
            self.trace('adb.endpoint.result', endpoint=endpoint, output=reply)
            raw=self.adb('devices','-l',device=False).decode('utf-8','replace')
            self.trace('adb.devices',output=raw)
            devices=[line.split()[0] for line in raw.splitlines() if re.match(r'^\S+\s+device\b',line)]
            if self.serial=='auto': self.serial=endpoint
        elif not devices:
            import socket
            import os
            endpoints = []
            # MuMu chooses ports per VM; discover active local endpoints, never assume 16384.
            roots = {Path(self.exe).parent.parent, Path(os.environ.get("ProgramFiles", "C:/Program Files"))/"Netease/MuMuPlayer"}
            configs = {p for root in roots for p in (root/"vms").glob("*/configs/vm_config.json")}
            self.trace('mumu.config.search',roots=sorted(str(r) for r in roots),files=sorted(str(p) for p in configs))
            for config_file in sorted(configs):
                try: config = read_json(config_file)
                except (OSError,ValueError) as e:
                    self.trace('mumu.config.error',path=config_file,error=str(e));continue
                def ports(value):
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if re.sub(r'[^a-z]','',key.lower()) in {"adbhostport", "adbport"}:
                                yield child
                            elif key.lower()=='adb' and isinstance(child,dict):
                                for port_key,port_value in child.items():
                                    if re.sub(r'[^a-z]','',port_key.lower())=='hostport':yield port_value
                            else:
                                yield from ports(child)
                    elif isinstance(value, list):
                        for child in value:
                            yield from ports(child)
                for port in ports(config):
                    self.trace('mumu.port.probe',path=config_file,port=port)
                    try:
                        with socket.create_connection(("127.0.0.1", int(port)), timeout=.2):
                            endpoints.append(f"127.0.0.1:{int(port)}")
                            self.trace('mumu.port.open',port=port)
                    except (OSError, ValueError, TypeError, OverflowError) as e:
                        self.trace('mumu.port.unavailable',port=port,error=str(e))
                        continue
            endpoints = sorted(set(endpoints))
            self.trace('mumu.endpoints',endpoints=endpoints)
            if len(endpoints) == 1:
                reply=self.adb("connect", endpoints[0], device=False).decode('utf-8','replace')
                self.trace('adb.endpoint.result',endpoint=endpoints[0],output=reply)
                raw = self.adb("devices", "-l", device=False).decode("utf-8", "replace")
                self.trace('adb.devices',output=raw)
                devices = [line.split()[0] for line in raw.splitlines() if re.match(r"^\S+\s+device\b", line)]
        if not devices:
            self.trace('adb.no_device',output=raw)
            if re.search(r'\sunauthorized\b',raw):
                raise PilotError('Android non autorizzato: accettare il debug ADB nell’emulatore e riprovare. Dettagli in Diagnostica.')
            if re.search(r'\soffline\b',raw):
                raise PilotError('Android rilevato ma offline: attendere l’avvio completo di MuMu e riprovare. Dettagli in Diagnostica.')
            raise PilotError('Nessun dispositivo Android collegato. Avviare la VM MuMu e abilitare ADB nelle sue impostazioni. Se il rilevamento automatico fallisce, inserire la porta ADB in Opzioni collegamento. Dettagli in Diagnostica.')
        if self.serial == "auto":
            if len(devices) != 1:
                raise PilotError(f"Più dispositivi Android: {devices}. Indicare il serial in Opzioni collegamento.")
            self.serial = devices[0]
        if self.serial not in devices:
            raise PilotError(f"Dispositivo non connesso: {self.serial}. Avviare MuMu e abilitare ADB.")
        self.trace('adb.connected',serial=self.serial)
        return self.serial

    def foreground(self):
        text = self.adb("shell", "dumpsys", "window").decode("utf-8", "replace")
        match = re.search(r"mCurrentFocus=Window\{[^\n]*?\s([a-zA-Z][\w.]*)/", text)
        return match.group(1) if match else ""

    def info(self):
        info = {"package": self.package, "serial": self.serial}
        for key, prop in (("android_version", "ro.build.version.release"), ("device_model", "ro.product.model"), ("system_locale", "persist.sys.locale")):
            info[key] = self.adb("shell", "getprop", prop).decode("utf-8", "replace").strip()
        dump = self.adb("shell", "dumpsys", "package", self.package).decode("utf-8", "replace")
        for key in ("versionName", "versionCode"):
            match = re.search(re.escape(key) + r"=([^\s]+)", dump)
            info[key] = match.group(1) if match else "unknown"
        return info

    def prepare_launch(self):
        """Find a launcher icon without opening the game or consuming a model call."""
        self._launch_tap=None
        name=self.config.get('game_name','').strip()
        if not self.package and re.fullmatch(r'[a-zA-Z][\w]*(?:\.[\w]+)+',name):self.package=name
        if self.package:
            if not self.adb('shell','pm','path',self.package).strip():
                users=re.findall(r'UserInfo\{(\d+):',self.adb('shell','pm','list','users').decode('utf-8','replace'))
                matches=[u for u in users if self.adb('shell','pm','path','--user',u,self.package).strip().startswith(b'package:')]
                if len(matches)!=1:raise PilotError('Gioco non installato o presente in più profili: usare il nome dell’icona nel launcher')
                self.user=matches[0]
            self.adb('shell','am','force-stop',*(['--user',self.user] if self.user else []),self.package)
            return
        if not name:raise PilotError('Indicare il nome del gioco da aprire')
        normalized=lambda s:''.join(c for c in unicodedata.normalize('NFKC',s).casefold() if c.isalnum())
        self.adb('shell','input','keyevent','3');time.sleep(.5)
        self._launcher_package=self.foreground()
        seen=set()
        for page in range(12):
            if self.foreground()!=self._launcher_package:raise PilotError('Launcher Android cambiato durante la ricerca del gioco')
            self.adb('shell','uiautomator','dump','/sdcard/lqa-launcher.xml')
            raw=self.adb('shell','cat','/sdcard/lqa-launcher.xml').decode('utf-8','replace')
            nodes=ET.fromstring(raw).iter('node');matches=[];labels=[];width=height=0
            for node in nodes:
                bounds=[int(n) for n in re.findall(r'\d+',node.get('bounds',''))]
                if len(bounds)!=4:continue
                x1,y1,x2,y2=bounds;width=max(width,x2);height=max(height,y2)
                texts={node.get('text',''),node.get('content-desc','')};labels.extend(t for t in texts if t)
                if any(normalized(t)==normalized(name) or (len(normalized(t))>=8 and normalized(name).startswith(normalized(t))) for t in texts) and x2>x1 and y2>y1:
                    matches.append(((x1+x2)//2,(y1+y2)//2))
            matches=list(dict.fromkeys(matches))
            if len(matches)>1:raise PilotError('Più icone con questo nome: indicare il package Android esatto')
            if matches:self._launch_tap=matches[0];return
            signature=tuple(sorted(labels))
            if signature in seen:break
            seen.add(signature)
            if not width or not height:break
            self.adb('shell','input','swipe',str(int(width*.85)),str(height//2),str(int(width*.15)),str(height//2),'350');time.sleep(.4)
        raise PilotError('Gioco non trovato nel launcher: usare il nome esatto sotto l’icona o il package Android. Non aprire il gioco manualmente.')

    def launch(self):
        if getattr(self,'_launch_tap',None):
            if self.foreground()!=self._launcher_package:raise PilotError('Il launcher non è più in primo piano')
            self.adb('shell','input','tap',*(str(n) for n in self._launch_tap))
            for _ in range(100):
                package=self.foreground()
                # MuMu may launch the game as u10 while `pm list packages` lists u0 only.
                # Window focus is the authoritative observation of the selected icon's app.
                if re.fullmatch(r'[A-Za-z][\w]*(?:\.[\w]+)+',package) and package!=self._launcher_package and not package.startswith(('com.android.','com.google.android.')):
                    self.package=package;self.trace('game.launched',package=package);return
                time.sleep(.1)
            raise PilotError('Il gioco non è entrato in primo piano; nessun altro input inviato')
        if not self.package:
            raise PilotError("Configurare device.package")
        # Resolve only the requested game's launcher. No random events, no data reset.
        component = self.adb("shell", "cmd", "package", "resolve-activity", "--brief",
                             *(['--user',self.user] if self.user else []),
                             "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", self.package).decode().strip().splitlines()
        if not component or not re.fullmatch(re.escape(self.package) + r"/[\w.$]+", component[-1]):
            raise PilotError(f"Launcher non trovato per {self.package}")
        self.adb("shell", "am", "start", *(['--user',self.user] if self.user else []), "-n", component[-1])

    def capture(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = self.adb("exec-out", "screencap", "-p")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                width, height = im.size
                thumbnail = im.convert("L").resize((16, 16)).tobytes()
        except (OSError, ValueError) as e:
            raise PilotError("Screenshot ADB non valido") from e
        path.write_bytes(raw)
        return {"id": path.stem, "path": str(path.resolve()), "width": width, "height": height,
                "sha256": digest(raw), "visual_hash": digest(thumbnail)[:16], "captured_at": now(),
                "package": self.foreground()}

    def act(self, action, evidence, guard_path, *, allow_game_progress=False, allow_required_terms=False):
        validate_action(action, allow_game_progress,allow_required_terms)
        if action["kind"] in {"inspect", "finish", "blocked"}:
            return {"executed": False, "reason": action["kind"]}
        current = self.capture(guard_path)
        if current["package"] != self.package:
            return {"executed": False, "reason": "foreground_changed", "observed_package": current["package"]}
        if (current["width"], current["height"]) != (evidence["width"], evidence["height"]):
            return {"executed": False, "reason": "orientation_changed"}
        w, h = current["width"], current["height"]
        x, y = min(w - 1, round(action["x"] * w)), min(h - 1, round(action["y"] * h))
        x2, y2 = min(w - 1, round(action["x2"] * w)), min(h - 1, round(action["y2"] * h))
        kind = action["kind"]
        if kind in {"tap", "long_press", "swipe", "type_text", "back"}:
            region = None if kind in {"back", "type_text"} else (max(0, x - 40), max(0, y - 30), min(w, x + 40), min(h, y + 30))
            distance = visual_distance(evidence["path"], current["path"], region)
            # A tutorial hand may briefly cover the target. Reobserve without
            # relaxing the threshold; never tap while the target still differs.
            if kind in {"tap", "long_press"}:
                for retry in range(3):
                    if distance <= self.config.get("stale_threshold", .16):
                        break
                    time.sleep(.2)
                    retry_path = Path(guard_path).with_name(f"{Path(guard_path).stem}-retry{retry + 1}.png")
                    current = self.capture(retry_path)
                    if current["package"] != self.package:
                        return {"executed": False, "reason": "foreground_changed", "observed_package": current["package"]}
                    if (current["width"], current["height"]) != (w, h):
                        return {"executed": False, "reason": "orientation_changed"}
                    distance = visual_distance(evidence["path"], current["path"], region)
            if distance > self.config.get("stale_threshold", .16):
                return {"executed": False, "reason": "target_changed", "distance": distance}
        if kind == "tap":
            self.adb("shell", "input", "tap", str(x), str(y))
        elif kind in {"swipe", "long_press"}:
            if kind == "long_press":
                x2, y2 = x, y
            self.adb("shell", "input", "swipe", str(x), str(y), str(x2), str(y2), str(max(100, round(action["duration_ms"]))))
        elif kind == "back":
            self.adb("shell", "input", "keyevent", "4")
        elif kind == "type_text":
            self.adb("shell", "input", "text", shlex.quote(action["text"].replace(" ", "%s")))
        elif kind == "wait":
            time.sleep(max(.2, action["duration_ms"] / 1000))
        if kind != "wait":
            time.sleep(self.config.get("settle_seconds", 1.2))
        return {"executed": True, "kind": kind, "guard": current["id"]}


def preview(evidence, output, size=1280):
    with Image.open(evidence["path"]) as im:
        im.thumbnail((size, size))
        im.convert("RGB").save(output, quality=90)
    return Path(output)
