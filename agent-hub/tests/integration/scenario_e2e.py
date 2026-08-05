#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hub ↔ RPA(mock) 业务场景集成测试（运营逐步驱动，全程经 mock RPA worker）。

按 agent-client 真实功能项组织 6 渠道业务场景，CLI 自动化驱动，逐步从队列/steps 确认。
运行后在同目录生成 last-run-report.md（结果 + 过程 + worker 执行链证据），便于查看。

前置：
  1. agent-hub 在 :8642 运行（建议 MXAI_MOCK=1 确定性）：
       $env:MXAI_MOCK='1'; .\scripts\start-agent-hub.ps1 -Env test
  2. mock RPA worker 已连：
       agent-hub\.venv\Scripts\python.exe automan\mock-rpa-cli\mock_worker.py --json-log --timeout 0
运行：
  agent-hub\.venv\Scripts\python.exe agent-hub\tests\integration\scenario_e2e.py
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error

# 仓库根（本文件在 agent-hub/tests/integration/ 下）
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REPORT_PATH = os.path.join(os.path.dirname(__file__), "last-run-report.md")

BASE = "http://127.0.0.1:8642"
MX = BASE + "/api/plugins/mxai"
OK = {"已完成"}; FAILED = {"异常失败"}
RPT: list[str] = []
def rpt(line: str = ""): RPT.append(line)

def _tok():
    with urllib.request.urlopen(BASE + "/api/auth/dev/local-ipc-token", timeout=5) as r:
        return json.loads(r.read())["token"]
TOKEN = _tok()

def req(method, path, body=None):
    url = path if path.startswith("http") else (MX + path)
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(url, data=data, method=method)
    rq.add_header("Authorization", "Bearer " + TOKEN)
    if data is not None: rq.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(rq, timeout=35) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode()[:160]}

def task_of(agent, task_id):
    st, d = req("GET", f"/queue/tasks?agent={agent}&page_size=200")
    if st != 200: return None
    for t in d.get("tasks") or d.get("items") or []:
        if t.get("task_id") == task_id: return t
    return None

def steps_of(task_id):
    st, d = req("GET", f"/queue/tasks/{task_id}/steps")
    return d.get("steps") or [] if st == 200 else []

def worker_proof(steps):
    return any(s.get("mode") in ("rpa_worker_ws", "cli") or s.get("step_id") == "mock_cli" for s in steps)

def steps_brief(steps):
    return " → ".join(f"{s.get('step_id')}({s.get('mode') or s.get('status')})" for s in steps)

def summarize(resp, task):
    res = (task or {}).get("payload", {}).get("result") if task else None
    res = res or resp.get("result") or {}
    if not isinstance(res, dict): return ""
    bits = []
    if res.get("reply"): bits.append(f"回复「{str(res['reply'].get('text',''))[:22]}」src={res['reply'].get('source')}")
    for k in ("replied", "collected", "matched", "posted", "count", "total", "sent"):
        if k in res: bits.append(f"{k}={res[k]}")
    return " ".join(bits)

# ── 预置 CRM 线索（模拟公域采集已发生）──
SEEDED = {"douyin": [], "xiaohongshu": [], "shipinhao": []}
seed_note = ""
try:
    sys.path.insert(0, os.path.join(REPO, "agent-hub", "src"))
    os.environ.setdefault("HUB_DATA_DIR", r"C:/ProgramData/MarketingHub")
    from plugins.mxai.crm.lead_service import save_leads
    from plugins.mxai.rpa.types import CollectedComment
    for ch in SEEDED:
        cmts = [CollectedComment(comment_id=f"cmt_{ch}_1", author=f"意向_{ch}_1", text="这个多少钱？怎么购买？", video_id=f"vid_{ch}", keyword="报价"),
                CollectedComment(comment_id=f"cmt_{ch}_2", author=f"意向_{ch}_2", text="想咨询下套餐价格", video_id=f"vid_{ch}", keyword="套餐")]
        SEEDED[ch] = save_leads(profile_id=ch, source_channel=ch, comments=cmts)
    seed_note = "预置线索: " + ", ".join(f"{k}={len(v)}" for k, v in SEEDED.items())
