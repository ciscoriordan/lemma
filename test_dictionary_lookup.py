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
    ("χρόνια", "χρόνια", "headword lookup 'years/ages' (also plural of χρόνος)"),

    # Adjective inflections
    ("καλή", "καλός", "feminine of 'good'"),
    ("καλό", "καλός", "neuter of 'good'"),
    ("μεγάλη", "μεγάλος", "feminine of 'big'"),
    ("μεγάλο", "μεγάλος", "neuter of 'big'"),
    ("όμορφο", "όμορφος", "neuter of 'beautiful'"),
    ("όμορφη", "όμορφος", "feminine of 'beautiful'"),

    # Headword self-lookup (should always work)
    ("τρώω", "τρώω", "headword self-lookup 'eat'"),
    ("σπίτι", "σπίτι", "headword self-lookup 'house'"),
    ("καλός", "καλός", "headword self-lookup 'good'"),
    ("όμορφος", "όμορφος", "headword self-lookup 'beautiful'"),
    ("ομορφιά", "ομορφιά", "headword self-lookup 'beauty'"),
]

# Expected POS lines - the POS must start with the expected text.
# Full builds have gender/variant info (e.g., "noun, feminine (plural ...)"),
# basic builds have just the POS type. Using startswith handles both.
# Each tuple: (headword, expected_pos_prefix, description)
KNOWN_POS_FORMATS = [
    ("θάλασσα", "noun", "POS starts with 'noun'"),
    ("σκύλος", "noun", "POS starts with 'noun'"),
    ("Ελλάδα", "name", "POS starts with 'name'"),
]


class DictionaryIndex:
    """Simulates Kindle's dictionary lookup index."""

    def __init__(self):
        # word -> list of (headword, definitions_preview)
        self.index = {}
        self.headwords = set()
        self.total_inflections = 0
        # headword -> list of POS line strings (text inside <p><i>...</i></p>)
        self.pos_lines = {}

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
        pos_pattern = re.compile(r'<p><i>(.*?)</i></p>')

        for m in entry_pattern.finditer(content):
            entry_html = m.group(1)

            orth_match = orth_pattern.search(entry_html)
            if not orth_match:
                continue

            headword = html.unescape(orth_match.group(1))
            self.headwords.add(headword)

            # Extract POS lines
            for pm in pos_pattern.finditer(entry_html):
                pos_text = html.unescape(pm.group(1))
                self.pos_lines.setdefault(headword, []).append(pos_text)

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

    # Find the latest builds - try both English and Greek Wiktionary sources
    all_dirs = sorted(glob.glob(os.path.join(base, 'lemma_greek_*')))
    build_dirs = [d for d in all_dirs
                  if os.path.isdir(d) and 'pct' not in d
                  and os.path.exists(os.path.join(d, 'content.html'))]

    if not build_dirs:
        return []

    # Group by date and find the latest date
    latest_date = None
    for d in build_dirs:
        date_match = re.search(r'lemma_greek_\w+_(\d{8})', os.path.basename(d))
        if date_match:
            date = date_match.group(1)
            if latest_date is None or date > latest_date:
                latest_date = date

    if latest_date:
        return [d for d in build_dirs
                if latest_date in os.path.basename(d)]

    return build_dirs[-1:]


def run_tests(index, cases=None, label="lookup"):
    """Run known lookup tests and report results."""
    if cases is None:
        cases = KNOWN_LOOKUPS
    passed = 0
    failed = 0
    missing_headword = 0

    print(f"\nRunning {len(cases)} {label} tests...\n")

    for form, expected_headword, desc in cases:
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


