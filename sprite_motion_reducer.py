#!/usr/bin/env python3
"""Sprite Motion Reducer v0.1.

Convert a short action video/GIF into raw frames, a reduced sprite sheet,
variable-duration preview GIF, Unity timing metadata, and a keyframe report.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class FramePick:
    order: int
    source_frame: int
    source_time_ms: int
    duration_ms: int
    sheet_x: int
    sheet_y: int
    tags: list[str]
    score: float
    locked: bool


def parse_int_list(value: str | None) -> set[int]:
    if not value:
        return set()
    result: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        result.add(int(part))
    return result


def read_video_frames(path: Path, fps_override: float | None) -> tuple[list[Image.Image], float, int, list[int]]:
    reader = imageio.get_reader(path)
    meta = reader.get_meta_data()
    frames: list[Image.Image] = []
    frame_durations_ms: list[int] = []
    is_gif = path.suffix.lower() == ".gif"

    for index, frame in enumerate(reader):
        image = Image.fromarray(frame).convert("RGBA")
        frames.append(image)
        if is_gif:
            try:
                duration = int(reader.get_meta_data(index).get("duration") or 0)
            except (IndexError, OSError, RuntimeError):
                duration = 0
            if duration > 0:
                frame_durations_ms.append(duration)
    reader.close()

    if not frames:
        raise ValueError(f"No frames could be read from {path}")

    if is_gif and len(frame_durations_ms) == len(frames):
        duration_ms = sum(frame_durations_ms)
        fps = fps_override or len(frames) / (duration_ms / 1000)
        return frames, fps, duration_ms, frame_durations_ms

    fps = fps_override or float(meta.get("fps") or 0)
    meta_duration = float(meta.get("duration", 0) or 0)
    duration_ms = int(round(meta_duration * 1000)) if meta_duration > 0 else 0

    if fps <= 0:
        if duration_ms > 0:
            fps = len(frames) / (duration_ms / 1000)
        else:
            fps = 30.0

    if duration_ms <= 0:
        duration_ms = int(round(len(frames) / fps * 1000))

    constant_duration = max(1, int(round(1000 / fps)))
    return frames, fps, duration_ms, [constant_duration] * len(frames)


def resize_frames(frames: Iterable[Image.Image], size: tuple[int, int] | None) -> list[Image.Image]:
    if size is None:
        return [frame.copy() for frame in frames]
    return [ImageOps.contain(frame, size, method=Image.Resampling.LANCZOS).resize(size) for frame in frames]


def save_raw_frames(frames: list[Image.Image], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        frame.save(folder / f"frame_{index:04d}.png")


def frame_difference_scores(frames: list[Image.Image]) -> list[float]:
    if len(frames) == 1:
        return [0.0]

    arrays = [np.asarray(frame, dtype=np.float32) / 255.0 for frame in frames]
    diffs = [0.0]
    for current, previous in zip(arrays[1:], arrays[:-1]):
        rgb_diff = float(np.mean(np.abs(current[:, :, :3] - previous[:, :, :3])))
        alpha_diff = float(np.mean(np.abs(current[:, :, 3] - previous[:, :, 3])))
        diffs.append(rgb_diff * 0.7 + alpha_diff * 0.3)

    scores = [0.0] * len(frames)
    for index in range(1, len(frames)):
        delta = abs(diffs[index] - diffs[index - 1])
        scores[index] = diffs[index] * 0.7 + delta * 0.3
    return scores


def average_keyframes(total: int, target: int, loop: bool, locked: set[int], excluded: set[int]) -> list[int]:
    must_keep = {0, *locked}
    if not loop:
        must_keep.add(total - 1)
    must_keep = {index for index in must_keep if 0 <= index < total and index not in excluded}

    if target <= len(must_keep):
        return sorted(must_keep)[:target]

    picks = set(must_keep)
    slots = target - len(picks)
    for value in np.linspace(0, total - 1, slots + 2)[1:-1]:
        index = int(round(value))
        while index in picks or index in excluded:
            index = min(total - 1, index + 1)
            if index in picks or index in excluded:
                break
        if index not in excluded:
            picks.add(index)
    return fill_missing(sorted(picks), total, target, excluded)


def diff_keyframes(
    scores: list[float],
    target: int,
    loop: bool,
    locked: set[int],
    excluded: set[int],
    minimum_distance: int | None,
) -> list[int]:
    total = len(scores)
    must_keep = {0, *locked}
    if not loop:
        must_keep.add(total - 1)
    selected = {index for index in must_keep if 0 <= index < total and index not in excluded}

    if target <= len(selected):
        return sorted(selected)[:target]

    base_distance = minimum_distance
    if base_distance is None:
        base_distance = max(1, int(total / target / 2))

    ranked = sorted(range(total), key=lambda index: scores[index], reverse=True)
    distance = base_distance
    while len(selected) < target and distance >= 0:
        changed = False
        for index in ranked:
            if len(selected) >= target:
                break
            if index in selected or index in excluded:
                continue
            if distance and any(abs(index - other) < distance for other in selected):
                continue
            selected.add(index)
            changed = True
        if not changed:
            distance -= 1

    return fill_missing(sorted(selected), total, target, excluded)


def fill_missing(picks: list[int], total: int, target: int, excluded: set[int]) -> list[int]:
    selected = set(picks)
    if len(selected) >= target:
        return sorted(selected)[:target]
    for index in np.linspace(0, total - 1, target * 2):
        candidate = int(round(index))
        if candidate not in selected and candidate not in excluded:
            selected.add(candidate)
        if len(selected) >= target:
            break
    for candidate in range(total):
        if len(selected) >= target:
            break
        if candidate not in selected and candidate not in excluded:
            selected.add(candidate)
    return sorted(selected)[:target]


def calculate_durations(picks: list[int], fps: float, total_duration_ms: int) -> list[int]:
    if len(picks) == 1:
        return [total_duration_ms]

    times = [index / fps * 1000 for index in picks]
    boundaries = [0.0]
    for previous, current in zip(times, times[1:]):
        boundaries.append((previous + current) / 2)
    boundaries.append(float(total_duration_ms))

    durations = [max(1, int(round(boundaries[index + 1] - boundaries[index]))) for index in range(len(picks))]
    drift = total_duration_ms - sum(durations)
    durations[-1] = max(1, durations[-1] + drift)
    return durations


def make_sprite_sheet(
    frames: list[Image.Image],
    picks: list[int],
    columns: int,
    rows: int,
    padding: int,
) -> Image.Image:
    if columns * rows < len(picks):
        raise ValueError(f"Grid {columns}x{rows} cannot hold {len(picks)} frames")

    frame_width, frame_height = frames[0].size
    width = columns * frame_width + max(0, columns - 1) * padding
    height = rows * frame_height + max(0, rows - 1) * padding
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for order, frame_index in enumerate(picks):
        column = order % columns
        row = order // columns
        x = column * (frame_width + padding)
        y = row * (frame_height + padding)
        sheet.alpha_composite(frames[frame_index], (x, y))
    return sheet


def save_preview_gif(path: Path, frames: list[Image.Image], durations: list[int]) -> None:
    images = [frame.convert("RGBA") for frame in frames]
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        disposal=2,
    )


def build_frame_picks(
    picks: list[int],
    scores: list[float],
    fps: float,
    durations: list[int],
    columns: int,
    locked: set[int],
) -> list[FramePick]:
    result: list[FramePick] = []
    for order, source_frame in enumerate(picks):
        tags: list[str] = []
        if source_frame == 0:
            tags.append("start")
        if order == len(picks) - 1:
            tags.append("end")
        if source_frame in locked:
            tags.append("locked")
        if not tags:
            tags.append("diff_peak")

        result.append(
            FramePick(
                order=order,
                source_frame=source_frame,
                source_time_ms=int(round(source_frame / fps * 1000)),
                duration_ms=durations[order],
                sheet_x=order % columns,
                sheet_y=order // columns,
                tags=tags,
                score=round(float(scores[source_frame]), 6),
                locked=source_frame in locked,
            )
        )
    return result


def write_unity_json(
    path: Path,
    source_video: Path,
    sheet_name: str,
    fps: float,
    raw_count: int,
    source_duration_ms: int,
    frame_size: tuple[int, int],
    columns: int,
    rows: int,
    padding: int,
    loop: bool,
    picks: list[FramePick],
) -> None:
    data = {
        "version": "0.1",
        "animation_name": source_video.stem,
        "source": {
            "video": source_video.name,
            "duration_ms": source_duration_ms,
            "source_fps": round(fps, 3),
            "raw_frame_count": raw_count,
        },
        "sheet": {
            "image": sheet_name,
            "columns": columns,
            "rows": rows,
            "frame_width": frame_size[0],
            "frame_height": frame_size[1],
            "padding": padding,
        },
        "animation": {
            "loop": loop,
            "total_duration_ms": sum(pick.duration_ms for pick in picks),
            "frames": [
                {
                    "order": pick.order,
                    "source_frame": pick.source_frame,
                    "source_time_ms": pick.source_time_ms,
                    "duration_ms": pick.duration_ms,
                    "duration_sec": round(pick.duration_ms / 1000, 6),
                    "sheet_x": pick.sheet_x,
                    "sheet_y": pick.sheet_y,
                    "tags": pick.tags,
                    "score": pick.score,
                    "locked": pick.locked,
                }
                for pick in picks
            ],
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, picks: list[FramePick], total_duration_ms: int) -> None:
    lines = [
        "# Keyframe Report",
        "",
        f"- Selected frames: {len(picks)}",
        f"- Total duration: {total_duration_ms} ms",
        "",
        "| Order | Source Frame | Source Time | Duration | Sheet | Score | Tags |",
        "| ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for pick in picks:
        lines.append(
            f"| {pick.order} | {pick.source_frame} | {pick.source_time_ms} ms | "
            f"{pick.duration_ms} ms | ({pick.sheet_x}, {pick.sheet_y}) | "
            f"{pick.score:.6f} | {', '.join(pick.tags)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def infer_grid(target: int, grid: list[int] | None) -> tuple[int, int]:
    if grid:
        return grid[0], grid[1]
    side = int(math.ceil(math.sqrt(target)))
    return side, int(math.ceil(target / side))


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_frames, fps, source_duration_ms, original_durations = read_video_frames(input_path, args.fps)
    size = tuple(args.size) if args.size else None
    frames = resize_frames(raw_frames, size)
    frame_width, frame_height = frames[0].size

    columns, rows = infer_grid(args.target, args.grid)
    locked = parse_int_list(args.lock)
    excluded = parse_int_list(args.exclude)

    scores = frame_difference_scores(frames)
    if args.strategy == "average":
        picks = average_keyframes(len(frames), args.target, args.loop, locked, excluded)
    else:
        picks = diff_keyframes(scores, args.target, args.loop, locked, excluded, args.min_distance)

    durations = calculate_durations(picks, fps, source_duration_ms)
    frame_picks = build_frame_picks(picks, scores, fps, durations, columns, locked)

    save_raw_frames(frames, output_dir / "raw_frames")
    save_preview_gif(output_dir / "preview_original.gif", frames, original_durations)

    sheet_name = f"reduced_sheet_{columns}x{rows}.png"
    sheet = make_sprite_sheet(frames, picks, columns, rows, args.padding)
    sheet.save(output_dir / sheet_name)

    reduced_frames = [frames[index] for index in picks]
    save_preview_gif(output_dir / "preview_reduced.gif", reduced_frames, durations)

    write_unity_json(
        output_dir / "unity_timing.json",
        input_path,
        sheet_name,
        fps,
        len(frames),
        source_duration_ms,
        (frame_width, frame_height),
        columns,
        rows,
        args.padding,
        args.loop,
        frame_picks,
    )
    write_report(output_dir / "keyframe_report.md", frame_picks, sum(durations))

    print(f"Sprite Motion Reducer finished: {output_dir}")
    print(f"Raw frames: {len(frames)} | Selected: {len(picks)} | FPS: {fps:.3f}")
    print(f"Sheet: {sheet_name} | Timing: unity_timing.json | Preview: preview_reduced.gif")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert action video/GIF into reduced sprite sheet data.")
    parser.add_argument("input", help="Input .mp4 or .gif")
    parser.add_argument("--target", type=int, default=16, help="Target keyframe count, such as 9, 16, 24, 32")
    parser.add_argument("--grid", nargs=2, type=int, metavar=("COLUMNS", "ROWS"), help="Sprite sheet grid")
    parser.add_argument("--output", required=True, help="Output folder")
    parser.add_argument("--size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Output cell size")
    parser.add_argument("--loop", action="store_true", help="Do not force last source frame for looping animation")
    parser.add_argument("--fps", type=float, help="Original FPS override")
    parser.add_argument("--min-distance", type=int, help="Minimum source-frame distance between selected keyframes")
    parser.add_argument("--lock", help="Comma-separated source frames that must be kept, e.g. 0,8,15")
    parser.add_argument("--exclude", help="Comma-separated source frames that must not be selected")
    parser.add_argument("--padding", type=int, default=0, help="Padding between sheet cells in pixels")
    parser.add_argument("--strategy", choices=("diff", "average"), default="diff", help="Keyframe selection strategy")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.target <= 0:
        parser.error("--target must be greater than 0")
    if args.padding < 0:
        parser.error("--padding cannot be negative")
    run(args)


if __name__ == "__main__":
    main()