except Exception as exc:
    seed_note = f"预置线索跳过（{exc}）"
print("==", seed_note, "==", flush=True)

SCEN = [
 ("抖音获客智能体 · 公域获客漏斗", "douyin", [
   ("①自动首评·对标新视频抢首评", "POST", "/agents/douyin/tasks/first-comment", {"benchmarks": ["@行业对标号A", "@行业对标号B"], "scripts": ["有需要欢迎私信咨询~"]}),
   ("②评论采集·关键词挖意向线索", "POST", "/agents/douyin/tasks/comment-collect", {"search_keywords": ["智能客服", "报价", "多少钱"]}),
   ("③AI评论回复·公域回复意向用户", "POST", "/agents/douyin/tasks/comment-reply", {"search_keywords": ["智能客服", "报价"]}),
   ("④私信触达·高意向用户深聊", "POST", "/agents/douyin/tasks/dm", {"recipient": "user_dy_888", "message": "您好，看到您对产品感兴趣，方便聊聊具体需求吗？"}),
   ("⑤入站应答·用户主动私信咨询", "POST", "/agents/douyin/inbound", {"message_id": "dm_dy_1", "sender": "user_dy_888", "message": "你们报价怎么算？"}),
 ]),
 ("小红书获客智能体 · 种草获客", "xiaohongshu", [
   ("①评论采集·种草笔记挖意向", "POST", "/agents/xiaohongshu/tasks/comment-collect", {"search_keywords": ["求链接", "怎么买", "种草"]}),
   ("②AI评论回复·意向用户回复", "POST", "/agents/xiaohongshu/tasks/comment-reply", {"search_keywords": ["求链接", "怎么买"]}),
   ("③私信触达·引导私域", "POST", "/agents/xiaohongshu/tasks/dm", {"recipient": "xhs_user_66", "message": "已私信您链接和优惠~"}),
 ]),
 ("视频号获客智能体 · 公域获客", "shipinhao", [
   ("①自动首评·新视频抢首评", "POST", "/agents/shipinhao/tasks/first-comment", {"benchmarks": ["@视频号对标A"], "scripts": ["欢迎私信了解详情"]}),
   ("②评论采集·关键词挖意向", "POST", "/agents/shipinhao/tasks/comment-collect", {"search_keywords": ["怎么合作", "加盟"]}),
   ("③AI评论回复", "POST", "/agents/shipinhao/tasks/comment-reply", {"search_keywords": ["怎么合作", "加盟"]}),
   ("④私信触达", "POST", "/agents/shipinhao/tasks/dm", {"recipient": "sph_user_1", "message": "您好，合作详情私信您了~"}),
 ]),
 ("个人微信智能体 · 私域培育", "wechat", [
   ("①入站应答·新客咨询AI回复", "POST", "/agents/wechat/inbound", {"message_id": "wx_in_1", "sender": "wxid_newlead", "message": "你好，想了解下你们的产品"}),
   ("②主动加好友·批量沉淀意向客户", "POST", "/agents/wechat/tasks/add-friends", {"contacts": ["wxid_lead_a", "wxid_lead_b", "wxid_lead_c"]}),
   ("③定时触达·沉默客户回访", "POST", "/agents/wechat/tasks/scheduled-msg", {"recipient": "wxid_newlead", "message": "上次咨询的产品，给您整理了资料~", "run_now": True}),
 ]),
 ("企业微信智能体 · 客户服务全流程", "qiyeweixin", [
   ("①客户接待·入站咨询AI回复", "POST", "/agents/qiyeweixin/inbound", {"message_id": "qw_in_1", "sender": "qw_cust_1", "message": "你好，售后问题咨询"}),
   ("②发送文件·发产品手册", "POST", "/agents/qiyeweixin/tasks/send-file", {"recipient": "qw_cust_1", "file_path": "C:/材料/产品手册.pdf"}),
   ("③批量加客户", "POST", "/agents/qiyeweixin/tasks/add-contacts", {"contacts": ["qw_c1", "qw_c2", "qw_c3"]}),
   ("④售后回访·定时触达", "POST", "/agents/qiyeweixin/tasks/scheduled-msg", {"recipient": "qw_cust_1", "message": "您的问题已处理，满意请评价~", "run_now": True}),
 ]),
 ("Boss直聘人事智能体 · 招聘全流程", "boss", [
   ("①候选人搜索·简历拓聊", "POST", "/agents/boss/tasks/boss-search", {"keywords": ["Python 后端", "3年经验"]}),
   ("②打招呼·批量触达候选人", "POST", "/agents/boss/tasks/greet", {"candidates": ["cand_1", "cand_2"], "template": "您好，看到您的简历很匹配我们的岗位"}),
   ("③应聘回复·求职者回复应答", "POST", "/agents/boss/tasks/apply-respond", {"application_id": "app_1001", "message": "感谢投递，方便约个电话沟通吗？"}),
   ("④邀约沟通·邀面试", "POST", "/agents/boss/tasks/invite", {"candidate_id": "cand_1", "slot": "本周四 15:00"}),
   ("⑤跟进触达", "POST", "/agents/boss/tasks/follow-up", {"candidate": "cand_2", "message": "方便的话我们约个时间细聊~"}),
 ]),
]
AGENTS = [a for _, a, _ in SCEN]

