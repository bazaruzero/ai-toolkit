# Release notes page structure (postgresql.org)

The skill scripts parse these page shapes. Update this file if
postgresql.org changes its markup.

## URL layout

- Index of all releases: `https://www.postgresql.org/docs/release/`
- One page per version: `https://www.postgresql.org/docs/release/<major>.<minor>/`
  (e.g. `https://www.postgresql.org/docs/release/16.4/`)

## Minor release pages (e.g. 16.4)

Structure:

```html
<div class="sect2" id="RELEASE-16-4-CHANGES">
  <h3 class="title">E.12.2. Changes ...</h3>
  <ul class="itemizedlist">
    <li class="listitem">
      <p>Prevent infinite loop in VACUUM (Melanie Plageman)
        <a class="ulink" href="https://postgr.es/c/06bf404cd">§</a></p>
      <p>Full explanation of the fix...</p>
      <p>Optional extra paragraph (e.g. CVE credits)</p>
    </li>
    ...
  </ul>
</div>
```

- Every changelist item is a `<li class="listitem">`.
- The first `<p>` is the entry summary: short title, author in parentheses,
  then one or more `§` commit links (`https://postgr.es/c/<hash>`).
- Following `<p>` elements are the full description.

## Major release pages (e.g. 17.0)

The changelist is nested under numbered sections:

```html
<div class="sect2" id="RELEASE-17-CHANGES">          (h3 "Changes")
  <div class="sect3" id="RELEASE-17-SERVER">         (h4 "Server")
    <div class="sect4" id="RELEASE-17-OPTIMIZER">    (h5 "Optimizer")
      <ul class="itemizedlist"> ... <li class="listitem"> ... </ul>
    </div>
  </div>
</div>
```

- Section depth alternates between `sect3` (h4) and `sect4` (h5).
- Some section titles are entirely link anchors (e.g. `Logical Replication`,
  `psql`), so link text must be kept when extracting titles.
- The `Overview` section is a plain bullet list (no commit links, no author
  lines).
- Entries can contain sub-lists (`itemizedlist` nested inside an `li`);
  sub-bullets are skipped when extracting entries.
- `pg_surgery`-style entries mention identifiers such as
  `heap_force_freeze`, so word matching must treat `_` as a separator.

## Per-item anchors

Minor release pages give list items stable ids only in some versions, and
major release pages give them none, so there is no reliable per-entry URL.
The scripts therefore link to the entry's commit (`https://postgr.es/c/...`,
the `§` anchor), or to the release page URL when no commit link exists.

## Search behavior

- Queries are case-insensitive; multiple `--query` flags are OR-ed.
- A single-word query matches identifier-like text around `_` and `-`
  (lookarounds `(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])` instead of `\b`).
- A multi-word query is a loose phrase: the words must appear in sequence
  within a 200-character window.
- A match in any paragraph of an entry (summary or description) selects the
  whole entry.

## Version selection

- `--versions` accepts single versions, intra-major ranges (`16.1-16.4`),
  lists, and comma-joined multi-branch spans (`15.14-15.19,16.0-16.15`).
  A single range must stay within one major branch; join ranges with commas
  to cover several branches.
- `--since X.Y` (fetch and search scripts) selects every release at or
  above X.Y across all major branches. The fetch script expands it from the
  live index page; the search script expands it from the cached versions.
- With `--include-empty`, the search emits one placeholder row per selected
  version that has no matches (`no matching entries`), and one per selected
  version absent from the cache (`not in cache (fetch it first)`), so the
  output covers every version in the requested range.
