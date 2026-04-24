# Claude Code Toolkit

Personal configuration and customization hub for Claude Code CLI — custom scripts, MCP servers, and workflow tools.

## Commands

- `node scripts/statusline-command.js` — test statusline output (reads context from stdin)
- `cd mcp-servers/video-analyzer && uv venv && uv pip install -e .` — set up video-analyzer MCP server
- `claude mcp add video-analyzer -- <path>/.venv/bin/video-analyzer` — register video-analyzer with Claude
- `git clone --recurse-submodules` — required for webharvest submodule

## Architecture

```
├── scripts/
│   └── statusline-command.js    # Custom status bar: 5h/7d rate limits + context usage
├── mcp-servers/
│   ├── webharvest/              # Git submodule: local web scraper (no API keys)
│   └── video-analyzer/          # Python: video download/frame extraction/transcription
├── configs/                     # JSON config snapshots
├── research/                    # Notes on studying other setups
└── IDEAS.md                     # Backlog
```

## Key Details

- statusline reads credentials from `~/.claude/.credentials.json`, caches API calls with 60s TTL
- video-analyzer requires: ffmpeg, yt-dlp, openai-whisper (optional)
- webharvest is a git submodule — use `--recurse-submodules` when cloning
