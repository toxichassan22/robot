from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import soundfile as sf


REPEATED_FILLER_RE = re.compile(r"^(?:ا+|آ+|ام+|مم+|اه+|آه+|اوه+|يعني+|طيب+|هم+|هه+)\W*$")
ANNOTATION_RE = re.compile(r"\[(.*?)\]|\((.*?)\)|\{(.*?)\}")
MULTISPACE_RE = re.compile(r"\s+")
LAUGH_RE = re.compile(r"(?:ضحك|ضحكة|ههه|هاها|هههه|lol)", re.IGNORECASE)
MUSIC_RE = re.compile(r"(?:موسيقى|music|intro)", re.IGNORECASE)


@dataclass(slots=True)
class SegmentWindow:
    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


@dataclass(slots=True)
class PreparedSample:
    file_name: str
    relative_path: str
    start_sec: float
    end_sec: float
    duration_sec: float
    raw_text: str
    cleaned_text: str
    review_required: bool
    review_reason: str


@dataclass(slots=True)
class SkippedSample:
    file_name: str
    start_sec: float
    end_sec: float
    duration_sec: float
    raw_text: str
    cleaned_text: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a clean Arabic TTS dataset from a local file or YouTube URL. "
            "The pipeline downloads/extracts audio, trims the intro, runs VAD, "
            "transcribes each segment, and writes dataset metadata."
        )
    )
    parser.add_argument("--url", help="YouTube or direct media URL.")
    parser.add_argument("--input", help="Local audio/video file path.")
    parser.add_argument(
        "--output-dir",
        default="dataset",
        help="Dataset output directory. Default: %(default)s",
    )
    parser.add_argument(
        "--speaker-name",
        default="egyptian_speaker",
        help="Speaker label used in XTTS train/eval metadata.",
    )
    parser.add_argument(
        "--trim-start-seconds",
        type=float,
        default=5.0,
        help="Seconds to cut from the beginning to remove intro music.",
    )
    parser.add_argument(
        "--target-sample-rate",
        type=int,
        default=22050,
        help="Sample rate for final clips. Default: %(default)s",
    )
    parser.add_argument(
        "--vad-sample-rate",
        type=int,
        default=16000,
        help="Sample rate used by Silero VAD. Default: %(default)s",
    )
    parser.add_argument(
        "--min-segment-seconds",
        type=float,
        default=2.0,
        help="Discard segments shorter than this.",
    )
    parser.add_argument(
        "--max-segment-seconds",
        type=float,
        default=8.0,
        help="Split segments longer than this.",
    )
    parser.add_argument(
        "--merge-gap-seconds",
        type=float,
        default=0.35,
        help="Merge nearby VAD segments separated by less than this gap.",
    )
    parser.add_argument(
        "--segment-padding-ms",
        type=int,
        default=250,
        help="Padding added around VAD segments.",
    )
    parser.add_argument(
        "--min-silence-ms",
        type=int,
        default=350,
        help="Minimum silence used by VAD.",
    )
    parser.add_argument(
        "--min-speech-ms",
        type=int,
        default=250,
        help="Minimum speech length used by VAD.",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        help="faster-whisper model name or local path. Default: %(default)s",
    )
    parser.add_argument(
        "--whisper-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Inference device for faster-whisper.",
    )
    parser.add_argument(
        "--whisper-compute-type",
        default="auto",
        help="Compute type for faster-whisper. Default resolves from device.",
    )
    parser.add_argument(
        "--language",
        default="ar",
        help="Language hint passed to Whisper. Default: %(default)s",
    )
    parser.add_argument(
        "--initial-prompt",
        default="النص التالي عربي واضح مناسب لتدريب نظام نطق.",
        help="Optional prompt to stabilize transcription style.",
    )
    parser.add_argument(
        "--model-cache-dir",
        default="dataset/_models",
        help="Directory for Whisper/Silero caches to keep downloads inside the project.",
    )
    parser.add_argument(
        "--eval-ratio",
        type=float,
        default=0.05,
        help="Fraction of accepted clips written to metadata_eval.csv.",
    )
    parser.add_argument(
        "--yt-dlp-bin",
        default="yt-dlp",
        help="Path to yt-dlp binary.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help="Path to ffmpeg binary.",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep downloaded/raw intermediate files under _work.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Clear the output directory before creating the dataset.",
    )

    args = parser.parse_args()
    if bool(args.url) == bool(args.input):
        parser.error("Pass exactly one of --url or --input.")
    if args.min_segment_seconds <= 0:
        parser.error("--min-segment-seconds must be positive.")
    if args.max_segment_seconds <= args.min_segment_seconds:
        parser.error("--max-segment-seconds must be greater than --min-segment-seconds.")
    if args.eval_ratio < 0 or args.eval_ratio >= 1:
        parser.error("--eval-ratio must be in [0, 1).")
    return args


