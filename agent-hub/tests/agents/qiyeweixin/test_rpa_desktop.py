"""LT-002.04.1：企微桌面 RPA."""

def test_qywx_add_contacts(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/tasks/add-contacts",
        json={"contacts": ["13800001111", "13800002222"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"


def test_qywx_send_file(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/tasks/send-file",
        json={"recipient": "ww_user", "file_path": "/tmp/demo.pdf"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"
