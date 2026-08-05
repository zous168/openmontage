"""从 agent-hub/pyproject.toml 安装依赖。

合并成单一仓库后依赖只有一处声明。这个脚本让不用 uv 的人也能装：
读 pyproject，把包名交给 pip。没有第二份清单，也就没有漂移。

    python scripts/install_deps.py            # 主依赖
    python scripts/install_deps.py --dev      # 加开发工具链
    python scripts/install_deps.py --gpu      # 加 torch 栈（上千 MB）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "agent-hub" / "pyproject.toml"


def _load() -> dict:
    if not PYPROJECT.is_file():
        sys.exit(f"找不到 {PYPROJECT} —— 依赖声明的唯一来源")
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev", action="store_true", help="附加开发工具链")
    ap.add_argument("--gpu", action="store_true", help="附加本地 GPU 推理栈")
    ap.add_argument("--dry-run", action="store_true", help="只打印将安装什么")
    args = ap.parse_args()

    data = _load()
    packages: list[str] = list(data["project"]["dependencies"])
    if args.dev:
        packages += data.get("dependency-groups", {}).get("dev", [])
    if args.gpu:
        packages += data["project"].get("optional-dependencies", {}).get("gpu", [])

    if not packages:
        sys.exit("pyproject 里没读到任何依赖 —— 文件结构可能变了")

    print(f"从 {PYPROJECT.name} 安装 {len(packages)} 个依赖")
    if args.dry_run:
        for pkg in packages:
            print(f"  {pkg}")
        return 0

    return subprocess.run(
        [sys.executable, "-m", "pip", "install", *packages], check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
