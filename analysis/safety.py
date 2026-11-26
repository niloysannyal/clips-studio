"""CPU-safe pre-flight safety analysis for short candidate clips (10-60s).

Designed strictly for short rendered candidates (never full VODs) so it runs
in ~0.2s on CPU-only PyTorch / AMD hardware:
1. Licensed / copyrighted music detection via vocal-band spectral energy ratio.
2. Optional Demucs vocal/SFX isolation when explicitly enabled in config.
3. TikTok gore/blood safety check by sampling 1 fps frames for sustained
   crimson pixel dominance.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import numpy as np

from core.binaries import ffmpeg


def check_music_risk(clip_path: Path) -> tuple[bool, float]:
    """Detect heavy background music vs clean vocal speech over 1s windows.

    Returns (music_copyright_risk, vocal_band_ratio). Failure-safe: returns
    (False, 1.0) if audio cannot be probed.
    """
    try:
        cmd = [
            ffmpeg(), "-v", "error",
            "-i", str(clip_path),
            "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode != 0 or len(res.stdout) < 32000:
            return False, 1.0
        pcm = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        sr = 16000
        n_secs = pcm.size // sr
        if n_secs < 1:
            return False, 1.0
        freqs = np.fft.rfftfreq(sr, d=1.0 / sr)
        vocal_mask = (freqs >= 300.0) & (freqs <= 3400.0)
        full_mask = (freqs >= 60.0) & (freqs <= 7500.0)
        music_edge_mask = ((freqs >= 60.0) & (freqs < 280.0)) | ((freqs >= 3800.0) & (freqs <= 7500.0))

        ratios: list[float] = []
        music_heavy_windows = 0
        for s in range(n_secs):
            chunk = pcm[s * sr : (s + 1) * sr]
            if float(np.sqrt(np.mean(chunk * chunk))) < 0.012:
                continue  # skip silent seconds
            spec = np.abs(np.fft.rfft(chunk)) ** 2
            full_e = float(spec[full_mask].sum()) + 1e-12
            vocal_e = float(spec[vocal_mask].sum())
            edge_e = float(spec[music_edge_mask].sum())
            ratio = vocal_e / full_e
            ratios.append(ratio)
            if ratio < 0.45 and (edge_e / full_e) > 0.50:
                music_heavy_windows += 1

        if not ratios:
            return False, 1.0
        avg_ratio = round(float(np.mean(ratios)), 4)
        risk = (music_heavy_windows / len(ratios)) >= 0.40 and avg_ratio < 0.48
        return bool(risk), avg_ratio
    except Exception:
        return False, 1.0


def strip_music_demucs(clip_path: Path) -> bool:
    """Run Demucs on a short candidate clip to suppress licensed background tracks.

    Returns True only if Demucs ran and replaced clip audio cleanly. Fails safe
    without raising if Demucs is not installed.
    """
    if importlib.util.find_spec("demucs") is None:
        return False
    import tempfile
    import sys

    try:
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            wav_path = tmp_dir / "audio.wav"
            subprocess.run(
                [ffmpeg(), "-y", "-v", "error", "-i", str(clip_path), "-vn", "-ac", "2", "-ar", "44100", str(wav_path)],
                check=True, capture_output=True, timeout=30,
            )
            subprocess.run(
                [sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(tmp_dir), str(wav_path)],
                check=True, capture_output=True, timeout=180,
            )
            stems = list(tmp_dir.rglob("vocals.wav"))
            if not stems:
                return False
            out_tmp = clip_path.with_suffix(".nomusic.mp4")
            subprocess.run(
                [
                    ffmpeg(), "-y", "-v", "error",
                    "-i", str(clip_path),
                    "-i", str(stems[0]),
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    str(out_tmp),
                ],
                check=True, capture_output=True, timeout=30,
            )
            shutil.move(str(out_tmp), str(clip_path))
            return True
    except Exception:
        return False


def _format_range(start_s: int, end_s: int) -> str:
    return f"{start_s // 60:02d}:{start_s % 60:02d}-{end_s // 60:02d}:{end_s % 60:02d}"


def check_gore_safety(clip_path: Path, *, red_area_threshold: float = 0.08, min_streak_s: int = 3) -> tuple[bool, str]:
    """Sample 1 fps downscaled frames and flag sustained blood/crimson spikes."""
    try:
        w, h = 160, 284
        cmd = [
            ffmpeg(), "-v", "error",
            "-i", str(clip_path),
            "-vf", f"fps=1,scale={w}:{h}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        frame_bytes = w * h * 3
        if res.returncode != 0 or len(res.stdout) < frame_bytes:
            return False, ""
        n_frames = len(res.stdout) // frame_bytes
        raw = np.frombuffer(res.stdout[: n_frames * frame_bytes], dtype=np.uint8).reshape((n_frames, h, w, 3))

        crimson_flags: list[bool] = []
        for idx in range(n_frames):
            frame = raw[idx].astype(np.float32)
            r, g, b = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
            blood_mask = (r > 110.0) & (r > g * 1.85) & (r > b * 1.85)
            crimson_flags.append(float(np.mean(blood_mask)) >= red_area_threshold)

        best_start = best_end = -1
        cur_start: int | None = None
        for sec, flagged in enumerate(crimson_flags):
            if flagged:
                if cur_start is None:
                    cur_start = sec
            else:
                if cur_start is not None and (sec - cur_start) >= min_streak_s:
                    if (sec - cur_start) > (best_end - best_start):
                        best_start, best_end = cur_start, sec
                cur_start = None
        if cur_start is not None and (n_frames - cur_start) >= min_streak_s:
            if (n_frames - cur_start) > (best_end - best_start):
                best_start, best_end = cur_start, n_frames

        if best_start >= 0:
            return True, _format_range(best_start, best_end)
        return False, ""
    except Exception:
        return False, ""


def analyze_candidate_safety(clip_path: Path, config: dict | None = None) -> dict:
    """Run CPU-safe copyright music and gore pre-flight checks on a candidate clip."""
    music_risk, vocal_ratio = check_music_risk(clip_path)
    music_stripped = False
    strip_music = bool(((config or {}).get("wantedfeed") or {}).get("strip_music", False))
    if music_risk and strip_music:
        music_stripped = strip_music_demucs(clip_path)
        if music_stripped:
            music_risk = False
    gore_warn, warning_range = check_gore_safety(clip_path)
    return {
        "music_copyright_risk": music_risk,
        "vocal_band_ratio": vocal_ratio,
        "gore_safety_warning": gore_warn,
        "warning_range": warning_range,
        "music_stripped": music_stripped,
    }
