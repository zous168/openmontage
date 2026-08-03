"""Edit-stage preview — Remotion Studio / HyperFrames preview launchers for Backlot."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from backlot.state import REPO_ROOT

COMPOSER_DIR = REPO_ROOT / "remotion-composer"
_PREVIEW_SESSIONS: dict[str, dict[str, Any]] = {}


def _read_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _project_port(project_id: str, base: int) -> int:
    digest = hashlib.md5(project_id.encode()).hexdigest()[:4]
    return base + (int(digest, 16) % 120)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _stop_listener(port: int) -> None:
    """Best-effort kill of whatever is listening on *port* (stale preview server)."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            return
        raw = out.stdout or b""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("mbcs", errors="replace")
        pids: set[int] = set()
        token = f":{port}"
        for line in text.splitlines():
            if "LISTENING" not in line or token not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
        for pid in pids:
            if pid <= 0:
                continue
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    else:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    # Give the OS a moment to release the port.
    time.sleep(0.5)


def _load_playbook(project_dir: Path, edit_decisions: dict) -> Optional[dict]:
    meta = _read_json(project_dir / "meta.json") or {}
    playbook_name = (
        meta.get("style_playbook")
        or (edit_decisions.get("metadata") or {}).get("playbook")
    )
    if not playbook_name:
        return None
    try:
        from styles.playbook_loader import load_playbook  # type: ignore

        return load_playbook(playbook_name)
    except Exception:
        return None


def _composition_id(edit_decisions: dict) -> str:
    from tools.video.video_compose import VideoCompose

    family = edit_decisions.get("renderer_family") or "explainer-data"
    bespoke = edit_decisions.get("bespoke") or {}
    if edit_decisions.get("composition_mode") == "atelier" and bespoke.get("composition_id"):
        return str(bespoke["composition_id"])
    return VideoCompose._get_composition_id(family)


def _prepare_remotion_props(project_dir: Path, edit_decisions: dict) -> tuple[Path, Path]:
    from lib.composition_timeline import normalize_composition_props
    from tools.video.video_compose import VideoCompose

    tool = VideoCompose()
    props = normalize_composition_props(json.loads(json.dumps(edit_decisions)))
    output_path = (project_dir / "renders" / "preview_stub.mp4").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    public_dir = tool._prepare_remotion_props(props, output_path)
    if public_dir is None:
        raise ValueError("无法为 Remotion 预览准备 props（请确认项目在 projects/ 下）")
    if "themeConfig" not in props:
        playbook_name = (
            props.get("playbook")
            or props.get("theme")
            or (props.get("metadata") or {}).get("playbook")
            or (_read_json(project_dir / "meta.json") or {}).get("style_playbook")
        )
        theme_config = tool._build_theme_from_playbook(playbook_name, edit_decisions)
        if theme_config:
            props["themeConfig"] = theme_config
    props_path = project_dir / "renders" / ".remotion_preview_props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    return props_path.resolve(), public_dir.resolve()


def _ensure_hyperframes_workspace(project_dir: Path, edit_decisions: dict) -> Path:
    workspace = project_dir / "hyperframes"
    if (workspace / "index.html").is_file():
        return workspace

    from tools.video.hyperframes_compose import HyperFramesCompose

    asset_manifest = _read_json(project_dir / "artifacts" / "asset_manifest.json") or {}
    hf_inputs: dict[str, Any] = {
        "operation": "scaffold_workspace",
        "workspace_path": str(workspace),
        "edit_decisions": edit_decisions,
        "asset_manifest": asset_manifest,
    }
    playbook = _load_playbook(project_dir, edit_decisions)
    if playbook:
        hf_inputs["playbook"] = playbook

    result = HyperFramesCompose().execute(hf_inputs)
    if not result.success:
        raise RuntimeError(result.error or "HyperFrames workspace scaffold 失败")
    if not (workspace / "index.html").is_file():
        raise RuntimeError("HyperFrames workspace 已生成但缺少 index.html")
    return workspace


