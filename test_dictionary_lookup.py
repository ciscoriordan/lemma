#!/usr/bin/env python3
"""
Simulate Kindle dictionary lookup against generated dictionary files.

Parses content.html from build directories, builds a lookup index,
and tests that inflected forms resolve to the correct headwords.

Usage:
    python3 test_dictionary_lookup.py [build_dir_or_glob]

    # Test the latest full build (all volumes):
    python3 test_dictionary_lookup.py

    # Test a specific volume:
    python3 test_dictionary_lookup.py lemma_greek_el_20260405_alpha_beta_gamma_delta

    # Test a 1% build:
    python3 test_dictionary_lookup.py lemma_greek_el_20260405_1.0pct

    # Interactive mode - type words to look up:
    python3 test_dictionary_lookup.py -i
"""

import glob
import html
import os
import re
import sys
import time


# Known inflection -> headword pairs for validation.
# Each tuple: (inflected_form, expected_headword, description)
KNOWN_LOOKUPS = [
    # Common verbs
    ("τρώει", "τρώω", "present 3sg of 'eat'"),
    ("έτρωγα", "τρώω", "imperfect 1sg of 'eat'"),
    ("φάει", "τρώω", "subjunctive 3sg of 'eat'"),
    ("πήγα", "πηγαίνω", "aorist 1sg of 'go'"),
    ("πηγαίνει", "πηγαίνω", "present 3sg of 'go'"),
    ("είναι", "είμαι", "present 3sg of 'be'"),
    ("ήταν", "είμαι", "imperfect 3sg of 'be'"),
    ("βλέπει", "βλέπω", "present 3sg of 'see'"),
    ("είδα", "βλέπω", "aorist 1sg of 'see'"),
    ("έχει", "έχω", "present 3sg of 'have'"),
    ("είχα", "έχω", "imperfect 1sg of 'have'"),
    ("λέει", "λέω", "present 3sg of 'say'"),
    ("είπε", "λέω", "aorist 3sg of 'say'"),
    ("θέλει", "θέλω", "present 3sg of 'want'"),
    ("ήθελα", "θέλω", "imperfect 1sg of 'want'"),
    ("κάνει", "κάνω", "present 3sg of 'do/make'"),
    ("έκανε", "κάνω", "aorist 3sg of 'do/make'"),
    ("ξέρει", "ξέρω", "present 3sg of 'know'"),
    ("ήξερα", "ξέρω", "imperfect 1sg of 'know'"),
    ("μπορεί", "μπορώ", "present 3sg of 'can'"),
    ("μπορούσα", "μπορώ", "imperfect 1sg of 'can'"),
    ("δίνει", "δίνω", "present 3sg of 'give'"),
    ("έδωσε", "δίνω", "aorist 3sg of 'give'"),
    ("παίρνει", "παίρνω", "present 3sg of 'take'"),
    ("πήρε", "παίρνω", "aorist 3sg of 'take'"),
    ("γράφει", "γράφω", "present 3sg of 'write'"),
    ("έγραψε", "γράφω", "aorist 3sg of 'write'"),

    # Common nouns - case inflections
    ("σπιτιού", "σπίτι", "genitive sg of 'house'"),
    ("σπίτια", "σπίτι", "plural of 'house'"),
    ("ανθρώπου", "άνθρωπος", "genitive sg of 'person'"),
    ("ανθρώπων", "άνθρωπος", "genitive pl of 'person'"),
    ("γυναίκα", "γυναίκα", "headword lookup for 'woman'"),
    ("γυναίκας", "γυναίκα", "genitive sg of 'woman'"),
    ("γυναίκες", "γυναίκα", "plural of 'woman'"),
    ("παιδιού", "παιδί", "genitive sg of 'child'"),
    ("παιδιά", "παιδί", "plural of 'child'"),
    ("χρόνου", "χρόνος", "genitive sg of 'year/time'"),
    ("χρόνια", "χρόνος", "plural of 'year/time'"),

    # Adjective inflections
    ("καλή", "καλός", "feminine of 'good'"),
    ("καλό", "καλός", "neuter of 'good'"),
    ("μεγάλη", "μεγάλος", "feminine of 'big'"),
    ("μεγάλο", "μεγάλος", "neuter of 'big'"),

    # Headword self-lookup (should always work)
    ("τρώω", "τρώω", "headword self-lookup 'eat'"),
    ("σπίτι", "σπίτι", "headword self-lookup 'house'"),
    ("καλός", "καλός", "headword self-lookup 'good'"),
]


