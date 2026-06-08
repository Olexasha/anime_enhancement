from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config.pipeline_config import (
    PROJECT_ROOT,
    PipelineConfig,
    configure_app_local_tools,
)
from src.config.runtime_paths import (
    bundled_bin_path,
    default_data_dir,
    is_frozen,
    platform_key,
    profiles_dir,
    resource_path,
)


@dataclass(slots=True)
class DependencyCheck:
    name: str
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def expected_ai_binaries(project_root: Path | None = None) -> dict[str, Path]:
    _ = project_root
    return {
        "RealESRGAN": bundled_bin_path("realesrgan-ncnn-vulkan"),
        "waifu2x": bundled_bin_path("waifu2x-ncnn-vulkan"),
        "RIFE": bundled_bin_path("rife-ncnn-vulkan"),
    }


def check_environment(
    config: PipelineConfig | None = None, project_root: Path = PROJECT_ROOT
) -> list[DependencyCheck]:
    configure_app_local_tools(project_root)
    config = config or PipelineConfig.from_env()
    checks: list[DependencyCheck] = []

    python_version = sys.version_info
    if python_version >= (3, 13) and python_version < (3, 14):
        checks.append(
            DependencyCheck(
                "Python", "ok", f"Python {sys.version.split()[0]} подходит."
            )
        )
    else:
        checks.append(
            DependencyCheck(
                "Python",
                "error",
                f"Требуется Python 3.13.x, найден {sys.version.split()[0]}.",
            )
        )

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            checks.append(DependencyCheck(tool, "ok", f"{tool} найден: {path}"))
        else:
            checks.append(
                DependencyCheck(
                    tool,
                    "error",
                    f"{tool} не найден. Установите FFmpeg или запустите install.ps1/install.sh.",
                )
            )

    for name, path in expected_ai_binaries(project_root).items():
        if path.exists():
            checks.append(
                DependencyCheck(name, "ok", f"Исполняемый файл найден: {path}")
            )
        else:
            checks.append(
                DependencyCheck(
                    name,
                    "error",
                    "Исполняемый файл для текущей ОС "
                    f"({platform_key()}) не найден: {path}. "
                    "Windows/Linux/macOS требуют разные binaries.",
                )
            )

    _check_models(checks, project_root, config)
    _check_writable_dirs(checks, project_root)
    _check_disk_space(checks, config)
    _check_vulkan(checks)
    return checks


def has_errors(checks: list[DependencyCheck]) -> bool:
    return any(check.status == "error" for check in checks)


def format_report(checks: list[DependencyCheck]) -> str:
    labels = {"ok": "OK", "warn": "ПРЕДУПРЕЖДЕНИЕ", "error": "ОШИБКА"}
    return "\n".join(
        f"[{labels.get(check.status, check.status)}] {check.name}: {check.message}"
        for check in checks
    )


def _check_models(
    checks: list[DependencyCheck], project_root: Path, config: PipelineConfig
) -> None:
    realesrgan = (
        resource_path(
            Path("src")
            / "utils"
            / "realesrgan"
            / "models"
            / f"{config.REALESRGAN_MODEL_NAME}-x{config.UPSCALE_FACTOR}.param"
        )
    )
    if realesrgan.exists():
        checks.append(
            DependencyCheck(
                "Модель RealESRGAN", "ok", f"Модель найдена: {realesrgan.name}"
            )
        )
    else:
        fallback = (
            resource_path(
                Path("src")
                / "utils"
                / "realesrgan"
                / "models"
                / f"{config.REALESRGAN_MODEL_NAME}.param"
            )
        )
        status = "ok" if fallback.exists() else "error"
        message = (
            f"Модель найдена: {fallback.name}"
            if fallback.exists()
            else f"Модель не найдена: {realesrgan.name}"
        )
        checks.append(DependencyCheck("Модель RealESRGAN", status, message))

    waifu_model_dir = resource_path("src/utils/waifu2x/models")
    if waifu_model_dir.exists() and any(waifu_model_dir.rglob("*.param")):
        checks.append(
            DependencyCheck(
                "Модели waifu2x", "ok", f"Модели найдены в {waifu_model_dir}"
            )
        )
    else:
        checks.append(
            DependencyCheck(
                "Модели waifu2x", "error", f"Модели не найдены в {waifu_model_dir}"
            )
        )

    rife_model = (
        resource_path(
            Path("src")
            / "utils"
            / "rife"
            / "models"
            / ("rife-v4.6" if config.FRAMES_MULTIPLY_FACTOR > 2 else "rife-anime")
        )
    )
    if rife_model.exists() and any(rife_model.glob("*.param")):
        checks.append(
            DependencyCheck("Модель RIFE", "ok", f"Модель найдена: {rife_model}")
        )
    else:
        checks.append(
            DependencyCheck("Модель RIFE", "error", f"Модель не найдена: {rife_model}")
        )


def _check_writable_dirs(checks: list[DependencyCheck], project_root: Path) -> None:
    data_root = (
        default_data_dir()
        if is_frozen() or project_root == PROJECT_ROOT
        else project_root / "data"
    )
    dirs = [
        data_root / "audio",
        data_root / "tmp_video",
        data_root / "video_batches",
        data_root / "default_frame_batches",
        data_root / "upscaled_frame_batches",
        data_root / "output_video",
        profiles_dir()
        if is_frozen() or project_root == PROJECT_ROOT
        else project_root / "profiles",
    ]
    failed: list[str] = []
    for directory in dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError:
            failed.append(str(directory))
    if failed:
        checks.append(
            DependencyCheck(
                "Права записи", "error", "Нет записи в папки: " + ", ".join(failed)
            )
        )
    else:
        checks.append(
            DependencyCheck("Права записи", "ok", "Папки данных доступны для записи.")
        )


def _check_disk_space(checks: list[DependencyCheck], config: PipelineConfig) -> None:
    target = Path(config.FINAL_VIDEO).expanduser().parent
    try:
        usage = shutil.disk_usage(target if target.exists() else PROJECT_ROOT)
        free_gb = usage.free / (1024**3)
        if free_gb < 20:
            checks.append(
                DependencyCheck(
                    "Свободное место",
                    "warn",
                    f"Свободно {free_gb:.1f} ГБ. Для больших видео может потребоваться 50-200 ГБ.",
                )
            )
        else:
            checks.append(
                DependencyCheck("Свободное место", "ok", f"Свободно {free_gb:.1f} ГБ.")
            )
    except OSError as error:
        checks.append(
            DependencyCheck(
                "Свободное место", "warn", f"Не удалось проверить диск: {error}"
            )
        )


def _check_vulkan(checks: list[DependencyCheck]) -> None:
    vulkaninfo = shutil.which("vulkaninfo")
    if vulkaninfo:
        try:
            result = subprocess.run(
                [vulkaninfo, "--summary"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                checks.append(
                    DependencyCheck(
                        "Vulkan", "ok", "vulkaninfo успешно обнаружил Vulkan."
                    )
                )
            else:
                checks.append(
                    DependencyCheck(
                        "Vulkan",
                        "warn",
                        "vulkaninfo найден, но завершился с ошибкой. Проверьте драйвер GPU.",
                    )
                )
        except Exception as error:
            checks.append(
                DependencyCheck(
                    "Vulkan", "warn", f"Не удалось выполнить vulkaninfo: {error}"
                )
            )
    else:
        checks.append(
            DependencyCheck(
                "Vulkan",
                "warn",
                "vulkaninfo не найден. Проверка Vulkan пропущена; AI-утилиты могут сообщить ошибку драйвера при запуске.",
            )
        )
