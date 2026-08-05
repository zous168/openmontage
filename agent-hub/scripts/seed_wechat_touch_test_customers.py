#!/usr/bin/env python3
"""为分段定时触达联调写入 30 名微信测试客户（各 last_inbound_at 静默段）."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import uuid
from datetime import timedelta
from pathlib import Path

PREFIX = "segtest_wx_"

# (label, silence_seconds) — 相对 now 的入站时间偏移
_BUCKETS: list[tuple[str, int | None]] = [
    ("recent_30m", 30 * 60),
    ("silence_1h_2h", 2 * 3600),
    ("silence_1h_5h", 5 * 3600),
    ("silence_1h_8h", 8 * 3600),
    ("silence_1h_12h", 12 * 3600),
    ("silence_1h_18h", 18 * 3600),
    ("silence_1h_23h", 23 * 3600),
    ("silence_1d_26h", 26 * 3600),
    ("silence_1d_36h", 36 * 3600),
    ("silence_1d_2d", 2 * 86400),
    ("silence_1d_2d5", int(2.5 * 86400)),
    ("silence_1d_2d8", int(2.8 * 86400)),
    ("silence_3d_3d2", int(3.2 * 86400)),
    ("silence_3d_3d5", int(3.5 * 86400)),
    ("silence_3d_4d", 4 * 86400),
    ("silence_3d_4d5", int(4.5 * 86400)),
    ("silence_5d_6d", 6 * 86400),
    ("silence_5d_10d", 10 * 86400),
    ("silence_5d_15d", 15 * 86400),
    ("silence_5d_20d", 20 * 86400),
    ("silence_1mo_35d", 35 * 86400),
    ("silence_1mo_45d", 45 * 86400),
    ("silence_1mo_55d", 55 * 86400),
    ("silence_2mo_65d", 65 * 86400),
    ("silence_2mo_90d", 90 * 86400),
    ("silence_2mo_120d", 120 * 86400),
    ("no_inbound_a", None),
    ("no_inbound_b", None),
    ("silence_1h_rand", None),  # filled with random 1h–23h below
    ("silence_5d_rand", None),  # filled with random 5d–25d below
]

_SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
_TITLES = ["经理", "总监", "老板", "采购", "运营", "店长", "顾问", "主管"]
_INDUSTRIES = ["建材", "外贸", "餐饮", "教育", "医美", "物流", "电商", "制造"]

_FUNNEL_STAGES = ["consulting", "friend_added", "qualified", "negotiating"]


def _hub_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(_SURNAMES)}{rng.choice(_TITLES)}-{rng.choice(_INDUSTRIES)}"


def _resolve_offsets(rng: random.Random) -> list[tuple[str, int | None]]:
    out: list[tuple[str, int | None]] = []
    for label, sec in _BUCKETS:
        if label == "silence_1h_rand":
            out.append((label, rng.randint(3600 + 60, 23 * 3600)))
        elif label == "silence_5d_rand":
            out.append((label, rng.randint(5 * 86400 + 3600, 25 * 86400)))
        else:
            out.append((label, sec))
    return out


def seed_wechat_touch_test_customers(
    data_dir: Path,
    *,
    count: int = 30,
    seed: int | None = None,
    replace: bool = True,
) -> dict:
    src = _hub_root() / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from plugins.mxai.crm.storage.hub_repo import init_hub_schema
    from plugins.mxai.timeutil import utc_now

    rng = random.Random(seed)
    db_path = data_dir / "hub.db"
    init_hub_schema(db_path)

    buckets = _resolve_offsets(rng)[:count]
    now = utc_now()
    rows: list[dict] = []

    conn = sqlite3.connect(db_path)
    try:
        if replace:
            conn.execute(
                "DELETE FROM customers WHERE profile_id = 'wechat' AND customer_uid LIKE ?",
                (f"{PREFIX}%",),
            )

        for i, (bucket, silence_sec) in enumerate(buckets, start=1):
            uid = f"{PREFIX}{i:02d}"
            display = _random_name(rng)
            stage = rng.choice(_FUNNEL_STAGES)
            if silence_sec is None:
                last_inbound_at = None
            else:
                last_inbound_at = (now - timedelta(seconds=silence_sec)).replace(microsecond=0).isoformat()
            created = (now - timedelta(days=rng.randint(30, 180))).replace(microsecond=0).isoformat()
            stage_at = created

            conn.execute(
                """
                INSERT OR REPLACE INTO customers (
                    customer_uid, profile_id, display_name, source_channel,
                    funnel_stage, funnel_stage_at, created_at, updated_at, last_inbound_at
                ) VALUES (?, 'wechat', ?, 'wechat', ?, ?, ?, ?, ?)
                """,
                (uid, display, stage, stage_at, created, stage_at, last_inbound_at),
            )
            rows.append(
                {
                    "customer_uid": uid,
                    "display_name": display,
                    "funnel_stage": stage,
                    "bucket": bucket,
                    "last_inbound_at": last_inbound_at,
                    "silence_sec": silence_sec,
                }
            )
        conn.commit()
    finally:
        conn.close()

    return {"inserted": len(rows), "prefix": PREFIX, "customers": rows}


def main(argv: list[str] | None = None) -> int:
    src = _hub_root() / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from runtime_paths import resolve_hub_data_dir_path

    parser = argparse.ArgumentParser(description="Seed wechat segmented-touch test customers")
    parser.add_argument("--data-dir", default=None, help="Hub data root (default: HUB_DATA_DIR)")
    parser.add_argument("--count", type=int, default=30, help="Number of customers (max 30)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible names")
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help=f"Do not delete existing {PREFIX}* rows first",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else resolve_hub_data_dir_path()
    result = seed_wechat_touch_test_customers(
        data_dir,
        count=min(max(1, args.count), len(_BUCKETS)),
        seed=args.seed,
        replace=not args.no_replace,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