class DictionaryIndex:
    """Simulates Kindle's dictionary lookup index."""

    def __init__(self):
        # word -> list of (headword, definitions_preview)
        self.index = {}
        self.headwords = set()
        self.total_inflections = 0

    def load_content_html(self, filepath):
        """Parse a content.html file and add entries to the index."""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract entries using regex
        entry_pattern = re.compile(
            r'<idx:entry[^>]*>(.+?)</idx:entry>',
            re.DOTALL
        )
        orth_pattern = re.compile(r'<idx:orth\s+value="([^"]*)"')
        iform_pattern = re.compile(r'<idx:iform\s+value="([^"]*)"')
        def_pattern = re.compile(r"<p class='def'>(.*?)</p>")

        for m in entry_pattern.finditer(content):
            entry_html = m.group(1)

            orth_match = orth_pattern.search(entry_html)
            if not orth_match:
                continue

            headword = html.unescape(orth_match.group(1))
            self.headwords.add(headword)

            # Extract first definition for preview
            defs = def_pattern.findall(entry_html)
            preview = html.unescape(defs[0])[:80] if defs else "(no definition)"

            # Index the headword itself
            self.index.setdefault(headword, []).append((headword, preview))

            # Index all inflected forms
            for im in iform_pattern.finditer(entry_html):
                form = html.unescape(im.group(1))
                self.total_inflections += 1
                self.index.setdefault(form, []).append((headword, preview))

    def lookup(self, word):
        """Look up a word, returning list of (headword, definition_preview).

        Tries exact match first, then case variations (matching Kindle behavior).
        """
        # Exact match
        if word in self.index:
            return self.index[word]

        # Try lowercase
        lower = word.lower()
        if lower in self.index:
            return self.index[lower]

        # Try capitalized
        if word and word[0].islower():
            cap = word[0].upper() + word[1:]
            if cap in self.index:
                return self.index[cap]

        return []


def find_build_dirs(pattern=None):
    """Find build directories containing content.html files."""
    base = os.path.dirname(os.path.abspath(__file__))

    if pattern:
        # Specific directory or glob
        candidates = glob.glob(os.path.join(base, pattern))
        dirs = []
        for c in sorted(candidates):
            if os.path.isdir(c) and os.path.exists(os.path.join(c, 'content.html')):
                dirs.append(c)
        return dirs

    # Find the latest full build (all volumes)
    vol_dirs = sorted(glob.glob(os.path.join(
        base, 'lemma_greek_el_*_alpha_beta_gamma_delta'
    )))
    if not vol_dirs:
        # Try any directory with content.html
        all_dirs = sorted(glob.glob(os.path.join(base, 'lemma_greek_el_*')))
        return [d for d in all_dirs
                if os.path.isdir(d) and os.path.exists(os.path.join(d, 'content.html'))]

    # Get the latest date prefix and find all volumes for it
    latest = os.path.basename(vol_dirs[-1])
    # Extract date: lemma_greek_el_20260405_alpha_beta_gamma_delta -> 20260405
    date_match = re.search(r'lemma_greek_el_(\d{8})_', latest)
    if not date_match:
        return vol_dirs[-1:]

    date = date_match.group(1)
    prefix = f'lemma_greek_el_{date}_'
    all_volumes = sorted(glob.glob(os.path.join(base, f'{prefix}*')))
    # Exclude pct test builds
    return [d for d in all_volumes
            if os.path.isdir(d) and 'pct' not in d
            and os.path.exists(os.path.join(d, 'content.html'))]


def run_tests(index):
    """Run known lookup tests and report results."""
    passed = 0
    failed = 0
    missing_headword = 0

    print(f"\nRunning {len(KNOWN_LOOKUPS)} lookup tests...\n")

    for form, expected_headword, desc in KNOWN_LOOKUPS:
        results = index.lookup(form)
        headwords = [hw for hw, _ in results]

        if expected_headword not in index.headwords:
            missing_headword += 1
            print(f"  SKIP  {form} -> {expected_headword} ({desc})")
            print(f"        headword '{expected_headword}' not in dictionary")
            continue

        if expected_headword in headwords:
            passed += 1
        else:
            failed += 1
            if results:
                found = ", ".join(headwords[:3])
                print(f"  FAIL  {form} -> expected '{expected_headword}', got: {found} ({desc})")
            else:
                print(f"  FAIL  {form} -> expected '{expected_headword}', not found ({desc})")

    total_run = passed + failed
    print(f"\nResults: {passed}/{total_run} passed", end="")
    if missing_headword:
        print(f", {missing_headword} skipped (headword not in build)", end="")
    if failed:
        print(f", {failed} FAILED", end="")
    print()

    return failed == 0


def interactive_mode(index):
    """Interactive lookup - type Greek words to test."""
    print("\nInteractive lookup mode. Type a Greek word to look it up.")
    print("Type 'q' to quit.\n")

    while True:
        try:
            word = input("lookup> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not word or word == 'q':
            break

        results = index.lookup(word)
        if results:
            # Deduplicate by headword
            seen = set()
            for hw, preview in results:
                if hw not in seen:
                    seen.add(hw)
                    print(f"  {hw}: {preview}")
        else:
            print(f"  (not found)")


def main():
    interactive = '-i' in sys.argv
    pattern = None
    for arg in sys.argv[1:]:
        if arg != '-i':
            pattern = arg

    dirs = find_build_dirs(pattern)
    if not dirs:
        print("No build directories found. Run the generator first.")
        sys.exit(1)

    index = DictionaryIndex()

    print(f"Loading {len(dirs)} content file(s)...")
    start = time.time()
    for d in dirs:
        content_path = os.path.join(d, 'content.html')
        name = os.path.basename(d)
        index.load_content_html(content_path)
        print(f"  {name}: {len(index.headwords)} headwords so far")

    elapsed = time.time() - start
    print(f"\nLoaded {len(index.headwords)} headwords, "
          f"{index.total_inflections} inflections, "
          f"{len(index.index)} unique lookup keys "
          f"in {elapsed:.1f}s")

    all_passed = run_tests(index)

    if interactive:
        interactive_mode(index)

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