def run_pos_tests(index, cases=None):
    """Check POS line formatting against expected values."""
    if cases is None:
        cases = KNOWN_POS_FORMATS
    passed = 0
    failed = 0
    skipped = 0

    print(f"\nRunning {len(cases)} POS format tests...\n")

    for entry in cases:
        headword, expected_pos = entry[0], entry[1]
        desc = entry[2] if len(entry) > 2 else ""

        if headword not in index.headwords:
            skipped += 1
            print(f"  SKIP  {headword} ({desc})")
            print(f"        headword not in dictionary")
            continue

        actual_lines = index.pos_lines.get(headword, [])
        if any(line.startswith(expected_pos) for line in actual_lines):
            passed += 1
        else:
            failed += 1
            actual = actual_lines[0] if actual_lines else "(no POS line)"
            print(f"  FAIL  {headword}: expected POS starting with '{expected_pos}'")
            print(f"        got: '{actual}' ({desc})")

    total_run = passed + failed
    print(f"\nPOS format results: {passed}/{total_run} passed", end="")
    if skipped:
        print(f", {skipped} skipped", end="")
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
    all_passed = run_pos_tests(index) and all_passed

    # Run position verification and anchor link tests on content.html files
    for d in dirs:
        content_path = os.path.join(d, 'content.html')
        if os.path.exists(content_path):
            all_passed = run_position_verification_tests(content_path) and all_passed

            with open(content_path, 'r', encoding='utf-8') as f:
                # Quick check: only run if file contains cross-reference links
                head = f.read(100000)
                if '<a href="#hw_' in head:
                    all_passed = run_anchor_link_tests(content_path) and all_passed

    # Run MOBI validation on any .mobi files in the build directories
    mobi_files = []
    for d in dirs:
        for f in os.listdir(d):
            if f.endswith('.mobi'):
                mobi_files.append(os.path.join(d, f))
    if mobi_files:
        all_passed = run_mobi_validation_tests(mobi_files) and all_passed
    else:
        # Also check dist/ for MOBIs
        dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist')
        if os.path.isdir(dist_dir):
            mobi_files = [os.path.join(dist_dir, f)
                          for f in os.listdir(dist_dir) if f.endswith('.mobi')]
            if mobi_files:
                all_passed = run_mobi_validation_tests(mobi_files) and all_passed

    if interactive:
        interactive_mode(index)

    sys.exit(0 if all_passed else 1)


def _family_key(filename):
    """Return the filename family key with the trailing date stamp stripped.

    A "family" is the stable identity of a dictionary across versions, e.g.
    both 'lemma_greek_en_20260409.mobi' and 'lemma_greek_en_20260410.mobi'
    belong to family 'lemma_greek_en.mobi', while
    'lemma_greek_en_20260410_basic.mobi' belongs to 'lemma_greek_en_basic.mobi'.

    The date stamp is an 8-digit YYYYMMDD preceded by an underscore. It can
    appear anywhere in the basename (typically just before an optional
    variant suffix like '_basic').
    """
    base = os.path.basename(filename)
    # Strip a trailing or embedded _YYYYMMDD segment.
    stripped = re.sub(r'_\d{8}(?=(_|\.|$))', '', base)
    return stripped


def _dedupe_to_newest_per_family(mobi_files):
    """Keep only the newest file per family, by filesystem mtime.

    Stale older versions in dist/ should not gate deploys. We sort by mtime
    (newest first) and pick the first file we see per family key.
    """
    newest = {}
    for path in sorted(mobi_files, key=lambda p: os.path.getmtime(p), reverse=True):
        key = _family_key(path)
        if key not in newest:
            newest[key] = path
    return sorted(newest.values())


