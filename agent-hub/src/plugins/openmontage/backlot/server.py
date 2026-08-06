"""Backlot server — FastAPI routers: board state API, SSE, media, UI.

The project **board** is primarily a read-only observer: it derives stage/
script/storyboard state from files the pipeline already writes under
``projects/``. The **library** may still bootstrap empty workspaces via
``POST .../projects`` (``init_project`` only — no checkpoints, no agent
orchestration); that write path lives in ``backlot.bootstrap``.

Routes are split across ``APIRouter`` builders so Hermes can mount them
under plugin namespaces:

- API: ``/api/plugins/openmontage`` (or ``/api`` standalone)
- UI: ``/plugins/openmontage`` (or ``/`` standalone)
- Media/thumb share the API mount prefix when hub-mounted

``create_app()`` remains a thin wrapper that remounts routers at standalone
paths for TestClient / ``uvicorn`` tooling.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from plugins.openmontage.backlot.env_config import build_env_catalog, update_env_vars
from plugins.openmontage.backlot.app_settings import app_settings_response, update_app_settings
from plugins.openmontage.backlot.pipeline_admin import (
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
from plugins.openmontage.backlot.skill_tool_catalog import build_skill_tool_catalog
from plugins.openmontage.backlot.system_check import build_dependency_manifest, run_system_check
from plugins.openmontage.backlot.bootstrap import (
    BootstrapError,
    create_project_workspace,
    delete_project_workspace,
    list_pipeline_catalog,
    list_style_playbook_options,
    load_project_settings,
    stage_uploaded_media,
    update_project_settings,
)
from plugins.openmontage.backlot.flow_layout import load_flow_layout, save_flow_layout
from plugins.openmontage.backlot import API_VERSION
from plugins.openmontage.backlot.edit_preview import build_edit_preview_info, start_edit_preview
from plugins.openmontage.backlot.nle_edit import (
    DraftStaleError,
    apply_draft,
    read_draft,
    read_draft_props,
    write_draft,
)
from plugins.openmontage.backlot import stage_runner
from plugins.openmontage.lib.composition_timeline import build_composition_timeline
from plugins.openmontage.backlot.state import PROJECTS_DIR, REPO_ROOT, _is_demo_project, list_projects, load_board_state, summarize_project
from plugins.openmontage.lib.paths import BACKLOT_STATE_DIR

UI_DIR = Path(__file__).resolve().parent / "ui"
BRAND_DIR = REPO_ROOT / "assets"
THUMB_CACHE_DIR = BACKLOT_STATE_DIR / "thumbs"
THUMB_WIDTHS = (320, 640, 960)
_BRAND_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}

# Paths inside a project whose changes are pure noise for the board.
_IGNORE_PARTS = {"node_modules", ".git", "__pycache__", ".cache"}

SSE_HEARTBEAT_SECONDS = 15

_runtime_started = False
_watch_task: Optional[asyncio.Task] = None


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


class FlowLayoutBody(BaseModel):
    stages: Optional[dict[str, dict[str, float]]] = None
    viewport: Optional[dict[str, float]] = None


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


class NleEditBody(BaseModel):
    cuts: list[dict[str, Any]]
    overlays: Optional[list[dict[str, Any]]] = None
    decision_note: str = Field(default="", max_length=400)


class StageRunBody(BaseModel):
    stage: Optional[str] = Field(default=None, min_length=1, max_length=64)
    parameters: Optional[dict[str, Any]] = None
    feedback: Optional[str] = Field(default=None, max_length=2000)


class PipelineResetBody(BaseModel):
    from_stage: Optional[str] = Field(default=None, min_length=1, max_length=64)


class DecisionAppendBody(BaseModel):
    stage: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    # decision_log schema: options_considered 是对象数组(option_id/label/score/reason 必填)
    options_considered: list[str] = Field(default_factory=list, max_length=64)
    selected: str = Field(min_length=1, max_length=500)
    reason: str = Field(default="", max_length=400)


class StageApproveBody(BaseModel):
    stage: str = Field(min_length=1, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)


class StageRejectBody(BaseModel):
    stage: str = Field(min_length=1, max_length=64)
    feedback: str = Field(min_length=5, max_length=4000)


def mount_prefixes(*, hub: bool = False) -> dict[str, str]:
    if hub:
        return {
            "apiPrefix": "/api/plugins/openmontage",
            "uiPrefix": "/plugins/openmontage",
            "mediaPrefix": "/api/plugins/openmontage",
        }
    return {"apiPrefix": "/api", "uiPrefix": "", "mediaPrefix": ""}


def _ui_html(
    name: str,
    assets: tuple[str, ...],
    *,
    apiPrefix: str = "/api",
    uiPrefix: str = "",
    mediaPrefix: str = "",
) -> HTMLResponse:
    html = (UI_DIR / name).read_text(encoding="utf-8")
    brand_base = f"{uiPrefix}/brand" if uiPrefix else "/brand"
    html = html.replace("/assets/", f"{brand_base}/")

    # Cache-bust listed assets; rewrite into the UI mount when hub-prefixed.
    for asset in assets:
        path = UI_DIR / asset
        if not path.is_file():
            continue
        version = str(int(path.stat().st_mtime))
        replacement = f"{uiPrefix}/ui/{asset}?v={version}"
        html = re.sub(
            rf'/ui/{re.escape(asset)}(?:\?[^"\']*)?',
            replacement,
            html,
        )

    if uiPrefix:
        # Static nav / leftover asset tags (import map only covers ES module imports).
        html = html.replace('href="/"', f'href="{uiPrefix}/"')
        html = html.replace('href="/ui/', f'href="{uiPrefix}/ui/')
        html = html.replace('src="/ui/', f'src="{uiPrefix}/ui/')

    config = (
        "<script>window.__BACKLOT__="
        f"{{apiPrefix:{json.dumps(apiPrefix)},"
        f"uiPrefix:{json.dumps(uiPrefix)},"
        f"mediaPrefix:{json.dumps(mediaPrefix)}}};</script>"
    )
    inject = config
    if uiPrefix:
        import_map = json.dumps({"imports": {"/ui/": f"{uiPrefix}/ui/"}}, separators=(",", ":"))
        inject += f'<script type="importmap">{import_map}</script>'

    head_idx = html.find("<head>")
    if head_idx >= 0:
        insert_at = head_idx + len("<head>")
        html = html[:insert_at] + inject + html[insert_at:]
    else:
        html = inject + html
    return HTMLResponse(html)


def _safe_under(root: Path, file_path: str) -> Path:
    """Resolve file_path under root; reject traversal and missing files."""
    if not file_path or file_path.startswith(("/", "\\")) or ".." in Path(file_path).parts:
        raise HTTPException(status_code=403, detail="path escapes root")
    root_resolved = root.resolve()
    target = (root_resolved / file_path).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="path escapes root") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return target


async def ensure_runtime() -> None:
    """Idempotent: load env, start watcher, reconcile. Call from first SSE or on_ready."""
    global _runtime_started, _watch_task
    if _runtime_started:
        return
    _runtime_started = True
    from plugins.openmontage.lib.env_loader import load_env
    load_env(REPO_ROOT)
    try:
        await stage_runner.reconcile_runs()
    except Exception:
        pass
    try:
        loop = asyncio.get_running_loop()
        _watch_task = loop.create_task(_watch_projects())
    except RuntimeError:
        pass


def start_runtime_sync() -> None:
    """Called from plugin on_ready (sync). Watcher starts on first SSE via ensure_runtime."""
    from plugins.openmontage.lib.env_loader import load_env
    load_env(REPO_ROOT)


def _needs_ui_no_cache(path: str) -> bool:
    if path in {"/", ""}:
        return True
    if path.endswith(("/plugins/openmontage", "/plugins/openmontage/")):
        return True
    return (
        "/ui" in path
        or "/p/" in path
        or "/flow" in path
        or "/pipelines" in path
        or path.endswith(".html")
    )


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


def build_api_router() -> APIRouter:
    """JSON / SSE API routes without the `/api` prefix (caller mounts it)."""
    router = APIRouter()


    @router.get("/health")
    async def health() -> dict:
        return {"ok": True, "app": "backlot", "api_version": API_VERSION}

    @router.get("/projects")
    async def projects() -> list:
        return await asyncio.to_thread(_cached_summaries)

    @router.get("/pipelines")
    async def pipelines() -> list:
        return await asyncio.to_thread(list_pipeline_catalog)

    @router.get("/style-playbooks")
    async def style_playbooks() -> list:
        return await asyncio.to_thread(list_style_playbook_options)

    @router.get("/settings")
    async def app_settings() -> dict:
        return await asyncio.to_thread(app_settings_response)

    @router.patch("/settings")
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

    @router.get("/system/env-vars")
    async def system_env_vars() -> dict:
        return await asyncio.to_thread(build_env_catalog)

    @router.patch("/system/env-vars")
    async def patch_system_env_vars(payload: UpdateEnvVarsBody) -> dict:
        try:
            return await asyncio.to_thread(update_env_vars, payload.values)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/system/dependencies")
    async def system_dependencies(check: bool = False, verify: bool = False) -> dict:
        if check or verify:
            return await asyncio.to_thread(run_system_check, verify=verify)
        return await asyncio.to_thread(build_dependency_manifest)

    @router.get("/system/catalog")
    async def system_catalog() -> dict:
        return await asyncio.to_thread(build_skill_tool_catalog)

    @router.get("/system/pipelines")
    async def system_pipelines() -> dict:
        return await asyncio.to_thread(build_pipeline_admin_catalog)

    @router.patch("/system/pipelines/{pipeline_id}")
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

    @router.get("/system/pipelines/{pipeline_id}/config")
    async def system_pipeline_config(pipeline_id: str) -> dict:
        try:
            return await asyncio.to_thread(get_pipeline_config, pipeline_id)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/system/pipelines/{pipeline_id}/manifest")
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

    @router.get("/system/pipelines/{pipeline_id}/editor-hints")
    async def system_pipeline_editor_hints(pipeline_id: str) -> dict:
        try:
            return await asyncio.to_thread(build_pipeline_editor_hints, pipeline_id)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/system/pipelines/{pipeline_id}/stages/{stage_name}")
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

    @router.post("/system/pipelines/{pipeline_id}/stages")
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

    @router.delete("/system/pipelines/{pipeline_id}/stages/{stage_name}")
    async def delete_system_pipeline_stage(pipeline_id: str, stage_name: str) -> dict:
        try:
            return await asyncio.to_thread(delete_pipeline_stage, pipeline_id, stage_name)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/system/pipelines/{pipeline_id}/stages/order")
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

    @router.get("/system/skills/{skill_path:path}")
    async def system_skill_content(skill_path: str) -> dict:
        try:
            return await asyncio.to_thread(read_skill_markdown, skill_path)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/system/skills/{skill_path:path}")
    async def patch_system_skill_content(skill_path: str, payload: UpdateSkillBody) -> dict:
        try:
            return await asyncio.to_thread(write_skill_markdown, skill_path, payload.content)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/stage-media")
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

    @router.post("/projects")
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

    @router.delete("/projects/{project_id}")
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

    @router.get("/project/{project_id}/settings")
    async def project_settings(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            return await asyncio.to_thread(load_project_settings, project_dir)
        except BootstrapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/project/{project_id}/settings")
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

    @router.get("/project/{project_id}/flow-layout")
    async def project_flow_layout(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(load_flow_layout, project_dir)

    @router.patch("/project/{project_id}/flow-layout")
    async def patch_project_flow_layout(project_id: str, payload: FlowLayoutBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(
            save_flow_layout,
            project_dir,
            stages=payload.stages,
            viewport=payload.viewport,
        )

    @router.get("/project/{project_id}/state")
    async def project_state(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(load_board_state, project_dir)

    @router.get("/project/{project_id}/composition-timeline")
    async def composition_timeline(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        edit_path = project_dir / "artifacts" / "edit_decisions.json"
        if not edit_path.is_file():
            raise HTTPException(status_code=404, detail="edit_decisions 不存在")
        edit = json.loads(edit_path.read_text(encoding="utf-8"))
        return await asyncio.to_thread(build_composition_timeline, edit)

    @router.get("/project/{project_id}/edit-preview")
    async def edit_preview_info(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(build_edit_preview_info, project_dir)

    @router.post("/project/{project_id}/edit-preview/start")
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

    @router.get("/project/{project_id}/nle-edit/draft-props")
    async def nle_draft_props(project_id: str, request: Request, response: Response) -> dict:
        """Live preview props for the NLE preview iframe (cross-origin polled)."""
        project_dir = _safe_project_dir(project_id)
        # Cross-origin only for the NLE preview iframe, which is served from
        # the local preview-server port (localhost:34xx) — never a wildcard.
        origin = request.headers.get("origin") or ""
        if re.match(r"^http://localhost:34\d+$", origin):
            response.headers["Access-Control-Allow-Origin"] = origin
        try:
            return await asyncio.to_thread(read_draft_props, project_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/project/{project_id}/nle-edit/preview")
    async def nle_edit_preview(project_id: str, payload: NleEditBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        result = await asyncio.to_thread(write_draft, project_dir, payload.cuts, payload.overlays)
        hub.publish(project_id)
        return result

    @router.post("/project/{project_id}/nle-edit/apply")
    async def nle_edit_apply(project_id: str, payload: NleEditBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            # Applied content comes from the persisted draft file, not the
            # request body (see apply_draft).
            result = await asyncio.to_thread(
                apply_draft,
                project_dir,
                decision_note=payload.decision_note,
            )
        except DraftStaleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        hub.publish(project_id)
        return result

    @router.get("/project/{project_id}/nle-edit/draft")
    async def nle_edit_draft(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return await asyncio.to_thread(read_draft, project_dir)

    # ---- Headless-agent stage channel ----------------------------------

    @router.post("/project/{project_id}/pipeline/reset")
    async def pipeline_reset(project_id: str, payload: PipelineResetBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        busy = await asyncio.to_thread(stage_runner._busy_or_none, project_dir)
        if busy:
            raise HTTPException(status_code=409, detail=busy)
        from plugins.openmontage.lib.pipeline_reset import PipelineResetError, reset_from_stage, reset_to_first_stage

        def _do_reset() -> dict:
            if payload.from_stage:
                return reset_from_stage(project_id, payload.from_stage)
            return reset_to_first_stage(project_id)

        try:
            result = await asyncio.to_thread(_do_reset)
        except PipelineResetError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return result

    @router.post("/project/{project_id}/stage/run", status_code=202)
    async def stage_run(project_id: str, payload: StageRunBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            task = await asyncio.to_thread(
                stage_runner.prepare_stage_run,
                project_dir,
                stage=payload.stage,
                parameters=payload.parameters,
                feedback=payload.feedback,
            )
        except stage_runner.StageRunError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        asyncio.create_task(stage_runner.run_task(task))
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return {
            "ok": True,
            "task_id": task.task_id,
            "stage": task.stage,
            "status": task.status,
            "started_at": task.started_at,
            "log_path": f"runs/{task.task_id}.log",
        }

    @router.post("/project/{project_id}/decisions")
    async def append_project_decision(project_id: str, payload: DecisionAppendBody) -> dict:
        """Flow 节点核心信息保存:append 一条 decision_log 条目(审计 + board 展示)。"""
        project_dir = _safe_project_dir(project_id)
        from plugins.openmontage.lib.decision_log import append_decisions, suggest_next_decision_id

        decision_id = await asyncio.to_thread(suggest_next_decision_id, project_dir)
        # schema 要求 options_considered 为对象数组(option_id/label/score/reason)
        options = [
            {
                "option_id": opt,
                "label": opt,
                "score": 0,
                "reason": "flow 节点选项",
            }
            for opt in payload.options_considered
        ]
        try:
            await asyncio.to_thread(
                append_decisions,
                project_id,
                [{
                    "decision_id": decision_id,
                    "stage": payload.stage,
                    "category": payload.category,
                    "subject": payload.subject,
                    "options_considered": options,
                    "selected": payload.selected,
                    "reason": payload.reason,
                    "user_visible": True,
                    "user_approved": True,
                }],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return {"ok": True, "decision_id": decision_id}

    @router.get("/project/{project_id}/stage/runs")
    async def stage_runs(project_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        return {"runs": await asyncio.to_thread(stage_runner.list_runs, project_dir, limit=8)}

    @router.get("/project/{project_id}/stage/run/{task_id}/log")
    async def stage_run_log(
        project_id: str, task_id: str, offset: int = 0, limit: int = 200,
    ) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            return await asyncio.to_thread(
                stage_runner.read_run_log, project_dir, task_id,
                offset=offset, limit=limit,
            )
        except stage_runner.StageRunError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/project/{project_id}/stage/run/{task_id}/cancel")
    async def stage_run_cancel(project_id: str, task_id: str) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            result = await asyncio.to_thread(stage_runner.cancel_run, project_dir, task_id)
        except stage_runner.StageRunError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return result

    @router.post("/project/{project_id}/stage/approve")
    async def stage_approve(project_id: str, payload: StageApproveBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            result = await asyncio.to_thread(
                stage_runner.approve_stage,
                project_dir,
                payload.stage,
                notes=payload.notes or "",
            )
        except stage_runner.StageRunError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        asyncio.create_task(stage_runner.auto_advance_chain(project_dir, from_stage=result["stage"]))
        return result

    @router.post("/project/{project_id}/stage/reject")
    async def stage_reject(project_id: str, payload: StageRejectBody) -> dict:
        project_dir = _safe_project_dir(project_id)
        try:
            result = await asyncio.to_thread(
                stage_runner.reject_stage,
                project_dir,
                payload.stage,
                feedback=payload.feedback,
            )
        except stage_runner.StageRunError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        _invalidate_summary(project_id)
        hub.publish(project_id)
        return result

    @router.get("/project/{project_id}/events")
    async def project_events(project_id: str, request: Request) -> StreamingResponse:
        await ensure_runtime()
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

    @router.get("/library/events")
    async def library_events(request: Request) -> StreamingResponse:
        await ensure_runtime()

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

    return router


def build_media_router() -> APIRouter:
    """Media and thumbnail routes at mount-relative `/media` and `/thumb`."""
    router = APIRouter()

    # ---- Thumbnails (downscaled, cached on disk) ------------------------

    @router.get("/thumb/{project_id}/{file_path:path}")
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

    @router.get("/media/{project_id}/{file_path:path}")
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

    return router


def build_ui_router(*, hub: bool = False) -> APIRouter:
    """HTML pages, `/ui` assets, and `/brand` images."""
    router = APIRouter()
    prefixes = mount_prefixes(hub=hub)

    # ---- UI ------------------------------------------------------------

    @router.get("/p/{project_id}")
    async def board_page(project_id: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"), **prefixes)

    @router.get("/p/{project_path:path}")
    async def board_page_path(project_path: str) -> HTMLResponse:
        return _ui_html("board.html", ("board.css", "board.js"), **prefixes)

    @router.get("/flow/{project_id}")
    async def flow_page(project_id: str) -> HTMLResponse:
        if not (UI_DIR / "flow-dist" / "flow.js").is_file():
            raise HTTPException(
                status_code=503,
                detail="flow 视图未构建,请先运行: npm run build:flow",
            )
        return _ui_html(
            "flow.html",
            ("board.css", "flow-dist/flow.css", "flow-dist/flow.js"),
            **prefixes,
        )

    @router.get("/pipelines")
    async def pipelines_list_page() -> HTMLResponse:
        return _ui_html(
            "pipelines.html",
            ("board.css", "manifest-form.js", "md-editor.js", "loading.js", "pipelines.js", "i18n.js"),
            **prefixes,
        )

    @router.get("/pipelines/{pipeline_id}")
    async def pipelines_config_page(pipeline_id: str) -> HTMLResponse:
        return _ui_html(
            "pipelines.html",
            ("board.css", "manifest-form.js", "md-editor.js", "loading.js", "pipelines.js", "i18n.js"),
            **prefixes,
        )

    @router.get("/")
    async def library_page() -> HTMLResponse:
        return _ui_html("index.html", ("board.css", "library.js", "i18n.js"), **prefixes)

    @router.get("/ui/{file_path:path}")
    async def ui_static(file_path: str) -> FileResponse:
        if not UI_DIR.is_dir():
            raise HTTPException(status_code=404, detail="ui not found")
        return FileResponse(_safe_under(UI_DIR, file_path))

    @router.get("/brand/{file_path:path}")
    async def brand_static(file_path: str) -> FileResponse:
        if not BRAND_DIR.is_dir():
            raise HTTPException(status_code=404, detail="brand assets not found")
        target = _safe_under(BRAND_DIR, file_path)
        if target.suffix.lower() not in _BRAND_SUFFIXES:
            raise HTTPException(status_code=403, detail="brand asset type not allowed")
        return FileResponse(target)

    return router


def build_routers() -> tuple[APIRouter, APIRouter, APIRouter]:
    return build_api_router(), build_media_router(), build_ui_router()


def create_app() -> FastAPI:
    app = FastAPI(title="Backlot", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup() -> None:
        await ensure_runtime()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        global _watch_task
        task = _watch_task
        if task:
            task.cancel()
            _watch_task = None

    api, media, ui = build_routers()
    app.include_router(api, prefix="/api")
    app.include_router(media)
    app.include_router(ui)

    # The board is a long-lived SPA: a tab keeps running whatever board.js it
    # loaded, and browsers heuristically cache /ui assets. no-cache forces a
    # conditional revalidation (cheap 304 via ETag) on every load so UI fixes
    # show up on a plain refresh. Media/thumb responses keep normal caching.
    @app.middleware("http")
    async def ui_no_cache(request, call_next):
        response = await call_next(request)
        if _needs_ui_no_cache(request.url.path):
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
