#!/usr/bin/env python3
"""
build_all.py — 本地一键构建 Mac / Linux / Windows 三平台程序包

平台策略
──────────────────────────────────────────────────────────
  Mac     → PyInstaller 原生构建（当前 Mac 机器）
  Linux   → Docker  python:3.11-slim  (x86_64)
  Windows → Docker  cdrx/pyinstaller-windows  (Wine + Windows Python 3)

前提条件
──────────────────────────────────────────────────────────
  • Mac：已安装 uv、已配置 config.json（密码）
  • Linux / Windows：Docker Desktop 已启动

输出结构
──────────────────────────────────────────────────────────
  dist/
  ├── mac/
  │   └── doc-reader.app/   ← 双击运行（无终端）
  ├── linux/
  │   └── doc-reader
  ├── windows/
  │   └── doc-reader.exe
  ├── config.json           ← 三平台共用
  └── document/             ← 三平台共用（轻量 XOR 混淆的 .mde 文件）

用法
──────────────────────────────────────────────────────────
  uv run python build_all.py                   # 三平台全部构建
  uv run python build_all.py --platform mac    # 仅 Mac
  uv run python build_all.py --platform linux  # 仅 Linux
  uv run python build_all.py --platform windows
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

CWD      = os.path.abspath(".")
APP_NAME = "doc-reader"
DIST     = "dist"

# Python packages required at runtime + PyInstaller itself
PACKAGES = "flask bcrypt markdown Pygments pyinstaller"

# Modules PyInstaller's static analysis may miss
HIDDEN = [
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
]

# ── Helpers ────────────────────────────────────────────────────────────────────


def _hidden_flags() -> str:
    return " ".join(f"--hidden-import={h}" for h in HIDDEN)


def _pyi_cmd(sep: str) -> str:
    """Return a PyInstaller command string for the given path separator."""
    return (
        f"pyinstaller --onefile --noconsole --name={APP_NAME} "
        f"\"--add-data=templates{sep}templates\" "
        f"--clean --noconfirm "
        f"{_hidden_flags()} app.py"
    )


def _docker_ok() -> bool:
    return subprocess.run(
        ["docker", "info"], capture_output=True
    ).returncode == 0


def _run(cmd: list[str], label: str) -> bool:
    """Run a command; return True on success."""
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  ✗ {label} 构建失败 (exit {result.returncode})")
        return False
    return True


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# ── zlib obfuscation (compresses + makes files unreadable as plain text) ───────


def _build_shared_docs() -> None:
    """Write shared dist/config.json and dist/document/ (runs once for all platforms)."""
    # ── config.json ───────────────────────────────────────────────────────────
    shutil.copy("config.json", os.path.join(DIST, "config.json"))

    # ── zlib-compressed documents ──────────────────────────────────────────────
    doc_dst = os.path.join(DIST, "document")
    if os.path.exists(doc_dst):
        shutil.rmtree(doc_dst)
    count = 0
    for root, dirs, files in os.walk("document"):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fname in sorted(files):
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, "document")
            if fname.lower().endswith(".md"):
                mde_rel  = os.path.splitext(rel)[0] + ".mde"
                dst_path = os.path.join(doc_dst, mde_rel)
                os.makedirs(os.path.dirname(dst_path) or doc_dst, exist_ok=True)
                Path(dst_path).write_bytes(zlib.compress(Path(src).read_bytes(), level=6))
            else:
                dst_path = os.path.join(doc_dst, rel)
                os.makedirs(os.path.dirname(dst_path) or doc_dst, exist_ok=True)
                shutil.copy2(src, dst_path)
            count += 1
    print(f"  ✓ dist/document/  ({count} 个文件，仅处理一次)")
    print(f"  ✓ dist/config.json")


# ── Per-platform builds ────────────────────────────────────────────────────────


def _integrate_windows(exe_path: str) -> None:
    """
    将从 GitHub Actions 下载的 doc-reader.exe 集成到 dist/windows/。
    若 dist/document/ 不存在，同时运行共享目录后处理。
    """
    src = os.path.abspath(exe_path)
    if not os.path.isfile(src):
        print(f"  ✗ 找不到文件：{src}")
        sys.exit(1)
    dst_dir = os.path.join(DIST, "windows")
    _ensure_dir(dst_dir)
    dst = os.path.join(dst_dir, f"{APP_NAME}.exe")
    shutil.copy2(src, dst)
    print(f"  ✓ dist/windows/{APP_NAME}.exe")

    doc_dir = os.path.join(DIST, "document")
    if os.path.isdir(doc_dir):
        print(f"  ✓ dist/document/ 已存在，跳过重建")
    else:
        print(f"\n▶ [后处理] 混淆文档并写入共享目录 dist/ ...")
        _build_shared_docs()

    print(f"\n✓  Windows 集成完成。发布目录结构：")
    print(f"     dist/")
    print(f"     ├── mac/doc-reader.app")
    print(f"     ├── windows/doc-reader.exe")
    print(f"     ├── config.json")
    print(f"     └── document/")


def build_mac() -> bool:
    """Native PyInstaller build on this Mac."""
    print("\n▶ [Mac] 原生构建 ...")

    ok = _run(
        ["uv", "run", "pyinstaller",
         "--onefile", "--noconsole", f"--name={APP_NAME}",
         "--add-data=templates:templates",
         "--clean", "--noconfirm",
         *[f"--hidden-import={h}" for h in HIDDEN],
         "app.py"],
        "Mac",
    )
    if not ok:
        return False

    # --noconsole on Mac produces dist/doc-reader.app (a .app bundle)
    src = os.path.join(DIST, f"{APP_NAME}.app")
    dst = os.path.join(DIST, "mac", f"{APP_NAME}.app")
    _ensure_dir(os.path.join(DIST, "mac"))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"  ✓ dist/mac/{APP_NAME}.app")
    return True


def build_linux() -> bool:
    """Build Linux x86_64 binary inside a python:3.11-slim Docker container."""
    print("\n▶ [Linux] Docker 构建 (python:3.11-slim / linux/amd64) ...")

    shell = (
        f"pip install {PACKAGES} -q && "
        f"{_pyi_cmd(':')}"
    )
    ok = _run(
        [
            "docker", "run", "--rm",
            "--platform", "linux/amd64",
            "-v", f"{CWD}:/workspace",
            "-w", "/workspace",
            "python:3.11-slim",
            "bash", "-c", shell,
        ],
        "Linux",
    )
    if not ok:
        return False

    src = os.path.join(DIST, APP_NAME)
    dst = os.path.join(DIST, "linux", APP_NAME)
    _ensure_dir(os.path.join(DIST, "linux"))
    shutil.copy2(src, dst)
    os.chmod(dst, 0o755)
    print(f"  ✓ dist/linux/{APP_NAME}")
    return True


def build_windows() -> bool:
    """
    Build Windows x86_64 .exe using cdrx/pyinstaller-windows (Wine + Windows Python 3).

    The cdrx image's entrypoint sets up Wine and runs PyInstaller using Windows Python.
    It auto-installs packages from requirements.txt and reads flags from PYINSTALLER_FLAGS.
    We must NOT override the entrypoint with "bash -c" — that bypasses Wine setup and
    runs Linux pyinstaller instead, which produces a Linux binary with no .exe extension.

    Note: First run pulls ~2 GB image; subsequent runs use the local cache.
    """
    print("\n▶ [Windows] Docker + Wine 构建 (cdrx/pyinstaller-windows:python3) ...")
    print("  首次运行需拉取约 2 GB 镜像，请耐心等待 ...")

    # cdrx image auto-installs from requirements.txt via Wine pip
    tmp_req = os.path.join(CWD, "requirements.txt")
    pkgs_for_req = [p for p in PACKAGES.split() if p != "pyinstaller"]
    with open(tmp_req, "w", encoding="utf-8") as f:
        f.write("\n".join(pkgs_for_req) + "\n")

    # PYINSTALLER_FLAGS is read by the image's entrypoint; use Windows separator ';'
    pyi_flags = (
        f"--onefile --noconsole --name={APP_NAME} "
        f"--add-data=templates;templates "
        f"--clean --noconfirm "
        f"{_hidden_flags()}"
    )

    try:
        ok = _run(
            [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "-v", f"{CWD}:/src",
                "-e", f"PYINSTALLER_FLAGS={pyi_flags}",
                "cdrx/pyinstaller-windows:python3",
                "app.py",
            ],
            "Windows",
        )
    finally:
        if os.path.exists(tmp_req):
            os.remove(tmp_req)

    if not ok:
        print(
            "\n  ⚠  Windows Docker 构建失败。\n"
            "  备选方案：推送版本 tag 触发 GitHub Actions 云端构建：\n"
            "    git tag v1.0.0 && git push origin v1.0.0\n"
        )
        return False

    src = os.path.join(DIST, f"{APP_NAME}.exe")
    if not os.path.exists(src):
        dist_contents = sorted(os.listdir(DIST)) if os.path.isdir(DIST) else []
        print(f"  ✗ Windows .exe 未生成，dist/ 当前内容：{dist_contents}")
        print(
            "\n  ⚠  Wine 环境未产生 .exe（可能是 ARM Mac + QEMU + Wine 兼容性问题）。\n"
            "  备选方案：推送版本 tag 触发 GitHub Actions 云端构建：\n"
            "    git tag v1.0.0 && git push origin v1.0.0\n"
        )
        return False

    dst = os.path.join(DIST, "windows", f"{APP_NAME}.exe")
    _ensure_dir(os.path.join(DIST, "windows"))
    shutil.copy2(src, dst)
    print(f"  ✓ dist/windows/{APP_NAME}.exe")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

BUILDERS = {
    "mac":     build_mac,
    "linux":   build_linux,
    "windows": build_windows,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本地一键构建三平台 doc-reader"
    )
    parser.add_argument(
        "--platform",
        choices=["mac", "linux", "windows", "all"],
        default="all",
        help="构建目标平台（默认 all）",
    )
    parser.add_argument(
        "--add-windows",
        metavar="EXE_PATH",
        help="将从 GitHub Actions 下载的 doc-reader.exe 集成到 dist/windows/（跳过本地构建）",
    )
    args = parser.parse_args()

    # ── Shortcut: integrate a pre-built Windows exe ──────────────────────────
    if args.add_windows:
        print("=" * 60)
        print("  集成 GitHub Actions Windows 产物")
        print("=" * 60)
        _integrate_windows(args.add_windows)
        return


    targets = (
        list(BUILDERS.keys()) if args.platform == "all"
        else [args.platform]
    )

    print("=" * 60)
    print(f"  doc-reader 多平台构建  →  {', '.join(targets)}")
    print("=" * 60)

    # Check Docker availability before starting
    need_docker = any(t in targets for t in ("linux", "windows"))
    if need_docker and not _docker_ok():
        print(
            "\n⚠  Docker 未运行。Linux / Windows 构建需要 Docker Desktop。\n"
            "   请启动 Docker Desktop 后重试。"
        )
        if "mac" not in targets:
            sys.exit(1)
        targets = [t for t in targets if t == "mac"]
        print("   仅继续构建 Mac 版本 ...\n")

    # Run each platform build
    results: dict[str, bool] = {}
    for platform in targets:
        results[platform] = BUILDERS[platform]()

    # Post-build: build shared dist/document/ and dist/config.json (only once)
    succeeded = [p for p, ok in results.items() if ok]
    if succeeded:
        print(f"\n▶ [后处理] 混淆文档并写入共享目录 dist/ ...")
        _build_shared_docs()

    # Summary
    print(f"\n{'=' * 60}")
    print("  构建结果：")
    for platform in targets:
        if results.get(platform):
            print(f"  ✓  {platform:<10} dist/{platform}/")
        else:
            print(f"  ✗  {platform:<10} 构建失败")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
