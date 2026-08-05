"""cron_channel_relocate 合并逻辑."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.mxai.cfg.migrations._cron_channel_relocate import migrate_profile_cron


def test_merge_jobs_by_id_skips_duplicates(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "cron").mkdir()
    (dst / "cron").mkdir()
    (src / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [{"id": "a", "name": "from-src"}, {"id": "b", "name": "only-src"}]}),
        encoding="utf-8",
    )
    (dst / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [{"id": "a", "name": "keep-dst"}]}),
        encoding="utf-8",
    )

    changed = migrate_profile_cron(src, dst)
    assert changed == 1

    jobs = json.loads((dst / "cron" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    by_id = {j["id"]: j["name"] for j in jobs}
    assert by_id["a"] == "keep-dst"
    assert by_id["b"] == "only-src"
