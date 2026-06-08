from pathlib import Path

from src.config.dependency_checker import DependencyCheck, format_report, has_errors


def test_dependency_report_and_errors():
    checks = [
        DependencyCheck("Python", "ok", "Python подходит."),
        DependencyCheck("ffmpeg", "error", "ffmpeg не найден."),
    ]

    report = format_report(checks)

    assert has_errors(checks) is True
    assert "[OK] Python" in report
    assert "[ОШИБКА] ffmpeg" in report


def test_dependency_checker_can_be_monkeypatched(monkeypatch, tmp_path: Path):
    from src.config import dependency_checker as checker
    from src.config.pipeline_config import PipelineConfig

    monkeypatch.setattr(checker.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(checker, "expected_ai_binaries", lambda project_root: {})
    monkeypatch.setattr(
        checker, "_check_models", lambda checks, project_root, config: None
    )
    monkeypatch.setattr(
        checker,
        "_check_vulkan",
        lambda checks: checks.append(
            checker.DependencyCheck("Vulkan", "warn", "пропущено")
        ),
    )

    config = PipelineConfig(
        ORIGINAL_VIDEO=str(tmp_path / "in.mp4"), FINAL_VIDEO=str(tmp_path / "out.mp4")
    )
    checks = checker.check_environment(config, tmp_path)

    assert any(check.name == "ffmpeg" and check.status == "ok" for check in checks)
    assert any(check.name == "ffprobe" and check.status == "ok" for check in checks)
