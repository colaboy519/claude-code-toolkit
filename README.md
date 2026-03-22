# Claude Code Toolkit

Systematising everything around improving my Claude Code CLI — learning from others, building my own tools, and tracking what works.

## Philosophy

1. **Learn** — Study how others configure and extend Claude Code (configs, plugins, workflows)
2. **Build** — Create custom scripts, MCP servers, hooks, and skills
3. **Track** — Version everything so nothing gets lost and improvements compound

## Structure

```
├── scripts/          # Utility scripts (statusline, helpers)
├── hooks/            # Git and Claude Code hooks
├── skills/           # Custom skills and slash commands
├── mcp-servers/      # Custom MCP server projects
│   ├── webharvest/       # Local web scraping MCP server (submodule)
│   └── video-analyzer/  # Video analysis MCP server (frames, transcription, metadata)
├── configs/          # Settings snapshots and templates
├── research/         # Notes from studying others' setups and approaches
├── CLAUDE.md         # Project instructions for Claude Code
└── IDEAS.md          # Improvement ideas and backlog
```

## Current Customizations

- **Custom statusline** — Shows 5h/7d rate limit usage bars + context window usage
- **Opus 4.6 (1M context)** as default model
- **Plugins** — document-skills, financial-services suite
- **MCP servers** — Brave search, Firecrawl, Tavily, Jina, webharvest (self-built), video-analyzer (self-built)

## MCP Servers

### webharvest
Free, local-only web scraper with anti-bot bypass. Runs as a stdio MCP server — no API keys, no cloud dependency. Supports scraping, crawling, CSS extraction, DuckDuckGo search, and autonomous browser agent.

### video-analyzer
Local video analysis MCP server. Downloads from any platform (YouTube, Bilibili, Twitter/X, etc. via yt-dlp), extracts key frames as base64 images for Claude's vision, transcribes audio via Whisper, and returns structured metadata. No API keys required — everything runs locally using ffmpeg + yt-dlp + whisper.

## Getting Started

```bash
git clone --recurse-submodules https://github.com/colaboy519/claude-code-toolkit.git
```

Then symlink or copy configs into `~/.claude/` as needed.
