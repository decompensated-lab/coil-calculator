# Default AGENTS.md

Ensure compatibility between Claude Code and other agents
`CLAUDE.md` should be a symlink (committed) into AGENTS.md
`.agents/` and its contents (skills, etc.)is primary. Set committed symlinks for Claude Code to see the contents of `.agents`

## Security
Mitigate supply-chain attacks by explicitly setting a 7-day cooldown for Python packages, and a 3-day cooldown for anything web-related. Do vulnerability scans if a critical update (breaking the cooldown) is necessary.

## Toolchains
Use `uv`, `pnpm`. 
When containerization is to be used, prefer podman to Docker, but ensure compatibility. When making images, consider best practices for caching, building, inspired by https://docs.astral.sh/uv/guides/integration/docker/#non-editable-installs .

## Misc
Of a git repo is setup, then commit at reasonable times
