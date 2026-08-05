"""OPENMONTAGE_NON_PRODUCTION_SCRIPT — 取证分析（只读），不参与生产流水线。

用法:
  python _forensics.py snapshot <label>      # 记录指纹 + events 基线
  python _forensics.py report <label> <task> # 与 label 快照对比 + 解析 run 日志
"""
import hashlib, json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from plugins.openmontage.lib.paths import PROJECTS_DIR

PID = "my-copy-01"
PD = PROJECTS_DIR / PID
STORE = Path(__file__).parent / "_forensics_store"
EXCLUDE = {"runs", ".run.lock"}

def snap():
    out = {}
    for p in PD.rglob("*"):
        if not p.is_file(): continue
        rel = p.relative_to(PD).as_posix()
        if rel.split("/")[0] in EXCLUDE: continue
        out[rel] = [p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()[:16]]
    ev = PD / "events.jsonl"
    return {"files": out, "events_lines": len(ev.read_text(encoding="utf-8").splitlines()) if ev.is_file() else 0}

# --- 违规分类（依据 AGENT_GUIDE） ---
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
SANCTIONED = ("plugins.openmontage.lib.checkpoint", "plugins.openmontage.lib.decision_log", "plugins.openmontage.lib.project_status",
              "plugins.openmontage.lib.production_audit", "tool_registry", "registry.")
# 只匹配真正的写盘：2>&1 / 2>/dev/null 这类 fd 重定向、json.dumps（序列化成
# 字符串打印）都不是写操作，早期正则把它们误判成违规。
SHELL_WRITE = re.compile(
    r"(?<![0-9&])>>?\s*['\"]?[\w./\\-]"       # 文件重定向（排除 2>&1、&> ）
    r"|\btee\s"
    r"|open\([^)]*,\s*['\"][wax]b?['\"]"      # open(..., 'w'/'a'/'x')
    r"|json\.dump\("                          # dump( 而非 dumps(
    r"|\.write_text\(|\.write_bytes\(|\.mkdir\("
    r"|shutil\.(copy|move|rmtree)|os\.(replace|remove|rename|makedirs)"
    r"|\.save\("                              # PIL Image.save 等
)
EXPLORE = re.compile(r"\b(ls|dir|find|Get-ChildItem|tree)\b")
PY_SCRIPT = re.compile(r"python3?\s+[\w./\-]+\.py|cat\s*>\s*\S+\.py")

# 只认 OpenMontage 的 projects/ 工作区。裸匹配 "projects" 会把
# %USERPROFILE%\.claude\projects\... 下的 agent 记忆目录一并误判。
_WS = PD.as_posix().lower()
_WS_ALT = f"projects/{PID}"


def _in_workspace(text: str) -> bool:
    t = text.replace("\\", "/").lower()
    return _WS in t or _WS_ALT in t


def classify(name, inp):
    inp = inp or {}
    if name in WRITE_TOOLS:
        fp = str(inp.get("file_path") or inp.get("path") or "")
        if _in_workspace(fp):
            return "VIOLATION", f"直接写 projects/ 下文件: {fp}"
        return "GRAY", f"写工作区之外: {fp}"
    if name == "Bash":
        cmd = str(inp.get("command") or "")
        if PY_SCRIPT.search(cmd):
            return "VIOLATION", "创建/执行 .py 脚本"
        touches_proj = _in_workspace(cmd)
        if SHELL_WRITE.search(cmd) and touches_proj and not any(s in cmd for s in SANCTIONED):
            return "VIOLATION", "未经 lib API 写 projects/ 下数据"
        if EXPLORE.search(cmd) and touches_proj:
            return "VIOLATION", "用 shell 列目录探查项目结构"
        return "OK", ""
    return "OK", ""

def parse_log(task_id):
    log = PD / "runs" / f"{task_id}.log"
    calls = []
    if not log.is_file(): return calls
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s.startswith("{"): continue
        try: ev = json.loads(s)
        except Exception: continue
        if ev.get("type") != "assistant": continue
        for b in (ev.get("message") or {}).get("content") or []:
            if b.get("type") == "tool_use":
                verdict, why = classify(b.get("name"), b.get("input"))
                calls.append({"tool": b.get("name"), "verdict": verdict, "why": why,
                              "input": json.dumps(b.get("input"), ensure_ascii=False)[:220]})
    return calls

def main():
    STORE.mkdir(exist_ok=True)
    cmd, label = sys.argv[1], sys.argv[2]
    if cmd == "snapshot":
        (STORE / f"{label}.json").write_text(json.dumps(snap(), ensure_ascii=False), encoding="utf-8")
        s = snap(); print(f"snapshot[{label}]: {len(s['files'])} files, events_lines={s['events_lines']}")
        return
    base = json.loads((STORE / f"{label}.json").read_text(encoding="utf-8"))
    now = snap()
    added = sorted(set(now["files"]) - set(base["files"]))
    changed = sorted(k for k in set(now["files"]) & set(base["files"]) if now["files"][k] != base["files"][k])
    deleted = sorted(set(base["files"]) - set(now["files"]))
    print(f"=== B. 文件指纹 diff  新增={len(added)} 改动={len(changed)} 删除={len(deleted)}")
    for k in added[:60]: print("   + " + k)
    for k in changed[:60]: print("   ~ " + k)
    for k in deleted[:30]: print("   - " + k)

    calls = parse_log(sys.argv[3]) if len(sys.argv) > 3 else []
    print(f"\n=== A. 工具调用清单（共 {len(calls)} 次）")
    from collections import Counter
    print("   分布:", dict(Counter(c["tool"] for c in calls)))
    viol = [c for c in calls if c["verdict"] == "VIOLATION"]
    gray = [c for c in calls if c["verdict"] == "GRAY"]
    print(f"   *** 违规 {len(viol)} 次, 灰色 {len(gray)} 次 ***")
    for c in viol: print(f"   [违规] {c['tool']}: {c['why']}\n           {c['input']}")
    for c in gray: print(f"   [灰色] {c['tool']}: {c['why']}")

    ev = PD / "events.jsonl"
    lines = ev.read_text(encoding="utf-8").splitlines() if ev.is_file() else []
    new = lines[base["events_lines"]:]
    from collections import Counter as C2
    tools = C2()
    for l in new:
        try: e = json.loads(l)
        except Exception: continue
        if e.get("event") == "finish": tools[e.get("tool")] += 1
    print(f"\n=== C. events.jsonl 新增 {len(new)} 条; 工具 finish: {dict(tools)}")

main()
