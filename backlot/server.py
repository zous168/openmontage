"""Backlot server — FastAPI app: board state API, SSE change feed, media.

The project **board** is a read-only observer: it derives all stage/script/
storyboard state from files the pipeline already writes under ``projects/``.

The **library** may bootstrap empty workspaces via ``POST /api/projects``
(``init_project`` only — no checkpoints, no agent orchestration). That write
path lives in ``backlot.bootstrap`` and does not change how the board renders
or validates production state.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backlot.env_config import build_env_catalog, update_env_vars
from backlot.app_settings import app_settings_response, update_app_settings
from backlot.pipeline_admin import (
    add_pipeline_stage,
    build_pipeline_admin_catalog,
    build_pipeline_editor_hints,
    delete_pipeline_stage,
    get_pipeline_config,
    read_skill_markdown,
    reorder_pipeline_stages,
    update_pipeline_manifest,
    update_pipeline_stage,
    update_pipeline_ui,
    write_skill_markdown,
)
from backlot.skill_tool_catalog import build_skill_tool_catalog
from backlot.system_check import build_dependency_manifest, run_system_check
from backlot.bootstrap import (
    BootstrapError,
    create_project_workspace,
    delete_project_workspace,
    list_pipeline_catalog,
    list_style_playbook_options,
    load_project_settings,
    stage_uploaded_media,
    update_project_settings,
)
from backlot import API_VERSION
from backlot.edit_preview import build_edit_preview_info, start_edit_preview
from lib.composition_timeline import build_composition_timeline
from backlot.state import PROJECTS_DIR, REPO_ROOT, _is_demo_project, list_projects, load_board_state, summarize_project

UI_DIR = Path(__file__).resolve().parent / "ui"
THUMB_CACHE_DIR = REPO_ROOT / ".backlot" / "thumbs"
THUMB_WIDTHS = (320, 640, 960)

# Paths inside a project whose changes are pure noise for the board.
_IGNORE_PARTS = {"node_modules", ".git", "__pycache__", ".cache"}

SSE_HEARTBEAT_SECONDS = 15


class CreateProjectBody(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    pipeline_type: str = Field(min_length=1, max_length=64)
    style_playbook: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    inputs: Optional[dict[str, Any]] = None


class UpdateProjectSettingsBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    style_playbook: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    inputs: Optional[dict[str, Any]] = None
    replace_media: bool = False


class UpdateEnvVarsBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class UpdateAppSettingsBody(BaseModel):
    default_style_playbook: Optional[str] = Field(default=None, max_length=64)
    default_bootstrap_notes: Optional[str] = Field(default=None, max_length=2000)
    theme: Optional[str] = Field(default=None, max_length=16)
    font_scale: Optional[float] = None


class UpdatePipelineUiBody(BaseModel):
    hidden: Optional[bool] = None
    label_zh: Optional[str] = Field(default=None, max_length=80)
    summary_zh: Optional[str] = Field(default=None, max_length=200)


class UpdatePipelineStageBody(BaseModel):
    new_name: Optional[str] = Field(default=None, max_length=64)
    skill: Optional[str] = Field(default=None, max_length=240)
    produces: Optional[list[str]] = None
    tools_available: Optional[list[str]] = None
    required_artifacts_in: Optional[list[str]] = None
    optional_artifacts_in: Optional[list[str]] = None
    checkpoint_required: Optional[bool] = None
    review_focus: Optional[list[str]] = None
    success_criteria: Optional[list[str]] = None
    human_approval_default: Optional[bool] = None
    sub_stages: Optional[list[dict[str, Any]]] = None


class UpdatePipelineManifestBody(BaseModel):
    version: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = Field(default=None, max_length=4000)
    category: Optional[str] = Field(default=None, max_length=40)
    stability: Optional[str] = Field(default=None, max_length=20)
    default_checkpoint_policy: Optional[str] = Field(default=None, max_length=32)
    required_skills: Optional[list[str]] = None
    compatible_playbooks: Optional[Any] = None
    reference_input: Optional[dict[str, Any]] = None
    orchestration: Optional[dict[str, Any]] = None
    extensions: Optional[dict[str, Any]] = None
    ui: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class CreatePipelineStageBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    skill: Optional[str] = Field(default=None, max_length=240)
    produces: Optional[list[str]] = None
    tools_available: Optional[list[str]] = None
    required_artifacts_in: Optional[list[str]] = None
    optional_artifacts_in: Optional[list[str]] = None
    checkpoint_required: Optional[bool] = True
    human_approval_default: Optional[bool] = False
    review_focus: Optional[list[str]] = None
    success_criteria: Optional[list[str]] = None
    insert_after: Optional[str] = Field(default=None, max_length=64)


class ReorderPipelineStagesBody(BaseModel):
    stage_names: list[str] = Field(min_length=1)


class UpdateSkillBody(BaseModel):
    content: str = Field(max_length=500_000)


class EditPreviewStartBody(BaseModel):
    runtime: str = Field(min_length=1, max_length=32)
    mode: str = Field(default="studio", max_length=16)
    scaffold: bool = False


def _ui_html(name: str, assets: tuple[str, ...]) -> HTMLResponse:
    html = (UI_DIR / name).read_text(encoding="utf-8")
    for asset in assets:
        path = UI_DIR / asset
        if path.is_file():
            version = str(int(path.stat().st_mtime))
            html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={version}")
    return HTMLResponse(html)


class ChangeHub:
    """Fan-out of project-change notifications to SSE subscribers.

    Subscriptions are filtered: a board subscribed to one project only ever
    receives that project's ids, so unrelated-project bursts can't flood its
    queue and starve out the one notification it actually needs.
    """

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue, Optional[str]] = {}

    def subscribe(self, project_id: Optional[str] = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers[q] = project_id
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.pop(q, None)

    def publish(self, project_id: str) -> None:
        for q, only in list(self._subscribers.items()):
            if only is not None and only != project_id:
                continue
            try:
                q.put_nowait(project_id)
            except asyncio.QueueFull:
                # Queue holds only THIS subscriber's relevant ids, so a full
                # queue already guarantees a pending wake-up → safe to drop.
                pass


hub = ChangeHub()

# Library summaries are expensive to derive (full state parse per project);
# cache per project and invalidate from the watcher.
_summary_cache: dict[str, dict] = {}


def _invalidate_summary(project_id: str) -> None:
    _summary_cache.pop(project_id, None)


def _cached_summaries() -> list[dict]:
    if not PROJECTS_DIR.is_dir():
        return []
    summaries = []
    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if _is_demo_project(entry):
            _summary_cache.pop(entry.name, None)
            continue
        cached = _summary_cache.get(entry.name)
        if cached is None:
            try:
                cached = summarize_project(entry)
            except Exception:
                cached = {
                    "project_id": entry.name, "title": entry.name,
                    "pipeline_type": "unknown", "pipeline_label_zh": "未知",
                    "has_pipeline_state": False,
                    "poster": None, "live": False, "last_activity": 0,
                    "active_stage": None, "awaiting_human": False,
                    "stage_states": [], "completed_count": 0,
                    "render_count": 0, "scene_count": 0, "error": "unreadable",
                }
            _summary_cache[entry.name] = cached
        summaries.append(cached)
    summaries.sort(key=lambda s: (not s["live"], -(s["last_activity"] or 0)))
    return summaries


# Watch-loop hot path: pure string comparison, no per-path filesystem calls
# (change batches can be thousands of paths during a render).
import os as _os

_PROJECTS_ROOT_STR = _os.path.normcase(str(PROJECTS_DIR.resolve()))


def _project_of_change(path_str: str) -> Optional[str]:
    """Map a changed filesystem path to a project id (None = irrelevant)."""
    norm = _os.path.normcase(_os.path.normpath(path_str))
    if not norm.startswith(_PROJECTS_ROOT_STR):
        return None
    rel = norm[len(_PROJECTS_ROOT_STR):].lstrip("\\/")
    if not rel:
        return None
    parts = rel.replace("\\", "/").split("/")
    if _IGNORE_PARTS.intersection(parts):
        return None
    return parts[0]


async def _watch_projects() -> None:
    """Background task: watch projects/ and publish debounced changes."""
    try:
        from watchfiles import awatch
    except ImportError:
        return  # watcher unavailable → board still works via manual refresh
    if not PROJECTS_DIR.is_dir():
        return
    async for changes in awatch(PROJECTS_DIR, recursive=True, step=400):
        touched: set[str] = set()
        for _change, path_str in changes:
            pid = _project_of_change(path_str)
            if pid:
                touched.add(pid)
        for pid in touched:
            _invalidate_summary(pid)
            hub.publish(pid)


def create_app() -> FastAPI:
    app = FastAPI(title="Backlot", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup() -> None:
        from lib.env_loader import load_env
        load_env(REPO_ROOT)
        app.state.watch_task = asyncio.create_task(_watch_projects())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "watch_task", None)
        if task:
            task.cancel()

    # ---- API ----------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "app": "backlot", "api_version": API_VERSION}

    @app.get("/api/projects")
    async def projects() -> list:
        return await asyncio.to_thread(_cached_summaries)

    @app.get("/api/pipelines")
    async def pipelines() -> list:
        return await asyncio.to_thread(list_pipeline_catalog)

    @app.get("/api/style-playbooks")
    async def style_playbooks() -> list:
        return await asyncio.to_thread(list_style_playbook_options)

    @app.get("/api/settings")
    async def app_settings() -> dict:
        return await asyncio.to_thread(app_settings_response)

    @app.patch("/api/settings")
    async def patch_app_settings(payload: UpdateAppSettingsBody) -> dict:
        try:
            return await asyncio.to_thread(
                update_app_settings,
                default_style_playbook=payload.default_style_playbook,
                default_bootstrap_notes=payload.default_bootstrap_notes,
                theme=payload.theme,
                font_scale=payload.font_scale,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/system/env-vars")
    async def system_env_vars() -> dict:
        return await asyncio.to_thread(build_env_catalog)

    @app.patch("/api/system/env-vars")
    async def patch_system_env_vars(payload: UpdateEnvVarsBody) -> dict:
        try:
            return await asyncio.to_thread(update_env_vars, payload.values)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/system/dependencies")
    async def system_dependencies(check: bool = False, verify: bool = False) -> dict:
        if check or verify:
            return await asyncio.to_thread(run_system_check, verify=verify)
        return await asyncio.to_thread(build_dependency_manifest)

    @app.get("/api/system/catalog")
    async def system_catalog() -> dict:
        return await asyncio.to_thread(build_skill_tool_catalog)

    @app.get("/api/system/pipelines")
    async def system_pipelines() -> dict:
        return await asyncio.to_thread(build_pipeline_admin_catalog)

    @app.patch("/api/system/pipelines/{pipeline_id}")
    async def patch_system_pipeline(pipeline_id: str, payload: UpdatePipelineUiBody) -> dict:
        try:
            return await asyncio.to_thread(
                update_pipeline_ui,
                pipeline_id,
                hidden=payload.hidden,
                label_zh=payload.label_zh,
                summary_zh=payload.summary_zh,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/system/pipelines/{pipeline_id}/config")
    async def system_pipeline_config(pipeline_id: str) -> dict:
        try:
            return await asyncio.to_thread(get_pipeline_config, pipeline_id)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/system/pipelines/{pipeline_id}/manifest")
    async def patch_system_pipeline_manifest(
        pipeline_id: str,
        payload: UpdatePipelineManifestBody,
    ) -> dict:
        try:
            return await asyncio.to_thread(
                update_pipeline_manifest,
                pipeline_id,
                **payload.model_dump(exclude_unset=True),
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/system/pipelines/{pipeline_id}/editor-hints")
    async def system_pipeline_editor_hints(pipeline_id: str) -> dict:
        try:
            return await asyncio.to_thread(build_pipeline_editor_hints, pipeline_id)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/system/pipelines/{pipeline_id}/stages/{stage_name}")
    async def patch_system_pipeline_stage(
        pipeline_id: str,
        stage_name: str,
        payload: UpdatePipelineStageBody,
    ) -> dict:
        try:
            return await asyncio.to_thread(
                update_pipeline_stage,
                pipeline_id,
                stage_name,
                **payload.model_dump(exclude_unset=True),
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/system/pipelines/{pipeline_id}/stages")
    async def post_system_pipeline_stage(
        pipeline_id: str,
        payload: CreatePipelineStageBody,
    ) -> dict:
        try:
            return await asyncio.to_thread(
                add_pipeline_stage,
                pipeline_id,
                **payload.model_dump(exclude_unset=True),
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/system/pipelines/{pipeline_id}/stages/{stage_name}")
    async def delete_system_pipeline_stage(pipeline_id: str, stage_name: str) -> dict:
        try:
            return await asyncio.to_thread(delete_pipeline_stage, pipeline_id, stage_name)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/system/pipelines/{pipeline_id}/stages/order")
    async def put_system_pipeline_stage_order(
        pipeline_id: str,
        payload: ReorderPipelineStagesBody,
    ) -> dict:
        try:
            return await asyncio.to_thread(
                reorder_pipeline_stages,
                pipeline_id,
                payload.stage_names,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/system/skills/{skill_path:path}")
    async def system_skill_content(skill_path: str) -> dict:
        try:
            return await asyncio.to_thread(read_skill_markdown, skill_path)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/system/skills/{skill_path:path}")
    async def patch_system_skill_content(skill_path: str, payload: UpdateSkillBody) -> dict:
        try:
            return await asyncio.to_thread(write_skill_markdown, skill_path, payload.content)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/stage-media")
    async def stage_media(file: UploadFile = File(...)) -> dict:
        """Upload local media for bootstrap; returns server path for create_project ingest."""
        try:
            return await asyncio.to_thread(
                stage_uploaded_media,
                filename=file.filename or "upload.bin",
                stream=file.file,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects")
    async def create_project(payload: CreateProjectBody) -> dict:
        try:
            result = await asyncio.to_thread(
                create_project_workspace,
                project_id=payload.project_id,
                title=payload.title,
                pipeline_type=payload.pipeline_type,
                style_playbook=payload.style_playbook,
                notes=payload.notes,
                inputs=payload.inputs,
                projects_dir=PROJECTS_DIR,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _invalidate_summary(result["project_id"])
        hub.publish(result["project_id"])
        return result

    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str) -> dict:
        try:
            result = await asyncio.to_thread(
                delete_project_workspace,
                project_id=project_id,
                projects_dir=PROJECTS_DIR,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _invalidate_summary(result["project_id"])
        hub.publish(result["project_id"])
        return result

    @app.get("/api/project/{project_id}/settings")
    async def project_settings(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            return await asyncio.to_thread(load_project_settings, project_dir)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/project/{project_id}/settings")
    async def patch_project_settings(project_id: str, payload: UpdateProjectSettingsBody) -> dict:
        _safe_project_dir(project_id)
        try:
            result = await asyncio.to_thread(
                update_project_settings,
                project_id=project_id,
                title=payload.title,
                style_playbook=payload.style_playbook,
                notes=payload.notes,
                inputs=payload.inputs,
                replace_media=payload.replace_media,
                projects_dir=PROJECTS_DIR,
            )
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return result

    @app.get("/api/project/{project_id}/state")
    async def project_state(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(load_board_state, project_dir)

    @app.get("/api/project/{project_id}/composition-timeline")
    async def composition_timeline(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        edit_path = project_dir / "artifacts" / "edit_decisions.json"
        if not edit_path.is_file():
            raise HTTPException(status_code=404, detail="edit_decisions 不存在")
        edit = json.loads(edit_path.read_text(encoding="utf-8"))
        return await asyncio.to_thread(build_composition_timeline, edit)

    @app.get("/api/project/{project_id}/edit-preview")
    async def edit_preview_info(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(build_edit_preview_info, project_dir)

    @app.post("/api/project/{project_id}/edit-preview/start")
    async def edit_preview_start(project_id: str, payload: EditPreviewStartBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            return await asyncio.to_thread(
                start_edit_preview,
                project_dir,
                runtime=payload.runtime,
                mode=payload.mode,
                scaffold=payload.scaffold,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/project/{project_id}/events")
    async def project_events(project_id: str, request: Request) -> StreamingResponse:
        _safe_project_dir(project_id)  # 404 early for unknown projects

        async def stream():
            q = hub.subscribe(project_id)
            try:
                yield _sse({"type": "hello", "project_id": project_id})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    # Coalesce bursts: drain anything else queued.
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change", "project_id": project_id})
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/api/library/events")
    async def library_events(request: Request) -> StreamingResponse:
        async def stream():
            q = hub.subscribe()
            try:
                yield _sse({"type": "hello"})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        changed = await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change", "project_id": changed})
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ---- Thumbnails (downscaled, cached on disk) ------------------------

    @app.get("/thumb/{project_id}/{file_path:path}")
    async def thumb(project_id: str, file_path: str, w: int = 640) -> FileResponse:
        project_dir = _safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        width = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
        cached = await asyncio.to_thread(_thumbnail_for, target, width)
        if cached is None:
            # Never fall back to raw video bytes for an <img> consumer (F-03);
            # non-thumbable images are safe to serve as-is.
            if target.suffix.lower() in {".mp4", ".webm", ".mov"}:
                raise HTTPException(status_code=404, detail="no poster frame available")
            return FileResponse(target)
        return FileResponse(cached, media_type="image/jpeg")

    # ---- Media (range requests handled by FileResponse) ---------------

    @app.get("/media/{project_id}/{file_path:path}")
    async def media(project_id: str, file_path: str) -> FileResponse:
        project_dir = _safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        return FileResponse(target)

    # ---- UI ------------------------------------------------------------

    @app.get("/p/{project_id}")
    async def board_page(project_id: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"))

    @app.get("/p/{project_path:path}")
    async def board_page_path(project_path: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"))

    @app.get("/pipelines")
    async def pipelines_list_page() -> HTMLResponse:
        return _ui_html("pipelines.html", ("board.css", "manifest-form.js", "md-editor.js", "loading.js", "pipelines.js", "i18n.js"))

    @app.get("/pipelines/{pipeline_id}")
    async def pipelines_config_page(pipeline_id: str) -> HTMLResponse:
        return _ui_html("pipelines.html", ("board.css", "manifest-form.js", "md-editor.js", "loading.js", "pipelines.js", "i18n.js"))

    @app.get("/")
    async def library_page() -> HTMLResponse:
        return _ui_html("index.html", ("board.css", "library.js", "i18n.js"))

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
    assets_dir = REPO_ROOT / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # The board is a long-lived SPA: a tab keeps running whatever board.js it
    # loaded, and browsers heuristically cache /ui assets. no-cache forces a
    # conditional revalidation (cheap 304 via ETag) on every load so UI fixes
    # show up on a plain refresh. Media/thumb responses keep normal caching.
    @app.middleware("http")
    async def ui_no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/ui") or path.startswith("/p/") or path.startswith("/pipelines"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def _safe_project_dir(project_id: str) -> Path:
    # ':' rejects Windows drive-relative ids like "C:" (PROJECTS_DIR / "C:"
    # collapses back to PROJECTS_DIR itself).
    if any(c in project_id for c in "/\\:") or project_id in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid project id")
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    return project_dir


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _thumbnail_for(source: Path, width: int) -> Optional[Path]:
    """Downscale an image (or extract a video poster frame) to a cached JPEG."""
    suffix = source.suffix.lower()
    is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    is_video = suffix in {".mp4", ".webm", ".mov"}
    if not (is_image or is_video):
        return None
    try:
        import hashlib
        stat = source.stat()
        key = hashlib.sha1(
            f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{width}".encode()
        ).hexdigest()[:20]
        cached = THUMB_CACHE_DIR / f"{key}.jpg"
        if cached.is_file():
            return cached
        THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Unique temp per request — concurrent misses for the same source
        # must not write (and replace from) the same temp file.
        import uuid
        tmp = THUMB_CACHE_DIR / f"{key}.{uuid.uuid4().hex[:8]}.tmp.jpg"
        if is_video:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.5",
                 "-i", str(source), "-frames:v", "1",
                 "-vf", f"scale={width}:-2", str(tmp)],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not tmp.is_file():
                return None
        else:
            from PIL import Image
            with Image.open(source) as img:
                img = img.convert("RGB")
                img.thumbnail((width, width * 3))
                img.save(tmp, "JPEG", quality=82)
        tmp.replace(cached)
        return cached
    except Exception:
        return None


app = create_app()
