"""Prepare the GeoLab Mobile web files.

    python mobile/build_web.py            www/geolab.zip only (Pyodide then loads from the jsDelivr CDN)
    python mobile/build_web.py --bundle   also copy Pyodide + numpy + scipy into www/pyodide (offline app)

The apps for Android and iOS are built with --bundle so they work with no internet connection.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WWW = HERE / "www"
APP_JS = (WWW / "app.js").read_text(encoding="utf-8")
PYODIDE_VERSION = re.search(r'PYODIDE_VERSION = "([^"]+)"', APP_JS).group(1)
CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
CORE = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
SKIP = {"ai.py", "assistant.py", "__main__.py"}   # desktop only (AI services, command line)


def build_zip():
    out = WWW / "geolab.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "geolab").glob("*.py")):
            if f.name not in SKIP:
                z.write(f, f"geolab/{f.name}")
        z.write(WWW / "mobile_api.py", "mobile_api.py")
    print(f"wrote {out} ({out.stat().st_size // 1024} kB)")


def fetch(url) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "geolab-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def bundle():
    dest = WWW / "pyodide"
    dest.mkdir(exist_ok=True)
    for name in CORE:
        (dest / name).write_bytes(fetch(CDN + name))
        print("  ", name)
    lock = json.loads((dest / "pyodide-lock.json").read_text(encoding="utf-8"))
    pkgs = lock["packages"]
    need, todo = set(), ["numpy", "scipy"]
    while todo:
        n = todo.pop()
        if n in need:
            continue
        need.add(n)
        todo += [d.lower() for d in pkgs[n].get("depends", [])]
    for n in sorted(need):
        fn = pkgs[n]["file_name"]
        (dest / fn).write_bytes(fetch(CDN + fn))
        print("  ", fn)
    size = sum(f.stat().st_size for f in dest.iterdir()) // (1024 * 1024)
    print(f"bundled Pyodide {PYODIDE_VERSION} with {', '.join(sorted(need))} ({size} MB)")


if __name__ == "__main__":
    build_zip()
    if "--bundle" in sys.argv:
        bundle()
