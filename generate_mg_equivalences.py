#!/usr/bin/env python3
"""
Generate Modern Greek lemma equivalences from dilemma + Wiktionary data.

Finds cases where Wiktionary and dilemma disagree on canonical lemma forms,
groups equivalent lemmas, and picks the best canonical form using corpus
frequency as a tiebreaker.

Output: data/mg_lemma_equivalences.json

Usage:
    python3 generate_mg_equivalences.py
"""

import glob
import json
import os
import re
import sys
import time


def find_dilemma_data_dir():
    """Find dilemma data directory from env var or .env file."""
    dir_path = os.environ.get('DILEMMA_DATA_DIR', '')
    if not dir_path:
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
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
    if not dir_path or not os.path.isdir(dir_path):
        return None
    return dir_path


def load_frequency_data():
    """Load word frequencies from el_full.txt."""
    freq_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'el_full.txt')
    frequencies = {}
    if not os.path.exists(freq_file):
        print(f"Warning: frequency file not found at {freq_file}")
        return frequencies

    start = time.time()
    with open(freq_file, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(' ', 1)
            if len(parts) != 2:
                continue
            word, count = parts
            try:
                frequencies[word] = int(count)
            except ValueError:
                continue
    elapsed = time.time() - start
    print(f"Loaded {len(frequencies)} frequency entries in {elapsed:.1f}s")
    return frequencies


# Pattern matching "another form of X" in Greek Wiktionary glosses.
# This distinguishes genuine variant/alternative forms from paradigm inflections.
_VARIANT_GLOSS_RE = re.compile(
    r'(άλλη μορφή|εναλλακτικός τύπος|εναλλακτική μορφή|παραλλαγή|variant|alternative)',
    re.IGNORECASE
)


def load_wikt_data():
    """Load Wiktionary headwords and form_of relationships from the latest JSONL.

    Returns:
        headwords: set of all words with definitions (including form-of entries)
        true_headwords: set of words with non-form-of definitions (true lemmas)
        form_of_pairs: list of (form_word, target_lemma, pos) from Wikt form_of data
        variant_pairs: set of (form_word, target) where gloss says "variant form"
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(script_dir, 'greek_data_el_*.jsonl')))
    if not files:
        print("Error: no greek_data_el_*.jsonl file found")
        sys.exit(1)

    latest = files[-1]
    print(f"Loading Wiktionary data from {os.path.basename(latest)}...")
    start = time.time()

    headwords = set()
    true_headwords = set()
    form_of_pairs = []  # (form_word, target, pos)
    variant_pairs = set()  # (form_word, target) where gloss says "variant form"
    line_count = 0
    with open(latest, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line_count += 1
            try:
                entry = json.loads(line.strip())
            except (json.JSONDecodeError, Exception):
                continue

            if (entry.get('lang_code') != 'el'
                    and entry.get('lang') not in ('Greek', 'Ελληνικά')):
                continue

            word = entry.get('word')
            if not word or ' ' in word:
                continue

            senses = entry.get('senses', [])
            if not senses:
                continue

            has_gloss = any(s.get('glosses') for s in senses)
            if not has_gloss:
                continue

            headwords.add(word)
            pos = entry.get('pos', '')

            # Check if ALL senses are form_of
            all_form_of = all(
                isinstance(s.get('form_of'), list) and s['form_of']
                for s in senses
            )

            if not all_form_of:
                true_headwords.add(word)

            # Collect form_of relationships (even from mixed entries)
            for sense in senses:
                fof_list = sense.get('form_of')
                if isinstance(fof_list, list):
                    glosses = sense.get('glosses', [])
                    gloss = glosses[0] if glosses else ''
                    is_variant = bool(_VARIANT_GLOSS_RE.search(gloss))
                    for i, fof in enumerate(fof_list):
                        if isinstance(fof, dict) and fof.get('word'):
                            target = fof['word']
                            if target != word and ' ' not in target:
                                form_of_pairs.append((word, target, pos))
                                # For variant glosses, only pair with the first
                                # form_of target (the one the variant refers to).
                                # Later targets are paradigm references.
                                if is_variant and i == 0:
                                    variant_pairs.add((word, target))

    elapsed = time.time() - start
    print(f"Found {len(headwords)} headwords ({len(true_headwords)} true lemmas),"
          f" {len(form_of_pairs)} form_of pairs ({len(variant_pairs)} variant),"
          f" from {line_count} lines in {elapsed:.1f}s")
    return headwords, true_headwords, form_of_pairs, variant_pairs


def load_dilemma_form_to_lemma(data_dir):
    """Load mg_lookup_scored.json, return form->lemma dict (lemma only)."""
    scored_path = os.path.join(data_dir, 'mg_lookup_scored.json')
    if not os.path.exists(scored_path):
        print(f"Error: {scored_path} not found")
        sys.exit(1)

    print(f"Loading dilemma lookup data...")
    start = time.time()
    with open(scored_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    elapsed = time.time() - start
    print(f"Loaded {len(raw)} entries in {elapsed:.1f}s")

    # Extract form -> lemma mapping
    form_to_lemma = {}
    for form, info in raw.items():
        if isinstance(info, dict) and info.get('lemma'):
            form_to_lemma[form] = info['lemma']

    # Also build lemma -> forms for counting recovered inflections
    lemma_to_forms = {}
    for form, lemma in form_to_lemma.items():
        if form != lemma and ' ' not in form:
            lemma_to_forms.setdefault(lemma, []).append(form)

    del raw

    dilemma_lemmas = set(form_to_lemma.values())
    print(f"Unique dilemma lemmas: {len(dilemma_lemmas)}")
    return form_to_lemma, lemma_to_forms, dilemma_lemmas


def find_equivalences(headwords, true_headwords, form_of_pairs,
                       variant_pairs, form_to_lemma, dilemma_lemmas):
    """Find equivalence pairs between variant lemma forms.

    Three approaches combined:

    1. Variant form cross-reference: Wiktionary explicitly says W is a
       "variant form" (άλλη μορφή) of T, AND dilemma maps W to T.
       Both sources agree W is an alternative citation form of T.
       This catches πάω->πηγαίνω.

    2. Wiktionary form_of between dilemma lemmas (verbs/adj only):
       Wikt says W is a form_of T, where both W and T are dilemma lemmas.
       This catches τρώγω->τρώω where both are separate dilemma lemmas.
       Limited to verbs/adjectives to avoid article/pronoun paradigm merges.

    3. Variant form without dilemma confirmation: Wiktionary explicitly says
       W is a "variant form" of T, both are Wikt headwords, and T is a
       dilemma lemma. Does not require dilemma to agree (catches cases
       where dilemma doesn't know about W at all).
    """
    pairs = set()

    # Approach 1: Variant form cross-reference (Wikt variant + dilemma agree)
    variant_cross_ref = 0
    for form_word, target in variant_pairs:
        dilemma_lemma = form_to_lemma.get(form_word)
        if not dilemma_lemma:
            continue
        # Both sources must agree on the target
        if dilemma_lemma != target:
            continue
        if target not in headwords:
            continue
        pairs.add((form_word, target))
        variant_cross_ref += 1

    # Approach 2: Wiktionary form_of between dilemma lemmas (verb/adj only)
    EQUIV_POS = {'verb', 'adj'}
    wikt_based = 0
    for form_word, target, pos in form_of_pairs:
        if pos not in EQUIV_POS:
            continue
        if form_word not in headwords or target not in headwords:
            continue
        # Both must be dilemma lemmas (map to themselves)
        form_is_dilemma_lemma = (form_to_lemma.get(form_word) == form_word)
        target_is_dilemma_lemma = (form_to_lemma.get(target) == target)
        if form_is_dilemma_lemma and target_is_dilemma_lemma:
            if (form_word, target) not in pairs:
                pairs.add((form_word, target))
                wikt_based += 1

    # Approach 3: Variant form without dilemma confirmation
    # Wikt says W is a variant of T, T is a dilemma lemma and Wikt headword.
    # W may not be in dilemma at all, or dilemma may map it differently.
    variant_only = 0
    for form_word, target in variant_pairs:
        if (form_word, target) in pairs:
            continue
        if form_word not in headwords or target not in headwords:
            continue
        # Target must be a dilemma lemma (established headword)
        if target not in dilemma_lemmas:
            continue
        pairs.add((form_word, target))
        variant_only += 1

    print(f"Found {len(pairs)} equivalence pairs "
          f"({variant_cross_ref} variant+dilemma, {wikt_based} wikt-form_of,"
          f" {variant_only} variant-only)")
    return list(pairs)


def build_equivalence_groups(pairs):
    """Build transitive equivalence groups using union-find."""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    # Collect groups
    groups = {}
    all_words = set()
    for a, b in pairs:
        all_words.add(a)
        all_words.add(b)
    for w in all_words:
        root = find(w)
        groups.setdefault(root, set()).add(w)

    # Convert to sorted lists, cap group size to avoid runaway merges
    MAX_GROUP_SIZE = 10
    group_list = []
    oversized = 0
    for members in groups.values():
        if len(members) <= MAX_GROUP_SIZE:
            group_list.append(sorted(members))
        else:
            oversized += 1
    if oversized:
        print(f"  Dropped {oversized} oversized groups (>{MAX_GROUP_SIZE} members)")
    group_list.sort(key=lambda g: g[0])
    return group_list


def pick_canonical(group, frequencies, true_headwords, dilemma_lemmas,
                    lemma_to_forms):
    """Pick the canonical form from an equivalence group.

    Priority (highest first):
    1. Is a true Wikt headword (independent definitions)
    2. Is a dilemma lemma (maps to itself in dilemma)
    3. Has more inflection forms in dilemma (bigger paradigm = more likely the real lemma)
    4. Higher corpus frequency (tiebreaker)
    5. Alphabetically first (final tiebreaker)
    """
    def sort_key(word):
        is_true_hw = 1 if word in true_headwords else 0
        is_dilemma_lemma = 1 if word in dilemma_lemmas else 0
        n_forms = len(lemma_to_forms.get(word, []))
        freq = frequencies.get(word, 0) or frequencies.get(word.lower(), 0)
        # Sort descending on all criteria, ascending on word (alphabetical tiebreak)
        return (-is_true_hw, -is_dilemma_lemma, -n_forms, -freq, word)

    ranked = sorted(group, key=sort_key)
    return ranked[0]


def count_recovered_inflections(equivalences, lemma_to_forms):
    """Count how many inflections would be recovered through equivalence mapping."""
    recovered = 0
    for variant, canonical in equivalences.items():
        # Forms that the variant brings from its dilemma entry
        variant_forms = set(lemma_to_forms.get(variant, []))
        canonical_forms = set(lemma_to_forms.get(canonical, []))
        # New forms the canonical gains
        new_forms = variant_forms - canonical_forms
        recovered += len(new_forms)
    return recovered


def main():
    print("=" * 60)
    print("MG Lemma Equivalence Generator")
    print("=" * 60)

    # Step 1: Find dilemma data
    data_dir = find_dilemma_data_dir()
    if not data_dir:
        print("Error: DILEMMA_DATA_DIR not set or not found")
        print("Set it in .env or as an environment variable")
        sys.exit(1)
    print(f"Dilemma data dir: {data_dir}")
    print()

    # Step 2: Load data
    frequencies = load_frequency_data()
    print()
    headwords, true_headwords, form_of_pairs, variant_pairs = load_wikt_data()
    print()
    form_to_lemma, lemma_to_forms, dilemma_lemmas = load_dilemma_form_to_lemma(data_dir)
    print()

    # Step 3: Find equivalences
    pairs = find_equivalences(headwords, true_headwords, form_of_pairs,
                              variant_pairs, form_to_lemma, dilemma_lemmas)
    print()

    # Step 4: Build equivalence groups
    groups = build_equivalence_groups(pairs)
    print(f"Built {len(groups)} equivalence groups")

    # Show group size distribution
    size_dist = {}
    for g in groups:
        size = len(g)
        size_dist[size] = size_dist.get(size, 0) + 1
    for size in sorted(size_dist.keys()):
        print(f"  Groups of size {size}: {size_dist[size]}")
    print()

    # Step 5: Pick canonical for each group, build variant->canonical map
    equivalences = {}
    canonical_set = set()
    for group in groups:
        canonical = pick_canonical(group, frequencies, true_headwords,
                                      dilemma_lemmas, lemma_to_forms)
        canonical_set.add(canonical)
        for member in group:
            if member != canonical:
                equivalences[member] = canonical

    print(f"Generated {len(equivalences)} variant -> canonical mappings")
    print(f"Covering {len(canonical_set)} canonical forms")
    print()

    # Step 6: Count recovered inflections
    recovered = count_recovered_inflections(equivalences, lemma_to_forms)
    print(f"Estimated inflections recovered through equivalences: {recovered}")
    print()

    # Step 7: Show top pairs by frequency difference
    print("Top 30 equivalence pairs (by canonical frequency):")
    top_pairs = []
    for variant, canonical in equivalences.items():
        can_freq = frequencies.get(canonical, 0) or frequencies.get(canonical.lower(), 0)
        var_freq = frequencies.get(variant, 0) or frequencies.get(variant.lower(), 0)
        top_pairs.append((canonical, variant, can_freq, var_freq))
    top_pairs.sort(key=lambda x: -x[2])

    for canonical, variant, can_freq, var_freq in top_pairs[:30]:
        var_forms = len(lemma_to_forms.get(variant, []))
        can_forms = len(lemma_to_forms.get(canonical, []))
        print(f"  {variant} -> {canonical}"
              f"  (freq: {var_freq:,} vs {can_freq:,},"
              f"  forms: {var_forms} vs {can_forms})")
    print()

    # Step 8: Write output
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'mg_lemma_equivalences.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(equivalences, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Wrote {len(equivalences)} equivalences to {output_path}")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Wikt headwords:        {len(headwords):,} ({len(true_headwords):,} true lemmas)")
    print(f"  Dilemma lemmas:        {len(dilemma_lemmas):,}")
    print(f"  Equivalence groups:    {len(groups):,}")
    print(f"  Variant -> canonical:  {len(equivalences):,}")
    print(f"  Inflections recovered: {recovered:,}")


if __name__ == '__main__':
    main()
