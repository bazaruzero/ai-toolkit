#!/usr/bin/env python3
"""Self-test for the postgresql-release-notes skill scripts.

Uses small HTML fixtures modeled on the real postgresql.org markup, so no
network access is required.

Usage:
  python3 tests/test_scripts.py
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_release_notes as fetch_mod  # noqa: E402
import search_release_notes as search_mod  # noqa: E402

MINOR_PAGE = """
<html><body>
<div class="sect2" id="RELEASE-16-4-CHANGES">
  <div class="titlepage"><div><h3 class="title">
    E.12.2.&nbsp;Changes <a href="#RELEASE-16-4-CHANGES" class="id_link">#</a>
  </h3></div></div>
  <div class="itemizedlist">
    <ul class="itemizedlist">
      <li class="listitem">
        <p>Prevent infinite loop in <code class="command">VACUUM</code>
        (Melanie Plageman)
        <a class="ulink" href="https://postgr.es/c/06bf404cd" target="_top">a</a></p>
        <p>After a disconnected standby reconnected, VACUUM could get
        confused about which tuples are removable, freezing them
        incorrectly.</p>
      </li>
      <li class="listitem">
        <p>Fix <code class="function">heap_force_freeze</code> in
        pg_surgery (Michael Paquier)
        <a class="ulink" href="https://postgr.es/c/51f63ba2b" target="_top">a</a></p>
      </li>
    </ul>
  </div>
</div>
</body></html>
"""

MAJOR_PAGE = """
<html><body>
<div class="sect2" id="RELEASE-17-CHANGES">
  <div class="titlepage"><div><h3 class="title">
    E.12.3.&nbsp;Changes <a href="#RELEASE-17-CHANGES" class="id_link">#</a>
  </h3></div></div>
  <div class="sect3" id="RELEASE-17-SERVER">
    <div class="titlepage"><div><h4 class="title">
      E.12.3.1.&nbsp;Server <a href="#RELEASE-17-SERVER" class="id_link">#</a>
    </h4></div></div>
    <div class="sect4" id="RELEASE-17-OPTIMIZER">
      <div class="titlepage"><div><h5 class="title">
        E.12.3.1.1.&nbsp;Optimizer
        <a href="#RELEASE-17-OPTIMIZER" class="id_link">#</a>
      </h5></div></div>
      <ul class="itemizedlist">
        <li class="listitem">
          <p>Allow vacuum to more efficiently remove and freeze tuples
          (Melanie Plageman)
          <a class="ulink" href="https://postgr.es/c/6dbb49026" target="_top">a</a></p>
        </li>
      </ul>
    </div>
  </div>
  <div class="sect3" id="RELEASE-17-LOGICAL">
    <div class="titlepage"><div><h4 class="title">
      E.12.3.1.8.&nbsp;<a class="link" href="logical-replication.html"
      title="Logical Replication">Logical Replication</a>
      <a href="#RELEASE-17-LOGICAL" class="id_link">#</a>
    </h4></div></div>
    <ul class="itemizedlist">
      <li class="listitem">
        <p>Logical replication enhancements, including:</p>
        <div class="itemizedlist">
          <ul class="itemizedlist">
            <li class="listitem"><p>Failover control</p></li>
          </ul>
        </div>
      </li>
    </ul>
  </div>
