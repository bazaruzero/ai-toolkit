#!/usr/bin/env python3
"""Search cached PostgreSQL release notes pages for keywords or phrases.

Reads the cache produced by fetch_release_notes.py and prints every matching
release-note entry with a stable link to its source.

Only the Python standard library is used.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

INDEX_URL = "https://www.postgresql.org/docs/release/"

COMMIT_LINK_RE = re.compile(
    r'<a[^>]*class="ulink"[^>]*href="(https://postgr\.es/c/[^"]*)"[^>]*>'
    r'.*?</a>',
    re.S,
)


def parse_version(text):
    match = re.match(r"^(\d+)(?:\.(\d+))?$", text.strip())
    if not match:
        raise ValueError(f"invalid version: {text!r}")
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major <= 0 or minor < 0:
        raise ValueError(f"invalid version: {text!r}")
    return major, minor


def format_version(version):
    major, minor = version
    return f"{major}.{minor}"


def expand_version_spec(spec):
    """Turn '17.0-17.3', '16.1,16.4' or '17.2' into a sorted list of versions."""
    range_match = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$", spec.strip())
    if range_match:
        low = parse_version(range_match.group(1))
        high = parse_version(range_match.group(2))
        if low > high:
            raise ValueError(f"descending version range: {spec!r}")
        if low[0] != high[0]:
            raise ValueError(
                f"version range must stay within one major branch: {spec!r}"
            )
        return [(low[0], minor) for minor in range(low[1], high[1] + 1)]
    versions = [parse_version(part) for part in spec.split(",") if part.strip()]
    if not versions:
        raise ValueError(f"empty version spec: {spec!r}")
    return sorted(set(versions))


def strip_tags(fragment):
    """Convert an HTML fragment to plain text, keeping inline link text.

    Commit-link markers ("§" anchors to postgr.es) are dropped because they
    carry no meaning; documentation link anchors keep their text.
    """
    fragment = re.sub(
        r'<a[^>]*class="ulink"[^>]*>.*?</a>', " ", fragment, flags=re.S
    )
    fragment = re.sub(r"<a [^>]*>(.*?)</a>", r"\1", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"\s+'s\b", "'s", fragment)
    return re.sub(r"\s+", " ", fragment).strip()


def paragraph_texts(list_item_html):
    """Extract the <p> texts of a changelist <li> in document order."""
    paragraphs = re.findall(r"<p>(.*?)</p>", list_item_html, re.S)
    return [strip_tags(paragraph) for paragraph in paragraphs]


SECTION_ID_RE = re.compile(
    r'<div class="sect[1-4]" id="([^"]+)">\s*'
    r'<div class="titlepage">.*?<h([3-5]) class="title">(.*?)'
    r'(?:\s*<a href="#|</h\2>)',
    re.S,
)


def clean_section_title(raw_title):
    """Convert a section heading to plain text, keeping link text."""
    raw_title = re.sub(r"<a [^>]*>(.*?)</a>", r"\1", raw_title, flags=re.S)
    raw_title = re.sub(r"<[^>]+>", " ", raw_title)
    raw_title = html.unescape(raw_title)
    raw_title = re.sub(
        r"^\s*[A-Z]\.\d+(?:\.\d+)*\.\s*", "", raw_title
    )
    return re.sub(r"\s+", " ", raw_title).strip()


def iterate_entries(html_text):
    """Yield (section_title, listitem_html) for every changelist entry.

    The changelist of a minor release (e.g. 16.4) lives in a single
    "Changes" sect2. A major release (e.g. 17.0) groups entries under
    nested sect3/sect4 headings (Server, Optimizer, Replication, ...), so
    entries are attributed to the nearest enclosing section title.
    """
    matches = list(SECTION_ID_RE.finditer(html_text))
    for index, match in enumerate(matches):
        chunk = html_text[match.start():matches[index + 1].start()
                          if index + 1 < len(matches) else len(html_text)]
        title = clean_section_title(match.group(3))
        for item in re.findall(
            r'<li class="listitem">(.*?)</li>', chunk, re.S
        ):
            # nested listitems (sub-bullets) are skipped: only top-level
            # entries carry the entry summary and the commit link.
            if '<li class="listitem">' in item or '<div class="itemizedlist">' in item:
                continue
            yield title, item


def compile_matchers(queries):
    """Compile query terms into regexes.

    A single word matches on a boundary that treats underscores and other
    punctuation as separators, so "freeze" also matches "heap_force_freeze".
    A multi-word query matches its words in sequence (a loose phrase).
    """
    matchers = []
    for query in queries:
        if " " in query:
            words = [re.escape(word) for word in query.split()]
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + r"[\s\S]{0,200}?".join(words) + r"(?![A-Za-z0-9])",
                re.I,
            )
        else:
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + re.escape(query) + r"(?![A-Za-z0-9])",
                re.I,
            )
        matchers.append(pattern)
    return matchers


def entry_matches(texts, matchers):
    combined = " ".join(texts)
    return any(pattern.search(combined) for pattern in matchers)


def find_files(cache_dir):
    return sorted(
        cache_dir.glob("release-*.html"),
        key=lambda path: version_sort_key_from_path(path.name),
    )


def version_sort_key_from_path(name):
    match = re.match(r"release-(\d+)\.(\d+)\.html$", name)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


def load_cache_versions(cache_dir):
    versions = []
    for path in find_files(cache_dir):
        match = re.match(r"release-(\d+)\.(\d+)\.html$", path.name)
        if match:
            versions.append((int(match.group(1)), int(match.group(2))))
    return sorted(set(versions))


def filter_versions(versions, version_spec):
    if not version_spec:
        return versions
    selected = expand_version_spec(version_spec)
    selected_set = set(selected)
    return [version for version in versions if version in selected_set]


def collect_results(cache_dir, version_spec, queries):
    matchers = compile_matchers(queries)
    results = []
    for path in find_files(cache_dir):
        version = version_sort_key_from_path(path.name)
        if version == (0, 0):
            continue
        if version_spec and version not in set(expand_version_spec(version_spec)):
            continue
        html_text = path.read_text(encoding="utf-8")
        for section, item_html in iterate_entries(html_text):
            texts = paragraph_texts(item_html)
            if not texts:
                continue
            if not entry_matches(texts, matchers):
                continue
            commit_match = COMMIT_LINK_RE.search(item_html)
            url = commit_match.group(1) if commit_match else (
                INDEX_URL + format_version(version) + "/"
            )
            major, minor = version
            release_label = format_version(version)
            if minor == 0:
                release_label = f"{release_label} ({section})" if section else release_label
            results.append(
                {
                    "release": release_label,
                    "section": section,
                    "entry": texts[0],
                    "description": " ".join(texts[1:]) if len(texts) > 1 else "",
                    "url": url,
                    "version_key": version,
                }
            )
    results.sort(key=lambda result: result["version_key"], reverse=True)
    for result in results:
        result.pop("version_key", None)
    return results


def render_table(results):
    if not results:
        return "No matching entries"
    header = "| Release | Change | Link |"
    separator = "| ------- | ------ | ---- |"
    rows = []
    for result in results:
        entry = result["entry"].replace("|", "\\|")
        rows.append(f"| {result['release']} | {entry} | {result['url']} |")
    return "\n".join([header, separator] + rows)


def render_json(results):
    return json.dumps(results, indent=2, ensure_ascii=False)


def render_full(results):
    if not results:
        return "No matching entries"
    blocks = []
    for result in results:
        lines = [f"Release: {result['release']}"]
        if result["section"]:
            lines.append(f"Section: {result['section']}")
        lines.append(f"Entry: {result['entry']}")
        if result["description"]:
            lines.append(f"Details: {result['description']}")
        lines.append(f"URL: {result['url']}")
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Search cached PostgreSQL release notes for keywords or phrases."
    )
    parser.add_argument(
        "--cache-dir", default=".cache",
        help="cache directory written by fetch_release_notes.py (default: .cache)",
    )
    parser.add_argument(
        "--query", action="append", default=[],
        help="keyword or quoted phrase; repeatable, matches are OR-ed",
    )
    parser.add_argument(
        "--topic", action="append", default=[],
        help="alias of --query for readability",
    )
    parser.add_argument(
        "--versions", default=None,
        help="restrict search to a version range/list, e.g. '15.14-15.31' or '16.4'",
    )
    parser.add_argument(
        "--format", choices=("table", "json", "full"), default="table",
        help="output format (default: table)",
    )
    parser.add_argument(
        "--show-full", action="store_true",
        help="show full entry text (implies --format full)",
    )
    parser.add_argument(
        "--json-out", default=None,
        help="also write results as JSON to this file",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    queries = args.query + args.topic
    if not queries:
        print("error: provide at least one --query (or --topic) term", file=sys.stderr)
        return 2

    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_dir():
        print(
            f"error: cache directory not found: {cache_dir}; "
            "run fetch_release_notes.py first",
            file=sys.stderr,
        )
        return 2

    cached = load_cache_versions(cache_dir)
    if not cached:
        print(
            f"error: no release pages in {cache_dir}; "
            "run fetch_release_notes.py first",
            file=sys.stderr,
        )
        return 2

    if args.versions:
        try:
            selected = set(expand_version_spec(args.versions))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        missing = sorted(selected - set(cached))
        if missing:
            print(
                "error: versions not in cache: "
                + ", ".join(format_version(version) for version in missing),
                file=sys.stderr,
            )
            return 2

    try:
        results = collect_results(cache_dir, args.versions, queries)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.show_full or args.format == "full":
        print(render_full(results))
    elif args.format == "json":
        print(render_json(results))
    else:
        print(render_table(results))

    if args.json_out:
        Path(args.json_out).write_text(render_json(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
