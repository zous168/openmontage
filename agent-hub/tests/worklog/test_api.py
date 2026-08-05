"""LT-002.09.1 / CR-64：工作明细 API."""

import sqlite3

from plugins.mxai.worklog.service import append_worklog, purge_expired_worklogs, _db_path


def test_worklog_list_export(mxai_env, mxai_client) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="comment_collect",
        exec_status="成功",
        data_dir=mxai_env,
    )
    lst = mxai_client.get("/api/plugins/mxai/worklogs?agent=douyin").json()
    assert lst["total"] >= 1
    export = mxai_client.post(
        "/api/plugins/mxai/worklogs/export",
        json={"profile_id": "douyin", "limit": 10},
    )
    assert export.status_code == 200
    assert "log_id" in export.text


def test_worklog_query_q_and_status(mxai_env, mxai_client) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="unique_op_marker",
        exec_status="失败",
        op_object="客户张三",
        fail_reason="timeout",
        task_id="task_search_01",
        data_dir=mxai_env,
    )
    append_worklog(
        profile_id="douyin",
        op_type="other",
        exec_status="成功",
        data_dir=mxai_env,
    )
    by_q = mxai_client.get("/api/plugins/mxai/worklogs?q=unique_op_marker").json()
    assert by_q["total"] >= 1
    assert all("unique_op_marker" in (i.get("op_type") or "") for i in by_q["items"])

    by_status = mxai_client.get(
        "/api/plugins/mxai/worklogs?exec_status=失败&agent=douyin"
    ).json()
    assert by_status["total"] >= 1
    assert all(i.get("exec_status") == "失败" for i in by_status["items"])

    by_task = mxai_client.get("/api/plugins/mxai/worklogs?task_id=task_search_01").json()
    assert by_task["total"] >= 1
    assert all(i.get("task_id") == "task_search_01" for i in by_task["items"])


def test_purge_expired_worklogs(mxai_env) -> None:
    db = _db_path(mxai_env)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO work_logs (
            log_id, op_time, profile_id, op_type, op_object,
            exec_status, fail_reason, elapsed_ms, task_id
        ) VALUES ('log_old', datetime('now', '-40 days'), 'douyin', 'stale', '', '成功', NULL, NULL, NULL)
        """
    )
    conn.commit()
    conn.close()

    deleted = purge_expired_worklogs(30, data_dir=mxai_env)
    assert deleted >= 1

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT COUNT(*) FROM work_logs WHERE log_id = 'log_old'").fetchone()
    conn.close()
    assert int(row[0]) == 0
