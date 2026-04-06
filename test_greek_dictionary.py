#!/usr/bin/env python3
#
#  test_greek_dictionary.py
#  Test Greek dictionary lookups without building MOBI files
#
#  Created by Francisco Riordan on 4/22/25.
#

import argparse
import glob
import os
import re
import sys
import time
from lib.greek_dictionary_generator import GreekDictionaryGenerator
from lib.downloader import Downloader
from lib.entry_processor import EntryProcessor


class DictionaryTester:
    def __init__(self, source_lang='el'):
        self.source_lang = source_lang
        self.generator = GreekDictionaryGenerator(source_lang)
        self.entries = {}
        self.inflection_map = {}

    def load_and_process(self):
        print("Loading and processing entries...")

        # Use today's date
        today_date = time.strftime("%Y%m%d")
        jsonl_file = f"greek_data_{self.source_lang}_{today_date}.jsonl"

        # Check if today's file exists
        if not os.path.exists(jsonl_file):
            print(f"Today's data file ({jsonl_file}) not found. Downloading...")

            # Download using the generator's download functionality
            self.generator.update_download_date(today_date)
            downloader = Downloader(self.source_lang, today_date)
            success, filename, actual_date = downloader.download()

            if success:
                jsonl_file = filename
                self.generator.update_download_date(actual_date)
                print(f"Downloaded: {jsonl_file}")
            else:
                # Fall back to most recent file if download fails
                files = sorted(glob.glob(f"greek_data_{self.source_lang}_*.jsonl"))
                if files:
                    latest_file = files[-1]
                    print(f"Download failed. Using most recent file: {latest_file}")
                    jsonl_file = latest_file
                    m = re.search(rf"greek_data_{self.source_lang}_(\d{{8}})\.jsonl", latest_file)
                    if m:
                        self.generator.update_download_date(m.group(1))
                else:
                    print("Error: No data files found and download failed")
                    sys.exit(1)
        else:
            print(f"Using data file: {jsonl_file}")
            self.generator.update_download_date(today_date)

        # Process entries (this loads them into self.generator.entries)
        processor = EntryProcessor(self.generator)
        processor.process()

        self.entries = self.generator.entries
        self._build_inflection_map()

        print(f"Loaded {len(self.entries)} headwords")
        print(f"Built inflection map with {len(self.inflection_map)} inflected forms")

    def _build_inflection_map(self):
        # Build a map from inflected forms to their headwords
        for headword, entries_list in self.entries.items():
            for entry in entries_list:
                # Add the headword itself (with case variations)
                self._add_to_inflection_map(headword, headword)
                self._add_to_inflection_map(headword.lower(), headword)
                capitalized = headword[0].upper() + headword[1:] if headword else headword
                self._add_to_inflection_map(capitalized, headword)

                # Add all inflections
                for inflection in (entry.get('inflections') or []):
                    self._add_to_inflection_map(inflection, headword)

    def _add_to_inflection_map(self, form, headword):
        if form not in self.inflection_map:
            self.inflection_map[form] = []
        if headword not in self.inflection_map[form]:
            self.inflection_map[form].append(headword)

    def test_lookup(self, word):
        print(f"\n{'=' * 60}")
        print(f"Testing lookup: '{word}'")
        print(f"{'=' * 60}")

        # Direct lookup
        if word in self.entries:
            print(f"\nFOUND as headword:")
            for entry in self.entries[word]:
                print(f"  POS: {entry['pos']}")
                print(f"  Definitions: {'; '.join(entry['definitions'])}")
                inflection_count = len(entry.get('inflections') or [])
                print(f"  Inflections in memory: {inflection_count} forms")

                # Simulate HTML generation filtering
                single_word_inflections = [i for i in (entry.get('inflections') or []) if ' ' not in i]
                limited_inflections = single_word_inflections[:50]
                print(f"  Inflections after filtering: {len(limited_inflections)} forms (single words only, max 50)")
        else:
            print(f"\nNOT FOUND as headword")

        # Inflection lookup
        if word in self.inflection_map:
            print(f"\nFOUND as inflection of:")
            for headword in self.inflection_map[word]:
                print(f"  -> {headword}")
        else:
            print(f"\nNOT FOUND as inflection")

        # Check case variations
        variations = list(set([word.lower(), word[0].upper() + word[1:] if word else word, word.upper()]) - {word})
        found_variations = [v for v in variations if v in self.inflection_map]

        if found_variations:
            print(f"\nCase variations found:")
            for var in found_variations:
                print(f"  '{var}' -> {', '.join(self.inflection_map[var])}")

    def test_dictionary_entry(self, headword, test_word=None):
        print(f"\n{'=' * 60}")
        print(f"Testing dictionary entry for: '{headword}'")
        print(f"{'=' * 60}")

        if headword in self.entries:
            for entry in self.entries[headword]:
                all_inflections = entry.get('inflections') or []

                # Simulate HTML generation filtering (same as html_generator.py)
                single_word_inflections = [i for i in all_inflections if ' ' not in i]

                # Check if this is a proper noun
                is_proper_noun = entry.get('pos') and ('proper' in entry['pos'].lower() or 'name' in entry['pos'].lower())

                if is_proper_noun:
                    limited_inflections = single_word_inflections[:30]
                else:
                    # Separate lowercase and capitalized forms
                    lowercase_forms = [i for i in single_word_inflections if i and i[0] == i[0].lower()]
                    capitalized_forms = [i for i in single_word_inflections if i and i[0] == i[0].upper() and i != i.upper()]
                    uppercase_forms = [i for i in single_word_inflections if i and i == i.upper() and len(i) > 1]

                    # Prioritize lowercase, then capitalized, then uppercase
                    combined = []
                    seen = set()
                    for form in lowercase_forms + capitalized_forms + uppercase_forms:
                        if form not in seen:
                            seen.add(form)
                            combined.append(form)
                    limited_inflections = combined[:30]

                print(f"\nEntry for '{headword}' ({entry['pos']}):")
                print(f"  Total inflections collected: {len(all_inflections)}")
                print(f"  Multi-word forms removed: {sum(1 for i in all_inflections if ' ' in i)}")
                print(f"  Single-word inflections: {len(single_word_inflections)}")
                print(f"  Final inflections in dictionary: {len(limited_inflections)} (limited to 30)")
                if not is_proper_noun:
                    print("  Prioritizing: 1) Listed forms, 2) Lowercase, 3) Capitalized")
                if entry.get('expanded_from_template'):
                    print("  Note: Some inflections were expanded from templates")

                # Check for specific test word if provided
                if test_word:
                    test_cap = test_word[0].upper() + test_word[1:] if test_word else test_word
                    if test_word in limited_inflections or test_cap in limited_inflections:
                        print(f"  '{test_word}' IS included in the final dictionary entry")
                        try:
                            position = limited_inflections.index(test_word)
                        except ValueError:
                            position = limited_inflections.index(test_cap)
                        print(f"     -> Position: {position + 1} of {len(limited_inflections)}")
                    else:
                        print(f"  '{test_word}' is NOT in the final dictionary entry")

                        # Check if it was filtered out
                        if test_word in all_inflections:
                            print("     -> It was in the original inflections but got filtered out")
                            if test_word in single_word_inflections:
                                position = single_word_inflections.index(test_word)
                                print(f"     -> Position in single-word list: {position + 1} of {len(single_word_inflections)}")
                                print("     -> It didn't make the top 30 cut")
                        else:
                            print("     -> It was never in the inflections list")

                print(f"\n  First 10 inflections that will be in dictionary:")
                for inf in limited_inflections[:10]:
                    print(f"    - {inf}")

                if len(limited_inflections) > 10:
                    print(f"    ... and {len(limited_inflections) - 10} more")
        else:
            print(f"Headword '{headword}' not found!")

    def test_verb_forms(self, headword):
        print(f"\n{'=' * 60}")
        print(f"Testing all forms of verb: '{headword}'")
        print(f"{'=' * 60}")

        if headword in self.entries:
            all_forms = [headword]

            for entry in self.entries[headword]:
                all_forms.extend(entry.get('inflections') or [])

            # Deduplicate while preserving order
            seen = set()
            unique_forms = []
            for form in all_forms:
                if form not in seen:
                    seen.add(form)
                    unique_forms.append(form)
            all_forms = unique_forms

            print(f"Found {len(all_forms)} total forms")

            # Group by first letter
            by_letter = {}
            for form in all_forms:
                letter = form[0].upper() if form else '?'
                by_letter.setdefault(letter, []).append(form)

            for letter in sorted(by_letter.keys()):
                forms = by_letter[letter]
                print(f"\n{letter}:")
                for form in sorted(forms):
                    status = "OK" if form in self.inflection_map else "MISSING"
                    print(f"  [{status}] {form}")

            # Check for forms not in the inflection map
            missing = [form for form in all_forms if form not in self.inflection_map]

            if missing:
                print(f"\nMISSING FORMS:")
                for form in missing:
                    print(f"  {form} - NOT IN INFLECTION MAP")
            else:
                print(f"\nAll forms lookup correctly!")
        else:
            print(f"Headword '{headword}' not found!")

    def show_statistics(self):
        print(f"\nDictionary Statistics:")

        total_inflections = 0
        max_inflections = 0
        max_word = None

        for headword, entries_list in self.entries.items():
            for entry in entries_list:
                inflection_count = len(entry.get('inflections') or [])
                total_inflections += inflection_count

                if inflection_count > max_inflections:
                    max_inflections = inflection_count
                    max_word = headword

        print(f"Headwords: {len(self.entries)}")
        print(f"Total inflections: {total_inflections}")
        print(f"Most inflected word: '{max_word}' with {max_inflections} forms")

    def interactive_mode(self):
        print("\nEntering interactive test mode. Type 'exit' to quit.")
        print("Commands:")
        print("  lookup <word>     - Test single word lookup")
        print("  verb <word>       - Test all forms of a verb")
        print("  entry <word> [test_word]  - Show what inflections make it to the dictionary")
        print("  stats             - Show dictionary statistics")
        print("  exit              - Exit")

        while True:
            try:
                user_input = input("\n> ")
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if user_input == 'exit':
                break

            if user_input.startswith('lookup '):
                word = user_input[len('lookup '):].strip()
                self.test_lookup(word)
            elif user_input.startswith('verb '):
                word = user_input[len('verb '):].strip()
                self.test_verb_forms(word)
            elif user_input.startswith('entry '):
                parts = user_input[len('entry '):].strip().split(None, 1)
                headword = parts[0]
                test_word = parts[1] if len(parts) > 1 else None
                self.test_dictionary_entry(headword, test_word)
            elif user_input == 'stats':
                self.show_statistics()
            else:
                print("Unknown command. Try 'lookup <word>', 'verb <word>', 'entry <word> [test_word]', 'stats', or 'exit'")


