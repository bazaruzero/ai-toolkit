---
name: postgresql-release-notes
description: Search PostgreSQL release notes and summarize matching changes as a table with per-item links, with a row for every version in the requested range (marking releases without matches). Use when the user asks about fixes, changes, or new functionality in specific PostgreSQL minor versions, e.g. "find autovacuum freezing changes since 15.14", "what changed in 16.4", or "show logical replication fixes in 17.x". Use ONLY for PostgreSQL release-note lookups, not for general PostgreSQL usage questions.
license: MIT
compatibility: opencode, claude, generic
metadata:
  version: 1.1.0
  keywords: postgresql, release notes, changelog, minor release, patch release, autovacuum
---

# PostgreSQL Release Notes Search

Answer questions about changes in PostgreSQL minor releases by searching the
official release notes at <https://www.postgresql.org/docs/release/>.

## When to use

- "Find changes related to <topic> starting from version X.Y"
- "What was fixed in 16.4?"
- "Show all vacuum/autovacuum fixes in 17.x"
- Any request that maps to "which release notes mention <subject> in <version range>"

Do NOT use for general PostgreSQL how-to questions (syntax, tuning advice,
error messages). Only for release-note research.

## Workflow

1. **Parse the request** into: `topic` (subject keywords, may be empty = all
   changes), `from_version` (inclusive lower bound, optional), and
   `to_version` (inclusive upper bound, optional, defaults to latest).
2. **List candidate releases** with the fetcher:

   ```bash
   python3 scripts/fetch_release_notes.py list
   ```

   This prints every release published on postgresql.org with a one-line
   summary, in ascending order. Note: `list` uses a single live request and
   does not use the cache.
3. **Filter versions** by the requested bounds yourself (the scripts accept
   an explicit version list so you stay in control of the range).
4. **Fetch the notes** for those versions:

    ```bash
    # all minor releases of one major branch, e.g. 17.0-17.10
    python3 scripts/fetch_release_notes.py fetch --major 17 --cache-dir .cache

    # everything published at or above a base version, across branches
    # (e.g. "since 15.14" -> 15.14+, all of 16.x, 17.x, 18.x, ...)
    python3 scripts/fetch_release_notes.py fetch --since 15.14 --cache-dir .cache

    # explicit versions (range, list, single version, or comma-joined
    # multi-branch span)
    python3 scripts/fetch_release_notes.py fetch --versions "15.14-15.19,16.0-16.4" --cache-dir .cache
    python3 scripts/fetch_release_notes.py fetch --versions 16.4 --cache-dir .cache

    # bump the cache to a required minimum release (default: 2025-01-01)
    python3 scripts/fetch_release_notes.py fetch --major 16 --min-release 16.9 --cache-dir .cache
    ```
5. **Search the fetched notes** for the topic keywords:

    ```bash
    # per-version coverage: one row per version since 15.14, matching or not
    python3 scripts/search_release_notes.py --cache-dir .cache \
        --query "vacuum freeze" --since 15.14 --include-empty --format table

    # terms are OR-ed; quoted phrases match as a whole:
    python3 scripts/search_release_notes.py --cache-dir .cache \
        --query "freeze frozen" --query "heap page pruning" --format markdown --json out.json
    ```

    Output fields: release, section, entry, description, url. Exit code 0 with
    "No matching entries" when nothing matches. Re-run with broader terms or a
    wider version range before concluding there are no matches.
    `--since` expands against the cache (fetch first!), `--versions` accepts
    a comma-joined multi-branch span like `15.14-15.19,16.0-16.15`.
    With `--include-empty` every version in the requested range appears in the
    output — versions without matches get an explicit placeholder row
    (`no matching entries`, or `not in cache (fetch it first)`).
6. **Read the full text** of promising entries if the summary is not enough:

   ```bash
   python3 scripts/search_release_notes.py --cache-dir .cache \
       --versions 15.14 --topic autovacuum --show-full
   ```

   `--show-full` prints the complete description of every matched entry.
7. **Compose the final answer** as a table (see Output format) using the URLs
   from the search output. Verify topic relevance yourself: the search is
   keyword-based, so drop false positives before presenting results.

Always pass `--cache-dir .cache` (relative to this skill's directory) so
repeated searches reuse downloads instead of hitting postgresql.org again.
The cache never expires; use `fetch` again to add or refresh versions.

## Scripts

| Script | Purpose |
| ------ | ------- |
| `scripts/fetch_release_notes.py` | Download and cache release notes pages; list all available releases |
| `scripts/search_release_notes.py` | Keyword/phrase search over the cached notes |

Run `python3 <script> --help` for the full option reference. Both scripts
require only Python 3.8+ (stdlib only) and network access for `fetch`/`list`.
Use `python3 scripts/fetch_release_notes.py list` to check network access and
see what is available.

Entry URLs link to the commit (`https://postgr.es/c/...`) because the
per-item HTML anchors in the release notes are not stable for citation.

## Output format

Present results as a markdown table, in English, sorted newest release
first:

```markdown
| Release | Change | Link |
| ------- | ------ | ---- |
| 16.4 | Prevent infinite loop in VACUUM when a standby reconnects with an old running transaction | https://postgr.es/c/06bf404cd |
| 16.3 | no matching entries | |
```

Rules:
- One row per matching release-note entry, newest release first.
- Release column: the version (e.g. `17.2`). On the initial release of a
  major version, prefix the section heading, e.g. `17.0 (Performance)`.
- Change column: one short English sentence condensed from the entry text,
  not a verbatim copy.
- Link column: the entry's commit link (`§`), or the release page URL
  (`https://www.postgresql.org/docs/release/<version>/`) when the entry has
  no commit link.
- Complete version coverage: when the request defines a version range or a
  base version ("since X.Y"), the table must contain at least one row for
  EVERY release in that range, newest first — including releases with no
  matching entries, rendered as `| X.Y | no matching entries | |`. Never
  silently skip releases. Run the search with `--include-empty` to get this
  row set directly, and use it as the skeleton of the final answer.
- If nothing matches anywhere, say so explicitly and list the versions
  searched.

## Notes

- `search_release_notes.py` matches case-insensitively. Word-boundary rules
  also make terms like `17` match `17.x`, so pass concrete topic keywords,
  not version numbers, in `--query`.
- The `list` subcommand always fetches fresh data; it does not read or write
  the cache.
- `--include-empty` needs an explicit version scope (`--versions` or
  `--since`); it prints one placeholder row per version without matches, so
  the report covers every version in the requested range. Versions missing
  from the cache are flagged `not in cache (fetch it first)` — fetch them
  and re-run before finalizing the answer.
- See `reference/release-notes-structure.md` for details of the page format
  and the search algorithm if you need to extend the scripts.
- Everything in this skill is in English by design; keep generated reports
  in English even if the user asks in another language.
