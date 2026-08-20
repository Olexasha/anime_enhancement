from __future__ import annotations

import json
import math
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
STATIC_SCENE_FALLBACK_MIN_RUN_FRAMES = 12
STATIC_SCENE_MAX_MEAN_LUMA_DIFF = 0.12
STATIC_SCENE_CHANGED_PIXEL_THRESHOLD = 8
STATIC_SCENE_MAX_CHANGED_PIXEL_RATIO = 0.0005
STATIC_SCENE_LOCAL_GRID_SIZE = (32, 32)
STATIC_SCENE_MAX_LOCAL_MEAN_LUMA_DIFF = 3


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
class StaticSceneRun:
    start_frame: int
    end_frame: int

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1


@dataclass(frozen=True, slots=True)
class GuardSegment:
    frame_paths: tuple[str, ...]
    start_frame: int
    end_frame: int
    is_static: bool


@dataclass(frozen=True, slots=True)
class SceneCutPlan:
    cuts: tuple[SceneCut, ...]
    static_runs: tuple[StaticSceneRun, ...] = ()


@dataclass(frozen=True, slots=True)
class SceneCutScanResult:
    plans_by_batch: dict[int, SceneCutPlan]
    cuts: tuple[SceneCut, ...]
    static_runs: tuple[StaticSceneRun, ...]
    requested_method: str
    method: str


@dataclass(slots=True)
class _FrameFeature:
    scene_feature: Any
    luma: np.ndarray


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


