"""Thin shim -> launches the central repo server and opens THIS dashboard.

The real server lives at the repo root (../server.py) and serves every dashboard
from one port, so they don't collide. This shim just keeps the old habit working:

    cd "JEM Marketing Daily Report"
    python serve.py        # starts ../server.py and opens this dashboard

It computes this folder's slug, opens http://localhost:8765/<slug>/dashboard.html,
then hands off to the central server's main loop.
"""

from __future__ import annotations

import importlib.util
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

spec = importlib.util.spec_from_file_location("nsaw_central_server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def main() -> None:
    slug = server.slugify(HERE.name)
    url = f"http://localhost:{server.PORT}/{slug}/dashboard.html"
    print(f"Central server (../server.py) -> opening {url}")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    server.main()  # serves ALL dashboards; this one is already open


if __name__ == "__main__":
    main()
