#
#  lib/greek_dictionary_generator.py
#  Main generator class
#
#  Created by Francisco Riordan on 4/22/25.
#

import gc
import sys
import time
from lib.dilemma_inflections import DilemmaInflections
from lib.downloader import Downloader
from lib.entry_processor import EntryProcessor
from lib.epub_generator import EpubGenerator
from lib.html_generator import HtmlGenerator
from lib.mobi_generator import MobiGenerator


LETTER_GROUPS = [
    ('alpha_beta_gamma_delta', 'αβγδ', 'Α-Δ'),
    ('epsilon_zeta_eta_theta', 'εζηθ', 'Ε-Θ'),
    ('iota_kappa_lambda_mu', 'ικλμ', 'Ι-Μ'),
    ('nu_xi_omicron_pi', 'νξοπ', 'Ν-Π'),
    ('rho_sigma_tau_upsilon', 'ρστυ', 'Ρ-Υ'),
    ('phi_chi_psi_omega', 'φχψω', 'Φ-Ω'),
]

_ACCENT_FROM = 'άέήίόύώΐΰϊϋ'
_ACCENT_TO   = 'αεηιουωιυιυ'
_BASE_TABLE = str.maketrans(_ACCENT_FROM, _ACCENT_TO)


def _first_greek_lower(word):
    """Return the base lowercase Greek letter for the first character."""
    if not word:
        return ''
    ch = word[0].lower().translate(_BASE_TABLE)
    if 'α' <= ch <= 'ω':
        return ch
    return ''


def _partition_entries(entries):
    """Split entries dict into letter-group buckets."""
    letter_to_group = {}
    for name, letters, _ in LETTER_GROUPS:
        for ch in letters:
            letter_to_group[ch] = name

    buckets = {name: {} for name, _, _ in LETTER_GROUPS}
    for word, entry_list in entries.items():
        first = _first_greek_lower(word)
        group = letter_to_group.get(first, LETTER_GROUPS[-1][0])
        buckets[group][word] = entry_list

    return buckets


class GreekDictionaryGenerator:
    def __init__(self, source_lang='en', limit_percent=None, generate_mobi=False, max_inflections=None):
        if source_lang not in ('en', 'el'):
            raise ValueError("Source language must be 'en' or 'el'")
        self.source_lang = source_lang
        self.limit_percent = limit_percent
        self.generate_mobi = generate_mobi
        self.max_inflections = max_inflections
        self.entries = {}
        self.lemma_inflections = {}
        self.extraction_date = None
        self.download_date = time.strftime("%Y%m%d")
        self.output_dir = f"lemma_greek_{self.source_lang}_{self.download_date}"
        self.dilemma_inflections = None
        self.volume_suffix = None
        self.volume_label = None

        # Ensure download_date is set
        if not self.download_date:
            raise RuntimeError("Download date could not be set")

        source_desc = 'English' if source_lang == 'en' else 'Greek'
        print("Initialized with:")
        print(f"  Source: {source_desc} Wiktionary")
        print(f"  Download date: {self.download_date}")
        if limit_percent:
            print(f"  Word limit: {limit_percent}% of entries")

    def generate(self):
        print("Lemma - Greek Kindle Dictionary Generator")
        print(f"Download date: {self.download_date}")

        self._download_data()
        if self.source_lang == 'el':
            self.dilemma_inflections = DilemmaInflections()
        self._process_entries()
        gc.collect()

        all_entries = self.entries
        base_output_dir = self.output_dir
        buckets = _partition_entries(all_entries)

        volume_count = 0
        for group_name, _, group_label in LETTER_GROUPS:
            group_entries = buckets[group_name]
            if not group_entries:
                continue

            volume_count += 1
            print(f"\n=== Volume: {group_name} ({len(group_entries)} entries) ===")

            self.entries = group_entries
            self.output_dir = f"{base_output_dir}_{group_name}"
            self.volume_suffix = group_name
            self.volume_label = group_label

            self._create_output_files()
            gc.collect()
            self._generate_epub()

            if self.generate_mobi:
                self._generate_mobi()

            gc.collect()

        self.entries = all_entries
        self.output_dir = base_output_dir
        self.volume_suffix = None
        self.volume_label = None

        print("\nDictionary generation complete!")
        print(f"Generated {volume_count} volumes")
        if self.extraction_date:
            print(f"Wiktionary extraction date: {self.extraction_date}")

    def update_output_dir(self, new_dir):
        self.output_dir = new_dir

    def update_download_date(self, new_date):
        self.download_date = new_date

    def set_extraction_date(self, date):
        self.extraction_date = date

    def _download_data(self):
        downloader = Downloader(self.source_lang, self.download_date)
        success, filename, actual_date = downloader.download()

        if actual_date != self.download_date:
            self.download_date = actual_date
            self.output_dir = f"lemma_greek_{self.source_lang}_{self.download_date}"
            print(f"Updated download date to: {self.download_date}")

        if not success:
            print("Error: Download failed")
            sys.exit(1)

    def _process_entries(self):
        processor = EntryProcessor(self)
        processor.process()

    def _create_output_files(self):
        html_generator = HtmlGenerator(self)
        html_generator.create_output_files()
        self._opf_filename = html_generator.opf_filename

    def _generate_epub(self):
        epub_generator = EpubGenerator(self, self._opf_filename)
        epub_generator.generate()

    def _generate_mobi(self):
        mobi_generator = MobiGenerator(self, self._opf_filename)
        mobi_generator.generate()
