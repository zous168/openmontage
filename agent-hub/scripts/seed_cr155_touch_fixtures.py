#!/usr/bin/env python3
"""写入 / 清理 CR-155 私域触达预览矩阵 fixture（doc 40）."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _hub_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    hub_root = _hub_root()
    src = hub_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from plugins.mxai.cfg.bootstrap.cr155_fixture_seed import (
        cleanup_cr155_touch_fixtures,
        seed_cr155_touch_fixtures,
    )
    from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
    from runtime_paths import resolve_hub_data_dir_path

    parser = argparse.ArgumentParser(description="Seed or cleanup CR-155 scheduled-touch fixtures")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Hub data root (default: platform HUB_DATA_DIR)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove fixture rows and restore workbench backups",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Seed without deleting existing cr155_fixture_* rows first",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else resolve_hub_data_dir_path()
    data_dir.mkdir(parents=True, exist_ok=True)

    bootstrap = ensure_runtime_bootstrap(data_dir)
    if not bootstrap.ok:
        print(f"warning: bootstrap had failures: {bootstrap.failed}", file=sys.stderr)

    if args.cleanup:
        result = cleanup_cr155_touch_fixtures(data_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("remaining_customers", 0) == 0 else 1

    result = seed_cr155_touch_fixtures(data_dir, replace=not args.no_replace)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
