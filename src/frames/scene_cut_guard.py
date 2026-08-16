from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.utils.logger import logger
from src.video.video_helpers import sort_frame_paths

FRAME_NUMBER_RE = re.compile(r"(\d+)(?=\.[^.]+$)")
SUPPORTED_METHODS = {"auto", "histogram", "ssim"}


@dataclass(frozen=True, slots=True)
class SceneCut:
    from_frame: int
    to_frame: int
    score: float


@dataclass(frozen=True, slots=True)
class SceneSegment:
    frame_paths: tuple[str, ...]
    start_frame: int
    end_frame: int


@dataclass(frozen=True, slots=True)
class SceneCutPlan:
    cuts: tuple[SceneCut, ...]


@dataclass(frozen=True, slots=True)
class SceneCutScanResult:
    plans_by_batch: dict[int, SceneCutPlan]
    cuts: tuple[SceneCut, ...]
    requested_method: str
    method: str


def frame_number(path: str | Path) -> int:
    match = FRAME_NUMBER_RE.search(Path(path).name)
    if not match:
        raise ValueError(f"Не удалось определить номер кадра: {path}")
    return int(match.group(1))


def effective_detection_method(method: str) -> str:
    normalized = (method or "auto").strip().lower()
    if normalized not in SUPPORTED_METHODS:
        logger.warning(
            f"Неизвестный метод Scene Cut Guard: {method!r}; используется histogram"
        )
        return "histogram"
    if normalized == "auto":
        return "histogram"
    return normalized


def list_batch_frames(
    input_root: str | Path,
    batch_num: int,
    image_format: str,
) -> list[str]:
    batch_dir = Path(input_root) / f"batch_{batch_num}"
    if not batch_dir.exists():
        return []
    ext = f".{image_format.lower().lstrip('.')}"
    return sort_frame_paths(
        [
            str(path)
            for path in batch_dir.iterdir()
            if path.is_file() and path.name.lower().endswith(ext)
        ]
    )


def build_scene_cut_plans(
    *,
    input_root: str | Path,
    batch_numbers: range,
    image_format: str,
    method: str,
    threshold: float,
    min_scene_frames: int,
) -> SceneCutScanResult:
    requested_method = (method or "auto").strip().lower()
    effective_method = effective_detection_method(requested_method)
    frames_by_batch = {
        batch_num: list_batch_frames(input_root, batch_num, image_format)
        for batch_num in batch_numbers
    }
    all_frames: list[str] = []
    for batch_num in batch_numbers:
        all_frames.extend(frames_by_batch[batch_num])

    cuts = detect_scene_cuts(
        all_frames,
        method=effective_method,
        threshold=threshold,
        min_scene_frames=min_scene_frames,
    )
    cuts_by_pair = {(cut.from_frame, cut.to_frame): cut for cut in cuts}

    plans: dict[int, SceneCutPlan] = {}
    for batch_num, frame_paths in frames_by_batch.items():
        frame_numbers = [frame_number(path) for path in frame_paths]
        batch_cuts: list[SceneCut] = []
        for index in range(max(0, len(frame_numbers) - 1)):
            cut = cuts_by_pair.get((frame_numbers[index], frame_numbers[index + 1]))
            if cut is not None:
                batch_cuts.append(cut)
        plans[batch_num] = SceneCutPlan(
            cuts=tuple(batch_cuts),
        )

    return SceneCutScanResult(
        plans_by_batch=plans,
        cuts=tuple(cuts),
        requested_method=requested_method,
        method=effective_method,
    )


def detect_scene_cuts(
    frame_paths: list[str],
    *,
    method: str,
    threshold: float,
    min_scene_frames: int,
) -> list[SceneCut]:
    sorted_frames = sort_frame_paths(frame_paths)
    if len(sorted_frames) < 2:
        return []

    features: list[Any | None] = [
        _read_scene_feature(path, method) for path in sorted_frames
    ]
    candidates: list[tuple[int, SceneCut]] = []
    for index in range(len(sorted_frames) - 1):
        left_feature = features[index]
        right_feature = features[index + 1]
        if left_feature is None or right_feature is None:
            continue
        score = _feature_distance(left_feature, right_feature, method)
        if score >= threshold:
            candidates.append(
                (
                    index,
                    SceneCut(
                        from_frame=frame_number(sorted_frames[index]),
                        to_frame=frame_number(sorted_frames[index + 1]),
                        score=round(float(score), 6),
                    ),
                )
            )

    return _filter_short_scene_candidates(
        candidates,
        total_frames=len(sorted_frames),
        min_scene_frames=max(1, int(min_scene_frames)),
    )


