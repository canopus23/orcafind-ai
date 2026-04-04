import os
import shutil
import subprocess
import tempfile


def _ffmpeg_path() -> str:
    return os.getenv("FFMPEG_PATH") or "ffmpeg"


def lowres_watermark_mp4(video_bytes: bytes) -> bytes:
    """
    Convert MP4 bytes to a low-resolution MP4 with a text watermark.
    Requires ffmpeg in PATH (or via FFMPEG_PATH env var).
    """
    ffmpeg = _ffmpeg_path()
    if not shutil.which(ffmpeg):
        raise RuntimeError("ffmpeg is not available")

    watermark_text = (os.getenv("VIDEO_WATERMARK_TEXT") or "OrcaFind AI").replace(":", "\\:")

    # Output target: 540x960, padded/cropped while preserving aspect ratio.
    vf = (
        "scale=540:960:force_original_aspect_ratio=decrease,"
        "pad=540:960:(ow-iw)/2:(oh-ih)/2,"
        f"drawtext=text='{watermark_text}':"
        "fontcolor=white@0.86:fontsize=28:"
        "box=1:boxcolor=black@0.35:boxborderw=10:"
        "x=w-tw-22:y=h-th-22"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.mp4")
        out_path = os.path.join(tmpdir, "output.mp4")

        with open(in_path, "wb") as f:
            f.write(video_bytes)

        cmd = [
            ffmpeg,
            "-y",
            "-i",
            in_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-maxrate",
            "900k",
            "-bufsize",
            "1200k",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            out_path,
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr[-400:]}")

        with open(out_path, "rb") as f:
            return f.read()

