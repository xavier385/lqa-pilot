"""Build an allowlisted, account-independent distribution. No run or auth data."""
import hashlib
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
files = [root/name for name in ("README.md", "CONTRIBUTING.md", "VALIDAZIONE.md", "pyproject.toml", "Start.ps1", "Start.cmd", "Setup.ps1", "Setup.cmd", ".gitignore", "LQA Pilot.pyw", "webapp/vercel.json", "webapp/build.mjs", "webapp/.vercelignore")]
for directory, suffixes in [("lqa_pilot", {".py", ".json", ".mjs", ".html", ".css", ".js"}), ("examples", {".json"}), ("tests", {".py"}), ("tools", {".py"})]:
    files += [p for p in (root/directory).rglob("*") if p.is_file() and p.suffix in suffixes
              and "__pycache__" not in p.parts and p.name != "analyze_update_popup.py"]
for file in files:
    if any(value in file.read_text(encoding="utf-8") for value in (str(Path.home()), Path.home().as_posix())):
        raise RuntimeError(f"Personal path in distribution: {file.relative_to(root)}")
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for file in sorted(set(files)):
        archive.write(file, "LQA-Pilot/"+file.relative_to(root).as_posix())
checksum = hashlib.sha256(target.read_bytes()).hexdigest()
target.with_suffix(".sha256").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
print(target, target.stat().st_size, "bytes", "sha256", checksum)