def _resolve_npx() -> str:
    for name in ("npx", "npx.cmd"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("未找到 npx，请确认已安装 Node.js 并加入 PATH")


def _resolve_node() -> str:
    for name in ("node", "node.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("未找到 node，请确认已安装 Node.js 并加入 PATH")


def _build_remotion_studio_cmd(
    *,
    entry: Path,
    port: int,
    props_path: Path,
    public_dir: Path,
) -> list[str]:
    """Prefer `node …/remotion-cli.js` over `npx` to avoid Windows console flashes."""
    # npm workspaces hoist @remotion/cli to the repo root; fall back there
    # when the composer-local path is gone (post-workspaces layout).
    cli_js = COMPOSER_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli_js.is_file():
        cli_js = REPO_ROOT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    flags = [
        f"--port={port}",
        f"--props={props_path.as_posix()}",
        f"--public-dir={public_dir.as_posix()}",
    ]
    if cli_js.is_file():
        return [_resolve_node(), str(cli_js), "studio", str(entry), *flags]
    return ["npx", "remotion", "studio", str(entry), *flags]


def _spawn_detached(cmd: list[str], *, cwd: Path) -> subprocess.Popen:
    if cmd and cmd[0] == "npx":
        cmd = [_resolve_npx(), *cmd[1:]]
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kwargs["creationflags"] = creationflags
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError as exc:
        raise RuntimeError(f"无法启动预览进程：{' '.join(cmd)}") from exc


def _wait_for_port(port: int, *, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.4)
    return False


def build_edit_preview_info(project_dir: Path) -> dict[str, Any]:
    project_id = project_dir.name
    edit = _read_json(project_dir / "artifacts" / "edit_decisions.json") or {}
    runtime = edit.get("render_runtime") or "remotion"
    hf_ws = project_dir / "hyperframes"
    remotion_port = _project_port(project_id, 3000)
    hf_port = _project_port(project_id, 3200)
    hf_play_port = hf_port + 1

    npx_ok = bool(shutil.which("npx"))
    composition_id = None
    props_ready = False
    try:
        if edit.get("cuts"):
            composition_id = _composition_id(edit)
            props_path = project_dir / "renders" / ".remotion_preview_props.json"
            props_ready = props_path.is_file()
    except ValueError:
        composition_id = None

    studio_url = f"http://localhost:{remotion_port}"
    if composition_id:
        studio_url = f"{studio_url}/{composition_id}"

    nle_port = _project_port(project_id, 3400)

    return {
        "render_runtime": runtime,
        "remotion": {
            "available": npx_ok and COMPOSER_DIR.is_dir(),
            "composition_id": composition_id,
            "props_ready": props_ready,
            "props_path": str(project_dir / "renders" / ".remotion_preview_props.json"),
            "port": remotion_port,
            "running": _port_open(remotion_port),
            "studio_url": studio_url,
            "nle_preview_url": (
                f"http://localhost:{nle_port}/?projectId={project_id}"
                if _port_open(nle_port)
                else None
            ),
            "nle_preview_running": _port_open(nle_port),
        },
        "hyperframes": {
            "available": npx_ok,
            "workspace_ready": (hf_ws / "index.html").is_file(),
            "workspace_path": str(hf_ws),
            "preview_port": hf_port,
            "play_port": hf_play_port,
            "preview_running": _port_open(hf_port),
            "play_running": _port_open(hf_play_port),
            "preview_url": f"http://localhost:{hf_port}/#project/{hf_ws.name}",
            "play_url": f"http://localhost:{hf_play_port}",
        },
        "ffmpeg": {
            "note": "FFmpeg 运行时无 composition 预览器；请使用上方通用时间轴审阅剪切。",
        },
    }


def start_edit_preview(
    project_dir: Path,
    *,
    runtime: str,
    mode: str = "studio",
    scaffold: bool = False,
) -> dict[str, Any]:
    project_id = project_dir.name
    edit = _read_json(project_dir / "artifacts" / "edit_decisions.json") or {}
    if not edit.get("cuts"):
        raise ValueError("edit_decisions 尚无剪切片段，无法打开高级预览")

    if runtime == "remotion" and mode == "nle":
        return start_nle_preview(project_dir)

    if runtime == "remotion":
        if not shutil.which("npx") and not shutil.which("npx.cmd"):
            raise RuntimeError("未找到 npx，无法启动 Remotion Studio")
        if not COMPOSER_DIR.is_dir():
            raise RuntimeError(f"未找到 remotion-composer：{COMPOSER_DIR}")

        props_path, public_dir = _prepare_remotion_props(project_dir, edit)
        composition_id = _composition_id(edit)
        port = _project_port(project_id, 3000)
        url = f"http://localhost:{port}/{composition_id}"

        # Always restart so --props / --public-dir match the current project.
        if _port_open(port):
            _stop_listener(port)

        entry = COMPOSER_DIR / "src" / "index.tsx"
        cmd = _build_remotion_studio_cmd(
            entry=entry,
            port=port,
            props_path=props_path,
            public_dir=public_dir,
        )
        _spawn_detached(cmd, cwd=COMPOSER_DIR)
        if not _wait_for_port(port):
            raise RuntimeError(f"Remotion Studio 在 {port} 端口启动超时")

        _PREVIEW_SESSIONS[f"{project_id}:remotion"] = {
            "runtime": "remotion",
            "port": port,
            "url": url,
            "props_path": str(props_path),
            "public_dir": str(public_dir),
        }
        return {
            "runtime": "remotion",
            "mode": mode,
            "url": url,
            "composition_id": composition_id,
            "props_path": str(props_path),
            "public_dir": str(public_dir),
            "hint": f"已加载项目「{project_id}」的 cuts 与素材（composition: {composition_id}）。",
        }

    if runtime == "hyperframes":
        if not shutil.which("npx"):
            raise RuntimeError("未找到 npx，无法启动 HyperFrames 预览")

        workspace = project_dir / "hyperframes"
        if scaffold or not (workspace / "index.html").is_file():
            workspace = _ensure_hyperframes_workspace(project_dir, edit)

        if mode == "play":
            port = _project_port(project_id, 3200) + 1
            url = f"http://localhost:{port}"
            if not _port_open(port):
                cmd = ["npx", "hyperframes", "play", f"--port={port}"]
                _spawn_detached(cmd, cwd=workspace)
                if not _wait_for_port(port, timeout=60.0):
                    raise RuntimeError(f"HyperFrames Player 在 {port} 端口启动超时")
        else:
            port = _project_port(project_id, 3200)
            url = f"http://localhost:{port}/#project/{workspace.name}"
            if not _port_open(port):
                cmd = ["npx", "hyperframes", "preview", f"--port={port}"]
                _spawn_detached(cmd, cwd=workspace)
                if not _wait_for_port(port, timeout=60.0):
                    raise RuntimeError(f"HyperFrames Studio 在 {port} 端口启动超时")

        _PREVIEW_SESSIONS[f"{project_id}:hyperframes"] = {
            "runtime": "hyperframes",
            "mode": mode,
            "port": port,
            "url": url,
        }
        return {
            "runtime": "hyperframes",
            "mode": mode,
            "url": url,
            "workspace_path": str(workspace),
            "hint": "HyperFrames Studio 中可编辑时间轴；Player 模式为轻量嵌入预览。",
        }

    raise ValueError(f"不支持的预览 runtime：{runtime}")


def start_nle_preview(project_dir: Path) -> dict[str, Any]:
    """Start the NLE live-preview server (webpack-bundled Player iframe).

    The preview iframe polls GET /nle-edit/draft-props, so the server only
    bundles src/preview.tsx once; no props are baked into the bundle.
    """
    project_id = project_dir.name
    if not _resolve_node_safe():
        raise RuntimeError("未找到 node，无法启动 NLE 预览")
    script = COMPOSER_DIR / "scripts" / "preview-server.mjs"
    if not script.is_file():
        raise RuntimeError(f"缺少 NLE 预览脚本：{script}")

    port = _project_port(project_id, 3400)
    if _port_open(port):
        _stop_listener(port)

    cmd = [_resolve_node(), str(script), f"--port={port}", f"--public-dir={project_dir}"]
    _spawn_detached(cmd, cwd=COMPOSER_DIR)
    if not _wait_for_port(port, timeout=120.0):
        raise RuntimeError(f"NLE 预览服务在 {port} 端口启动超时")

    url = f"http://localhost:{port}/?projectId={project_id}"
    _PREVIEW_SESSIONS[f"{project_id}:nle"] = {
        "runtime": "remotion",
        "mode": "nle",
        "port": port,
        "url": url,
    }
    return {
        "runtime": "remotion",
        "mode": "nle",
        "url": url,
        "port": port,
        "hint": "NLE 实时预览已启动——在时间线上拖拽 cut 后点「预览草稿」。",
    }


def _resolve_node_safe() -> bool:
    try:
        _resolve_node()
        return True
    except RuntimeError:
        return False
