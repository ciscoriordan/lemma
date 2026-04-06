#
#  lib/frequency_ranker.py
#  Ranks inflected forms by corpus frequency
#
#  Frequency data from FrequencyWords (OpenSubtitles 2018):
#  https://github.com/hermitdave/FrequencyWords
#

import os
import time


class FrequencyRanker:
    def __init__(self):
        self.frequencies = {}
        self._load_frequencies()

    def available(self):
        return len(self.frequencies) > 0

    def rank(self, forms):
        """Sort forms by descending frequency. Unattested forms sort to the end."""
        return sorted(forms, key=lambda form: -self.frequency(form))

    def frequency(self, word):
        return self.frequencies.get(word) or self.frequencies.get(word.lower(), 0)

    def _load_frequencies(self):
        freq_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'el_full.txt')
        if not os.path.exists(freq_file):
            return

        start = time.time()
        with open(freq_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(' ', 1)
                if len(parts) != 2:
                    continue
                word, count = parts
                try:
                    self.frequencies[word] = int(count)
                except ValueError:
                    continue

        elapsed = time.time() - start
        print(f"Loaded {len(self.frequencies)} frequency entries in {elapsed:.1f}s")