def run_mobi_validation_tests(mobi_files):
    """Validate MOBI file structure for dictionary recognition.

    Checks that each MOBI has the required binary structure for Kindle
    to recognize it as a dictionary: correct PalmDB header, MOBI header
    with dictionary type, EXTH records with language metadata, and INDX
    records for the lookup index.

    Also checks for PalmDB name uniqueness across distinct filename
    families (a "family" is a filename with its _YYYYMMDD date stamp
    stripped). Duplicate PalmDB names across different dictionaries cause
    the Kindle's FSCK to rename files, making them invisible in the
    dictionary list. Duplicate names within the same family are expected
    (they are just different builds of the same dictionary) and are
    ignored; we only validate the newest file per family.
    """
    import struct

    passed = 0
    failed = 0
    palmdb_names = {}  # name -> filepath, for uniqueness check (keyed by family)

    # Dedupe: only validate the newest file per family. Stale older builds in
    # dist/ are not relevant to whether today's build will deploy cleanly.
    mobi_files = _dedupe_to_newest_per_family(mobi_files)

    print(f"\nRunning MOBI validation on {len(mobi_files)} file(s)...\n")

    for mobi_path in sorted(mobi_files):
        filename = os.path.basename(mobi_path)
        errors = []

        try:
            with open(mobi_path, 'rb') as f:
                data = f.read()
        except IOError as e:
            errors.append(f"Cannot read file: {e}")
            failed += 1
            print(f"  FAIL  {filename}")
            for err in errors:
                print(f"        {err}")
            continue

        if len(data) < 78:
            errors.append(f"File too small ({len(data)} bytes), minimum PalmDB header is 78 bytes")
            failed += 1
            print(f"  FAIL  {filename}")
            for err in errors:
                print(f"        {err}")
            continue

        # 1. PalmDB header checks
        palmdb_name = data[0:32].split(b'\x00')[0].decode('latin-1', errors='replace')
        db_type = data[60:64]
        db_creator = data[64:68]
        num_records = struct.unpack_from('>H', data, 76)[0]

        if db_type != b'BOOK':
            errors.append(f"PalmDB type is '{db_type}', expected 'BOOK'")
        if db_creator != b'MOBI':
            errors.append(f"PalmDB creator is '{db_creator}', expected 'MOBI'")
        if num_records == 0:
            errors.append("PalmDB has 0 records")
        if len(palmdb_name) > 31:
            errors.append(f"PalmDB name too long ({len(palmdb_name)} bytes, max 31)")

        # Check PalmDB name uniqueness across distinct filename families.
        # Two files in the same family (same dictionary, different build dates)
        # are expected to share a PalmDB name, because kindling derives it from
        # the stable OPF title. Only a collision across different families is a
        # real problem on the device.
        family = _family_key(mobi_path)
        if palmdb_name in palmdb_names and palmdb_names[palmdb_name][0] != family:
            errors.append(
                f"PalmDB name '{palmdb_name}' conflicts with "
                f"'{os.path.basename(palmdb_names[palmdb_name][1])}' - "
                f"Kindle FSCK will rename both files, hiding them from the dictionary list"
            )
        else:
            palmdb_names[palmdb_name] = (family, mobi_path)

        # 2. Record 0 / MOBI header checks
        if num_records > 0:
            rec0_offset = struct.unpack_from('>I', data, 78)[0]
            if rec0_offset + 280 > len(data):
                errors.append("Record 0 offset out of bounds")
            else:
                rec0 = data[rec0_offset:]

                # PalmDOC header
                compression = struct.unpack_from('>H', rec0, 0)[0]
                if compression not in (1, 2, 17480):
                    errors.append(f"Invalid compression type: {compression}")

                # MOBI header magic
                mobi_magic = rec0[16:20]
                if mobi_magic != b'MOBI':
                    errors.append(f"No MOBI header (expected 'MOBI', got {mobi_magic})")
                else:
                    header_length = struct.unpack_from('>I', rec0, 20)[0]
                    mobi_type = struct.unpack_from('>I', rec0, 24)[0]
                    text_encoding = struct.unpack_from('>I', rec0, 28)[0]

                    if mobi_type != 2:
                        errors.append(f"MOBI type is {mobi_type}, expected 2 (MOBI Book)")
                    if text_encoding != 65001:
                        errors.append(f"Text encoding is {text_encoding}, expected 65001 (UTF-8)")

                    # 3. EXTH checks
                    exth_flag = struct.unpack_from('>I', rec0, 128)[0]
                    has_exth = bool(exth_flag & 0x40)

                    if not has_exth:
                        errors.append("EXTH flag not set - dictionary metadata missing")
                    else:
                        exth_offset = 16 + header_length
                        exth_magic = rec0[exth_offset:exth_offset + 4]
                        if exth_magic != b'EXTH':
                            errors.append(f"EXTH header missing at expected offset {exth_offset}")
                        else:
                            exth_count = struct.unpack_from('>I', rec0, exth_offset + 8)[0]
                            exth_types = set()
                            pos = exth_offset + 12
                            for _ in range(exth_count):
                                if pos + 8 > len(rec0):
                                    break
                                rec_type = struct.unpack_from('>I', rec0, pos)[0]
                                rec_len = struct.unpack_from('>I', rec0, pos + 4)[0]
                                exth_types.add(rec_type)
                                pos += rec_len

                            # EXTH 531 = DictionaryInLanguage, 532 = DictionaryOutLanguage
                            if 531 not in exth_types:
                                errors.append("EXTH 531 (DictionaryInLanguage) missing")
                            if 532 not in exth_types:
                                errors.append("EXTH 532 (DictionaryOutLanguage) missing")

                    # 4. INDX record checks
                    #
                    # The MOBI header field at offset 0x50 is "First Non-book
                    # index" per the MobileRead MOBI spec: it's the first
                    # record that is not part of the compressed text. It is
                    # NOT guaranteed to be the first INDX record. Kindle
                    # dictionaries commonly place cover / HD-image-container
                    # records between the text and the INDX records, so the
                    # record at first_non_book is often a JPEG. The Kindle
                    # finds the INDX section via EXTH and header pointers,
                    # not by positional assumption.
                    #
                    # So we scan the range [first_non_book, num_records) for
                    # any record whose payload begins with the 'INDX' magic.
                    # If none is found, the dictionary truly has no index
                    # and is broken. If at least one is found, it is fine.
                    first_non_book = struct.unpack_from('>I', rec0, 80)[0]
                    found_indx = False
                    for rec_idx in range(first_non_book, num_records):
                        rec_off_pos = 78 + rec_idx * 8
                        if rec_off_pos + 4 > len(data):
                            break
                        rec_off = struct.unpack_from('>I', data, rec_off_pos)[0]
                        if rec_off + 4 > len(data):
                            continue
                        if data[rec_off:rec_off + 4] == b'INDX':
                            found_indx = True
                            break
                    if not found_indx:
                        errors.append(
                            f"No INDX record found after text section "
                            f"(scanned records {first_non_book}..{num_records - 1})"
                        )

        if errors:
            failed += 1
            print(f"  FAIL  {filename}")
            for err in errors:
                print(f"        {err}")
        else:
            passed += 1

    total = passed + failed
    print(f"\nMOBI validation results: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED", end="")
    print()
    return failed == 0


