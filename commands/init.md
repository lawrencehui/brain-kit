---
description: Create the brain this plugin runs on (vault, sync schedule, brain CLI)
argument-hint: "[--vault ~/brain] [--dev ~/Dev]"
---

Set up the user's brain-kit second brain. The plugin already provides the MCP server and hooks,
so the installer must skip those two steps.

1. Run: `npx -y create-second-brain --skip mcp,hook $ARGUMENTS`
   If the npm package is unavailable, run `npx -y github:lawrencehui/brain-kit --skip mcp,hook $ARGUMENTS` instead.
2. Report what it created (vault path, schedule, CLI) and any warnings, verbatim where they matter.
3. Tell the user to restart Claude Code so the plugin's MCP server connects to the new brain.

Do not pass `--skip schedule` unless the user asked; the scheduled sync is what keeps the brain current.
