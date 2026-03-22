"""Video Analyzer MCP Server.

Downloads videos, extracts frames, transcribes audio, and returns
structured data for Claude's multimodal analysis.

External dependencies (must be on PATH):
  - ffmpeg / ffprobe
  - yt-dlp
  - whisper (OpenAI whisper CLI, optional for transcription)
"""

import asyncio
import base64
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, ImageContent, Tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_bin(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


async def _run_async(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return await asyncio.to_thread(_run, cmd, timeout)


def _probe_json(path: str) -> dict:
    """Get video metadata via ffprobe."""
    result = _run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return json.loads(result.stdout)


def _get_duration(probe: dict) -> float:
    """Extract duration in seconds from ffprobe output."""
    if "format" in probe and "duration" in probe["format"]:
        return float(probe["format"]["duration"])
    for stream in probe.get("streams", []):
        if "duration" in stream:
            return float(stream["duration"])
    return 0.0


def _has_audio(probe: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

async def download_video(url: str, output_dir: str, max_height: int = 480) -> str:
    """Download video via yt-dlp. Returns path to downloaded file."""
    output_path = str(Path(output_dir) / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-playlist",
        "--socket-timeout", "30",
        url,
    ]
    result = await _run_async(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    # Find the downloaded file
    for f in Path(output_dir).iterdir():
        if f.name.startswith("video.") and f.suffix in (".mp4", ".webm", ".mkv"):
            return str(f)
    raise RuntimeError("Download succeeded but no video file found")


async def extract_frames(
    video_path: str,
    output_dir: str,
    interval_seconds: float = 30.0,
    max_frames: int = 20,
    width: int = 640,
) -> list[str]:
    """Extract frames at regular intervals. Returns list of JPEG paths."""
    probe = _probe_json(video_path)
    duration = _get_duration(probe)

    if duration <= 0:
        interval_seconds = 1.0
        count = min(5, max_frames)
    else:
        # Adjust interval so we don't exceed max_frames
        count = min(int(duration / interval_seconds) + 1, max_frames)
        if count < 1:
            count = 1
        interval_seconds = duration / count

    frames_dir = Path(output_dir) / "frames"
    frames_dir.mkdir(exist_ok=True)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval_seconds},scale={width}:-1",
        "-frames:v", str(count),
        "-q:v", "3",
        str(frames_dir / "frame_%04d.jpg"),
        "-y",
    ]
    result = await _run_async(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Frame extraction failed: {result.stderr}")

    paths = sorted(frames_dir.glob("frame_*.jpg"))
    return [str(p) for p in paths]


async def extract_audio(video_path: str, output_dir: str) -> str | None:
    """Extract audio track as WAV. Returns path or None if no audio."""
    probe = _probe_json(video_path)
    if not _has_audio(probe):
        return None

    audio_path = str(Path(output_dir) / "audio.wav")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        audio_path, "-y",
    ]
    result = await _run_async(cmd)
    if result.returncode != 0:
        return None
    return audio_path


async def transcribe_audio(audio_path: str, output_dir: str, language: str | None = None) -> str:
    """Transcribe audio using OpenAI Whisper CLI. Returns transcript text."""
    cmd = [
        "whisper", audio_path,
        "--model", "base",
        "--output_format", "txt",
        "--output_dir", output_dir,
    ]
    if language:
        cmd.extend(["--language", language])

    result = await _run_async(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Whisper transcription failed: {result.stderr}")

    # Whisper writes <filename>.txt
    txt_path = Path(output_dir) / (Path(audio_path).stem + ".txt")
    if txt_path.exists():
        return txt_path.read_text().strip()
    # Fallback: find any .txt
    for f in Path(output_dir).glob("*.txt"):
        return f.read_text().strip()
    return ""


def get_metadata(video_path: str) -> dict:
    """Return structured metadata about the video."""
    probe = _probe_json(video_path)
    fmt = probe.get("format", {})
    video_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )
    audio_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "audio"),
        {},
    )

    return {
        "duration_seconds": _get_duration(probe),
        "format": fmt.get("format_name"),
        "size_bytes": int(fmt.get("size", 0)),
        "video_codec": video_stream.get("codec_name"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "fps": video_stream.get("r_frame_rate"),
        "has_audio": bool(audio_stream),
        "audio_codec": audio_stream.get("codec_name"),
        "tags": fmt.get("tags", {}),
    }


def frames_to_base64(frame_paths: list[str]) -> list[dict]:
    """Convert frame files to base64 dicts with timestamps."""
    results = []
    for i, path in enumerate(frame_paths):
        data = Path(path).read_bytes()
        results.append({
            "index": i,
            "filename": Path(path).name,
            "base64": base64.b64encode(data).decode(),
            "mime_type": "image/jpeg",
        })
    return results


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

app = Server("video-analyzer")


TOOLS = [
    Tool(
        name="analyze_video",
        description=(
            "Download a video from URL (YouTube, Bilibili, or any yt-dlp supported site), "
            "extract key frames and metadata. Returns frames as base64 images for visual analysis. "
            "Optionally transcribes audio."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Video URL (YouTube, Bilibili, direct link, or any yt-dlp supported URL)",
                },
                "frame_interval": {
                    "type": "number",
                    "description": "Seconds between frame captures (default: 30)",
                    "default": 30,
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Maximum number of frames to extract (default: 20)",
                    "default": 20,
                },
                "transcribe": {
                    "type": "boolean",
                    "description": "Whether to transcribe the audio track (default: false)",
                    "default": False,
                },
                "language": {
                    "type": "string",
                    "description": "Language hint for transcription (e.g. 'zh', 'en', 'ja'). Auto-detect if omitted.",
                },
                "max_height": {
                    "type": "integer",
                    "description": "Max video height in pixels for download (default: 480, lower = faster)",
                    "default": 480,
                },
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="analyze_local_video",
        description=(
            "Analyze a local video file — extract key frames, metadata, and optionally transcribe audio. "
            "Returns frames as base64 images for visual analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the local video file",
                },
                "frame_interval": {
                    "type": "number",
                    "description": "Seconds between frame captures (default: 30)",
                    "default": 30,
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Maximum number of frames to extract (default: 20)",
                    "default": 20,
                },
                "transcribe": {
                    "type": "boolean",
                    "description": "Whether to transcribe the audio track (default: false)",
                    "default": False,
                },
                "language": {
                    "type": "string",
                    "description": "Language hint for transcription (e.g. 'zh', 'en', 'ja'). Auto-detect if omitted.",
                },
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="video_metadata",
        description="Get metadata (duration, resolution, codecs, etc.) for a video URL or local file without downloading the full video.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Video URL or local file path",
                },
            },
            "required": ["source"],
        },
    ),
    Tool(
        name="transcribe_video",
        description="Download and transcribe the audio from a video URL or local file using Whisper.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Video URL or local file path",
                },
                "language": {
                    "type": "string",
                    "description": "Language hint (e.g. 'zh', 'en', 'ja'). Auto-detect if omitted.",
                },
            },
            "required": ["source"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


async def _process_video(
    video_path: str,
    work_dir: str,
    frame_interval: float,
    max_frames: int,
    transcribe: bool,
    language: str | None,
) -> list[TextContent | ImageContent]:
    """Shared logic for analyzing a video file."""
    contents: list[TextContent | ImageContent] = []

    # Metadata
    meta = get_metadata(video_path)
    contents.append(TextContent(
        type="text",
        text=f"## Video Metadata\n```json\n{json.dumps(meta, indent=2)}\n```",
    ))

    # Frames
    frame_paths = await extract_frames(
        video_path, work_dir,
        interval_seconds=frame_interval,
        max_frames=max_frames,
    )

    if frame_paths:
        contents.append(TextContent(
            type="text",
            text=f"## Extracted Frames ({len(frame_paths)} frames at ~{frame_interval}s intervals)",
        ))
        for fp in frame_paths:
            data = Path(fp).read_bytes()
            contents.append(ImageContent(
                type="image",
                data=base64.b64encode(data).decode(),
                mimeType="image/jpeg",
            ))

    # Transcription
    if transcribe:
        if not _check_bin("whisper"):
            contents.append(TextContent(
                type="text",
                text="## Transcription\n**Error:** `whisper` CLI not found on PATH. Install with: `pip install openai-whisper`",
            ))
        else:
            audio_path = await extract_audio(video_path, work_dir)
            if audio_path:
                transcript = await transcribe_audio(audio_path, work_dir, language)
                contents.append(TextContent(
                    type="text",
                    text=f"## Transcript\n{transcript}" if transcript else "## Transcript\n(No speech detected)",
                ))
            else:
                contents.append(TextContent(
                    type="text",
                    text="## Transcript\nNo audio track found in video.",
                ))

    return contents


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    try:
        if name == "analyze_video":
            url = arguments["url"]
            frame_interval = arguments.get("frame_interval", 30)
            max_frames = arguments.get("max_frames", 20)
            transcribe = arguments.get("transcribe", False)
            language = arguments.get("language")
            max_height = arguments.get("max_height", 480)

            with tempfile.TemporaryDirectory(prefix="video-mcp-") as work_dir:
                video_path = await download_video(url, work_dir, max_height)
                return await _process_video(
                    video_path, work_dir, frame_interval, max_frames, transcribe, language
                )

        elif name == "analyze_local_video":
            path = arguments["path"]
            if not Path(path).exists():
                return [TextContent(type="text", text=f"Error: File not found: {path}")]

            frame_interval = arguments.get("frame_interval", 30)
            max_frames = arguments.get("max_frames", 20)
            transcribe = arguments.get("transcribe", False)
            language = arguments.get("language")

            with tempfile.TemporaryDirectory(prefix="video-mcp-") as work_dir:
                return await _process_video(
                    path, work_dir, frame_interval, max_frames, transcribe, language
                )

        elif name == "video_metadata":
            source = arguments["source"]
            is_url = source.startswith("http://") or source.startswith("https://")

            if is_url:
                # Use yt-dlp to get metadata without full download
                result = await _run_async([
                    "yt-dlp", "--dump-json", "--no-download", source,
                ], timeout=60)
                if result.returncode != 0:
                    return [TextContent(type="text", text=f"Error: {result.stderr}")]
                info = json.loads(result.stdout)
                meta = {
                    "title": info.get("title"),
                    "duration_seconds": info.get("duration"),
                    "uploader": info.get("uploader"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "like_count": info.get("like_count"),
                    "description": (info.get("description") or "")[:500],
                    "webpage_url": info.get("webpage_url"),
                    "extractor": info.get("extractor"),
                    "resolution": info.get("resolution"),
                    "fps": info.get("fps"),
                    "has_subtitles": bool(info.get("subtitles")),
                    "available_subtitles": list((info.get("subtitles") or {}).keys()),
                }
                return [TextContent(
                    type="text",
                    text=f"## Video Metadata\n```json\n{json.dumps(meta, indent=2, ensure_ascii=False)}\n```",
                )]
            else:
                if not Path(source).exists():
                    return [TextContent(type="text", text=f"Error: File not found: {source}")]
                meta = get_metadata(source)
                return [TextContent(
                    type="text",
                    text=f"## Video Metadata\n```json\n{json.dumps(meta, indent=2)}\n```",
                )]

        elif name == "transcribe_video":
            source = arguments["source"]
            language = arguments.get("language")

            if not _check_bin("whisper"):
                return [TextContent(
                    type="text",
                    text="Error: `whisper` CLI not found. Install with: `pip install openai-whisper`",
                )]

            is_url = source.startswith("http://") or source.startswith("https://")

            with tempfile.TemporaryDirectory(prefix="video-mcp-") as work_dir:
                if is_url:
                    video_path = await download_video(source, work_dir)
                else:
                    if not Path(source).exists():
                        return [TextContent(type="text", text=f"Error: File not found: {source}")]
                    video_path = source

                audio_path = await extract_audio(video_path, work_dir)
                if not audio_path:
                    return [TextContent(type="text", text="No audio track found in video.")]

                transcript = await transcribe_audio(audio_path, work_dir, language)
                return [TextContent(
                    type="text",
                    text=f"## Transcript\n{transcript}" if transcript else "## Transcript\n(No speech detected)",
                )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception("Tool execution failed")
        return [TextContent(type="text", text=f"Error: {e}")]


def main():
    import asyncio as _asyncio

    async def _run_server():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    _asyncio.run(_run_server())


if __name__ == "__main__":
    main()
