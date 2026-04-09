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
        self._form_to_lemma = {}
        self._equivalences = {}  # variant -> canonical
        self._reverse_equivalences = {}  # canonical -> [variants]
        self._ranked_forms = {}  # lemma -> [forms] pre-ranked by corpus frequency
        self._polytonic_ranked = {}  # monotonic -> [polytonic variants] ranked by frequency
        self._load_ranked_forms()
        self._load_polytonic_ranked()
        self._load_data()
        self._load_equivalences()

    def available(self):
        return len(self.lemma_to_forms) > 0

    def has_ranked_forms(self):
        """Return True if pre-ranked forms from mg_ranked_forms.json are loaded."""
        return len(self._ranked_forms) > 0

    def get_ranked_forms(self, lemma):
        """Return pre-ranked forms for a lemma if available, or None.

        Checks the lemma directly, then equivalent lemmas. Returns the
        pre-ranked list (already in corpus frequency order, case-deduplicated)
        or None if no ranked forms are available for this lemma.
        """
        if not self._ranked_forms:
            return None

        # Direct match
        if lemma in self._ranked_forms:
            return self._ranked_forms[lemma]

        # Check equivalent lemmas
        equiv_lemmas = self._get_equivalent_lemmas(lemma)
        for eq_lemma in equiv_lemmas:
            if eq_lemma != lemma and eq_lemma in self._ranked_forms:
                return self._ranked_forms[eq_lemma]

        # Fallback: if lemma is a known form, check its dilemma lemma
        dilemma_lemma = self._form_to_lemma.get(lemma)
        if dilemma_lemma and dilemma_lemma in self._ranked_forms:
            return self._ranked_forms[dilemma_lemma]

        return None

    def get_inflections(self, lemma):
        """Return inflections for a lemma, including equivalent lemma forms."""
        # Direct match
        forms = list(self.lemma_to_forms.get(lemma, []))

        # Collect forms from equivalent lemmas
        equiv_lemmas = self._get_equivalent_lemmas(lemma)
        for eq_lemma in equiv_lemmas:
            if eq_lemma != lemma:
                eq_forms = self.lemma_to_forms.get(eq_lemma, [])
                forms.extend(eq_forms)
                if eq_lemma not in forms:
                    forms.append(eq_lemma)

        # Fallback: if still empty and lemma is a known form, use its dilemma lemma's forms
        if not forms:
            dilemma_lemma = self._form_to_lemma.get(lemma)
            if dilemma_lemma:
                forms = list(self.lemma_to_forms.get(dilemma_lemma, []))

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for f in forms:
            if f not in seen:
                seen.add(f)
                deduped.append(f)
        return deduped

    def get_all_lemmas(self, word):
        """Return all compatible headwords for a given form.

        Given a form, finds its dilemma lemma, finds all equivalents
        of that lemma, and returns all of them.
        """
        lemma = self._form_to_lemma.get(word)
        if not lemma:
            return []
        return self._get_equivalent_lemmas(lemma)

    def _get_equivalent_lemmas(self, lemma):
        """Return all equivalent lemma forms for a given lemma."""
        canonical = self._equivalences.get(lemma, lemma)
        result = [canonical]
        variants = self._reverse_equivalences.get(canonical, [])
        for v in variants:
            if v != canonical:
                result.append(v)
        if lemma not in result:
            result.append(lemma)
        return result

    def confidence_for(self, form):
        """Return the confidence tier (1-5) for a form, or 0 if unknown."""
        return self._form_confidence.get(form, 0)

    def free_inflection_table(self):
        """Free lemma_to_forms and _form_to_lemma after enhancement phase.

        Keeps _ranked_forms for html_generator and _form_confidence as fallback.
        """
        self.lemma_to_forms.clear()
        self._form_to_lemma.clear()
        gc.collect()

    def _load_ranked_forms(self):
        """Load pre-ranked, case-deduplicated forms from mg_ranked_forms.json.

        Tries in order:
        1. lemma project's own data/ directory
        2. DILEMMA_DATA_DIR env var or .env file
        3. HuggingFace Hub (ciscoriordan/dilemma-data)
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 1. Check lemma's own data/ directory
        local_path = os.path.join(project_root, 'data', 'mg_ranked_forms.json')
        if os.path.exists(local_path):
            self._read_ranked_forms(local_path)
            return

        # 2. Check DILEMMA_DATA_DIR
        data_dir = self._find_data_dir()
        if data_dir:
            ranked_path = os.path.join(data_dir, 'mg_ranked_forms.json')
            if os.path.exists(ranked_path):
                self._read_ranked_forms(ranked_path)
                return

        # 3. Try HuggingFace Hub
        try:
            from huggingface_hub import hf_hub_download
            cached_path = hf_hub_download(
                repo_id='ciscoriordan/dilemma-data',
                filename='mg_ranked_forms.json',
                repo_type='dataset',
            )
            self._read_ranked_forms(cached_path)
            return
        except Exception:
            pass

        print("mg_ranked_forms.json not found, will fall back to inverted lookup ranking")

    def _read_ranked_forms(self, path):
        """Read mg_ranked_forms.json into self._ranked_forms."""
        print(f"Loading pre-ranked forms from {path}...")
        start = time.time()
        with open(path, 'r', encoding='utf-8') as f:
            self._ranked_forms = json.load(f)
        elapsed = time.time() - start
        print(f"Loaded pre-ranked forms for {len(self._ranked_forms)} lemmas in {elapsed:.1f}s")

    def has_polytonic_ranked(self):
        """Return True if corpus-ranked polytonic variants are loaded."""
        return len(self._polytonic_ranked) > 0

    def get_polytonic_variants(self, form):
        """Return corpus-ranked polytonic variants for a monotonic form, or empty list."""
        return self._polytonic_ranked.get(form, [])

    def _load_polytonic_ranked(self):
        """Load corpus-ranked polytonic variants from mg_polytonic_ranked.json.

        Tries in order:
        1. lemma project's own data/ directory
        2. DILEMMA_DATA_DIR env var or .env file
        3. HuggingFace Hub (ciscoriordan/dilemma-data)
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 1. Check lemma's own data/ directory
        local_path = os.path.join(project_root, 'data', 'mg_polytonic_ranked.json')
        if os.path.exists(local_path):
            self._read_polytonic_ranked(local_path)
            return

        # 2. Check DILEMMA_DATA_DIR
        data_dir = self._find_data_dir()
        if data_dir:
            ranked_path = os.path.join(data_dir, 'mg_polytonic_ranked.json')
            if os.path.exists(ranked_path):
                self._read_polytonic_ranked(ranked_path)
                return

        # 3. Try HuggingFace Hub
        try:
            from huggingface_hub import hf_hub_download
            cached_path = hf_hub_download(
                repo_id='ciscoriordan/dilemma-data',
                filename='mg_polytonic_ranked.json',
                repo_type='dataset',
            )
            self._read_polytonic_ranked(cached_path)
            return
        except Exception:
            pass

        print("mg_polytonic_ranked.json not found, polytonic will use blind generation fallback")

    def _read_polytonic_ranked(self, path):
        """Read mg_polytonic_ranked.json into self._polytonic_ranked."""
        print(f"Loading polytonic ranked variants from {path}...")
        start = time.time()
        with open(path, 'r', encoding='utf-8') as f:
            self._polytonic_ranked = json.load(f)
        elapsed = time.time() - start
        print(f"Loaded polytonic variants for {len(self._polytonic_ranked)} monotonic forms in {elapsed:.1f}s")

    def _load_equivalences(self):
        """Load MG lemma equivalences from data/mg_lemma_equivalences.json."""
        equiv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'mg_lemma_equivalences.json'
        )
        if not os.path.exists(equiv_path):
            return

        start = time.time()
        with open(equiv_path, 'r', encoding='utf-8') as f:
            self._equivalences = json.load(f)
        elapsed = time.time() - start

        for variant, canonical in self._equivalences.items():
            self._reverse_equivalences.setdefault(canonical, []).append(variant)

        print(f"Loaded {len(self._equivalences)} lemma equivalences in {elapsed:.1f}s")

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
            if not lemma:
                continue
            self._form_to_lemma[form] = lemma
            if form == lemma:
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
            self._form_to_lemma[form] = lemma
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
