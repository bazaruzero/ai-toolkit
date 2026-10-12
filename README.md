# AI Toolkit

A collection of skills, sub-agents, prompts, and other artifacts for working with AI assistants.

## Install (opencode)

Copy the skill folder into your project's `.opencode/skill/` (or `~/.config/opencode/skill/` globally):

```bash
mkdir -p .opencode/skill
cp -r skills/postgresql-release-notes .opencode/skill/
```

Restart opencode — the skill appears in the available skills list and loads automatically whenever a request matches its description.

## Usage

Just describe your task; the skill is picked up automatically:

> what changed in PostgreSQL 17.4?

Or explicitly:

```
/skill postgresql-release-notes find autovacuum fixes since 16.4
```