def ensure_command(command_name: str) -> str:
    resolved = shutil.which(command_name)
    if not resolved:
        raise RuntimeError(f"Required command '{command_name}' was not found on PATH.")
    return resolved


def run_command(command: Sequence[str], cwd: Path | None = None) -> None:
    process = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
    )
    if process.returncode == 0:
        return

    message = process.stderr.strip() or process.stdout.strip() or "Unknown command failure"
    raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")


def maybe_clear_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def acquire_source_audio(args: argparse.Namespace, work_dir: Path) -> Path:
    if args.input:
        source = Path(args.input).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Input file was not found: {source}")
        return source

    yt_dlp_bin = ensure_command(args.yt_dlp_bin)
    output_template = work_dir / "source.%(ext)s"
    run_command(
        (
            yt_dlp_bin,
            "-f",
            "bestaudio",
            "-x",
            "--audio-format",
            "wav",
            "--audio-quality",
            "0",
            "-o",
            str(output_template),
            args.url,
        )
    )
    downloaded = work_dir / "source.wav"
    if not downloaded.exists():
        raise FileNotFoundError("yt-dlp finished, but source.wav was not created.")
    return downloaded


def normalize_audio(input_path: Path, output_path: Path, ffmpeg_bin: str, trim_start: float, sample_rate: int) -> None:
    ensure_command(ffmpeg_bin)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if trim_start > 0:
        cmd += ["-ss", f"{trim_start:.3f}"]
    cmd += [
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-vn",
        "-sn",
        "-dn",
        str(output_path),
    ]
    run_command(cmd)


def configure_model_cache(model_cache_dir: Path) -> None:
    hf_home = model_cache_dir / ".hf-home"
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
    os.environ.setdefault("XDG_CACHE_HOME", str(model_cache_dir / ".xdg-cache"))
    model_cache_dir.mkdir(parents=True, exist_ok=True)


def detect_speech_windows(audio_path: Path, args: argparse.Namespace) -> list[SegmentWindow]:
    configure_model_cache(Path(args.model_cache_dir).expanduser().resolve())
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError as exc:
        raise RuntimeError("silero-vad is not installed. Run: pip install silero-vad") from exc

    model = load_silero_vad()
    audio = read_audio(str(audio_path), sampling_rate=args.vad_sample_rate)
    timestamps = get_speech_timestamps(
        audio,
        model,
        sampling_rate=args.vad_sample_rate,
        min_speech_duration_ms=args.min_speech_ms,
        min_silence_duration_ms=args.min_silence_ms,
        speech_pad_ms=args.segment_padding_ms,
    )
    return [
        SegmentWindow(
            start_sec=stamp["start"] / args.vad_sample_rate,
            end_sec=stamp["end"] / args.vad_sample_rate,
        )
        for stamp in timestamps
    ]


def merge_and_split_windows(
    windows: Sequence[SegmentWindow],
    min_segment_seconds: float,
    max_segment_seconds: float,
    merge_gap_seconds: float,
) -> list[SegmentWindow]:
    if not windows:
        return []

    merged: list[SegmentWindow] = [SegmentWindow(windows[0].start_sec, windows[0].end_sec)]
    for window in windows[1:]:
        previous = merged[-1]
        if (
            window.start_sec - previous.end_sec <= merge_gap_seconds
            and window.end_sec - previous.start_sec <= max_segment_seconds
        ):
            previous.end_sec = max(previous.end_sec, window.end_sec)
        else:
            merged.append(SegmentWindow(window.start_sec, window.end_sec))

    final_windows: list[SegmentWindow] = []
    for window in merged:
        duration = window.duration_sec
        if duration < min_segment_seconds:
            continue
        if duration <= max_segment_seconds:
            final_windows.append(window)
            continue

        segment_count = max(2, math.ceil(duration / max_segment_seconds))
        chunk_size = duration / segment_count
        current = window.start_sec
        for _ in range(segment_count):
            end = min(window.end_sec, current + chunk_size)
            chunk = SegmentWindow(current, end)
            if chunk.duration_sec >= min_segment_seconds:
                final_windows.append(chunk)
            current = end

    return final_windows


