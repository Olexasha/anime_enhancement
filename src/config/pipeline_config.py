from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from src.config.runtime_paths import (
    default_data_dir,
    project_root,
    resource_path,
)

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


PROJECT_ROOT = project_root()
PROFILE_VERSION = 1


def _default_input_video() -> str:
    return str(default_data_dir() / "input_video" / "input.mp4")


def _default_output_video() -> str:
    return str(default_data_dir() / "output_video" / "enhanced.mp4")


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "да", "истина", "вкл"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "нет", "ложь", "выкл"}:
        return False
    raise ValueError(f"Некорректное булево значение: {value!r}")


@dataclass(slots=True)
class PipelineConfig:
    ORIGINAL_VIDEO: str = ""
    FINAL_VIDEO: str = ""
    RESOLUTION: str = "4K"
    START_BATCH_TO_IMPROVE: int = 1
    END_BATCH_TO_IMPROVE: int = 0
    FRAMES_PER_BATCH: int = 1000
    OUTPUT_IMAGE_FORMAT: str = "png"
    ENABLE_DENOISE: bool = False
    ENABLE_INTERPOLATION: bool = True
    REALESRGAN_MODEL_NAME: str = "realesr-animevideov3"
    UPSCALE_FACTOR: int = 3
    DENOISE_FACTOR: int = 3
    WAIFU2X_UPSCALE_FACTOR: int = 1
    INTERMEDIATE_VIDEO_ENCODER: str = "libx264"
    INTERMEDIATE_VIDEO_CRF: int = 12
    INTERMEDIATE_VIDEO_PRESET: str = "medium"
    INTERMEDIATE_VIDEO_PIX_FMT: str = "yuv444p"
    INTERMEDIATE_VIDEO_CONTAINER: str = "mkv"
    FRAMES_MULTIPLY_FACTOR: int = 3
    ENABLE_UHD_MODE: bool = True
    ENABLE_SPATIAL_TTA_MODE: bool = False
    ENABLE_TEMPORAL_TTA_MODE: bool = False
    KEEP_TEMP_FILES: bool = False
    LOG_LEVEL: str = "INFO"

    def __post_init__(self) -> None:
        if not self.ORIGINAL_VIDEO:
            self.ORIGINAL_VIDEO = _default_input_video()
        if not self.FINAL_VIDEO:
            self.FINAL_VIDEO = _default_output_video()

    @classmethod
    def defaults(cls) -> PipelineConfig:
        return cls()

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> PipelineConfig:
        env_path = env_file if env_file is not None else PROJECT_ROOT / ".env"
        load_dotenv(env_path, override=False)
        values: dict[str, Any] = {}
        for field in fields(cls):
            raw = os.getenv(field.name)
            if raw is not None:
                values[field.name] = _coerce_value(raw, field.type)
        return cls(**_migrate_profile_payload(values))

    @classmethod
    def from_json(cls, path: str | Path) -> PipelineConfig:
        profile_path = Path(path)
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Профиль настроек не найден: {profile_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Профиль настроек содержит некорректный JSON: {profile_path}"
            ) from error

        if isinstance(payload, dict) and "settings" in payload:
            payload = payload["settings"]
        if not isinstance(payload, dict):
            raise ValueError("Профиль настроек должен быть JSON-объектом")

        payload = _migrate_profile_payload(payload)
        allowed = {field.name for field in fields(cls)}
        values = {
            key: _coerce_value(
                value, next(f.type for f in fields(cls) if f.name == key)
            )
            for key, value in payload.items()
            if key in allowed
        }
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json_payload(self) -> dict[str, Any]:
        return {"version": PROFILE_VERSION, "settings": self.to_dict()}

    def save_json(self, path: str | Path) -> Path:
        profile_path = Path(path)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            json.dumps(self.to_json_payload(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return profile_path

    def apply_to_environment(self) -> None:
        for key, value in self.to_dict().items():
            os.environ[key] = _serialize_env_value(value)
        os.environ["ANIME_ENHANCEMENT_CONFIG_ACTIVE"] = "1"
        configure_app_local_tools()

    def validate(self, *, require_input_exists: bool = True) -> list[str]:
        errors: list[str] = []
        input_path = Path(self.ORIGINAL_VIDEO).expanduser()
        output_path = Path(self.FINAL_VIDEO).expanduser()

        if require_input_exists and not input_path.is_file():
            errors.append(f"Входное видео не найдено: {input_path}")
        if output_path.exists() and output_path.is_dir():
            errors.append(
                f"FINAL_VIDEO должен быть путем к файлу, а не к папке: {output_path}"
            )
        if not output_path.suffix:
            errors.append(
                "FINAL_VIDEO должен содержать имя файла и расширение, например enhanced.mp4"
            )
        if self.START_BATCH_TO_IMPROVE < 1:
            errors.append("START_BATCH_TO_IMPROVE должен быть не меньше 1")
        if self.END_BATCH_TO_IMPROVE < 0:
            errors.append("END_BATCH_TO_IMPROVE должен быть 0 или больше")
        if (
            self.END_BATCH_TO_IMPROVE
            and self.END_BATCH_TO_IMPROVE < self.START_BATCH_TO_IMPROVE
        ):
            errors.append(
                "END_BATCH_TO_IMPROVE не может быть меньше START_BATCH_TO_IMPROVE"
            )
        if self.FRAMES_PER_BATCH < 1:
            errors.append("FRAMES_PER_BATCH должен быть больше 0")
        if self.OUTPUT_IMAGE_FORMAT.lower() not in {"png", "jpg", "jpeg", "webp"}:
            errors.append("OUTPUT_IMAGE_FORMAT должен быть png, jpg, jpeg или webp")
        if self.UPSCALE_FACTOR not in {1, 2, 3, 4}:
            errors.append("UPSCALE_FACTOR должен быть 1, 2, 3 или 4")
        if self.DENOISE_FACTOR not in {-1, 0, 1, 2, 3}:
            errors.append("DENOISE_FACTOR должен быть от -1 до 3")
        if self.WAIFU2X_UPSCALE_FACTOR not in {1, 2}:
            errors.append("WAIFU2X_UPSCALE_FACTOR должен быть 1 или 2")
        if self.INTERMEDIATE_VIDEO_ENCODER != "libx264":
            errors.append("INTERMEDIATE_VIDEO_ENCODER должен быть libx264")
        if not 0 <= self.INTERMEDIATE_VIDEO_CRF <= 51:
            errors.append("INTERMEDIATE_VIDEO_CRF должен быть от 0 до 51")
        if self.INTERMEDIATE_VIDEO_PIX_FMT not in {
            "bgr24",
            "rgb24",
            "bgr0",
            "yuv420p",
            "yuv422p",
            "yuv444p",
        }:
            errors.append(
                "INTERMEDIATE_VIDEO_PIX_FMT должен быть bgr24, rgb24, bgr0, "
                "yuv420p, yuv422p или yuv444p"
            )
        if self.INTERMEDIATE_VIDEO_CONTAINER not in {"mkv", "mp4"}:
            errors.append("INTERMEDIATE_VIDEO_CONTAINER должен быть mkv или mp4")
        if self.INTERMEDIATE_VIDEO_ENCODER == "libx264":
            if self.INTERMEDIATE_VIDEO_PIX_FMT not in {
                "yuv420p",
                "yuv422p",
                "yuv444p",
            }:
                errors.append(
                    "libx264 для short-видео требует INTERMEDIATE_VIDEO_PIX_FMT "
                    "yuv420p, yuv422p или yuv444p"
                )
        if self.FRAMES_MULTIPLY_FACTOR < 1:
            errors.append("FRAMES_MULTIPLY_FACTOR должен быть больше 0")
        return errors


def _coerce_value(value: Any, target_type: Any) -> Any:
    if target_type in {bool, "bool"}:
        return parse_bool(value)
    if target_type in {int, "int"}:
        return int(value)
    if target_type in {float, "float"}:
        return float(value)
    return str(value)


def _migrate_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Мигрирует старые JSON-профили на текущий stream-copy video-master."""
    migrated = dict(payload)
    migrated["INTERMEDIATE_VIDEO_ENCODER"] = "libx264"
    migrated["INTERMEDIATE_VIDEO_PRESET"] = "medium"
    migrated["INTERMEDIATE_VIDEO_PIX_FMT"] = "yuv444p"
    migrated["INTERMEDIATE_VIDEO_CONTAINER"] = "mkv"
    try:
        intermediate_crf = int(migrated.get("INTERMEDIATE_VIDEO_CRF", 0))
    except (TypeError, ValueError):
        intermediate_crf = 0
    if intermediate_crf in {0, 14}:
        migrated["INTERMEDIATE_VIDEO_CRF"] = 12
    return migrated


def _serialize_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def configure_app_local_tools(project_root: Path | None = None) -> None:
    root = project_root or PROJECT_ROOT
    candidates = [
        resource_path("tools/ffmpeg/bin"),
        resource_path("tools/ffmpeg"),
        root / ".tools" / "ffmpeg" / "bin",
    ]
    existing = [str(path) for path in candidates if path.exists()]
    if not existing:
        return
    current_path = os.environ.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    for path in reversed(existing):
        if path not in parts:
            parts.insert(0, path)
    os.environ["PATH"] = os.pathsep.join(parts)


FIELD_LABELS: dict[str, str] = {
    "ORIGINAL_VIDEO": "Исходное видео",
    "FINAL_VIDEO": "Итоговый файл",
    "RESOLUTION": "Целевое качество",
    "START_BATCH_TO_IMPROVE": "Начальный батч",
    "END_BATCH_TO_IMPROVE": "Конечный батч",
    "FRAMES_PER_BATCH": "Кадров в батче",
    "OUTPUT_IMAGE_FORMAT": "Формат кадров",
    "ENABLE_DENOISE": "Денойз перед апскейлом",
    "ENABLE_INTERPOLATION": "Интерполяция кадров",
    "REALESRGAN_MODEL_NAME": "Модель апскейла",
    "UPSCALE_FACTOR": "Множитель апскейла",
    "DENOISE_FACTOR": "Сила денойза",
    "WAIFU2X_UPSCALE_FACTOR": "Множитель waifu2x",
    "INTERMEDIATE_VIDEO_ENCODER": "Кодировщик short-видео",
    "INTERMEDIATE_VIDEO_CRF": "Качество short-видео",
    "INTERMEDIATE_VIDEO_PRESET": "Сжатие short-видео",
    "INTERMEDIATE_VIDEO_PIX_FMT": "Формат пикселей short-видео",
    "INTERMEDIATE_VIDEO_CONTAINER": "Контейнер short-видео",
    "FRAMES_MULTIPLY_FACTOR": "Множитель FPS",
    "ENABLE_UHD_MODE": "UHD-режим RIFE",
    "ENABLE_SPATIAL_TTA_MODE": "Spatial TTA RIFE",
    "ENABLE_TEMPORAL_TTA_MODE": "Temporal TTA RIFE",
    "KEEP_TEMP_FILES": "Сохранять временные файлы",
    "LOG_LEVEL": "Подробность логов",
}


FIELD_TOOLTIPS: dict[str, str] = {
    "ORIGINAL_VIDEO": "Видео, которое будет обрабатываться. Обычно это файл после монтажа или готовый исходник.",
    "FINAL_VIDEO": "Полный путь к итоговому видеофайлу. Это именно файл результата, не папка.",
    "RESOLUTION": "Метка целевого качества для профиля и логов. Реальный размер задаётся множителем апскейла.",
    "START_BATCH_TO_IMPROVE": "С какого батча начать обработку. Обычно 1. Полезно для продолжения или диагностики.",
    "END_BATCH_TO_IMPROVE": "На каком батче остановиться. 0 означает обработать все батчи до конца.",
    "FRAMES_PER_BATCH": "Сколько кадров класть в один батч. Меньше значение снижает пиковую нагрузку на диск/память.",
    "OUTPUT_IMAGE_FORMAT": "Формат промежуточных кадров. PNG рекомендуется для максимального качества без потерь.",
    "ENABLE_DENOISE": "Включает предварительный денойз через waifu2x. Может убрать шум, но также может замылить детали.",
    "ENABLE_INTERPOLATION": "Включает интерполяцию кадров через RIFE, чтобы увеличить FPS.",
    "REALESRGAN_MODEL_NAME": "Модель RealESRGAN для апскейла. Для аниме обычно лучше realesr-animevideov3.",
    "UPSCALE_FACTOR": "Во сколько раз увеличить размер кадра на этапе RealESRGAN.",
    "DENOISE_FACTOR": "Сила шумоподавления waifu2x: -1 авто/без шума, 0-3 уровни шума.",
    "WAIFU2X_UPSCALE_FACTOR": "Дополнительный множитель waifu2x на этапе денойза. Обычно должен быть 1.",
    "INTERMEDIATE_VIDEO_ENCODER": "Кодировщик short-видео. Production path использует libx264 video-master и затем stream-copy в final.",
    "INTERMEDIATE_VIDEO_CRF": "Качество short-видео для libx264. Ниже значение означает выше качество и больше файл. Production default: 12.",
    "INTERMEDIATE_VIDEO_PRESET": "Баланс скорости и размера short-видео для libx264. Production default: medium.",
    "INTERMEDIATE_VIDEO_PIX_FMT": "Формат пикселей short-видео. Production default yuv444p сохраняет цветовую детализацию без 4:2:0 subsampling.",
    "INTERMEDIATE_VIDEO_CONTAINER": "Контейнер short-видео. Production default mkv.",
    "FRAMES_MULTIPLY_FACTOR": "Во сколько раз увеличить FPS через RIFE. Например, 3 делает выходной FPS равным исходному FPS x3.",
    "ENABLE_UHD_MODE": "UHD-режим RIFE для высокого разрешения. Обычно нужен при 4K.",
    "ENABLE_SPATIAL_TTA_MODE": "Spatial TTA RIFE может улучшить качество, но сильно замедляет интерполяцию.",
    "ENABLE_TEMPORAL_TTA_MODE": "Temporal TTA RIFE повышает стабильность движения, но замедляет интерполяцию.",
    "KEEP_TEMP_FILES": "Не удалять временные кадры, short-видео, concat-файлы и merged-видео. Полезно для диагностики.",
    "LOG_LEVEL": "Минимальный уровень подробности логов в файлах и консоли.",
}


PRESETS: dict[str, dict[str, Any]] = {
    "Максимальное качество": {
        "ENABLE_DENOISE": False,
        "ENABLE_INTERPOLATION": True,
        "FRAMES_MULTIPLY_FACTOR": 3,
        "REALESRGAN_MODEL_NAME": "realesr-animevideov3",
        "UPSCALE_FACTOR": 3,
        "INTERMEDIATE_VIDEO_ENCODER": "libx264",
        "INTERMEDIATE_VIDEO_CRF": 12,
        "INTERMEDIATE_VIDEO_PRESET": "medium",
        "INTERMEDIATE_VIDEO_PIX_FMT": "yuv444p",
        "INTERMEDIATE_VIDEO_CONTAINER": "mkv",
        "ENABLE_UHD_MODE": True,
        "ENABLE_TEMPORAL_TTA_MODE": True,
    },
    "Быстрее": {
        "ENABLE_DENOISE": False,
        "ENABLE_INTERPOLATION": True,
        "FRAMES_MULTIPLY_FACTOR": 2,
        "UPSCALE_FACTOR": 2,
        "ENABLE_UHD_MODE": False,
    },
    "Слабое железо": {
        "ENABLE_DENOISE": False,
        "ENABLE_INTERPOLATION": False,
        "FRAMES_MULTIPLY_FACTOR": 1,
        "UPSCALE_FACTOR": 2,
        "FRAMES_PER_BATCH": 300,
        "ENABLE_UHD_MODE": False,
    },
    "Только апскейл": {
        "ENABLE_DENOISE": False,
        "ENABLE_INTERPOLATION": False,
        "FRAMES_MULTIPLY_FACTOR": 1,
        "UPSCALE_FACTOR": 3,
    },
    "Без интерполяции": {
        "ENABLE_INTERPOLATION": False,
        "FRAMES_MULTIPLY_FACTOR": 1,
    },
}


def apply_preset(config: PipelineConfig, preset_name: str) -> PipelineConfig:
    values = config.to_dict()
    values.update(PRESETS.get(preset_name, {}))
    return PipelineConfig(**values)
