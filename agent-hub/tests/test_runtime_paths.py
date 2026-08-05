"""runtime_paths data root resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import runtime_paths as rp


def test_resolve_hub_data_dir_dev_uses_repo_dot_data():
    with patch.object(rp, "resolve_install_root_for_data", return_value=None):
        with patch.object(rp, "resolve_repo_root", return_value=Path("H:/work/marketing-hub")):
            assert rp.resolve_hub_data_dir_path() == Path("H:/work/marketing-hub/.data")


def test_resolve_hub_data_dir_frozen_uses_install_data():
    install = Path("C:/Apps/MxAI")
    with patch.object(rp, "resolve_install_root_for_data", return_value=install):
        assert rp.resolve_hub_data_dir_path() == install / "data"


def test_resolve_hub_logs_dir_under_data_root():
    with patch.object(rp, "resolve_hub_data_dir_path", return_value=Path("H:/repo/.data")):
        assert rp.resolve_hub_logs_dir_path() == Path("H:/repo/.data/logs")


def test_resolve_install_root_for_data_frozen_exe():
    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", "C:\\Apps\\MxAI\\agent-hub.exe"):
            assert rp.resolve_install_root_for_data() == Path("C:/Apps/MxAI")


def test_get_hub_logs_dir():
    from hermes_constants import get_hub_logs_dir

    with patch("hermes_constants._agent_base_dir", return_value=Path("H:/repo/.data")):
        assert get_hub_logs_dir() == Path("H:/repo/.data/logs")
