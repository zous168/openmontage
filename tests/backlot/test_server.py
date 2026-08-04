"""Server/API tests for Backlot.

These cover the deterministic eval surface in internal/evals/BACKLOT_EVAL_PLAN.md:
API shape, path safety, media/thumb serving, range requests, and loose
performance budgets.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backlot import API_VERSION
from backlot import server as server_mod
from backlot import state as state_mod
from backlot import app_settings as app_settings_mod


@pytest.fixture
def app_settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(app_settings_mod, "SETTINGS_PATH", path)
    return path


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(server_mod, "_PROJECTS_ROOT_STR", __import__("os").path.normcase(str(root.resolve())))
    monkeypatch.setattr(server_mod, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return root


@pytest.fixture
def client(projects_root, monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    with TestClient(server_mod.create_app()) as c:
        yield c


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_project(root: Path, project_id: str = "film") -> Path:
    project = root / project_id
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "renders").mkdir(parents=True)
    _write_json(
        project / "project.json",
        {
            "project_id": project_id,
            "title": "Film",
            "pipeline_type": "cinematic",
            "created_at": "2026-07-02T00:00:00Z",
        },
    )
    _write_json(
        project / "checkpoint_script.json",
        {
            "version": "1.0",
            "project_id": project_id,
            "pipeline_type": "cinematic",
            "stage": "script",
            "status": "awaiting_human",
            "timestamp": "2026-07-02T00:01:00Z",
            "artifacts": {},
        },
    )
    return project


def _write_png(path: Path, color: tuple[int, int, int] = (200, 40, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (24, 16), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


class TestBacklotServerApi:
    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "app": "backlot", "api_version": API_VERSION}

    def test_pipeline_reset_to_first_stage(self, client, projects_root, monkeypatch):
        import lib.paths as paths_mod

        monkeypatch.setattr(paths_mod, "PROJECTS_DIR", projects_root)
        project = _make_project(projects_root, "film")
        _write_json(
            project / "checkpoint_research.json",
            {
                "version": "1.0",
                "project_id": "film",
                "pipeline_type": "cinematic",
                "stage": "research",
                "status": "completed",
                "timestamp": "2026-07-02T00:00:30Z",
                "artifacts": {},
            },
        )

        res = client.post("/api/project/film/pipeline/reset", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["from_stage"] == "research"
        assert body["next_stage"] == "research"
        assert "script" in body["removed_stages"]
        assert "research" in body["removed_stages"]
        assert not (project / "checkpoint_script.json").exists()
        assert not (project / "checkpoint_research.json").exists()
        assert list((project / "history").glob("checkpoint_*_reset_*.json"))

    def test_style_playbooks_api_returns_chinese_labels(self, client):
        res = client.get("/api/style-playbooks")
        assert res.status_code == 200
        body = res.json()
        assert body[0]["label_zh"] == "默认（不指定）"
        labels = {item["value"]: item["label_zh"] for item in body if item["value"]}
        assert labels["clean-professional"] == "干净专业"
        assert labels["anime-ghibli"] == "吉卜力动画风"
        clean = next(item for item in body if item["value"] == "clean-professional")
        assert "hint_zh" in clean

    def test_projects_api_hides_demo_workspaces(self, client, projects_root):
        demo = projects_root / "backlot-demo-run"
        demo.mkdir()
        _write_json(demo / "project.json", {
            "project_id": "backlot-demo-run",
            "title": "The Last Lighthouse",
            "pipeline_type": "cinematic",
            "demo": True,
        })
        _make_project(projects_root, "real-film")

        res = client.get("/api/projects")
        assert res.status_code == 200
        ids = [p["project_id"] for p in res.json()]
        assert ids == ["real-film"]

        board = client.get("/api/project/backlot-demo-run/state")
        assert board.status_code == 200
        assert board.json()["title"] == "The Last Lighthouse"

    def test_projects_shape_and_state(self, client, projects_root):
        _make_project(projects_root, "film")

        projects = client.get("/api/projects")
        assert projects.status_code == 200
        body = projects.json()
        assert len(body) == 1
        assert body[0]["project_id"] == "film"
        assert body[0]["awaiting_human"] is True
        assert "stage_states" in body[0]

        state = client.get("/api/project/film/state")
        assert state.status_code == 200
        state_body = state.json()
        assert state_body["project_id"] == "film"
        assert state_body["title"] == "Film"
        assert state_body["stages"]

    def test_pipelines_catalog_excludes_internal(self, client):
        res = client.get("/api/pipelines")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list)
        assert len(body) >= 11
        ids = {p["id"] for p in body}
        assert "framework-smoke" not in ids
        assert "reference-driven" in ids
        assert "cinematic" in ids
        ref = next(p for p in body if p["id"] == "reference-driven")
        ref_keys = {f["key"] for f in ref["bootstrap_fields"]}
        assert "reference_url" in ref_keys
        assert "reference_media_path" in ref_keys
        assert "video_gen_clip_duration_seconds" in ref_keys
        assert "aspect_ratio" in ref_keys
        assert "quality_tier" in ref_keys
        sample = next(p for p in body if p["id"] == "cinematic")
        assert sample["label_zh"]
        assert "summary_zh" in sample
        assert "bootstrap_fields" in sample
        cine_keys = {f["key"] for f in sample["bootstrap_fields"]}
        assert "reference_url" in cine_keys
        assert "reference_media_path" in cine_keys
        th = next(p for p in body if p["id"] == "talking-head")
        assert any(f["key"] == "source_media_path" for f in th["bootstrap_fields"])
        clip = next(p for p in body if p["id"] == "clip-factory")
        assert any(f["key"] == "clip_count" for f in clip["bootstrap_fields"])
        loc = next(p for p in body if p["id"] == "localization-dub")
        assert any(f["key"] == "dub_mode" for f in loc["bootstrap_fields"])
        for p in body:
            assert p["bootstrap_fields"], f"{p['id']} missing bootstrap_fields"

    def test_reference_url_extracts_from_douyin_share_text(self):
        from backlot.bootstrap import normalize_media_url, validate_production_inputs

        share = (
            "2.35 复制打开抖音，看看【示例】 "
            "https://v.douyin.com/tyV7nsNEpOw/ "
            "07/31 TL:/"
        )
        assert normalize_media_url(share) == "https://v.douyin.com/tyV7nsNEpOw/"
        parsed = validate_production_inputs(
            "reference-driven",
            {"reference_url": share, "target_platform": "douyin"},
        )
        assert parsed["reference_url"] == "https://v.douyin.com/tyV7nsNEpOw/"

    def test_create_project_bootstraps_workspace(self, client, projects_root):
        res = client.post(
            "/api/projects",
            json={
                "project_id": "new-promo",
                "title": "春季带货",
                "pipeline_type": "avatar-spokesperson",
                "style_playbook": "clean-professional",
                "notes": "测试备注",
                "inputs": {
                    "topic": "春季新品口红带货",
                    "script_or_offer": "主打滋润不拔干，限时第二件半价",
                    "target_platform": "douyin",
                    "target_duration_seconds": 60,
                },
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["project_id"] == "new-promo"
        assert body["pipeline_type"] == "avatar-spokesperson"

        marker = projects_root / "new-promo" / "project.json"
        assert marker.is_file()
        marker_data = json.loads(marker.read_text(encoding="utf-8"))
        assert marker_data["title"] == "春季带货"
        assert marker_data["pipeline_type"] == "avatar-spokesperson"
        assert marker_data["style_playbook"] == "clean-professional"

        meta = projects_root / "new-promo" / "meta.json"
        assert meta.is_file()
        meta_data = json.loads(meta.read_text(encoding="utf-8"))
        assert meta_data["bootstrap_notes"] == "测试备注"
        assert meta_data["production_inputs"]["topic"] == "春季新品口红带货"
        assert meta_data["production_inputs"]["script_or_offer"] == "主打滋润不拔干，限时第二件半价"
        assert meta_data["production_inputs"]["target_platform"] == "douyin"

        listed = client.get("/api/projects").json()
        assert any(p["project_id"] == "new-promo" for p in listed)

        state = client.get("/api/project/new-promo/state")
        assert state.status_code == 200
        state_body = state.json()
        assert state_body["pipeline"]["pipeline_type"] == "avatar-spokesperson"
        assert state_body["style_playbook"] == "clean-professional"
        assert state_body["style_playbook_label_zh"] == "干净专业"

    def test_create_project_rejects_duplicate(self, client, projects_root):
        _make_project(projects_root, "taken")
        res = client.post(
            "/api/projects",
            json={
                "project_id": "taken",
                "title": "重复",
                "pipeline_type": "cinematic",
                "inputs": {
                    "topic": "测试主题",
                    "target_platform": "generic",
                    "target_duration_seconds": 90,
                },
            },
        )
        assert res.status_code == 400
        assert "已存在" in res.json()["detail"]

    def test_create_project_rejects_bad_id(self, client):
        res = client.post(
            "/api/projects",
            json={
                "project_id": "Bad ID!",
                "title": "x",
                "pipeline_type": "cinematic",
                "inputs": {
                    "topic": "x",
                    "target_platform": "generic",
                    "target_duration_seconds": 60,
                },
            },
        )
        assert res.status_code == 400

    def test_create_talking_head_requires_source(self, client, projects_root, tmp_path):
        res = client.post(
            "/api/projects",
            json={
                "project_id": "talk-vid",
                "title": "口播",
                "pipeline_type": "talking-head",
                "inputs": {"target_platform": "douyin"},
            },
        )
        assert res.status_code == 400
        assert "源素材" in res.json()["detail"]

    def test_create_talking_head_ingests_source(self, client, projects_root, tmp_path):
        src = tmp_path / "clip.mp4"
        src.write_bytes(b"\x00" * 128)
        res = client.post(
            "/api/projects",
            json={
                "project_id": "talk-vid",
                "title": "春季口播",
                "pipeline_type": "talking-head",
                "inputs": {
                    "source_media_path": str(src),
                    "target_platform": "douyin",
                    "target_duration_seconds": 45,
                },
            },
        )
        assert res.status_code == 200
        meta = json.loads((projects_root / "talk-vid" / "meta.json").read_text(encoding="utf-8"))
        assert meta["production_inputs"]["source_media_path"] == "assets/video/source.mp4"
        assert meta["production_inputs"]["target_platform"] == "douyin"
        assert (projects_root / "talk-vid" / "assets" / "video" / "source.mp4").is_file()

    def test_stage_media_upload_and_ingest(self, client, projects_root, tmp_path, monkeypatch):
        import backlot.bootstrap as boot
        staging = tmp_path / "staging"
        staging.mkdir()
        monkeypatch.setattr(boot, "MEDIA_STAGING_DIR", staging)

        files = {"file": ("demo.mp4", b"\x00" * 256, "video/mp4")}
        staged = client.post("/api/stage-media", files=files)
        assert staged.status_code == 200
        staged_path = staged.json()["path"]
        assert Path(staged_path).is_file()

        res = client.post(
            "/api/projects",
            json={
                "project_id": "upload-vid",
                "title": "上传口播",
                "pipeline_type": "talking-head",
                "inputs": {
                    "source_media_path": staged_path,
                    "target_platform": "douyin",
                },
            },
        )
        assert res.status_code == 200
        assert (projects_root / "upload-vid" / "assets" / "video" / "source.mp4").is_file()

    def test_create_documentary_montage_inputs(self, client, projects_root):
        res = client.post(
            "/api/projects",
            json={
                "project_id": "doc-m",
                "title": "蒙太奇",
                "pipeline_type": "documentary-montage",
                "inputs": {
                    "thematic_question": "互联网如何改变了我们的注意力？",
                    "tone_register": "contemplative",
                    "target_platform": "bilibili",
                    "target_duration_seconds": 120,
                },
            },
        )
        assert res.status_code == 200
        meta = json.loads((projects_root / "doc-m" / "meta.json").read_text(encoding="utf-8"))
        pi = meta["production_inputs"]
        assert pi["thematic_question"].startswith("互联网")
        assert pi["tone_register"] == "contemplative"

    def test_create_screen_demo_synthetic_without_source(self, client, projects_root):
        res = client.post(
            "/api/projects",
            json={
                "project_id": "demo-cli",
                "title": "CLI 演示",
                "pipeline_type": "screen-demo",
                "inputs": {
                    "production_mode": "synthetic_terminal",
                    "demo_brief": "演示 npm install 与首次运行",
                    "target_platform": "youtube",
                },
            },
        )
        assert res.status_code == 200

    def test_create_cinematic_with_reference(self, client, projects_root, tmp_path):
        ref_video = tmp_path / "ref.mp4"
        ref_video.write_bytes(b"\x00" * 128)

        res = client.post(
            "/api/projects",
            json={
                "project_id": "ref-clone",
                "title": "量子计算参考风格短片",
                "pipeline_type": "cinematic",
                "inputs": {
                    "topic": "面向高中生的 CRISPR 科普，保留参考片节奏感",
                    "reference_url": "https://www.youtube.com/shorts/example",
                    "reference_media_path": str(ref_video),
                    "target_platform": "douyin",
                    "target_duration_seconds": 45,
                },
            },
        )
        assert res.status_code == 200
        meta = json.loads((projects_root / "ref-clone" / "meta.json").read_text(encoding="utf-8"))
        assert meta["intake_mode"] == "reference"
        assert "meta/video-reference-analyst" in meta["required_meta_skills"]
        pi = meta["production_inputs"]
        assert pi["reference_url"].startswith("https://")
        assert pi["reference_media_path"] == "assets/video/reference.mp4"
        assert (projects_root / "ref-clone" / "assets" / "video" / "reference.mp4").is_file()

        listed = client.get("/api/projects").json()
        card = next(p for p in listed if p["project_id"] == "ref-clone")
        assert card["has_reference"] is True
        assert card["pipeline_type"] == "cinematic"

    def test_delete_project_removes_workspace(self, client, projects_root):
        _make_project(projects_root, "to-delete")
        assert (projects_root / "to-delete").is_dir()

        res = client.delete("/api/projects/to-delete")
        assert res.status_code == 200
        assert res.json() == {"project_id": "to-delete", "deleted": True}
        assert not (projects_root / "to-delete").exists()

        listed = client.get("/api/projects").json()
        assert not any(p["project_id"] == "to-delete" for p in listed)

    def test_delete_unknown_project(self, client):
        res = client.delete("/api/projects/missing-one")
        assert res.status_code == 400

    def test_delete_invalid_project_id(self, client):
        res = client.delete("/api/projects/not%20valid")
        assert res.status_code == 400

    def test_get_project_settings(self, client, projects_root):
        project = projects_root / "settings-demo"
        project.mkdir()
        _write_json(project / "project.json", {
            "project_id": "settings-demo",
            "title": "设置测试",
            "pipeline_type": "talking-head",
            "style_playbook": "clean-professional",
            "created_at": "2026-08-01T00:00:00Z",
        })
        _write_json(project / "meta.json", {
            "version": "1.0",
            "bootstrap_notes": "备注",
            "production_inputs": {
                "source_media_path": "assets/video/source.mp4",
                "target_platform": "douyin",
                "target_duration_seconds": 30,
            },
        })

        res = client.get("/api/project/settings-demo/settings")
        assert res.status_code == 200
        body = res.json()
        assert body["title"] == "设置测试"
        assert body["pipeline_type"] == "talking-head"
        assert body["style_playbook"] == "clean-professional"
        assert body["bootstrap_notes"] == "备注"
        assert body["production_inputs"]["target_platform"] == "douyin"
        assert any(f["key"] == "target_platform" for f in body["bootstrap_fields"])
        assert any(f["key"] == "aspect_ratio" for f in body["bootstrap_fields"])
        assert any(f["key"] == "thumbnail_text_hook" for f in body["bootstrap_fields"])
        assert body["deliverable"]["resolution"] == "1080x1920"
        assert body["cover_brief"]["source"] == "auto_frame"
        assert body["deliverable"]["aspect_ratio"] == "9:16"
        assert body["source_media"]["path"] == "assets/video/source.mp4"
        assert body["source_media"]["exists"] is False

    def test_flow_layout_get_and_patch(self, client, projects_root):
        project = projects_root / "flow-layout-demo"
        project.mkdir()
        _write_json(project / "project.json", {
            "project_id": "flow-layout-demo",
            "title": "Flow Layout",
            "pipeline_type": "cinematic",
            "created_at": "2026-08-01T00:00:00Z",
        })
        _write_json(project / "meta.json", {"version": "1.0"})

        empty = client.get("/api/project/flow-layout-demo/flow-layout")
        assert empty.status_code == 200
        assert empty.json()["stages"] == {}

        patched = client.patch(
            "/api/project/flow-layout-demo/flow-layout",
            json={
                "stages": {"script": {"x": 120, "y": 40}, "assets": {"x": 420, "y": 40}},
                "viewport": {"x": -10, "y": 5, "zoom": 0.85},
            },
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["stages"]["script"] == {"x": 120.0, "y": 40.0}
        assert body["viewport"]["zoom"] == 0.85

        again = client.get("/api/project/flow-layout-demo/flow-layout")
        assert again.json()["stages"]["assets"]["x"] == 420.0

    def test_get_project_settings_legacy_without_marker(self, client, projects_root):
        project = projects_root / "legacy-no-marker"
        project.mkdir()
        (project / "artifacts").mkdir()
        _write_json(project / "artifacts" / "script.json", {
            "version": "1.0",
            "title": "旧项目标题",
        })

        res = client.get("/api/project/legacy-no-marker/settings")
        assert res.status_code == 200
        body = res.json()
        assert body["title"] == "旧项目标题"
        assert body["pipeline_type"] == "unknown"
        assert body["legacy_marker"] is True

    def test_get_app_settings_defaults(self, client, app_settings_file):
        res = client.get("/api/settings")
        assert res.status_code == 200
        body = res.json()
        assert body["theme"] == "dark"
        assert body["font_scale"] == 1.12
        assert body["default_style_playbook"] == ""
        assert "projects_dir" in body

    def test_patch_app_settings(self, client, app_settings_file):
        res = client.patch(
            "/api/settings",
            json={
                "default_style_playbook": "clean-professional",
                "default_bootstrap_notes": "默认备注",
                "theme": "light",
                "font_scale": 1.2,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["default_style_playbook"] == "clean-professional"
        assert body["default_bootstrap_notes"] == "默认备注"
        assert body["theme"] == "light"
        assert body["font_scale"] == 1.2

    def test_get_system_dependencies_manifest(self, client):
        res = client.get("/api/system/dependencies")
        assert res.status_code == 200
        body = res.json()
        assert body["status_mode"] == "manifest"
        assert body["verified"] is False
        groups = body.get("dependency_groups") or []
        assert len(groups) >= 1
        assert body["summary"]["deps_total"] >= 1
        first_group = groups[0]
        assert "items" in first_group
        assert len(first_group["items"]) >= 1
        dep = first_group["items"][0]
        assert "label_zh" in dep
        assert "description_zh" in dep
        assert "purpose" in dep
        assert "path" in dep
        assert "tools_zh" in dep
        manim = next(
            (item for group in groups for item in group["items"] if item.get("name") == "manim"),
            None,
        )
        assert manim is not None
        assert "动画" in manim["description_zh"]
        assert manim["tools_zh"] == ["数学动画"]
        assert body.get("tool_checklist") == []

    def test_get_system_dependencies_check(self, client):
        res = client.get("/api/system/dependencies?check=1")
        assert res.status_code == 200
        body = res.json()
        assert body["verified"] is True
        assert body["status_mode"] == "dependencies"
        assert len(body.get("dependency_groups") or []) >= 1
        assert body["summary"]["deps_ok"] is not None
        offers = body.get("setup_offers") or []
        if offers:
            kling = next((o for o in offers if o.get("tool") == "kling_avatar"), None)
            if kling:
                assert kling.get("tool_label_zh") == "可灵数字人"
                assert kling.get("install_hint_zh")
                assert "环境变量" in kling["install_hint_zh"]

    def test_get_system_dependencies_verify(self, client):
        res = client.get("/api/system/dependencies?check=1&verify=1")
        assert res.status_code == 200
        body = res.json()
        assert body["verified"] is True
        assert isinstance(body["tools"], list)
        assert body["summary"]["deps_total"] >= 1

    def test_get_system_catalog(self, client):
        res = client.get("/api/system/catalog")
        assert res.status_code == 200
        body = res.json()
        assert "layers" in body
        assert body["summary"]["layer2_skills"] >= 1
        assert body["summary"]["layer3_skills"] >= 1
        layer_ids = [layer["id"] for layer in body["layers"]]
        assert layer_ids == ["skills_l2", "skills_l3"]
        assert body.get("tools_tab") == "deps"
        pipeline_group = next(
            (g for g in body["layers"][0]["groups"] if g["id"] == "pipelines"),
            None,
        )
        assert pipeline_group is not None
        assert pipeline_group.get("subgroups")
        first_l2 = body["layers"][0]["groups"][0]["items"][0]
        assert first_l2.get("name_zh")
        assert first_l2.get("description_zh")
        first_l3 = body["layers"][1]["groups"][0]["items"][0]
        assert first_l3.get("name_zh")
        assert first_l3.get("description_zh")
        pipeline_item = pipeline_group["subgroups"][0]["items"][0]
        assert pipeline_item.get("name_zh")
        assert pipeline_item.get("description_zh")
        assert pipeline_item.get("stage_label_zh")

    def test_get_system_pipelines(self, client):
        res = client.get("/api/system/pipelines")
        assert res.status_code == 200
        body = res.json()
        assert body["summary"]["total"] >= 10
        assert body["summary"]["visible"] >= 1
        pipes = body.get("pipelines") or []
        assert len(pipes) == body["summary"]["total"]
        cinematic = next((p for p in pipes if p["id"] == "cinematic"), None)
        assert cinematic is not None
        assert cinematic.get("label_zh")
        assert cinematic.get("stages")
        assert len(cinematic["stages"]) >= 1
        assert "label_zh" in cinematic["stages"][0]
        assert "manifest_path" in cinematic

    def test_patch_system_pipeline_ui(self, client, tmp_path, monkeypatch):
        import yaml
        from lib import pipeline_loader as pl

        defs = tmp_path / "pipeline_defs"
        defs.mkdir()
        manifest = {
            "name": "test-pipe",
            "version": "1.0",
            "description": "Test pipeline",
            "category": "custom",
            "stability": "beta",
            "stages": [{"name": "script", "skill": "meta/reviewer"}],
        }
        (defs / "test-pipe.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin.PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.bootstrap.PIPELINE_DEFS_DIR", defs)

        res = client.get("/api/system/pipelines")
        assert res.status_code == 200
        assert any(p["id"] == "test-pipe" for p in res.json()["pipelines"])

        patch = client.patch(
            "/api/system/pipelines/test-pipe",
            json={"hidden": True, "label_zh": "测试流水线", "summary_zh": "仅供测试"},
        )
        assert patch.status_code == 200
        updated = patch.json()
        assert updated["hidden"] is True
        assert updated["label_zh"] == "测试流水线"
        assert updated["summary_zh"] == "仅供测试"

        raw = yaml.safe_load((defs / "test-pipe.yaml").read_text(encoding="utf-8"))
        assert raw["ui"]["hidden"] is True
        assert raw["ui"]["label_zh"] == "测试流水线"

    def test_get_pipeline_config_and_stage_skill(self, client, tmp_path, monkeypatch):
        import yaml
        from lib import pipeline_loader as pl

        defs = tmp_path / "pipeline_defs"
        skills = tmp_path / "skills" / "pipelines" / "demo"
        defs.mkdir(parents=True)
        skills.mkdir(parents=True)
        skill_ref = "pipelines/demo/script-director"
        (skills / "script-director.md").write_text("# Script Director\n\nDo the script.", encoding="utf-8")
        manifest = {
            "name": "demo-pipe",
            "version": "1.0",
            "category": "custom",
            "stability": "beta",
            "stages": [{
                "name": "script",
                "skill": skill_ref,
                "review_focus": ["Hook is strong"],
                "success_criteria": ["Schema-valid script"],
                "human_approval_default": True,
            }],
        }
        (defs / "demo-pipe.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin.PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin._SKILLS_ROOT", tmp_path / "skills")

        cfg = client.get("/api/system/pipelines/demo-pipe/config")
        assert cfg.status_code == 200
        body = cfg.json()
        assert body["id"] == "demo-pipe"
        assert body["stages"][0]["review_focus"] == ["Hook is strong"]

        skill = client.get(f"/api/system/skills/{skill_ref}")
        assert skill.status_code == 200
        assert "Script Director" in skill.json()["content"]

        patch_stage = client.patch(
            "/api/system/pipelines/demo-pipe/stages/script",
            json={"review_focus": ["Updated focus"], "human_approval_default": False},
        )
        assert patch_stage.status_code == 200
        assert patch_stage.json()["review_focus"] == ["Updated focus"]
        assert patch_stage.json()["human_approval_default"] is False

        patch_skill = client.patch(
            f"/api/system/skills/{skill_ref}",
            json={"content": "# Updated\n\nNew instructions."},
        )
        assert patch_skill.status_code == 200
        assert "Updated" in patch_skill.json()["content"]

    def test_pipeline_stage_structure_crud(self, client, tmp_path, monkeypatch):
        import yaml
        from lib import pipeline_loader as pl

        defs = tmp_path / "pipeline_defs"
        skills = tmp_path / "skills" / "pipelines" / "demo"
        defs.mkdir(parents=True)
        skills.mkdir(parents=True)
        skill_ref = "pipelines/demo/script-director"
        (skills / "script-director.md").write_text("# Script\n", encoding="utf-8")
        manifest = {
            "name": "demo-pipe",
            "version": "1.0",
            "category": "custom",
            "stability": "beta",
            "stages": [{
                "name": "script",
                "skill": skill_ref,
                "produces": ["script"],
                "tools_available": ["tts_selector"],
            }],
        }
        (defs / "demo-pipe.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin.PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin._SKILLS_ROOT", tmp_path / "skills")
        monkeypatch.setattr("backlot.pipeline_admin._ARTIFACTS_SCHEMA_DIR", tmp_path / "schemas" / "artifacts")

        patch_struct = client.patch(
            "/api/system/pipelines/demo-pipe/stages/script",
            json={
                "produces": ["script", "brief"],
                "tools_available": ["tts_selector", "elevenlabs_tts"],
                "required_artifacts_in": ["brief"],
                "checkpoint_required": False,
            },
        )
        assert patch_struct.status_code == 200
        body = patch_struct.json()
        assert body["produces"] == ["script", "brief"]
        assert "elevenlabs_tts" in body["tools_available"]
        assert body["required_artifacts_in"] == ["brief"]
        assert body["checkpoint_required"] is False

        created = client.post(
            "/api/system/pipelines/demo-pipe/stages",
            json={"name": "publish", "insert_after": "script", "produces": ["publish_log"]},
        )
        assert created.status_code == 200
        assert created.json()["name"] == "publish"

        reordered = client.put(
            "/api/system/pipelines/demo-pipe/stages/order",
            json={"stage_names": ["publish", "script"]},
        )
        assert reordered.status_code == 200
        assert [s["name"] for s in reordered.json()["stages"]] == ["publish", "script"]

        renamed = client.patch(
            "/api/system/pipelines/demo-pipe/stages/publish",
            json={"new_name": "delivery"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "delivery"

        deleted = client.delete("/api/system/pipelines/demo-pipe/stages/script")
        assert deleted.status_code == 200
        assert deleted.json()["stage_count"] == 1

        hints = client.get("/api/system/pipelines/demo-pipe/editor-hints")
        assert hints.status_code == 200
        assert "artifacts" in hints.json()
        assert "tools" in hints.json()

    def test_patch_pipeline_manifest_root_fields(self, client, tmp_path, monkeypatch):
        import yaml
        from lib import pipeline_loader as pl

        defs = tmp_path / "pipeline_defs"
        defs.mkdir(parents=True)
        manifest = {
            "name": "demo-pipe",
            "version": "1.0",
            "description": "Before",
            "category": "custom",
            "stability": "beta",
            "default_checkpoint_policy": "guided",
            "required_skills": ["meta/reviewer"],
            "stages": [{"name": "script", "skill": "meta/reviewer"}],
        }
        (defs / "demo-pipe.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", defs)
        monkeypatch.setattr("backlot.pipeline_admin.PIPELINE_DEFS_DIR", defs)

        patch = client.patch(
            "/api/system/pipelines/demo-pipe/manifest",
            json={
                "version": "2.0",
                "description": "After",
                "category": "cinematic",
                "stability": "production",
                "default_checkpoint_policy": "manual_all",
                "required_skills": ["meta/reviewer", "meta/onboarding"],
                "reference_input": {
                    "supported": True,
                    "analysis_depth": "deep",
                    "analysis_tools": ["video_analyzer"],
                },
                "extensions": {
                    "custom_scripts": True,
                    "custom_playbooks": False,
                    "custom_skills": True,
                    "custom_tools": False,
                },
                "ui": {"label_zh": "演示流水线", "summary_zh": "摘要", "hidden": True},
                "orchestration": {"mode": "ep", "budget_default_usd": 12.5},
                "metadata": {"owner": "qa"},
            },
        )
        assert patch.status_code == 200
        body = patch.json()
        assert body["version"] == "2.0"
        assert body["description"] == "After"
        assert body["label_zh"] == "演示流水线"
        assert body["manifest"]["reference_input"]["supported"] is True
        assert body["manifest"]["extensions"]["custom_playbooks"] is False
        assert body["manifest"]["metadata"]["owner"] == "qa"
        assert len(body["stages"]) == 1
        assert body["stages"][0]["name"] == "script"

        raw = yaml.safe_load((defs / "demo-pipe.yaml").read_text(encoding="utf-8"))
        assert raw["version"] == "2.0"
        assert raw["ui"]["hidden"] is True
        assert raw["stages"] == [{"name": "script", "skill": "meta/reviewer"}]

    def test_get_system_env_vars(self, client):
        res = client.get("/api/system/env-vars")
        assert res.status_code == 200
        body = res.json()
        assert body["total_count"] >= 1
        assert body["sections"]
        first_item = body["sections"][0]["items"][0]
        assert "name" in first_item
        assert "purpose" in first_item
        assert "path" in first_item
        assert "hint" in first_item
        assert body["sections"][0]["label"]
        assert body["sections"][0]["description"]

    def test_patch_system_env_vars(self, client, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        example_file = tmp_path / ".env.example"
        example_file.write_text(
            "# --- Test ---\nTEST_BACKLOT_KEY=\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("backlot.env_config.ENV_PATH", env_file)
        monkeypatch.setattr("backlot.env_config.ENV_EXAMPLE_PATH", example_file)

        res = client.patch("/api/system/env-vars", json={"values": {"TEST_BACKLOT_KEY": "secret-value"}})
        assert res.status_code == 200
        assert env_file.is_file()
        assert "TEST_BACKLOT_KEY=secret-value" in env_file.read_text(encoding="utf-8")
        body = res.json()
        item = next(
            i for sec in body["sections"] for i in sec["items"] if i["name"] == "TEST_BACKLOT_KEY"
        )
        assert item["configured"] is True
        assert item["masked_value"]

    def test_patch_project_settings_updates_title_and_platform(self, client, projects_root):
        project = projects_root / "patch-demo"
        project.mkdir()
        _write_json(project / "project.json", {
            "project_id": "patch-demo",
            "title": "旧标题",
            "pipeline_type": "animated-explainer",
            "created_at": "2026-08-01T00:00:00Z",
        })
        _write_json(project / "meta.json", {
            "version": "1.0",
            "production_inputs": {
                "topic": "旧主题",
                "target_platform": "douyin",
                "target_duration_seconds": 60,
            },
        })

        res = client.patch(
            "/api/project/patch-demo/settings",
            json={
                "title": "新标题",
                "style_playbook": "clean-professional",
                "notes": "新备注",
                "inputs": {"target_platform": "bilibili", "target_duration_seconds": 90},
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["title"] == "新标题"
        assert body["style_playbook"] == "clean-professional"
        assert body["bootstrap_notes"] == "新备注"
        assert body["production_inputs"]["target_platform"] == "bilibili"
        assert body["production_inputs"]["target_duration_seconds"] == 90

        marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
        assert marker["title"] == "新标题"
        assert marker["style_playbook"] == "clean-professional"

    def test_patch_rejects_media_when_pipeline_started(self, client, projects_root):
        project = _make_project(projects_root, "locked-media")
        _write_json(project / "meta.json", {
            "version": "1.0",
            "production_inputs": {
                "source_media_path": "assets/video/source.mp4",
                "target_platform": "douyin",
            },
        })

        res = client.patch(
            "/api/project/locked-media/settings",
            json={"inputs": {"source_media_path": "/tmp/new.mp4"}},
        )
        assert res.status_code == 400
        assert "源素材" in res.json()["detail"]

    def test_patch_allows_media_replace_when_flagged(self, client, projects_root, tmp_path):
        project = _make_project(projects_root, "replace-media")
        src = tmp_path / "new.mp4"
        src.write_bytes(b"\x00" * 128)
        _write_json(project / "meta.json", {
            "version": "1.0",
            "production_inputs": {
                "source_media_path": "assets/video/source.mp4",
                "target_platform": "douyin",
            },
        })

        res = client.patch(
            "/api/project/replace-media/settings",
            json={
                "inputs": {"source_media_path": str(src)},
                "replace_media": True,
            },
        )
        assert res.status_code == 200
        meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
        assert meta["production_inputs"]["source_media_path"] == "assets/video/source.mp4"
        assert (project / "assets" / "video" / "source.mp4").is_file()

    @pytest.mark.parametrize(
        ("url", "status"),
        [
            ("/api/project/../state", 404),
            ("/api/project/C:/state", 400),
            ("/api/project/nope/state", 404),
        ],
    )
    def test_project_id_rejects_bad_or_unknown_ids(self, client, url, status):
        response = client.get(url)
        assert response.status_code == status

    def test_media_rejects_path_traversal(self, client, projects_root):
        _make_project(projects_root, "film")
        response = client.get("/media/film/%2E%2E/project.json")
        assert response.status_code == 403

    def test_media_serves_range_requests(self, client, projects_root):
        project = _make_project(projects_root, "film")
        media = project / "renders" / "final.mp4"
        media.write_bytes(b"0123456789")

        response = client.get("/media/film/renders/final.mp4", headers={"Range": "bytes=2-5"})

        assert response.status_code == 206
        assert response.content == b"2345"
        assert response.headers["content-range"].startswith("bytes 2-5/10")

    def test_thumb_downscales_image_and_passes_through_non_media(self, client, projects_root):
        project = _make_project(projects_root, "film")
        _write_png(project / "assets" / "images" / "sc1.png")
        text = project / "artifacts" / "note.txt"
        text.write_text("hello", encoding="utf-8")

        image = client.get("/thumb/film/assets/images/sc1.png?w=320")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert image.content.startswith(b"\xff\xd8")

        passthrough = client.get("/thumb/film/artifacts/note.txt")
        assert passthrough.status_code == 200
        assert passthrough.content == b"hello"


class TestBacklotPerformanceBudgets:
    def test_projects_and_state_stay_within_loose_budgets(self, client, projects_root):
        for i in range(25):
            project = _make_project(projects_root, f"film-{i:02d}")
            _write_json(
                project / "artifacts" / "scene_plan.json",
                {"version": "1.0", "scenes": [{"id": "sc1", "start_seconds": 0, "end_seconds": 1}]},
            )

        t0 = time.perf_counter()
        cold = client.get("/api/projects")
        cold_s = time.perf_counter() - t0
        assert cold.status_code == 200
        assert cold_s < 2.0

        t1 = time.perf_counter()
        warm = client.get("/api/projects")
        warm_s = time.perf_counter() - t1
        assert warm.status_code == 200
        assert warm_s < 0.150

        t2 = time.perf_counter()
        state = client.get("/api/project/film-00/state")
        state_s = time.perf_counter() - t2
        assert state.status_code == 200
        assert state_s < 0.400

    def test_image_thumb_generation_stays_within_budget(self, client, projects_root):
        project = _make_project(projects_root, "film")
        _write_png(project / "assets" / "images" / "sc1.png")

        t0 = time.perf_counter()
        response = client.get("/thumb/film/assets/images/sc1.png?w=640")
        elapsed = time.perf_counter() - t0

        assert response.status_code == 200
        assert elapsed < 1.5


class TestFindingsFixes:
    """Regression tests for dogfood findings F-03 (thumb video fallback)."""

    def test_thumb_never_serves_raw_video_bytes(self, client, projects_root):
        p = _make_project(projects_root, "vid")
        fake_video = p / "renders" / "final.mp4"
        fake_video.parent.mkdir(parents=True, exist_ok=True)
        # Not a real video: ffmpeg poster extraction will fail.
        fake_video.write_bytes(b"\x00" * 4096)
        res = client.get("/thumb/vid/renders/final.mp4")
        assert res.status_code == 404  # never the raw video bytes (F-03)
