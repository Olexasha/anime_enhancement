import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.config.pipeline_config import PipelineConfig


def test_cli_initializes_multiprocessing_before_argparse(monkeypatch):
    import main as cli_main

    events = []

    def fake_initialize_multiprocessing():
        events.append("multiprocessing")

    def fake_parse_args(argv):
        events.append("argparse")
        raise RuntimeError("stop before config loading")

    monkeypatch.setattr(
        cli_main, "initialize_multiprocessing", fake_initialize_multiprocessing
    )
    monkeypatch.setattr(cli_main, "parse_args", fake_parse_args)

    with pytest.raises(RuntimeError, match="stop before config loading"):
        cli_main.main([])

    assert events == ["multiprocessing", "argparse"]


def test_cli_config_prints_effective_config(tmp_path: Path):
    profile = tmp_path / "profile.json"
    config = PipelineConfig(
        ORIGINAL_VIDEO=str(tmp_path / "input.mp4"),
        FINAL_VIDEO=str(tmp_path / "output.mp4"),
        ENABLE_INTERPOLATION=False,
    )
    config.save_json(profile)

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--config",
            str(profile),
            "--print-effective-config",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["settings"]["FINAL_VIDEO"] == str(tmp_path / "output.mp4")
    assert payload["settings"]["ENABLE_INTERPOLATION"] is False