def build_scene_segments(
    frame_paths: list[str],
    cuts: tuple[SceneCut, ...] | list[SceneCut],
) -> list[SceneSegment]:
    sorted_frames = sort_frame_paths(frame_paths)
    if not sorted_frames:
        return []

    cut_pairs = {(cut.from_frame, cut.to_frame) for cut in cuts}
    start_index = 0
    segments: list[SceneSegment] = []
    for index in range(len(sorted_frames) - 1):
        current_frame = frame_number(sorted_frames[index])
        next_frame = frame_number(sorted_frames[index + 1])
        if (current_frame, next_frame) not in cut_pairs:
            continue
        segment_paths = tuple(sorted_frames[start_index : index + 1])
        segments.append(
            SceneSegment(
                frame_paths=segment_paths,
                start_frame=frame_number(segment_paths[0]),
                end_frame=frame_number(segment_paths[-1]),
            )
        )
        start_index = index + 1

    segment_paths = tuple(sorted_frames[start_index:])
    segments.append(
        SceneSegment(
            frame_paths=segment_paths,
            start_frame=frame_number(segment_paths[0]),
            end_frame=frame_number(segment_paths[-1]),
        )
    )
    return segments


def write_scene_cut_debug(
    *,
    report_path: str | Path,
    enabled: bool,
    requested_method: str,
    method: str,
    threshold: float,
    min_scene_frames: int,
    cuts: tuple[SceneCut, ...] | list[SceneCut],
) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}

    existing = {
        (int(cut.get("from_frame", -1)), int(cut.get("to_frame", -1))): cut
        for cut in payload.get("cuts", [])
        if isinstance(cut, dict)
    }
    for cut in cuts:
        existing[(cut.from_frame, cut.to_frame)] = {
            "from_frame": cut.from_frame,
            "to_frame": cut.to_frame,
            "score": round(float(cut.score), 6),
        }

    payload = {
        "enabled": bool(enabled),
        "method": method,
        "requested_method": requested_method,
        "threshold": float(threshold),
        "min_scene_frames": int(min_scene_frames),
        "cuts": [
            existing[key]
            for key in sorted(existing, key=lambda item: (item[0], item[1]))
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_scene_feature(path: str, method: str) -> Any | None:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        logger.warning(f"Scene Cut Guard: кадр не прочитан: {path}")
        return None
    image = _resize_for_detection(image)
    if method == "ssim":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return gray.astype(np.float32) / 255.0

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [16, 8, 8],
        [0, 180, 0, 256, 0, 256],
    )
    cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
    luma = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean() / 255.0)
    return hist, luma


def _resize_for_detection(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge <= 180:
        return image
    scale = 180 / long_edge
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _feature_distance(left: Any, right: Any, method: str) -> float:
    if method == "ssim":
        return _ssim_distance(left, right)
    left_hist, left_luma = left
    right_hist, right_luma = right
    hist_distance = float(
        cv2.compareHist(left_hist, right_hist, cv2.HISTCMP_BHATTACHARYYA)
    )
    luma_distance = abs(float(left_luma) - float(right_luma))
    return max(0.0, min(1.0, hist_distance * 0.85 + luma_distance * 0.15))


def _ssim_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        right = cv2.resize(
            right,
            (left.shape[1], left.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    c1 = 0.01**2
    c2 = 0.03**2
    left_mean = float(left.mean())
    right_mean = float(right.mean())
    left_variance = float(((left - left_mean) ** 2).mean())
    right_variance = float(((right - right_mean) ** 2).mean())
    covariance = float(((left - left_mean) * (right - right_mean)).mean())
    numerator = (2 * left_mean * right_mean + c1) * (2 * covariance + c2)
    denominator = (left_mean**2 + right_mean**2 + c1) * (
        left_variance + right_variance + c2
    )
    similarity = numerator / max(denominator, 1e-9)
    return max(0.0, min(1.0, 1.0 - similarity))


def _filter_short_scene_candidates(
    candidates: list[tuple[int, SceneCut]],
    *,
    total_frames: int,
    min_scene_frames: int,
) -> list[SceneCut]:
    accepted: list[SceneCut] = []
    current_scene_start = 0
    for cut_index, cut in candidates:
        left_len = cut_index - current_scene_start + 1
        right_len = total_frames - cut_index - 1
        if left_len < min_scene_frames or right_len < min_scene_frames:
            continue
        accepted.append(cut)
        current_scene_start = cut_index + 1
    return accepted
