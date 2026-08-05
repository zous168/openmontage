#!/usr/bin/env python3
"""写入 MxAI 联调演示数据（worklog / 线索 / 队列 / 报表 / 知识库 / 聊天收藏等）."""

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

    from plugins.mxai.cfg.bootstrap.demo_seed import seed_demo_data
    from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
    from runtime_paths import resolve_hub_data_dir_path

    parser = argparse.ArgumentParser(description="Seed MxAI demo data into HUB_DATA_DIR")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Hub data root (default: HUB_DATA_DIR env or platform default)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear demo_* rows and re-seed",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else resolve_hub_data_dir_path()
    data_dir.mkdir(parents=True, exist_ok=True)

    bootstrap = ensure_runtime_bootstrap(data_dir)
    if not bootstrap.ok:
        print(f"warning: bootstrap had failures: {bootstrap.failed}", file=sys.stderr)

    result = seed_demo_data(data_dir, force=args.force)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
