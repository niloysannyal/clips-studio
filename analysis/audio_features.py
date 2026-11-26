"""Audio excitement signals, fully local (FFmpeg decode -> numpy).

Produces per-second feature arrays over the whole video:
  loudness  - RMS energy per second
  spike     - how loud this second is vs. the rolling 30s median
              (shouts, cheers, hype moments)
  burst     - density of sudden energy onsets within the second
              (laughter, applause, rapid-fire excitement)
  noisiness - zero-crossing rate (broadband/noisy audio like laughter and
              crowd noise scores high; clean speech scores low)

All arrays are raw values here; fusion.py normalizes them to per-video
percentiles. No ML models involved — this is signal processing, which is
exactly why it's fast (~seconds for a 30-minute video).
"""

from pathlib import Path

import numpy as np

from core import cancel
from core.binaries import ffmpeg

SAMPLE_RATE = 16000
FRAME = SAMPLE_RATE // 20  # 50 ms analysis frames


def extract_audio_features(video_path: Path) -> dict[str, np.ndarray]:
    """Returns {feature_name: array indexed by second}. Empty dict if the
    video has no audio stream. Streams 60s chunks from FFmpeg so even 7h+
    VODs use <5 MB RAM instead of buffering gigabytes of PCM."""
    import subprocess

    frames_per_sec = SAMPLE_RATE // FRAME
    sec_bytes = SAMPLE_RATE * 2  # 16-bit mono PCM per second
    chunk_bytes = sec_bytes * 60  # 60s (~1.92 MB) per read

    cmd = [
        ffmpeg(), "-v", "error",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    loudness_chunks: list[np.ndarray] = []
    burst_chunks: list[np.ndarray] = []
    zcr_chunks: list[np.ndarray] = []
    leftover = b""
    prev_last_rms: float | None = None

    try:
        assert proc.stdout is not None
        while True:
            cancel.check_active()
            raw = proc.stdout.read(chunk_bytes)
            if not raw:
                break
            buf = leftover + raw
            usable_bytes = (len(buf) // sec_bytes) * sec_bytes
            leftover = buf[usable_bytes:]
            if usable_bytes == 0:
                continue

            pcm = np.frombuffer(buf[:usable_bytes], dtype=np.int16).astype(np.float32) / 32768.0
            n_secs = usable_bytes // sec_bytes
            n_frames = n_secs * frames_per_sec
            frames = pcm.reshape(n_frames, FRAME)
            frame_rms = np.sqrt((frames ** 2).mean(axis=1))

            per_sec_rms = frame_rms.reshape(n_secs, frames_per_sec)
            loudness_chunks.append(per_sec_rms.mean(axis=1).astype(np.float32))

            if prev_last_rms is None:
                prev_arr = np.concatenate([[frame_rms[0]], frame_rms[:-1]])
                onsets = frame_rms > 2.0 * np.maximum(prev_arr, 1e-6)
                onsets[0] = False
            else:
                prev_arr = np.concatenate([[prev_last_rms], frame_rms[:-1]])
                onsets = frame_rms > 2.0 * np.maximum(prev_arr, 1e-6)
            prev_last_rms = float(frame_rms[-1])
            burst_chunks.append(onsets.reshape(n_secs, frames_per_sec).sum(axis=1).astype(np.float32))

            signs = np.signbit(frames)
            frame_zcr = (signs[:, 1:] != signs[:, :-1]).mean(axis=1)
            zcr_chunks.append(frame_zcr.reshape(n_secs, frames_per_sec).mean(axis=1).astype(np.float32))
    except Exception:
        proc.kill()
        proc.wait()
        raise

    stderr_bytes = proc.stderr.read() if proc.stderr else b""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg audio decode failed:\n{stderr_bytes[-1000:].decode(errors='replace')}")
    if not loudness_chunks:
        return {}

    loudness = np.concatenate(loudness_chunks)
    spike = loudness / np.maximum(_rolling_median(loudness, 30), 1e-6)
    spike = np.clip(spike, 0, 5)
    burst = np.concatenate(burst_chunks)
    noisiness = np.concatenate(zcr_chunks)
    audible = loudness > max(float(loudness.mean()) * 0.3, 1e-6)
    noisiness = (noisiness * audible).astype(np.float32)

    return {
        "loudness": loudness,
        "spike": spike,
        "burst": burst,
        "noisiness": noisiness,
    }


def _rolling_median(x: np.ndarray, window: int) -> np.ndarray:
    """Median of a centered window at each position (edges shrink)."""
    half = window // 2
    out = np.empty_like(x)
    for i in range(x.size):
        lo, hi = max(0, i - half), min(x.size, i + half + 1)
        out[i] = np.median(x[lo:hi])
    return out