def read_audio_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if isinstance(audio, np.ndarray) and audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    return audio, sample_rate


def normalize_peak(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 0.0:
        return audio
    return np.clip(audio / peak * 0.98, -1.0, 1.0)


def write_clip(audio: np.ndarray, sample_rate: int, window: SegmentWindow, output_path: Path) -> None:
    start = max(0, int(window.start_sec * sample_rate))
    end = min(len(audio), int(window.end_sec * sample_rate))
    clip = audio[start:end]
    if clip.size == 0:
        raise RuntimeError(f"Empty clip for {output_path.name}")
    sf.write(str(output_path), normalize_peak(clip), sample_rate)


def resolve_whisper_device(requested_device: str) -> str:
    if requested_device != "auto":
        return requested_device
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_compute_type(requested_compute_type: str, device: str) -> str:
    if requested_compute_type != "auto":
        return requested_compute_type
    return "float16" if device == "cuda" else "int8"


def load_whisper_model(args: argparse.Namespace):
    configure_model_cache(Path(args.model_cache_dir).expanduser().resolve())
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper") from exc

    model_cache_dir = Path(args.model_cache_dir).expanduser().resolve() / "faster-whisper"
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    device = resolve_whisper_device(args.whisper_device)
    compute_type = resolve_compute_type(args.whisper_compute_type, device)
    return WhisperModel(
        args.whisper_model,
        device=device,
        compute_type=compute_type,
        download_root=str(model_cache_dir),
    )


def transcribe_clip(model, clip_path: Path, args: argparse.Namespace) -> str:
    segments, _info = model.transcribe(
        str(clip_path),
        language=args.language,
        beam_size=5,
        best_of=5,
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=args.initial_prompt or None,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def clean_transcript(text: str) -> str:
    cleaned = ANNOTATION_RE.sub(" ", text or "")
    cleaned = cleaned.replace("ـ", "")
    cleaned = cleaned.replace("|", " ")
    cleaned = MULTISPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def review_reason_for_text(text: str) -> str:
    if not text:
        return "empty_transcript"
    if REPEATED_FILLER_RE.fullmatch(text):
        return "filler_only"
    if LAUGH_RE.search(text):
        return "contains_laughter"
    if MUSIC_RE.search(text):
        return "contains_music_marker"
    return ""


def build_train_eval_split(samples: Sequence[PreparedSample], eval_ratio: float) -> tuple[list[PreparedSample], list[PreparedSample]]:
    if eval_ratio <= 0 or len(samples) < 20:
        return list(samples), []

    eval_count = max(1, int(round(len(samples) * eval_ratio)))
    interval = max(1, len(samples) // eval_count)
    eval_indexes = set(range(interval - 1, len(samples), interval))
    eval_samples = [sample for idx, sample in enumerate(samples) if idx in eval_indexes]
    train_samples = [sample for idx, sample in enumerate(samples) if idx not in eval_indexes]
    return train_samples, eval_samples


def write_metadata_files(output_dir: Path, samples: Sequence[PreparedSample], speaker_name: str, eval_ratio: float) -> None:
    metadata_path = output_dir / "metadata.csv"
    with metadata_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj, delimiter="|", lineterminator="\n")
        for sample in samples:
            writer.writerow([sample.file_name, sample.cleaned_text])

    train_samples, eval_samples = build_train_eval_split(samples, eval_ratio)
    train_path = output_dir / "metadata_train.csv"
    with train_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj, delimiter="|", lineterminator="\n")
        for sample in train_samples:
            writer.writerow([sample.relative_path, sample.cleaned_text, speaker_name])

    eval_path = output_dir / "metadata_eval.csv"
    with eval_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj, delimiter="|", lineterminator="\n")
        for sample in eval_samples:
            writer.writerow([sample.relative_path, sample.cleaned_text, speaker_name])


def write_review_files(output_dir: Path, accepted: Sequence[PreparedSample], skipped: Sequence[SkippedSample]) -> None:
    review_path = output_dir / "review_candidates.csv"
    with review_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(
            [
                "file_name",
                "start_sec",
                "end_sec",
                "duration_sec",
                "raw_text",
                "cleaned_text",
                "review_reason",
            ]
        )
        for sample in accepted:
            if sample.review_required:
                writer.writerow(
                    [
                        sample.file_name,
                        f"{sample.start_sec:.3f}",
                        f"{sample.end_sec:.3f}",
                        f"{sample.duration_sec:.3f}",
                        sample.raw_text,
                        sample.cleaned_text,
                        sample.review_reason,
                    ]
                )

    skipped_path = output_dir / "skipped_segments.csv"
    with skipped_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(
            [
                "file_name",
                "start_sec",
                "end_sec",
                "duration_sec",
                "raw_text",
                "cleaned_text",
                "reason",
            ]
        )
        for sample in skipped:
            writer.writerow(
                [
                    sample.file_name,
                    f"{sample.start_sec:.3f}",
                    f"{sample.end_sec:.3f}",
                    f"{sample.duration_sec:.3f}",
                    sample.raw_text,
                    sample.cleaned_text,
                    sample.reason,
                ]
            )