</div>
</body></html>
"""

INDEX_PAGE = """
<html><body>
<a href="/docs/release/16.4/">16.4</a>
<a href="/docs/release/17/">17</a>
<a href="/docs/release/17.0/">17.0</a>
<a href="/docs/release/18.1/">18.1</a>
</body></html>
"""


class VersionTests(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(fetch_mod.parse_version("16.4"), (16, 4))
        self.assertEqual(fetch_mod.parse_version("17"), (17, 0))
        with self.assertRaises(ValueError):
            fetch_mod.parse_version("16.4.2")
        with self.assertRaises(ValueError):
            fetch_mod.parse_version("abc")

    def test_expand_range(self):
        self.assertEqual(
            search_mod.expand_version_spec("16.1-16.4"),
            [(16, 1), (16, 2), (16, 3), (16, 4)],
        )
        with self.assertRaises(ValueError):
            search_mod.expand_version_spec("16.4-16.1")
        with self.assertRaises(ValueError):
            search_mod.expand_version_spec("15.14-16.4")

    def test_expand_multi_branch_list(self):
        self.assertEqual(
            search_mod.expand_version_spec("15.14-15.15,16.0-16.1"),
            [(15, 14), (15, 15), (16, 0), (16, 1)],
        )
        self.assertEqual(
            search_mod.expand_version_spec("16.4,17.0"),
            [(16, 4), (17, 0)],
        )

    def test_expand_list_and_single(self):
        self.assertEqual(
            search_mod.expand_version_spec("16.1,16.3"), [(16, 1), (16, 3)]
        )
        self.assertEqual(search_mod.expand_version_spec("16.4"), [(16, 4)])

    def test_extract_releases_from_index(self):
        releases = fetch_mod.extract_releases_from_index(INDEX_PAGE)
        self.assertEqual(
            releases, [(16, 4), (17, 0), (18, 1)]
        )


class EntryTests(unittest.TestCase):
    def test_minor_page_entries(self):
        entries = list(search_mod.iterate_entries(MINOR_PAGE))
        self.assertEqual(len(entries), 2)
        title, item = entries[0]
        self.assertEqual(title, "Changes")
        texts = search_mod.paragraph_texts(item)
        self.assertTrue(texts[0].startswith("Prevent infinite loop in VACUUM"))
        self.assertIn("freezing", texts[1])

    def test_major_page_sections(self):
        entries = list(search_mod.iterate_entries(MAJOR_PAGE))
        titles = [title for title, _ in entries]
        # the "Logical Replication" bullet is a sub-list container and is
        # skipped, so only the Optimizer entry remains
        self.assertEqual(titles, ["Optimizer"])

    def test_sub_bullets_skipped(self):
        entries = list(search_mod.iterate_entries(MAJOR_PAGE))
        # The "Logical replication enhancements" parent bullet is a
        # sub-list container, not an entry; only top-level items count.
        for _, item in entries:
            self.assertNotIn("Failover control", search_mod.paragraph_texts(item)[0])

    def test_link_text_kept(self):
        # section titles made entirely of link anchors keep their text
        title = search_mod.clean_section_title(
            '<a class="link" href="l.html">Logical Replication</a>'
        )
        self.assertEqual(title, "Logical Replication")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cache = Path(self.tmp.name)
        (cache / "release-16.4.html").write_text(MINOR_PAGE, encoding="utf-8")
        (cache / "release-17.0.html").write_text(MAJOR_PAGE, encoding="utf-8")
        self.cache = cache

    def tearDown(self):
        self.tmp.cleanup()

    def test_underscore_identifier_match(self):
        results = search_mod.collect_results(
            self.cache, None, ["freeze"]
        )
        entries = [result["entry"] for result in results]
        # identifier-style match: freeze inside heap_force_freeze
        self.assertTrue(
            any("heap_force_freeze" in entry for entry in entries)
        )

    def test_word_form_not_matched(self):
        # exact-term matching: 'freeze' must not match the word form
        # 'freezing' in the description paragraph
        results = search_mod.collect_results(
            self.cache, "16.4", ["freeze"]
        )
        entries = [result["entry"] for result in results]
        self.assertFalse(
            any("Prevent infinite loop" in entry for entry in entries)
        )
        # ... but the loose-phrase query 'vacuum freezing' does match it
        phrase = search_mod.collect_results(
            self.cache, "16.4", ["vacuum freezing"]
        )
        self.assertEqual(len(phrase), 1)
        self.assertTrue(
            phrase[0]["entry"].startswith("Prevent infinite loop")
        )

    def test_major_release_labels_include_section(self):
        results = search_mod.collect_results(
            self.cache, "17.0", ["freeze"]
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["release"], "17.0 (Optimizer)")
        self.assertEqual(results[0]["url"], "https://postgr.es/c/6dbb49026")

    def test_entry_without_commit_link_gets_page_url(self):
        results = search_mod.collect_results(
            self.cache, "16.4", ["nonexistent-topic"]
        )
        self.assertEqual(results, [])

    def test_results_sorted_newest_first(self):
        results = search_mod.collect_results(
            self.cache, None, ["freeze"]
        )
        versions = [
            (result["release"].split(" ")[0].split("."))
            for result in results
        ]
        numeric = [(int(major), int(minor)) for major, minor in versions]
        self.assertEqual(numeric, sorted(numeric, reverse=True))

    def test_missing_version_in_cache_is_a_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "release-16.4.html").write_text(
                MINOR_PAGE, encoding="utf-8"
            )
            code = search_mod.main(
                ["--cache-dir", tmp, "--query", "vacuum",
                 "--versions", "16.9"]
            )
            self.assertEqual(code, 2)

    def test_include_empty_rows_for_versions_without_matches(self):
        # 16.4 has a match (heap_force_freeze), 17.0 does not; every
        # version in the spec still appears, newest first
        results = search_mod.collect_results(
            self.cache, "16.4,17.0", ["heap_force_freeze"], include_empty=True
        )
        releases = [result["release"] for result in results]
        self.assertEqual(releases, ["17.0", "16.4"])
        self.assertEqual(results[0]["entry"], "")
        self.assertTrue(results[1]["entry"])

    def test_include_empty_rows_for_versions_missing_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "release-16.4.html").write_text(
                MINOR_PAGE, encoding="utf-8"
            )
            cache = Path(tmp)
            results = search_mod.collect_results(
                cache, "16.4,16.9", ["freeze"], include_empty=True
            )
            releases = [result["release"] for result in results]
            self.assertEqual(releases, ["16.9", "16.4"])
            self.assertTrue(results[0]["missing_from_cache"])
            self.assertFalse("missing_from_cache" in results[1])

    def test_include_empty_renders_placeholder_rows(self):
        output = search_mod.render_table(
            search_mod.collect_results(
                self.cache, "16.4,17.0", ["heap_force_freeze"],
                include_empty=True
            ),
            include_empty=True,
        )
        self.assertIn("| 17.0 | _no matching entries_ |  |", output)
        self.assertIn("heap_force_freeze", output)

    def test_include_empty_requires_version_scope(self):
        code = search_mod.main(
            ["--cache-dir", str(self.cache), "--query", "vacuum",
             "--include-empty"]
        )
        self.assertEqual(code, 2)

    def test_since_expands_against_cache(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = search_mod.main(
                ["--cache-dir", str(self.cache), "--query", "heap_force_freeze",
                 "--since", "16.4", "--include-empty"]
            )
        self.assertEqual(code, 0)
        output = captured.getvalue()
        self.assertIn("| 17.0 | _no matching entries_ |  |", output)
        self.assertIn("heap_force_freeze", output)
        # --since and --versions are mutually exclusive
        code = search_mod.main(
            ["--cache-dir", str(self.cache), "--query", "vacuum",
             "--since", "16.4", "--versions", "17.0"]
        )
        self.assertEqual(code, 2)


class CLITests(unittest.TestCase):
    def run_cli(self, module, argv):
        argv = [str(arg) for arg in argv]
        with contextlib.redirect_stdout(io.StringIO()):
            return module.main(argv)

    def test_search_requires_query(self):
        self.assertEqual(self.run_cli(search_mod, ["--cache-dir", "/tmp"]), 2)

    def test_version_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "release-16.4.html").write_text(
                MINOR_PAGE, encoding="utf-8"
            )
            code = self.run_cli(
                search_mod,
                ["--cache-dir", tmp, "--query", "vacuum", "--versions", "16.4"],
            )
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
