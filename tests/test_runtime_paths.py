from pathlib import Path


def test_frozen_runtime_paths_stay_next_to_executable(monkeypatch, tmp_path):
    from src.config import runtime_paths

    app_dir = tmp_path / "AnimeEnhancement"
    exe_path = app_dir / "AnimeEnhancementCLI.exe"

    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(exe_path))
    monkeypatch.delenv("ANIME_ENHANCEMENT_DATA_DIR", raising=False)
    monkeypatch.delenv("ANIME_ENHANCEMENT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ANIME_ENHANCEMENT_USER_DATA_DIR", raising=False)

    assert runtime_paths.app_root() == app_dir
    assert runtime_paths.default_data_dir() == app_dir / "data"
    assert runtime_paths.profiles_dir() == app_dir / "profiles"
    assert runtime_paths.logs_parent_dir() == app_dir
    assert runtime_paths.user_config_dir() == app_dir / "config"


def test_data_dir_override_is_still_explicit(monkeypatch, tmp_path):
    from src.config import runtime_paths

    override = Path(tmp_path / "custom-data")

    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        runtime_paths.sys,
        "executable",
        str(tmp_path / "AnimeEnhancement" / "AnimeEnhancementCLI.exe"),
    )
    monkeypatch.setenv("ANIME_ENHANCEMENT_DATA_DIR", str(override))

    assert runtime_paths.default_data_dir() == override


def test_frozen_dev_build_uses_repo_data(monkeypatch, tmp_path):
    from src.config import runtime_paths

    repo_root = tmp_path / "repo"
    app_dir = repo_root / "dist" / "AnimeEnhancement"
    exe_path = app_dir / "AnimeEnhancementCLI.exe"
    (repo_root / "src" / "config").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")

    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(exe_path))
    monkeypatch.delenv("ANIME_ENHANCEMENT_DATA_DIR", raising=False)
    monkeypatch.delenv("ANIME_ENHANCEMENT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ANIME_ENHANCEMENT_USER_DATA_DIR", raising=False)

    assert runtime_paths.app_root() == app_dir
    assert runtime_paths.default_data_dir() == repo_root / "data"
    assert runtime_paths.profiles_dir() == repo_root / "profiles"
    assert runtime_paths.logs_parent_dir() == repo_root
    assert runtime_paths.user_config_dir() == repo_root / "config"
