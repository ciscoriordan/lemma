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


class GreekDictionaryGenerator:
    def __init__(self, source_lang='en', limit_percent=None, generate_mobi=False,
                 max_inflections=None, enable_links=False, enable_etymology=False):
        if source_lang not in ('en', 'el'):
            raise ValueError("Source language must be 'en' or 'el'")
        self.source_lang = source_lang
        self.limit_percent = limit_percent
        self.generate_mobi = generate_mobi
        self.max_inflections = max_inflections
        self.enable_links = enable_links
        self.enable_etymology = enable_etymology
        self.entries = {}
        self.extraction_date = None
        self.download_date = time.strftime("%Y%m%d")
        self.output_dir = f"lemma_greek_{self.source_lang}_{self.download_date}"
        self.dilemma_inflections = None

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
        self.dilemma_inflections = DilemmaInflections()
        self._process_entries()
        gc.collect()
        self._create_output_files()
        gc.collect()
        self._generate_epub()

        if self.generate_mobi:
            # Free all data before MOBI generation - it only needs the files on disk
            self.entries.clear()
            self.dilemma_inflections = None
            gc.collect()
            self._generate_mobi()

        print("\nDictionary generation complete!")
        print(f"Files created in {self.output_dir}/")
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
