"""Entry point: registers pages and starts NiceGUI as a desktop window or a web server.

    python -m apirunner            # desktop window (native)
    python -m apirunner --web      # browser at http://localhost:8080
"""

from __future__ import annotations

import argparse
import os

from nicegui import app, ui

from apirunner.ui import bulk_page, history_page, settings_page, single_call, templates_page

ROUTES = {
    "/": single_call.page,
    "/templates": templates_page.page,
    "/bulk": bulk_page.page,
    "/history": history_page.page,
    "/settings": settings_page.page,
}


def register_pages() -> None:
    for path, builder in ROUTES.items():
        ui.page(path, title="API Runner")(builder)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="API Runner - generic API caller with Excel bulk & retry")
    parser.add_argument("--web", action="store_true", help="run in the browser instead of a desktop window")
    parser.add_argument("--host", default=os.environ.get("APIRUNNER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APIRUNNER_PORT", "8080")))
    parser.add_argument("--no-show", action="store_true", help="do not open a browser (web mode)")
    args, _ = parser.parse_known_args(argv)

    register_pages()

    app.native.window_args["min_size"] = (1100, 720)
    ui.run(
        title="API Runner",
        favicon="🚀",
        host=args.host,
        port=args.port,
        native=not args.web,
        window_size=None if args.web else (1360, 860),
        show=not args.no_show,
        reload=False,
        storage_secret=os.environ.get("APIRUNNER_SECRET", "apirunner-local"),
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
