"""Local preview: serve only public web assets and approved computed data."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
PUBLIC_DATA = {"index.json", "priority.csv", "priority_segments.csv", "priority_bus.csv"}
PUBLIC_WEB = {"index.html", "app.js", "app.css", "config.js"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        allowed = {"/web/", "/web"} | {"/web/" + f for f in PUBLIC_WEB} | {"/data/" + f for f in PUBLIC_DATA}
        if path not in allowed:
            self.send_error(404)
            return None
        resolved = Path(self.translate_path(self.path)).resolve()
        if not resolved.is_relative_to(ROOT):
            self.send_error(404)
            return None
        return super().send_head()


if __name__ == "__main__":
    print("Local: http://localhost:8000/web/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
