# Video Analyzer MCP Server

MCP server for video analysis — download from any platform (YouTube, Bilibili, etc.), extract frames, transcribe audio, and return structured data for Claude's vision capabilities.

## Prerequisites

- Python 3.12+
- `ffmpeg` and `ffprobe` on PATH
- `yt-dlp` on PATH (for URL downloads)
- `whisper` on PATH (optional, for transcription — install via `pip install openai-whisper`)

## Install

```bash
cd mcp-servers/video-analyzer
uv venv && uv pip install -e .
```

## Add to Claude Code

```bash
claude mcp add video-analyzer -- /path/to/video-analyzer/.venv/bin/video-analyzer
```

## Tools

| Tool | Description |
|------|-------------|
| `analyze_video` | Download + extract frames + optional transcription from URL |
| `analyze_local_video` | Same but for local files |
| `video_metadata` | Quick metadata lookup (no download for URLs) |
| `transcribe_video` | Audio transcription only |

## Supported Platforms

Any site supported by yt-dlp, including:
- YouTube, Bilibili, Twitter/X, TikTok, Douyin
- Direct video URLs (.mp4, .webm, etc.)
- Local files