def calculate_static_scene_min_run_frames(
    fps: float | None,
    min_duration_seconds: float,
) -> int:
    if (
        fps is None
        or not math.isfinite(fps)
        or fps <= 0
        or not math.isfinite(min_duration_seconds)
        or min_duration_seconds <= 0
    ):
        return STATIC_SCENE_FALLBACK_MIN_RUN_FRAMES
    return max(2, math.ceil(fps * min_duration_seconds))


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
    static_min_run_frames: int = STATIC_SCENE_FALLBACK_MIN_RUN_FRAMES,
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

    cuts, static_runs = analyze_scene_frames(
        all_frames,
        method=effective_method,
        threshold=threshold,
        min_scene_frames=min_scene_frames,
        static_min_run_frames=static_min_run_frames,
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
        batch_static_runs: list[StaticSceneRun] = []
        for static_run in static_runs:
            matching_numbers = [
                number
                for number in frame_numbers
                if static_run.start_frame <= number <= static_run.end_frame
            ]
            if len(matching_numbers) >= 2:
                batch_static_runs.append(
                    StaticSceneRun(
                        start_frame=matching_numbers[0],
                        end_frame=matching_numbers[-1],
                    )
                )
        plans[batch_num] = SceneCutPlan(
            cuts=tuple(batch_cuts),
            static_runs=tuple(batch_static_runs),
        )

    return SceneCutScanResult(
        plans_by_batch=plans,
        cuts=tuple(cuts),
        static_runs=tuple(static_runs),
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
    cuts, _ = analyze_scene_frames(
        frame_paths,
        method=method,
        threshold=threshold,
        min_scene_frames=min_scene_frames,
    )
    return cuts


def analyze_scene_frames(
    frame_paths: list[str],
    *,
    method: str,
    threshold: float,
    min_scene_frames: int,
    static_min_run_frames: int = STATIC_SCENE_FALLBACK_MIN_RUN_FRAMES,
) -> tuple[list[SceneCut], list[StaticSceneRun]]:
    sorted_frames = sort_frame_paths(frame_paths)
    if len(sorted_frames) < 2:
        return [], []

    candidates: list[tuple[int, SceneCut]] = []
    static_runs: list[StaticSceneRun] = []
    previous_feature = _read_frame_feature(sorted_frames[0], method)
    static_anchor = previous_feature
    static_start_index = 0

    for index, current_path in enumerate(sorted_frames[1:], start=1):
        current_feature = _read_frame_feature(current_path, method)
        if previous_feature is None or current_feature is None:
            _append_static_run(
                static_runs,
                sorted_frames,
                static_start_index,
                index - 1,
                static_min_run_frames,
            )
            static_start_index = index
            static_anchor = current_feature
            previous_feature = current_feature
            continue

        score = _feature_distance(
            previous_feature.scene_feature,
            current_feature.scene_feature,
            method,
        )
        if score >= threshold:
            candidates.append(
                (
                    index - 1,
                    SceneCut(
                        from_frame=frame_number(sorted_frames[index - 1]),
                        to_frame=frame_number(current_path),
                        score=round(float(score), 6),
                    ),
                )
            )

        is_static = (
            score < threshold
            and static_anchor is not None
            and _frames_are_static(
                previous_feature.luma,
                current_feature.luma,
            )
            and _frames_are_static(
                static_anchor.luma,
                current_feature.luma,
            )
        )
        if not is_static:
            _append_static_run(
                static_runs,
                sorted_frames,
                static_start_index,
                index - 1,
                static_min_run_frames,
            )
            static_start_index = index
            static_anchor = current_feature
        previous_feature = current_feature

    _append_static_run(
        static_runs,
        sorted_frames,
        static_start_index,
        len(sorted_frames) - 1,
        static_min_run_frames,
    )

    cuts = _filter_short_scene_candidates(
        candidates,
        total_frames=len(sorted_frames),
        min_scene_frames=max(1, int(min_scene_frames)),
    )
    return cuts, static_runs


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


def build_guard_segments(
    frame_paths: list[str],
    cuts: tuple[SceneCut, ...] | list[SceneCut],
    static_runs: tuple[StaticSceneRun, ...] | list[StaticSceneRun],
) -> list[GuardSegment]:
    guarded_segments: list[GuardSegment] = []
    for scene in build_scene_segments(frame_paths, cuts):
        scene_paths = list(scene.frame_paths)
        frame_numbers = [frame_number(path) for path in scene_paths]
        static_mask = [False] * len(scene_paths)
        for static_run in static_runs:
            matching_indices = [
                index
                for index, number in enumerate(frame_numbers)
                if static_run.start_frame <= number <= static_run.end_frame
            ]
            if len(matching_indices) < 2:
                continue
            first_index = matching_indices[0]
            last_index = matching_indices[-1]
            for index in range(first_index, last_index + 1):
                static_mask[index] = True
            if first_index > 0:
                static_mask[first_index] = False
            if last_index < len(scene_paths) - 1:
                static_mask[last_index] = False

        group_start = 0
        for index in range(1, len(scene_paths) + 1):
            if (
                index < len(scene_paths)
                and static_mask[index] == static_mask[group_start]
            ):
                continue
            group_paths = tuple(scene_paths[group_start:index])
            guarded_segments.append(
                GuardSegment(
                    frame_paths=group_paths,
                    start_frame=frame_number(group_paths[0]),
                    end_frame=frame_number(group_paths[-1]),
                    is_static=static_mask[group_start],
                )
            )
            group_start = index
    return guarded_segments


def build_static_frame_map(
    frame_paths: list[str],
    static_runs: tuple[StaticSceneRun, ...] | list[StaticSceneRun],
) -> dict[str, str]:
    sorted_frames = sort_frame_paths(frame_paths)
    duplicates: dict[str, str] = {}
    for static_run in static_runs:
        matching_paths = [
            path
            for path in sorted_frames
            if static_run.start_frame <= frame_number(path) <= static_run.end_frame
        ]
        if len(matching_paths) < 2:
            continue
        representative = matching_paths[0]
        for duplicate in matching_paths[1:]:
            duplicates[duplicate] = representative
    return duplicates


def write_scene_cut_debug(
    *,
    report_path: str | Path,
    enabled: bool,
    requested_method: str,
    method: str,
    threshold: float,
    min_scene_frames: int,
    cuts: tuple[SceneCut, ...] | list[SceneCut],
    static_runs: tuple[StaticSceneRun, ...] | list[StaticSceneRun] = (),
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

    existing_static_runs = {
        (int(run.get("start_frame", -1)), int(run.get("end_frame", -1))): run
        for run in payload.get("static_runs", [])
        if isinstance(run, dict)
    }
    for static_run in static_runs:
        existing_static_runs[(static_run.start_frame, static_run.end_frame)] = {
            "start_frame": static_run.start_frame,
            "end_frame": static_run.end_frame,
            "frame_count": static_run.frame_count,
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
        "static_runs": [
            existing_static_runs[key]
            for key in sorted(
                existing_static_runs,
                key=lambda item: (item[0], item[1]),
            )
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_frame_feature(path: str, method: str) -> _FrameFeature | None:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        logger.warning(f"Scene Cut Guard: кадр не прочитан: {path}")
        return None
    luma = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detection_image = _resize_for_detection(image)
    if method == "ssim":
        gray = cv2.cvtColor(detection_image, cv2.COLOR_BGR2GRAY)
        scene_feature: Any = gray.astype(np.float32) / 255.0
        return _FrameFeature(scene_feature=scene_feature, luma=luma)

    hsv = cv2.cvtColor(detection_image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [16, 8, 8],
        [0, 180, 0, 256, 0, 256],
    )
    cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
    mean_luma = float(cv2.cvtColor(detection_image, cv2.COLOR_BGR2GRAY).mean() / 255.0)
    return _FrameFeature(scene_feature=(hist, mean_luma), luma=luma)


def _frames_are_static(left: np.ndarray, right: np.ndarray) -> bool:
    if left.shape != right.shape:
        return False
    difference = cv2.absdiff(left, right)
    if float(difference.mean()) > STATIC_SCENE_MAX_MEAN_LUMA_DIFF:
        return False
    local_difference = cv2.resize(
        difference,
        STATIC_SCENE_LOCAL_GRID_SIZE,
        interpolation=cv2.INTER_AREA,
    )
    if int(local_difference.max()) > STATIC_SCENE_MAX_LOCAL_MEAN_LUMA_DIFF:
        return False
    changed_ratio = float(
        np.count_nonzero(difference > STATIC_SCENE_CHANGED_PIXEL_THRESHOLD)
        / difference.size
    )
    return changed_ratio <= STATIC_SCENE_MAX_CHANGED_PIXEL_RATIO


def _append_static_run(
    runs: list[StaticSceneRun],
    frame_paths: list[str],
    start_index: int,
    end_index: int,
    min_run_frames: int,
) -> None:
    frame_count = end_index - start_index + 1
    if frame_count < max(2, min_run_frames):
        return
    runs.append(
        StaticSceneRun(
            start_frame=frame_number(frame_paths[start_index]),
            end_frame=frame_number(frame_paths[end_index]),
        )
    )


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