def write_summary(output_dir: Path, source_audio: Path, normalized_audio: Path, accepted: Sequence[PreparedSample], skipped: Sequence[SkippedSample]) -> None:
    summary = {
        "source_audio": str(source_audio),
        "normalized_audio": str(normalized_audio),
        "accepted_count": len(accepted),
        "skipped_count": len(skipped),
        "accepted_duration_sec": round(sum(sample.duration_sec for sample in accepted), 3),
        "skipped_duration_sec": round(sum(sample.duration_sec for sample in skipped), 3),
        "accepted": [asdict(sample) for sample in accepted],
        "skipped": [asdict(sample) for sample in skipped],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_dataset(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve()
    maybe_clear_output(output_dir, args.overwrite)
    wavs_dir = output_dir / "wavs"
    work_dir = output_dir / "_work"
    wavs_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    source_audio = acquire_source_audio(args, work_dir)
    normalized_audio = work_dir / "clean.wav"
    normalize_audio(
        input_path=source_audio,
        output_path=normalized_audio,
        ffmpeg_bin=args.ffmpeg_bin,
        trim_start=args.trim_start_seconds,
        sample_rate=args.target_sample_rate,
    )

    windows = detect_speech_windows(normalized_audio, args)
    windows = merge_and_split_windows(
        windows,
        min_segment_seconds=args.min_segment_seconds,
        max_segment_seconds=args.max_segment_seconds,
        merge_gap_seconds=args.merge_gap_seconds,
    )

    if not windows:
        raise RuntimeError("No speech windows were detected after VAD.")

    audio, sample_rate = read_audio_mono(normalized_audio)
    whisper_model = load_whisper_model(args)

    accepted: list[PreparedSample] = []
    skipped: list[SkippedSample] = []

    for index, window in enumerate(windows, start=1):
        file_name = f"segment_{index:04d}.wav"
        clip_path = wavs_dir / file_name
        write_clip(audio, sample_rate, window, clip_path)

        raw_text = transcribe_clip(whisper_model, clip_path, args)
        cleaned_text = clean_transcript(raw_text)
        reason = review_reason_for_text(cleaned_text)

        if len(cleaned_text) < 3:
            reason = reason or "transcript_too_short"

        if reason == "filler_only" or reason == "empty_transcript" or reason == "transcript_too_short":
            skipped.append(
                SkippedSample(
                    file_name=file_name,
                    start_sec=window.start_sec,
                    end_sec=window.end_sec,
                    duration_sec=window.duration_sec,
                    raw_text=raw_text,
                    cleaned_text=cleaned_text,
                    reason=reason,
                )
            )
            clip_path.unlink(missing_ok=True)
            continue

        accepted.append(
            PreparedSample(
                file_name=file_name,
                relative_path=f"wavs/{file_name}",
                start_sec=window.start_sec,
                end_sec=window.end_sec,
                duration_sec=window.duration_sec,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                review_required=bool(reason),
                review_reason=reason,
            )
        )

    if not accepted:
        raise RuntimeError("No usable samples were produced. Review skipped_segments.csv.")

    write_metadata_files(output_dir, accepted, args.speaker_name, args.eval_ratio)
    write_review_files(output_dir, accepted, skipped)
    write_summary(output_dir, source_audio, normalized_audio, accepted, skipped)

    if not args.keep_intermediate and args.input:
        try:
            shutil.rmtree(work_dir)
        except OSError:
            pass

    print(f"Dataset ready at: {output_dir}")
    print(f"Accepted clips : {len(accepted)}")
    print(f"Skipped clips  : {len(skipped)}")
    print(f"Audio minutes  : {sum(sample.duration_sec for sample in accepted) / 60:.2f}")
    print(f"Metadata       : {output_dir / 'metadata.csv'}")
    print(f"Review file    : {output_dir / 'review_candidates.csv'}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return build_dataset(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