def strip_idx_markup(html_text):
    """Strip idx namespace tags from HTML, matching kindling's strip_idx_markup.

    This must produce the same output as the Rust function in kindling
    so that position calculations in tests match the MOBI binary.
    """
    result = html_text
    result = re.sub(r'<\?xml[^?]*\?>\s*', '', result)
    result = re.sub(r'\s+xmlns:\w+="[^"]*"', '', result)
    result = re.sub(r'(?s)<head>.*?</head>', '<head><guide></guide></head>', result)
    result = re.sub(r'<idx:iform[^/]*/>\s*', '', result)
    result = re.sub(r'<idx:infl>\s*</idx:infl>\s*', '', result)
    result = re.sub(r'(?s)\s*<idx:infl>.*?</idx:infl>\s*', '', result)
    result = re.sub(r'<idx:orth[^>]*/>', '', result)
    result = re.sub(r'<idx:orth[^>]*>', '', result)
    result = re.sub(r'</idx:orth>', '', result)
    result = re.sub(r'<idx:short>\s*', '', result)
    result = re.sub(r'\s*</idx:short>', '', result)
    result = re.sub(r'<idx:entry[^>]*>\s*', '', result)
    result = re.sub(r'\s*</idx:entry>', '', result)
    result = re.sub(r'\s+', ' ', result)
    result = re.sub(r'>\s+<', '><', result)
    result = result.replace('</b><', '</b> <')
    result = result.replace('</p><hr', '</p> <hr')
    result = result.replace('/><b>', '/> <b>')
    return result.strip()


# Entries to verify: (iform, must_contain_text, must_not_contain_text, description)
# These catch MOBI index position corruption where lookups show the wrong entry.
POSITION_VERIFICATION_CASES = [
    ("όμορφο", "beautiful", "όμορφος + -ιά",
     "iform of όμορφος should show 'beautiful', not ομορφιά etymology"),
    ("όμορφη", "beautiful", None,
     "feminine of όμορφος should show 'beautiful'"),
    ("ομορφιά", "beauty", None,
     "headword ομορφιά should show 'beauty'"),
    ("καλή", "good", None,
     "feminine of καλός should show 'good'"),
    ("σπιτιού", "house", None,
     "genitive of σπίτι should show 'house'"),
]


