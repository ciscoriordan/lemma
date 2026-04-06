#
#  lib/dilemma_inflections.py
#  Loads Modern Greek inflection data from dilemma's lookup tables
#
#  Dilemma: https://github.com/fcsriordan/dilemma
#

import gc
import json
import os
import time


class DilemmaInflections:
    def __init__(self):
        self.lemma_to_forms = {}
        self._form_confidence = {}
        self._load_data()

    def available(self):
        return len(self.lemma_to_forms) > 0

    def get_inflections(self, lemma):
        return self.lemma_to_forms.get(lemma, [])

    def confidence_for(self, form):
        """Return the confidence tier (1-5) for a form, or 0 if unknown."""
        return self._form_confidence.get(form, 0)

    def free_inflection_table(self):
        """Free lemma_to_forms after enhancement phase. Keeps _form_confidence for ranking."""
        self.lemma_to_forms.clear()
        gc.collect()

    def _load_data(self):
        data_dir = self._find_data_dir()
        if not data_dir:
            return

        # Prefer scored version over flat version
        scored_path = os.path.join(data_dir, 'mg_lookup_scored.json')
        flat_path = os.path.join(data_dir, 'mg_lookup.json')

        if os.path.exists(scored_path):
            self._load_scored_data(scored_path)
        elif os.path.exists(flat_path):
            self._load_flat_data(flat_path)

    def _load_scored_data(self, path):
        """Load mg_lookup_scored.json with format {"form": {"lemma": "...", "confidence": N}}."""
        print("Loading dilemma MG lookup data (scored)...")
        start = time.time()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        elapsed = time.time() - start
        print(f"Parsed {len(data)} form-to-lemma entries in {elapsed:.1f}s")

        # Invert: form->{"lemma":..., "confidence":...} becomes lemma->[(form, confidence), ...]
        scored_index = {}
        for form, info in data.items():
            if not isinstance(info, dict):
                continue
            lemma = info.get('lemma')
            confidence = info.get('confidence', 0)
            if not lemma or form == lemma:
                continue
            if ' ' in form:
                continue
            scored_index.setdefault(lemma, []).append((form, confidence))
            self._form_confidence[form] = confidence

        # Free the raw JSON - this is the biggest single allocation (~2 GB)
        del data
        gc.collect()

        # Sort each lemma's forms by descending confidence, store form strings
        for lemma, form_list in scored_index.items():
            form_list.sort(key=lambda x: -x[1])
            self.lemma_to_forms[lemma] = [form for form, _conf in form_list]

        del scored_index
        gc.collect()

        print(f"Built inflection table for {len(self.lemma_to_forms)} lemmas")

    def _load_flat_data(self, path):
        """Load mg_lookup.json with flat {form: lemma} format."""
        print("Loading dilemma MG lookup data...")
        start = time.time()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        elapsed = time.time() - start
        print(f"Parsed {len(data)} form-to-lemma entries in {elapsed:.1f}s")

        # Invert: form->lemma becomes lemma->forms
        for form, lemma in data.items():
            if form == lemma:
                continue
            if ' ' in form:
                continue
            self.lemma_to_forms.setdefault(lemma, []).append(form)

        del data
        gc.collect()

        print(f"Built inflection table for {len(self.lemma_to_forms)} lemmas")

    def _find_data_dir(self):
        dir_path = os.environ.get('DILEMMA_DATA_DIR', '')

        if not dir_path:
            env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == 'DILEMMA_DATA_DIR':
                                dir_path = value.strip()

        if not dir_path:
            return None
        if not os.path.isdir(dir_path):
            return None
        return dir_path
