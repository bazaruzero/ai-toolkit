#!/usr/bin/env python3
"""Fetch PostgreSQL release notes pages and store them in a cache directory.

Only the Python standard library is used.

Usage:
  python3 fetch_release_notes.py list
  python3 fetch_release_notes.py fetch --major 17 [--min-release 17.2] [--cache-dir .cache]
  python3 fetch_release_notes.py fetch --versions "16.1-16.4" | "16.4" | "16.1,16.3"
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://www.postgresql.org/docs/release"
INDEX_URL = "https://www.postgresql.org/docs/release/"
USER_AGENT = "postgresql-release-notes-skill/1.0"
# Major branches still listed on the release index page.
SUPPORTED_BRANCHES = range(12, 19)


def http_get(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


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


def extract_releases_from_index(html_text):
    """Return a sorted list of [(major, minor)] linked from the index page."""
    releases = set()
    pattern = re.compile(r'href="/docs/release/(\d+)(?:\.(\d+))?/?"')
    for match in pattern.finditer(html_text):
        releases.add((int(match.group(1)), int(match.group(2) or 0)))
    return sorted(releases)


def fetch_version_page(version, cache_dir):
    """Download one release page into the cache. Return True on success."""
    label = format_version(version)
    try:
        html_text = http_get(f"{BASE_URL}/{label}/")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"skip {label}: not published on postgresql.org", file=sys.stderr)
            return False
        raise
    target = cache_dir / f"release-{label}.html"
    target.write_text(html_text, encoding="utf-8")
    print(f"fetched {label} -> {target}")
    return True


def build_parser():
    parser = argparse.ArgumentParser(
        description="Fetch PostgreSQL release notes pages into a cache directory."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser(
        "list", help="list all releases available on postgresql.org"
    )
    list_parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="output format (default: text)",
    )
    list_parser.add_argument(
        "--min-release", default=None,
        help="only list releases at or above this version (e.g. 17.2)",
    )

    fetch_parser = sub.add_parser(
        "fetch", help="download release notes pages into the cache"
    )
    target = fetch_parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--versions",
        help="version range, list, or single version: '17.0-17.3', '16.1,16.4', '16.4'",
    )
    target.add_argument(
        "--major", type=int,
        help="fetch all listed minor releases of one major branch (e.g. 17)",
    )
    fetch_parser.add_argument(
        "--min-release", default=None,
        help="skip releases below this version (e.g. 17.2); works with both modes",
    )
    fetch_parser.add_argument(
        "--cache-dir", default=".cache",
        help="directory for cached pages (default: .cache)",
    )
    return parser


def run_list(args):
    releases = extract_releases_from_index(http_get(INDEX_URL))
    if args.min_release:
        min_release = parse_version(args.min_release)
        releases = [release for release in releases if release >= min_release]
    if args.format == "json":
        print(json.dumps(
            [format_version(release) for release in releases], indent=2
        ))
    else:
        for release in releases:
            print(format_version(release))
    return 0


def run_fetch(args):
    if args.major:
        if args.major not in SUPPORTED_BRANCHES:
            print(
                f"unsupported major branch: {args.major} "
                f"(supported: {SUPPORTED_BRANCHES.start}-{SUPPORTED_BRANCHES.stop - 1})",
                file=sys.stderr,
            )
            return 2
        versions = [
            version for version in extract_releases_from_index(http_get(INDEX_URL))
            if version[0] == args.major
        ]
        if not versions:
            print(f"no releases found for branch {args.major}", file=sys.stderr)
            return 1
    else:
        try:
            versions = expand_version_spec(args.versions)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.min_release:
        min_release = parse_version(args.min_release)
        versions = [version for version in versions if version >= min_release]

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetched = sum(1 for version in versions if fetch_version_page(version, cache_dir))
    print(f"done: {fetched} page(s) stored in {cache_dir}")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return run_list(args)
        return run_fetch(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