def main():
    parser = argparse.ArgumentParser(
        description="Test Greek dictionary lookups without building MOBI files",
        usage="python3 test_greek_dictionary.py [options]",
    )

    parser.add_argument(
        "-s", "--source",
        default="el",
        help="Source language: 'en' or 'el' (default: el)",
    )

    parser.add_argument(
        "-w", "--word",
        help="Test lookup for specific word",
    )

    parser.add_argument(
        "-v", "--verb",
        help="Test all forms of a verb",
    )

    parser.add_argument(
        "-e", "--entry",
        help="Test if test_word is in headword's dictionary entry",
    )

    parser.add_argument(
        "test_word",
        nargs="?",
        default=None,
        help="Test word for --entry mode",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show dictionary statistics",
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive test mode",
    )

    args = parser.parse_args()

    tester = DictionaryTester(args.source)
    tester.load_and_process()

    if args.word:
        tester.test_lookup(args.word)
    elif args.verb:
        tester.test_verb_forms(args.verb)
    elif args.entry:
        tester.test_dictionary_entry(args.entry, args.test_word)
    elif args.stats:
        tester.show_statistics()
    elif args.interactive:
        tester.interactive_mode()
    else:
        # Default: test some common cases
        print("\nTesting some common lookups:")
        for word in ["έπαψε", "παύω", "άρχοντες", "άρχοντας", "Αναρωτιόταν", "αναρωτιέμαι"]:
            tester.test_lookup(word)


if __name__ == "__main__":
    main()