rpt("# Hub ↔ RPA(mock) 业务场景集成测试报告\n")
rpt(f"- 运行环境: agent-hub :8642 (MXAI_MOCK={os.environ.get('MXAI_MOCK','?')}), mock RPA worker via WS")
rpt(f"- {seed_note}")
rpt(f"- 判定标准: HTTP 200 + 任务状态「已完成」+ 经 mock worker 执行（steps 含 rpa_worker_ws/mock_cli）\n")

print("== 拉起工作 ==", flush=True)
st, d = req("POST", "/run/all/start")
rpt(f"**拉起工作**: `POST /run/all/start` → HTTP {st}, work_armed={d.get('work_armed')}, scheduler_active={d.get('scheduler_active')}\n")
for ag in AGENTS:
    req("POST", f"/run/agents/{ag}/start")
    req("PATCH", f"/agents/{ag}/modules/inbound_reply", {"enabled": True})
time.sleep(1)

all_steps = 0; all_pass = 0; scen_stat = []
for title, agent, steps in SCEN:
    print(f"\n== {title} ==", flush=True)
    rpt(f"\n## 场景 · {title}  `agent={agent}`\n")
    rpt("| 业务步骤 | HTTP | 状态 | 经worker | task_id | 执行链(steps) | 业务结果 |")
    rpt("|---------|------|------|---------|---------|--------------|---------|")
    s_pass = 0
    for label, method, path, body in steps:
        all_steps += 1
        st, resp = req(method, path, body)
        tid = resp.get("task_id") or (resp.get("task") or {}).get("task_id") or ""
        status = resp.get("status", ""); wk = False; biz = ""; chain = ""
        if tid:
            dl = time.monotonic() + 12
            while time.monotonic() < dl:
                t = task_of(agent, tid)
                status = (t or {}).get("status", status)
                if status in OK or status in FAILED:
                    stps = (t or {}).get("steps") or steps_of(tid)
                    wk = worker_proof(stps); chain = steps_brief(stps); biz = summarize(resp, t)
                    break
                time.sleep(0.4)
        else:
            biz = resp.get("_error", "")
        ok = status in OK and wk
        if ok: s_pass += 1; all_pass += 1
        flag = "✓" if ok else ("✗" if status in FAILED else "·")
        print(f"  [{flag}] {label}  status={status} worker={wk}", flush=True)
        rpt(f"| {flag} {label} | {st} | {status or '-'} | {wk} | `{tid[:16]}` | {chain} | {biz} |")
    scen_stat.append((title, s_pass, len(steps)))

rpt(f"\n## 汇总：{all_pass}/{all_steps} 业务步骤通过\n")
rpt("| 业务场景 | 通过 |")
rpt("|---------|------|")
for title, p, tot in scen_stat:
    rpt(f"| {'✓' if p==tot else '✗'} {title} | {p}/{tot} |")

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(RPT) + "\n")
print(f"\n汇总：{all_pass}/{all_steps} 通过 | 报告已写入: {REPORT_PATH}", flush=True)
sys.exit(0 if all_pass == all_steps else 1)
