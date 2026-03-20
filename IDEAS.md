# Improvement Ideas & Backlog

Track ideas for improving the Claude Code CLI experience.

## Statusline
- [ ] Add cost-per-session tracking
- [ ] Show tokens-per-minute throughput
- [ ] Color-code rate limit bars (green/yellow/red thresholds)
- [ ] Add cache hit rate display

## Hooks
- [ ] Pre-commit hook to lint CLAUDE.md files
- [ ] Post-tool hook to log tool usage stats
- [ ] Auto-backup settings before changes

## Skills
- [ ] Custom `/research` skill for multi-source web research
- [ ] `/deploy` skill for common deployment workflows
- [ ] `/review` skill tailored to personal code style

## MCP Servers
- [ ] Build custom MCP server for frequently used APIs
- [ ] Rate limit monitoring MCP server

## Workflow
- [ ] Session templates for different work contexts (coding, research, finance)
- [ ] Auto-context loading based on project type
- [ ] Prompt library for reusable task prompts

## Config Management
- [ ] Script to diff local settings vs repo settings
- [ ] Automated backup of ~/.claude/ configs
- [ ] Environment-specific config profiles (work vs personal)
