#!/usr/bin/env python3
"""Markdown Document Reader — Flask backend.

Path strategy
─────────────
Development (uv run python app.py):
  APP_DIR    = directory containing this script
  BUNDLE_DIR = same as APP_DIR  (templates are on disk)

Packaged (PyInstaller --onefile):
  APP_DIR    = directory containing the executable
               → config.json and document/ live here
  BUNDLE_DIR = sys._MEIPASS  (temp dir where PyInstaller extracts resources)
               → templates/ are extracted here at runtime

Password workflow
─────────────────
Edit config.json and set  "password": "plain_text".
On the next startup the app hashes it with bcrypt, writes
"password_hash" back to config.json, and removes the plain-text field.
To change the password, just add "password" again; the hash is replaced.

File obfuscation
───────────────
document/*.md files are zlib-compressed at build time and saved as *.mde.
The app decompresses them in memory at request time; plain .md files are
read directly (development mode).  zlib binary output is unreadable as
plain text while also reducing file size by ~60 %.

Distribution layout (packaged)
───────────────────────────────
  dist/
  ├── mac/doc-reader.app          ← executable
  ├── linux/doc-reader            ← executable
  ├── windows/doc-reader.exe      ← executable
  ├── config.json                 ← shared config
  └── document/                   ← shared .mde files
"""

import os
import sys
import json
import secrets
import webbrowser
import threading
import zlib
from functools import wraps
from pathlib import Path

import bcrypt
import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from pygments.formatters import HtmlFormatter
from flask import (
    Flask, render_template, request, session,
    redirect, url_for, jsonify, abort,
)

# ── Path resolution ────────────────────────────────────────────────────────────

_FROZEN = getattr(sys, "frozen", False)

# Directory that holds config.json / document/ (editable by the user)
if _FROZEN:
    _exe_dir = os.path.dirname(sys.executable)
    if sys.platform == "darwin" and os.path.basename(_exe_dir) == "MacOS":
        # --noconsole on Mac creates a .app bundle:
        #   sys.executable = .../dist/mac/doc-reader.app/Contents/MacOS/doc-reader
        # Go up 4 levels (MacOS → Contents → .app → mac/ → dist/) to reach the
        # shared dist/ folder that holds config.json and document/.
        APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_exe_dir))))
    else:
        # Windows / Linux: sys.executable = dist/windows/doc-reader.exe (or linux/)
        # Go up one level to reach the shared dist/ folder.
        APP_DIR = os.path.dirname(_exe_dir)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory that holds bundled read-only resources (templates/)
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)

CONFIG_FILE = os.path.join(APP_DIR, "config.json")

# ── Flask ──────────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder=os.path.join(BUNDLE_DIR, "templates"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Pygments CSS generated once at startup (style can be changed here)
PYGMENTS_CSS = HtmlFormatter(style="friendly").get_style_defs(".highlight")

# ── Config helpers ─────────────────────────────────────────────────────────────


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_docs_dir() -> str:
    """Return the absolute path to the docs directory."""
    raw = load_config().get("docs_dir", "./document")
    path = raw if os.path.isabs(raw) else os.path.join(APP_DIR, raw)
    return os.path.realpath(path)


# ── Bootstrap (runs once at import time) ──────────────────────────────────────


def _bootstrap() -> None:
    """
    • If config.json contains a plain-text "password" field:
        hash it → save as "password_hash", remove the plain-text field.
    • Ensure "secret_key" is present.
    • Ensure "file_key" (Fernet AES key) is present.
    All updates are written back to config.json atomically.
    """
    cfg = load_config()
    changed = False

    plain = cfg.pop("password", None)       # remove plain text (if any)
    if plain:
        cfg["password_hash"] = bcrypt.hashpw(
            plain.encode(), bcrypt.gensalt()
        ).decode()
        changed = True

    if not cfg.get("secret_key"):
        cfg["secret_key"] = secrets.token_hex(32)
        changed = True

    if changed:
        save_config(cfg)


_bootstrap()

# Set secret key from (now-updated) config
app.secret_key = load_config().get("secret_key", secrets.token_hex(32))

# ── Auth ───────────────────────────────────────────────────────────────────────


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def _safe_join(docs_dir: str, rel: str) -> str:
    """Resolve *rel* inside *docs_dir*, raising on path-traversal."""
    full = os.path.realpath(os.path.join(docs_dir, rel))
    base = os.path.realpath(docs_dir)
    if full != base and not full.startswith(base + os.sep):
        raise PermissionError(f"Path traversal attempt: {rel!r}")
    return full


