"""Simple API client UI: enter a URL, pick a method, send, and view the response."""

import json
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import ttk, scrolledtext

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


class ApiClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("API Client")
        self.geometry("900x650")
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        self.method = tk.StringVar(value="GET")
        ttk.Combobox(top, textvariable=self.method, values=METHODS, width=8,
                     state="readonly").pack(side="left")

        self.url = tk.StringVar(value="https://jsonplaceholder.typicode.com/todos/1")
        url_entry = ttk.Entry(top, textvariable=self.url)
        url_entry.pack(side="left", fill="x", expand=True, padx=6)
        url_entry.bind("<Return>", lambda _e: self.send())

        self.send_btn = ttk.Button(top, text="Send", command=self.send)
        self.send_btn.pack(side="left")

        req = ttk.Notebook(self)
        req.pack(fill="x", padx=8)
        self.headers_text = self._text_tab(req, "Headers (Key: Value per line)", 5)
        self.headers_text.insert("1.0", "Accept: application/json\n")
        self.body_text = self._text_tab(req, "Body", 5)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, padding=(8, 6)).pack(fill="x")

        resp = ttk.Notebook(self)
        resp.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.resp_body = self._text_tab(resp, "Response Body", 20)
        self.resp_headers = self._text_tab(resp, "Response Headers", 20)

    @staticmethod
    def _text_tab(notebook, title, height):
        widget = scrolledtext.ScrolledText(notebook, height=height, font=("Consolas", 10))
        notebook.add(widget, text=title)
        return widget

    def _parse_headers(self):
        headers = {}
        for line in self.headers_text.get("1.0", "end").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        return headers

    def send(self):
        url = self.url.get().strip()
        if not url:
            self.status.set("Please enter a URL")
            return
        body = self.body_text.get("1.0", "end").strip()
        self.send_btn.config(state="disabled")
        self.status.set(f"Sending {self.method.get()} {url} ...")
        threading.Thread(target=self._do_request,
                         args=(self.method.get(), url, self._parse_headers(), body),
                         daemon=True).start()

    def _do_request(self, method, url, headers, body):
        data = body.encode("utf-8") if body and method != "GET" else None
        if data and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = (resp.status, resp.reason, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as e:
            result = (e.code, e.reason, dict(e.headers), e.read())
        except Exception as e:  # network errors, bad URL, timeouts
            result = (None, str(e), {}, b"")
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.after(0, self._show_response, *result, elapsed_ms)

    def _show_response(self, code, reason, headers, raw, elapsed_ms):
        self.send_btn.config(state="normal")
        if code is None:
            self.status.set(f"Error: {reason}")
        else:
            self.status.set(f"Status: {code} {reason}  |  {elapsed_ms:.0f} ms  |  {len(raw)} bytes")

        text = raw.decode("utf-8", errors="replace")
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            pass

        for widget, content in ((self.resp_body, text),
                                (self.resp_headers,
                                 "\n".join(f"{k}: {v}" for k, v in headers.items()))):
            widget.delete("1.0", "end")
            widget.insert("1.0", content)


if __name__ == "__main__":
    ApiClientApp().mainloop()
