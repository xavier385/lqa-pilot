"""Project packages contain project data only; never credentials or machine executables."""
import copy
import tempfile
import shutil
import zipfile
from pathlib import Path

from .util import PilotError, read_json, resolve_input, write_json


def pack_project(project_file, archive):
    project_file, archive = Path(project_file).resolve(), Path(archive).resolve()
    if archive.exists():
        raise PilotError("Archivio già esistente; scegliere un nuovo nome")
    p = copy.deepcopy(read_json(project_file))
    with tempfile.TemporaryDirectory(prefix="lqa-project-") as tmp:
        root = Path(tmp)
        copied = {}
        def include(value):
            source = resolve_input(project_file.parent, value)
            if source.suffix.lower() not in {".json", ".txt", ".md", ".csv", ".tsv", ".xlsx", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mkv", ".mov", ".webm"}:
                raise PilotError(f"Formato non ammesso nel progetto portabile: {source.suffix}")
            if source.name.lower() in {"auth.json", "credentials.json", "config.toml"}:
                raise PilotError("File account/configurazione personale escluso dal pacchetto")
            if str(source) not in copied:
                rel = f"materials/{len(copied)+1:03d}-{source.name}"
                (root/rel).parent.mkdir(exist_ok=True)
                shutil.copy2(source, root/rel)
                copied[str(source)] = rel
            return copied[str(source)]
        p.pop("project_file", None)
        p.pop("material_manifest", None)
        p.pop("ffmpeg", None)
        p.setdefault("codex", {}).pop("executable", None)
        p.setdefault("device", {}).pop("adb", None)
        p["device"].pop("adb_path", None)
        p["device"].pop("endpoint", None)
        p["device"]["serial"] = "auto"
        for key in ("reference_images", "reference_images_all"):
            p[key] = [include(v) for v in p.get(key, [])]
        p["materials"] = [{**(item if isinstance(item, dict) else {}), "path": include(item["path"] if isinstance(item, dict) else item)} for item in p.get("materials", [])]
        if p.get("taxonomy"):
            p["taxonomy"] = include(p["taxonomy"])
        elif p.get("taxonomy_snapshot"):
            write_json(root/"taxonomy.json", p.pop("taxonomy_snapshot"))
            p["taxonomy"] = "taxonomy.json"
        write_json(root/"project.json", p)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for file in root.rglob("*"):
                if file.is_file():
                    z.write(file, file.relative_to(root).as_posix())
    return archive