# Supported document extensions: .md (plain, dev) / .mde (zlib-compressed, production)
_DOC_EXTS = {".md", ".mde"}


def _read_doc(full_path: str) -> str:
    """Read a document file, decompressing it if it has the .mde extension."""
    ext = os.path.splitext(full_path)[1].lower()
    if ext == ".mde":
        return zlib.decompress(Path(full_path).read_bytes()).decode("utf-8")
    return Path(full_path).read_text(encoding="utf-8")

# ── Routes ─────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return redirect(url_for("reader") if session.get("authenticated") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("reader"))
    error = None
    if request.method == "POST":
        cfg     = load_config()
        pw_hash = cfg.get("password_hash", "")
        entered = request.form.get("password", "")
        if pw_hash and bcrypt.checkpw(entered.encode(), pw_hash.encode()):
            session["authenticated"] = True
            return redirect(url_for("reader"))
        error = "密码错误，请重试"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/shutdown", methods=["POST"])
@login_required
def api_shutdown():
    """Gracefully stop the server after the response is sent."""
    def _stop():
        import time, signal
        time.sleep(0.4)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_stop, daemon=True).start()
    return jsonify({"status": "ok"})


@app.route("/reader")
@login_required
def reader():
    return render_template("reader.html", pygments_css=PYGMENTS_CSS)

# ── API ────────────────────────────────────────────────────────────────────────


@app.route("/api/files")
@login_required
def api_files():
    docs = get_docs_dir()
    return jsonify(_build_tree(docs, docs))


@app.route("/api/content")
@login_required
def api_content():
    rel = request.args.get("path", "").strip()
    if not rel:
        abort(400)
    docs = get_docs_dir()
    try:
        full = _safe_join(docs, rel)
    except PermissionError:
        abort(403)
    if not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in _DOC_EXTS:
        abort(404)
    try:
        raw = _read_doc(full)
    except (ValueError, Exception):
        abort(500)
    return jsonify({"html": _render_md(raw), "path": rel})


@app.route("/api/search")
@login_required
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    docs    = get_docs_dir()
    q_lower = q.lower()
    results = []
    for root, dirs, files in os.walk(docs):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _DOC_EXTS:
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, docs)
            try:
                text = _read_doc(full)
            except Exception:
                continue
            display = os.path.splitext(fname)[0]   # strip .md / .mde
            if q_lower not in text.lower() and q_lower not in display.lower():
                continue
            snippets = [
                line.strip()[:120]
                for line in text.splitlines()
                if q_lower in line.lower() and line.strip()
            ][:3]
            results.append({"path": rel, "name": fname, "display": display, "snippets": snippets})
            if len(results) == 30:
                break
    return jsonify(results)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _render_md(raw: str) -> str:
    md = markdown.Markdown(
        extensions=[
            "extra",     # tables, fenced_code, footnotes, attr_list, …
            "toc",       # auto-generates heading id attributes
            CodeHiliteExtension(css_class="highlight", guess_lang=False, linenums=False),
        ]
    )
    return md.convert(raw)


def _build_tree(path: str, base: str) -> list:
    items = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return items
    for e in entries:
        if e.name.startswith("."):
            continue
        rel = os.path.relpath(e.path, base)
        if e.is_dir(follow_symlinks=False):
            children = _build_tree(e.path, base)
            if children:
                items.append({"type": "dir", "name": e.name, "path": rel, "children": children})
        elif os.path.splitext(e.name)[1].lower() in _DOC_EXTS:
            display = os.path.splitext(e.name)[0]   # strip .md / .mde
            items.append({"type": "file", "name": e.name, "display": display, "path": rel})
    return items

# ── Entry point ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    cfg  = load_config()
    port = cfg.get("port", 5000)
    url  = f"http://127.0.0.1:{port}"

    if not cfg.get("password_hash"):
        print("⚠  未设置密码，请在 config.json 中添加 \"password\" 字段后重启")
    else:
        docs = get_docs_dir()
        os.makedirs(docs, exist_ok=True)      # create document dir if absent
        print(f"✓  文档目录: {docs}")
        print(f"✓  服务启动: {url}")
        print("   按 Ctrl+C 停止\n")
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=port, debug=False)