def run_position_verification_tests(content_html_path):
    """Verify that iform lookups show the correct definition content.

    This simulates kindling's entry position calculation by stripping idx
    markup and finding headword positions in the stripped text, exactly as
    kindling does when building the MOBI index. If the position for an
    iform points to the wrong entry (e.g., ομορφιά instead of όμορφος),
    the definition text at that position won't contain the expected words.

    This catches the critical bug where etymologies/definitions containing
    a headword cause find_entry_positions to map to the wrong location.
    """
    passed = 0
    failed = 0
    skipped = 0

    print(f"\nRunning {len(POSITION_VERIFICATION_CASES)} MOBI position verification tests...\n")

    with open(content_html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries (same as kindling's parse_dictionary_html)
    orth_re = re.compile(r'<idx:orth\s+value="([^"]*)"')
    iform_re = re.compile(r'<idx:iform\s+value="([^"]*)"')
    entry_open_tag = "<idx:entry"
    entry_close_tag = "</idx:entry>"
    search_pos = 0
    entries = []

    while True:
        start = content.find(entry_open_tag, search_pos)
        if start < 0:
            break
        after_open = content.find('>', start) + 1
        close_pos = content.find(entry_close_tag, after_open)
        if close_pos < 0:
            break
        entry_inner = content[after_open:close_pos]
        m = orth_re.search(entry_inner)
        if m:
            hw = html.unescape(m.group(1))
            infs = [html.unescape(m2.group(1)) for m2 in iform_re.finditer(entry_inner)]
            entries.append({'headword': hw, 'inflections': infs})
        search_pos = close_pos + len(entry_close_tag)

    # Build the stripped text (same as kindling's build_text_content)
    stripped = strip_idx_markup(content)
    body_match = re.search(r'(?s)<body[^>]*>(.*?)</body>', stripped)
    body = body_match.group(1).strip() if body_match else stripped
    head_match = re.search(r'(?s)<head[^>]*>.*?</head>', stripped)
    head = head_match.group(0) if head_match else '<head><guide></guide></head>'
    text = f'<html>{head}<body>{body}  <mbp:pagebreak/></body></html>'
    text_bytes = text.encode('utf-8')

    # Simulate find_entry_positions with entry-boundary check
    # (matching kindling's current implementation)
    entry_positions = {}
    search_start = 0
    for entry in entries:
        hw_bytes = entry['headword'].encode('utf-8')
        bold_needle = b'<b>' + hw_bytes + b'</b>'

        # Search for <b>headword</b> at entry boundary
        found = None
        scan_from = search_start
        while True:
            bold_pos = text_bytes.find(bold_needle, scan_from)
            if bold_pos < 0:
                break
            # Entry boundary check: preceded by <hr/> or near start
            if bold_pos < 200:
                found = (bold_pos, bold_pos + 3)
                break
            check_start = max(0, bold_pos - 8)
            preceding = text_bytes[check_start:bold_pos]
            if preceding.endswith(b'<hr/> ') or preceding.endswith(b'<hr/>') or preceding.endswith(b'/> '):
                found = (bold_pos, bold_pos + 3)
                break
            scan_from = bold_pos + len(bold_needle)

        if found:
            block_start, pos = found
            hr_pos = text_bytes.find(b'<hr/>', pos)
            if hr_pos >= 0:
                text_len = hr_pos - block_start
            else:
                text_len = len(text_bytes) - block_start

            entry_positions[entry['headword']] = (block_start, text_len)
            for inf in entry['inflections']:
                if inf not in entry_positions:
                    entry_positions[inf] = (block_start, text_len)
            search_start = pos + len(hw_bytes)

    # Run verification cases
    for iform, must_contain, must_not_contain, desc in POSITION_VERIFICATION_CASES:
        if iform not in entry_positions:
            skipped += 1
            print(f"  SKIP  '{iform}' not in index ({desc})")
            continue

        start_pos, text_len = entry_positions[iform]
        entry_text = text_bytes[start_pos:start_pos + text_len].decode('utf-8', errors='replace')

        ok = True
        if must_contain and must_contain not in entry_text:
            ok = False
            print(f"  FAIL  '{iform}': expected '{must_contain}' in definition ({desc})")
            print(f"        got: {entry_text[:120]}...")

        if must_not_contain and must_not_contain in entry_text:
            ok = False
            print(f"  FAIL  '{iform}': found forbidden '{must_not_contain}' in definition ({desc})")
            print(f"        got: {entry_text[:120]}...")

        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print(f"\nPosition verification results: {passed}/{total} passed", end="")
    if skipped:
        print(f", {skipped} skipped", end="")
    if failed:
        print(f", {failed} FAILED", end="")
    print()
    return failed == 0


def run_anchor_link_tests(content_html_path):
    """Validate that all anchor links in content.html have matching targets.

    When links are enabled, each <a href="#hw_X"> must have a corresponding
    id="hw_X" on an idx:entry element. Broken links indicate missing anchor
    IDs, which won't prevent dictionary recognition but make cross-references
    non-functional.
    """
    passed = 0
    failed = 0

    print(f"\nRunning anchor link tests on {os.path.basename(content_html_path)}...\n")

    with open(content_html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all link targets
    link_targets = set(re.findall(r'<a href="#(hw_[^"]+)"', content))
    # Find all anchor IDs
    anchor_ids = set(re.findall(r'id="(hw_[^"]+)"', content))

    if not link_targets:
        print("  (no cross-reference links found, skipping)")
        return True

    missing = link_targets - anchor_ids
    if missing:
        failed += 1
        print(f"  FAIL  {len(missing)} links have no matching anchor ID")
        # Show first 5 examples
        for target in sorted(missing)[:5]:
            print(f"        missing anchor: {target}")
        if len(missing) > 5:
            print(f"        ... and {len(missing) - 5} more")
    else:
        passed += 1

    total = passed + failed
    print(f"\nAnchor link results: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED", end="")
    print()
    return failed == 0


if __name__ == '__main__':
    main()
