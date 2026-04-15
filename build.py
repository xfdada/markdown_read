#!/usr/bin/env python3
"""
Cross-platform build script — packages the app with PyInstaller and
encrypts the document directory.

Modes
─────
  uv run python build.py               # full build: binary + encrypt docs
  uv run python build.py --binary-only # CI mode: binary only, no encryption

Output (full build)
───────────────────
  dist/
  ├── doc-reader          (Linux)
  ├── doc-reader.exe      (Windows)
  ├── doc-reader.app/     (Mac — .app bundle, no terminal window)
  ├── config.json         ← keep secure; contains file_key + password_hash
  └── document/           ← *.mde files (AES-encrypted)

No-terminal behaviour
─────────────────────
  --noconsole is passed to PyInstaller on all platforms:
    Mac     → creates a proper .app bundle; double-click to open
    Windows → no console window; runs silently in background
    Linux   → process runs without a controlling terminal
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from cryptography.fernet import Fernet

# ── Settings ───────────────────────────────────────────────────────────────────

APP_NAME     = "doc-reader"
ENTRY        = "app.py"
DIST_DIR     = "dist"
BINARY_ONLY  = "--binary-only" in sys.argv   # CI mode: skip encryption step
SEP          = ";" if sys.platform == "win32" else ":"

HIDDEN_IMPORTS = [
    "markdown.extensions.extra",
    "markdown.extensions.codehilite",
    "markdown.extensions.toc",
    "markdown.extensions.fenced_code",
    "markdown.extensions.tables",
    "markdown.extensions.footnotes",
    "markdown.extensions.attr_list",
    "markdown.extensions.def_list",
    "pygments",
    "pygments.lexers",
    "pygments.lexers.python",
    "pygments.lexers.shell",
    "pygments.lexers.javascript",
    "pygments.lexers.data",
    "pygments.formatters",
    "pygments.formatters.html",
    "pygments.styles",
    "pygments.styles.friendly",
    "bcrypt",
    "cryptography",
    "cryptography.fernet",
    "cryptography.hazmat.primitives.ciphers",
    "cryptography.hazmat.backends",
]

# ── Helpers ────────────────────────────────────────────────────────────────────


def ensure_file_key(config_path: str) -> Fernet:
    """Load or generate the Fernet file_key; persist to config.json if new."""
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("file_key"):
        cfg["file_key"] = Fernet.generate_key().decode()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("  ✓ 已生成文件加密密钥 (file_key) 写入 config.json")

    return Fernet(cfg["file_key"].encode())


def encrypt_docs(src_dir: str, dst_dir: str, fernet: Fernet) -> int:
    """Encrypt every .md file in src_dir → dst_dir as .mde. Returns file count."""
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)

    count = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fname in sorted(files):
            src_path = os.path.join(root, fname)
            rel      = os.path.relpath(src_path, src_dir)

            if fname.lower().endswith(".md"):
                mde_rel  = os.path.splitext(rel)[0] + ".mde"
                dst_path = os.path.join(dst_dir, mde_rel)
                os.makedirs(os.path.dirname(dst_path) or dst_dir, exist_ok=True)
                Path(dst_path).write_bytes(fernet.encrypt(Path(src_path).read_bytes()))
                print(f"  🔒 {rel}  →  {mde_rel}")
                count += 1
            else:
                dst_path = os.path.join(dst_dir, rel)
                os.makedirs(os.path.dirname(dst_path) or dst_dir, exist_ok=True)
                shutil.copy2(src_path, dst_path)

    return count


# ── Main build ─────────────────────────────────────────────────────────────────


def build() -> None:
    print("=" * 60)
    print(f"  构建 {APP_NAME}  [{sys.platform}]"
          + ("  [binary-only]" if BINARY_ONLY else ""))
    print("=" * 60)

    total_steps = 2 if BINARY_ONLY else 4

    # ── Step 1: PyInstaller ───────────────────────────────────────────────────
    print(f"\n[1/{total_steps}] 运行 PyInstaller ...\n")
    cmd = [
        "uv", "run", "pyinstaller",
        "--onefile",
        "--noconsole",              # Mac → .app bundle; Windows → no console
        f"--name={APP_NAME}",
        f"--add-data=templates{SEP}templates",
        "--clean",
        "--noconfirm",
        *[f"--hidden-import={h}" for h in HIDDEN_IMPORTS],
        ENTRY,
    ]
    subprocess.run(cmd, check=True)

    if BINARY_ONLY:
        _print_binary_only_summary()
        return

    # ── Step 2: Ensure file_key ───────────────────────────────────────────────
    print(f"\n[2/{total_steps}] 准备加密密钥 ...")
    fernet = ensure_file_key("config.json")

    # ── Step 3: Encrypt documents ─────────────────────────────────────────────
    print(f"\n[3/{total_steps}] 加密文档 ...")
    n = encrypt_docs("document", os.path.join(DIST_DIR, "document"), fernet)
    print(f"  ✓ 共加密 {n} 个文件  →  {DIST_DIR}/document/")

    # ── Step 4: Copy config ────────────────────────────────────────────────────
    print(f"\n[4/{total_steps}] 拷贝配置文件 ...")
    shutil.copy("config.json", os.path.join(DIST_DIR, "config.json"))
    print(f"  ✓ config.json  →  {DIST_DIR}/")

    _print_full_summary()


def _print_binary_only_summary() -> None:
    is_mac = sys.platform == "darwin"
    exe    = f"{APP_NAME}.app/" if is_mac else (APP_NAME + (".exe" if sys.platform == "win32" else ""))
    print(f"""
{'=' * 60}
  [binary-only] 构建完成

  可执行文件: dist/{exe}

  此模式不包含加密文档和配置文件。
  使用本地 config.json 和 document/ 配合此二进制文件即可。
{'=' * 60}
""")


def _print_full_summary() -> None:
    is_mac = sys.platform == "darwin"
    exe    = f"{APP_NAME}.app/" if is_mac else (APP_NAME + (".exe" if sys.platform == "win32" else ""))

    mac_note = (
        "\n  Mac 部署方式:\n"
        "    将 dist/ 目录下的 doc-reader.app、config.json、document/\n"
        "    放在同一文件夹内，双击 doc-reader.app 即可运行（无终端窗口）。"
    ) if is_mac else ""

    print(f"""
{'=' * 60}
  构建完成！

  发布目录  dist/
  ├── {exe:<30} ← 运行此文件
  ├── config.json                    ← 含加密密钥，请妥善保管
  └── document/                      ← 加密后的 .mde 文件
{mac_note}
  安全说明:
  • document/ 中的文件已用 AES-128 加密，直接打开无法阅读。
  • 解密密钥存储在 config.json 的 file_key 字段。
  • 分发时请将 dist/ 目录整体打包，不要单独发送 document/。
{'=' * 60}
""")


if __name__ == "__main__":
    build()
