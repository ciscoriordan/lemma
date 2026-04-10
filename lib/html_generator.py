#
#  lib/html_generator.py
#  Generates HTML files for the dictionary
#
#  Created by Francisco Riordan on 4/22/25.
#

import html
import os
import re
import shutil
import time
from lib.frequency_ranker import FrequencyRanker


MAX_INFLECTIONS = 255
MAX_POLYTONIC = 255

ACCENT_FROM = 'άέήίόύώΐΰϊϋΆΈΉΊΌΎΏ'
ACCENT_TO   = 'αεηιουωιυιυαεηιουω'
_ACCENT_TABLE = str.maketrans(ACCENT_FROM, ACCENT_TO)

POS_MAP = {
    "noun": "ουσ.",
    "verb": "ρ.",
    "participle": "μτχ.",
    "adj": "επίθ.",
    "adjective": "επίθ.",
    "adv": "επίρρ.",
    "adverb": "επίρρ.",
    "num": "αριθμ.",
    "numeral": "αριθμ.",
    "name": "κύρ.όν.",
    "proper noun": "κύρ.όν.",
    "article": "άρθρ.",
}

# Tags to strip from definition qualifiers (gender, participle, etc.)
# These are either shown in the head line or as POS section headers
_STRIP_TAGS = {'masculine', 'feminine', 'neuter', 'participle', 'singular', 'plural'}

_GENDER_EXPAND = {'m': 'masculine', 'f': 'feminine', 'n': 'neuter'}

# Polytonic breathing mark tables: monotonic vowel -> (smooth, rough) polytonic form
_BREATHING = {
    'α': ('ἀ', 'ἁ'), 'ά': ('ἄ', 'ἅ'),
    'ε': ('ἐ', 'ἑ'), 'έ': ('ἔ', 'ἕ'),
    'η': ('ἠ', 'ἡ'), 'ή': ('ἤ', 'ἥ'),
    'ι': ('ἰ', 'ἱ'), 'ί': ('ἴ', 'ἵ'),
    'ο': ('ὀ', 'ὁ'), 'ό': ('ὄ', 'ὅ'),
    'υ': ('ὐ', 'ὑ'), 'ύ': ('ὔ', 'ὕ'),
    'ω': ('ὠ', 'ὡ'), 'ώ': ('ὤ', 'ὥ'),
    'Α': ('Ἀ', 'Ἁ'), 'Ά': ('Ἄ', 'Ἅ'),
    'Ε': ('Ἐ', 'Ἑ'), 'Έ': ('Ἔ', 'Ἕ'),
    'Η': ('Ἠ', 'Ἡ'), 'Ή': ('Ἤ', 'Ἥ'),
    'Ι': ('Ἰ', 'Ἱ'), 'Ί': ('Ἴ', 'Ἵ'),
    'Ο': ('Ὀ', 'Ὁ'), 'Ό': ('Ὄ', 'Ὅ'),
    'Υ': ('Ὑ', 'Ὑ'), 'Ύ': ('Ὕ', 'Ὕ'),  # Υ initial always rough
    'Ω': ('Ὠ', 'Ὡ'), 'Ώ': ('Ὤ', 'Ὥ'),
}
_VOWELS_SET = set(_BREATHING.keys())
# Diphthongs where breathing goes on the second vowel
_DIPHTHONG_FIRSTS = set('αεοΑΕΟ')
_DIPHTHONG_SECONDS = set('ιυίύΙΥΊΎ')

# Monotonic acute → polytonic grave and circumflex equivalents.
# Grave appears on final-accented words before another word.
# Circumflex appears on long vowels (η, ω, and sometimes α, ι, υ).
_ACUTE_TO_GRAVE = {
    'ά': 'ὰ', 'έ': 'ὲ', 'ή': 'ὴ', 'ί': 'ὶ', 'ό': 'ὸ', 'ύ': 'ὺ', 'ώ': 'ὼ',
    'Ά': 'Ὰ', 'Έ': 'Ὲ', 'Ή': 'Ὴ', 'Ί': 'Ὶ', 'Ό': 'Ὸ', 'Ύ': 'Ὺ', 'Ώ': 'Ὼ',
}
_ACUTE_TO_CIRCUMFLEX = {
    'ά': 'ᾶ', 'ή': 'ῆ', 'ί': 'ῖ', 'ύ': 'ῦ', 'ώ': 'ῶ',
    # No circumflex for έ/ό (short vowels in Greek)
}
# Breathing + grave and breathing + circumflex combinations
_BREATHING_GRAVE = {
    'α': ('ἂ', 'ἃ'), 'ε': ('ἒ', 'ἓ'), 'η': ('ἢ', 'ἣ'), 'ι': ('ἲ', 'ἳ'),
    'ο': ('ὂ', 'ὃ'), 'υ': ('ὒ', 'ὓ'), 'ω': ('ὢ', 'ὣ'),
    'Α': ('Ἂ', 'Ἃ'), 'Ε': ('Ἒ', 'Ἓ'), 'Η': ('Ἢ', 'Ἣ'), 'Ι': ('Ἲ', 'Ἳ'),
    'Ο': ('Ὂ', 'Ὃ'), 'Υ': ('Ὓ', 'Ὓ'), 'Ω': ('Ὢ', 'Ὣ'),
}
_BREATHING_CIRCUMFLEX = {
    'α': ('ᾆ', 'ᾇ'), 'η': ('ᾖ', 'ᾗ'), 'ι': ('ἶ', 'ἷ'),
    'υ': ('ὖ', 'ὗ'), 'ω': ('ὦ', 'ὧ'),
    'Α': ('ᾎ', 'ᾏ'), 'Η': ('ᾞ', 'ᾟ'), 'Ι': ('Ἶ', 'Ἷ'),
    'Ω': ('Ὦ', 'Ὧ'),
}
_ACUTE_VOWELS = set(_ACUTE_TO_GRAVE.keys())


class HtmlGenerator:
    _shared_frequency_ranker = None

    def __init__(self, generator):
        self.generator = generator
        self.entries = generator.entries
        self.output_dir = generator.output_dir
        self._use_ranked_forms = (
            generator.dilemma_inflections is not None
            and generator.dilemma_inflections.has_ranked_forms()
        )
        if HtmlGenerator._shared_frequency_ranker is None:
            HtmlGenerator._shared_frequency_ranker = FrequencyRanker()
        self.frequency_ranker = HtmlGenerator._shared_frequency_ranker
        if self._use_ranked_forms:
            print("Using pre-ranked forms from dilemma for inflection ordering")
        self._opf_filename = None

    @property
    def opf_filename(self):
        return self._opf_filename

    @property
    def _is_full_build(self):
        """Full builds include extra info like head templates and examples."""
        return self.generator.enable_links or self.generator.enable_etymology

    # Matches Greek words (with accents/diacritics) that might be headwords
    _GREEK_WORD_RE = re.compile(r'([\u0370-\u03FF\u1F00-\u1FFF]+)')

    @staticmethod
    def _format_example_text(ex):
        """Format example text with bold offsets if available."""
        text = ex.get('text', '')
        offsets = ex.get('bold_text_offsets')
        if not offsets:
            return _escape_html(text)
        # Build string with <b> tags inserted at offsets (process right-to-left)
        for start, end in sorted(offsets, reverse=True):
            text = text[:start] + '\x01' + text[start:end] + '\x02' + text[end:]
        escaped = _escape_html(text)
        return escaped.replace('\x01', '<b>').replace('\x02', '</b>')

    @staticmethod
    def _sanitize_anchor_id(text):
        """Sanitize a string for use as an HTML id attribute.

        HTML id values must not contain spaces. Replace spaces with
        underscores so that href="#hw_X" and id="hw_X" always match.
        """
        return text.replace(' ', '_')

    def _linkify_definition(self, text):
        """Replace Greek words in definition text with anchor links if they are headwords."""
        if not self.generator.enable_links:
            return _escape_html(text)
        parts = self._GREEK_WORD_RE.split(text)
        result = []
        for part in parts:
            if self._GREEK_WORD_RE.fullmatch(part) and part in self.entries:
                escaped = _escape_html(part)
                anchor = self._sanitize_anchor_id(escaped)
                result.append(f'<a href="#hw_{anchor}">{escaped}</a>')
            else:
                result.append(_escape_html(part))
        return ''.join(result)

    def create_output_files(self):
        # Initialize with base output dir
        self._update_output_dir()

        # Clean up existing directory if it exists
        if os.path.isdir(self.output_dir):
            print(f"Removing existing directory: {self.output_dir}")
            shutil.rmtree(self.output_dir)

        os.makedirs(self.output_dir, exist_ok=True)

        self._create_content_html()
        self._create_cover()
        self._create_copyright_html()
        self._create_usage_html()
        self._create_opf_file()
        self._create_toc_ncx()

    def _update_output_dir(self):
        if not self.output_dir:
            print("Error: Output directory is nil or empty!")
            self.output_dir = f"lemma_greek_{time.strftime('%Y%m%d')}"
            print(f"Using fallback directory: {self.output_dir}")

        if self.generator.limit_percent is not None:
            self.output_dir = f"{self.output_dir}_{self.generator.limit_percent}pct"

        self.generator.update_output_dir(self.output_dir)

    def _rank_inflections(self, forms):
        """Three-tier ranking: frequency > confidence >= 3 > the rest."""
        dilemma = self.generator.dilemma_inflections
        freq = self.frequency_ranker

        tier1 = []  # attested in corpus, ranked by frequency
        tier2 = []  # not in corpus, but has Wiktionary page (confidence >= 3)
        tier3 = []  # table-only or unknown

        for form in forms:
            f = freq.frequency(form)
            c = dilemma.confidence_for(form) if dilemma else 0
            if f > 0:
                tier1.append((form, f))
            elif c >= 3:
                tier2.append((form, c))
            else:
                tier3.append((form, c))

        tier1.sort(key=lambda x: -x[1])
        tier2.sort(key=lambda x: -x[1])
        tier3.sort(key=lambda x: -x[1])

        return [form for form, _ in tier1 + tier2 + tier3]

    def _select_ranked_inflections(self, headword, entry_inflections, max_count):
        """Select inflections using pre-ranked forms from dilemma.

        The entry_inflections list comes from the entry processor, which has
        already decided what inflections this entry should have (Dilemma as
        primary, Wiktionary as fallback, none for form-of entries). This
        method re-ranks them using Dilemma's corpus frequency order.
        """
        if not entry_inflections:
            return []

        dilemma = self.generator.dilemma_inflections
        ranked = dilemma.get_ranked_forms(headword) if dilemma else None

        if not ranked:
            return entry_inflections[:max_count]

        ranked_lower = set(f.lower() for f in ranked)

        # Entry inflections not in ranked list go first
        result = []
        result_lower = set()
        for f in entry_inflections:
            low = f.lower()
            if low not in ranked_lower and low not in result_lower:
                result.append(f)
                result_lower.add(low)

        # Then ranked forms in corpus frequency order
        for form in ranked:
            low = form.lower()
            if low not in result_lower:
                result.append(form)
                result_lower.add(low)
            if len(result) >= max_count:
                break

        return result[:max_count]

    def _add_case_variants_after_cap(self, forms):
        """Add Capitalized and UPPER case variants of each form.

        These extra variants don't count toward the inflection cap since
        Kindle needs them for lookup matching but they're just case copies
        of forms already selected.
        """
        result = list(forms)
        seen = set(forms)
        for form in forms:
            capitalized = form[0].upper() + form[1:] if form else form
            if capitalized not in seen:
                result.append(capitalized)
                seen.add(capitalized)
            uppered = form.upper()
            if uppered not in seen:
                result.append(uppered)
                seen.add(uppered)
        return result

    def _normalize_for_sorting(self, word):
        normalized = word.lower().translate(_ACCENT_TABLE)
        # Remove non-Greek, non-Latin, non-digit characters
        return re.sub(r'[^\u0370-\u03FF\u1F00-\u1FFFA-Za-z0-9]', '', normalized)

    def _merge_form_of_into_parents(self):
        """Move pure form-of entries into their parent as iforms.

        A pure form-of entry is one where all sub-entries have form_of_targets.
        For single-parent cases, the word becomes an iform on the parent.
        For multi-parent cases, pick the most frequent parent.
        """
        dilemma = self.generator.dilemma_inflections
        freq = self.frequency_ranker

        merged_count = 0
        to_remove = []

        for word, entries in self.entries.items():
            if not all(e.get('form_of_targets') for e in entries):
                continue

            # Collect all unique targets that exist as headwords
            targets = []
            seen = set()
            for e in entries:
                for t in (e.get('form_of_targets') or []):
                    if t not in seen and t in self.entries:
                        targets.append(t)
                        seen.add(t)

            if not targets:
                continue

            # Pick the best parent by frequency
            if len(targets) == 1:
                best = targets[0]
            else:
                def parent_freq(t):
                    if freq:
                        return freq.frequency(t)
                    return 0
                best = max(targets, key=parent_freq)

            # Add this word as an inflection on the parent entry
            for pe in self.entries[best]:
                if pe.get('inflections') is None:
                    pe['inflections'] = []
                if word not in pe['inflections']:
                    pe['inflections'].append(word)

            to_remove.append(word)
            merged_count += 1

        for word in to_remove:
            del self.entries[word]

        print(f"  Merged {merged_count} form-of entries into parent headwords")

    def _build_iform_owners(self):
        """Assign each iform to exactly one headword based on frequency.

        When multiple headwords claim the same iform (e.g., both κλαίω and
        κλαίγω claim έκλαιγε), the Kindle shows whichever comes first in
        the file. We assign contested iforms to the highest-frequency
        headword so the best definition wins.
        """
        dilemma = self.generator.dilemma_inflections
        freq = self.frequency_ranker

        # Collect iform claims, tracking direct vs indirect (equivalence) sources
        direct_claims = {}   # iform -> set of headwords that directly own it
        all_claims = {}      # iform -> list of all headwords that claim it
        for word, entries in self.entries.items():
            for e in entries:
                for inf in (e.get('inflections') or []):
                    direct_claims.setdefault(inf, set()).add(word)
                    all_claims.setdefault(inf, [])
                    if word not in all_claims[inf]:
                        all_claims[inf].append(word)
            if self._use_ranked_forms and dilemma:
                for inf in (dilemma.get_ranked_forms(word) or []):
                    all_claims.setdefault(inf, [])
                    if word not in all_claims[inf]:
                        all_claims[inf].append(word)

        # Build equivalence lookup: alternate -> canonical
        equiv_canonical = {}
        if dilemma and dilemma._equivalences:
            equiv_canonical = dict(dilemma._equivalences)

        # For contested iforms between equivalent lemmas, canonical form wins.
        # For non-equivalent contested iforms, don't reassign (both keep it).
        self._iform_owner = {}  # iform -> winning headword
        contested = 0
        for iform, headwords in all_claims.items():
            unique = list(dict.fromkeys(headwords))
            if len(unique) <= 1:
                continue
            # Check if any pair is an equivalence pair
            winner = None
            for hw in unique:
                canonical = equiv_canonical.get(hw)
                if canonical and canonical in unique:
                    # hw is the alternate, canonical is the winner
                    winner = canonical
                    break
            if not winner:
                continue
            contested += 1
            for hw in unique:
                if hw != winner:
                    self._iform_owner[iform] = winner

        print(f"  Deduplicated {contested} contested iforms by frequency")

    def _create_content_html(self):
        print("Creating content.html...")

        # Merge pure form-of entries into their parents
        self._merge_form_of_into_parents()

        # Assign contested iforms to highest-frequency headword
        self._build_iform_owners()

        # Sort keys only to avoid copying all entry data
        sorted_keys = sorted(self.entries.keys(), key=self._normalize_for_sorting)
        total = len(sorted_keys)

        # Write HTML directly to file
        content_file = open(os.path.join(self.output_dir, 'content.html'), 'w', encoding='utf-8')

        # Write header
        content_file.write(self._html_header())

        # Process entries
        entry_count = 0

        for word in sorted_keys:
            self._write_entry(content_file, word, self.entries[word])
            entry_count += 1

            # Progress indicator
            if entry_count % 10000 == 0:
                print(f"  Processed {entry_count}/{total} entries...")

        # Write footer
        content_file.write(self._html_footer())
        content_file.close()

        print(f"  Created content.html with {entry_count} entries")

    def _html_header(self):
        return """\
<html xmlns:math="http://exslt.org/math" xmlns:svg="http://www.w3.org/2000/svg"
      xmlns:tl="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:saxon="http://saxon.sf.net/" xmlns:xs="http://www.w3.org/2001/XMLSchema"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:cx="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:mbp="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:mmc="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:idx="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <style>
      h5 { font-size: 1em; margin: 0; }
      p { margin: 0.2em 0; }
      b { font-weight: bold; }
      i { font-style: italic; }
      .pos { font-style: italic; }
      .def { margin-left: 20px; }
      .ex { margin-left: 20px; }
      .etym { margin-top: 0.3em; }
      hr { margin: 5px 0; border: none; border-top: 1px solid #ccc; }
    </style>
  </head>
  <body>
    <mbp:frameset>
"""

    def _html_footer(self):
        return """\
    </mbp:frameset>
  </body>
</html>
"""

    def _write_entry(self, io, word, entries):
        # Limit inflections to reduce complexity
        max_inflections = self.generator.max_inflections or MAX_INFLECTIONS

        # Combine all inflections from all entries for this word
        all_inflections = []
        seen = set()
        for e in entries:
            for inf in (e.get('inflections') or []):
                if inf not in seen:
                    seen.add(inf)
                    all_inflections.append(inf)

        # Filter out multi-word inflections (containing spaces)
        single_word_inflections = [inf for inf in all_inflections if ' ' not in inf]

        # Check if this is a proper noun
        is_proper_noun = any(
            e.get('pos') and ('proper' in e['pos'].lower() or 'name' in e['pos'].lower())
            for e in entries
        )

        if is_proper_noun:
            # For proper nouns, keep original order
            all_variations = single_word_inflections[:max_inflections]
        elif self._use_ranked_forms:
            all_variations = self._select_ranked_inflections(word, single_word_inflections, max_inflections)
        else:
            all_variations = self._rank_inflections(single_word_inflections)[:max_inflections]

        # Remove iforms owned by a higher-frequency headword
        all_variations = [
            inf for inf in all_variations
            if self._iform_owner.get(inf, word) == word
        ]

        # Add polytonic variants when explicitly enabled
        if self.generator.enable_polytonic:
            dilemma = self.generator.dilemma_inflections
            all_forms = [word] + all_variations
            polytonic_forms = []
            seen_poly = set(all_forms)

            if dilemma and dilemma.has_polytonic_ranked():
                # Use corpus-attested polytonic variants
                for form in all_forms:
                    for pv in dilemma.get_polytonic_variants(form):
                        if pv not in seen_poly:
                            seen_poly.add(pv)
                            polytonic_forms.append(pv)
            else:
                # Fallback: blind generation
                for form in all_forms:
                    for pv in _polytonic_variants(form):
                        if pv not in seen_poly:
                            seen_poly.add(pv)
                            polytonic_forms.append(pv)

            all_variations.extend(polytonic_forms[:MAX_POLYTONIC])

        escaped_word = _escape_html(word)
        if self.generator.enable_links:
            anchor_id = self._sanitize_anchor_id(escaped_word)
            io.write(f"""\
<idx:entry name="default" scriptable="yes" spell="yes" id="hw_{anchor_id}">
  <idx:short>
    <idx:orth value="{escaped_word}"><b>{escaped_word}</b>
""")
        else:
            io.write(f"""\
<idx:entry name="default" scriptable="yes" spell="yes">
  <idx:short>
    <idx:orth value="{escaped_word}"><b>{escaped_word}</b>
""")

        # Add inflections if any exist
        if all_variations:
            io.write("      <idx:infl>\n")
            for variation in all_variations:
                io.write(f'        <idx:iform value="{_escape_html(variation)}" exact="yes" />\n')
            io.write("      </idx:infl>\n")

        io.write("    </idx:orth>\n")
        io.write("  </idx:short>\n")


        # Simplify entries for Greek to reduce size
        if self.generator.source_lang == 'el':
            # Combine all definitions by POS, detecting participles
            pos_groups = {}
            pos_order = []
            for e in entries:
                pos_key = e.get('pos', 'unknown')
                if pos_key not in pos_groups:
                    pos_groups[pos_key] = []
                    pos_order.append(pos_key)
                pos_groups[pos_key].append(e)

            for idx, pos in enumerate(pos_order):
                pos_entries = pos_groups[pos]

                # Combine all definitions and examples for this POS
                all_definitions = []
                all_examples = []
                def_seen = set()
                for e in pos_entries:
                    entry_examples = e.get('examples') or []
                    for i, d in enumerate(e.get('definitions', [])):
                        if d not in def_seen:
                            def_seen.add(d)
                            all_definitions.append(d)
                            ex = entry_examples[i] if i < len(entry_examples) else None
                            all_examples.append(ex)

                # Detect if all definitions are participles, and use that as POS
                effective_pos = pos
                if pos == 'verb' and all_definitions:
                    if all(_def_has_tag(d, 'participle') for d in all_definitions):
                        effective_pos = 'participle'

                pos_display = self._format_pos(effective_pos)
                if self._is_full_build:
                    head_info = self._get_head_info_for_pos(pos_entries, word)
                    if head_info:
                        pos_display = f"{pos_display}, {head_info}"
                io.write(f"  <p><i>{_escape_html(pos_display)}</i></p>\n")

                # Limit definitions, stripping redundant qualifier tags
                for def_idx, definition in enumerate(all_definitions[:5]):
                    clean_def = _strip_def_qualifiers(definition)
                    if len(all_definitions) > 1:
                        io.write(f"  <p class='def'>{def_idx + 1}. {self._linkify_definition(clean_def)}</p>\n")
                    else:
                        io.write(f"  <p class='def'>{self._linkify_definition(clean_def)}</p>\n")

                    # Show example for full builds
                    if self._is_full_build and def_idx < len(all_examples):
                        ex = all_examples[def_idx]
                        if ex and ex.get('text'):
                            ex_text = self._format_example_text(ex)
                            ex_trans = _escape_html(ex.get('translation', ''))
                            if ex_trans:
                                io.write(f"  <p class='ex'>{ex_text} - {ex_trans}</p>\n")
                            else:
                                io.write(f"  <p class='ex'>{ex_text}</p>\n")

                # Add separator between POS groups
                if len(pos_order) > 1 and idx < len(pos_order) - 1:
                    io.write("  <br/><br/>\n")
        else:
            # Full format for English Wiktionary source
            for idx, entry in enumerate(entries):
                pos = entry.get('pos', 'unknown')
                defs = entry.get('definitions', [])
                entry_examples = entry.get('examples') or []

                # Detect participle: if all defs have participle tag, use that as POS
                effective_pos = pos
                if pos == 'verb' and defs:
                    if all(_def_has_tag(d, 'participle') for d in defs):
                        effective_pos = 'participle'

                pos_display = self._format_pos(effective_pos)
                if self._is_full_build:
                    head_info = self._get_head_info_for_pos([entry], word)
                    if head_info:
                        pos_display = f"{pos_display}, {head_info}"
                io.write(f"  <p><i>{_escape_html(pos_display)}</i></p>\n")

                if len(defs) > 1:
                    for def_idx, definition in enumerate(defs):
                        clean_def = _strip_def_qualifiers(definition)
                        io.write(f"  <p class='def'>{def_idx + 1}. {self._linkify_definition(clean_def)}</p>\n")
                        # Show example for full builds
                        if self._is_full_build and def_idx < len(entry_examples):
                            ex = entry_examples[def_idx]
                            if ex and ex.get('text'):
                                ex_text = self._format_example_text(ex)
                                ex_trans = _escape_html(ex.get('translation', ''))
                                if ex_trans:
                                    io.write(f"  <p class='ex'>{ex_text} - {ex_trans}</p>\n")
                                else:
                                    io.write(f"  <p class='ex'>{ex_text}</p>\n")
                else:
                    for def_idx, definition in enumerate(defs):
                        clean_def = _strip_def_qualifiers(definition)
                        io.write(f"  <p class='def'>{self._linkify_definition(clean_def)}</p>\n")
                        # Show example for full builds
                        if self._is_full_build and def_idx < len(entry_examples):
                            ex = entry_examples[def_idx]
                            if ex and ex.get('text'):
                                ex_text = self._format_example_text(ex)
                                ex_trans = _escape_html(ex.get('translation', ''))
                                if ex_trans:
                                    io.write(f"  <p class='ex'>{ex_text} - {ex_trans}</p>\n")
                                else:
                                    io.write(f"  <p class='ex'>{ex_text}</p>\n")

                etym = entry.get('etymology')
                if etym and etym.strip() and self.generator.enable_etymology:
                    etym = _strip_transliterations(etym)
                    etym = _clean_etymology(etym)
                    if etym:
                        io.write(f"  <br/>\n  <p class='etym'>Etymology: {_escape_html(etym)}</p>\n")

                if len(entries) > 1 and idx < len(entries) - 1:
                    io.write("  <br/><br/>\n")

        io.write("""\
</idx:entry>
<hr/>
""")

    def _get_head_info_for_pos(self, pos_entries, word):
        """Extract gender and variant info from head_expansion for POS line."""
        for e in pos_entries:
            head_exp = e.get('head_expansion')
            if head_exp:
                stripped = _strip_head_expansion(head_exp, word)
                if stripped:
                    return _format_head_for_pos(stripped)
        return None

    def _format_pos(self, pos):
        pos_display = pos or "unknown"

        if self.generator.source_lang == 'el':
            mapped = POS_MAP.get(pos_display.lower())
            if mapped:
                return mapped

        return pos_display

    def _create_cover(self):
        # Copy cover image to output directory
        cover_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'images', 'cover.jpg')
        cover_dst = os.path.join(self.output_dir, 'cover.jpg')
        if os.path.exists(cover_src):
            import shutil
            shutil.copy2(cover_src, cover_dst)
        else:
            print(f"  Warning: cover image not found at {cover_src}")

        # Create cover HTML that displays the image
        content = """\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
    <style>
      body { margin: 0; padding: 0; text-align: center; }
      img { max-width: 100%; height: auto; }
    </style>
  </head>
  <body>
    <img src="cover.jpg" alt="Lemma Greek Dictionary" />
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'cover.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_copyright_html(self):
        from datetime import datetime
        year = datetime.now().year
        extraction_date = self.generator.extraction_date or 'Unknown'

        content = f"""\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
  </head>
  <body>
    <h2>Copyright</h2>
    <p>Copyright {year} Francisco Riordan. All rights reserved.</p>
    <p>Dictionary compiled by <a href="https://github.com/ciscoriordan/lemma">Lemma</a>.</p>
    <p>MOBI generated by <a href="https://github.com/ciscoriordan/kindling">Kindling</a> by Francisco Riordan.</p>
    <h2>Data Sources</h2>
    <p>Dictionary content derived from <a href="https://en.wiktionary.org/">Wiktionary</a>,
    available under the <a href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.
    Machine-readable data provided by <a href="https://kaikki.org/">Kaikki.org</a>.</p>
    <p>Inflection data from <a href="https://github.com/ciscoriordan/dilemma">Dilemma</a> Greek lemmatizer by Francisco Riordan.</p>
    <p>Word frequency data from <a href="https://github.com/hermitdave/FrequencyWords">FrequencyWords</a> (OpenSubtitles 2018 corpus, MIT License).</p>
    <h2>Build Info</h2>
    <p>Wiktionary data extracted: {extraction_date}</p>
    <p>Dictionary created: {self.generator.download_date}</p>
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'copyright.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_usage_html(self):
        if self.generator.source_lang == 'en':
            dict_type = 'Greek-English'
        else:
            dict_type = 'Greek-Greek (monolingual)'

        source_desc = 'English' if self.generator.source_lang == 'en' else 'Greek'

        content = f"""\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
  </head>
  <body>
    <h2>How to Use Lemma Greek{" Basic" if not self._is_full_build else ""} Dictionary</h2>
    <span>This is a {dict_type} dictionary with Modern Greek words from {source_desc} Wiktionary.</span>
    <br><h3>Features</h3>
    <ul>
      <li>Look up any Greek word while reading</li>
      <li>Inflected forms automatically redirect to their lemma</li>
      <li>Includes part of speech information</li>
    </ul>
    <br><h3>To Set as Default Greek Dictionary</h3>
    <ul>
      <li>Look up any Greek word in your book</li>
      <li>Tap the dictionary name in the popup</li>
      <li>Select "Lemma Greek{" Basic" if not self._is_full_build else ""} Dictionary"</li>
    </ul>
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'usage.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_opf_file(self):
        source_name = 'en-el' if self.generator.source_lang == 'en' else 'el-el'
        if not self._is_full_build:
            edition = " Basic"
            edition_tag = "Basic"
        else:
            edition = ""
            edition_tag = ""

        unique_id = f"LemmaGreek{edition_tag}{source_name.upper().replace('-', '')}"
        display_title = f"Lemma Greek{edition} Dictionary"

        date_str = self.generator.extraction_date or self.generator.download_date
        title_with_date = display_title
        out_lang = 'en' if self.generator.source_lang == 'en' else 'el'

        build_tag = self.generator._build_tag
        opf_filename = f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}{build_tag}.opf"

        content = f"""\
<?xml version="1.0"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId">
  <metadata>
    <dc:title>{title_with_date}</dc:title>
    <dc:creator opf:role="aut">Francisco Riordan</dc:creator>
    <dc:language>el</dc:language>
    <dc:publisher>Lemma</dc:publisher>
    <dc:rights>Creative Commons Attribution-ShareAlike 4.0 International</dc:rights>
    <dc:date>{self.generator.download_date}</dc:date>
    <dc:identifier id="BookId" opf:scheme="UUID">{unique_id}-{self.generator.download_date}</dc:identifier>
    <meta name="wiktionary-extraction-date" content="{self.generator.extraction_date or 'Unknown'}" />
    <meta name="dictionary-name" content="{display_title}" />
    <meta name="cover" content="cover-image" />
    <x-metadata>
      <DictionaryInLanguage>el</DictionaryInLanguage>
      <DictionaryOutLanguage>{out_lang}</DictionaryOutLanguage>
      <DefaultLookupIndex>default</DefaultLookupIndex>
    </x-metadata>
  </metadata>
  <manifest>
    <item id="ncx"
          href="toc.ncx"
          media-type="application/x-dtbncx+xml" />
    <item id="cover-image"
          href="cover.jpg"
          media-type="image/jpeg" />
    <item id="cover"
          href="cover.html"
          media-type="application/xhtml+xml" />
    <item id="usage"
          href="usage.html"
          media-type="application/xhtml+xml" />
    <item id="copyright"
          href="copyright.html"
          media-type="application/xhtml+xml" />
    <item id="content"
          href="content.html"
          media-type="application/xhtml+xml" />
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover" />
    <itemref idref="usage" />
    <itemref idref="copyright"/>
    <itemref idref="content"/>
  </spine>
  <guide>
    <reference type="cover" title="Cover" href="cover.html"/>
    <reference type="index" title="IndexName" href="content.html"/>
  </guide>
</package>
"""
        with open(os.path.join(self.output_dir, opf_filename), 'w', encoding='utf-8') as f:
            f.write(content)

        # Store the OPF filename for use by MobiGenerator
        self._opf_filename = opf_filename

    def _create_toc_ncx(self):
        source_name = 'en-el' if self.generator.source_lang == 'en' else 'el-el'
        if not self._is_full_build:
            edition = " Basic"
            edition_tag = "Basic"
        else:
            edition = ""
            edition_tag = ""
        unique_id = f"LemmaGreek{edition_tag}{source_name.upper().replace('-', '')}"
        display_title = f"Lemma Greek{edition} Dictionary"

        content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{unique_id}-{self.generator.download_date}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{display_title}</text>
  </docTitle>
  <navMap>
    <navPoint id="cover" playOrder="1">
      <navLabel><text>Cover</text></navLabel>
      <content src="cover.html"/>
    </navPoint>
    <navPoint id="usage" playOrder="2">
      <navLabel><text>Usage</text></navLabel>
      <content src="usage.html"/>
    </navPoint>
    <navPoint id="copyright" playOrder="3">
      <navLabel><text>Copyright</text></navLabel>
      <content src="copyright.html"/>
    </navPoint>
    <navPoint id="content" playOrder="4">
      <navLabel><text>Dictionary</text></navLabel>
      <content src="content.html"/>
    </navPoint>
  </navMap>
</ncx>
"""
        with open(os.path.join(self.output_dir, 'toc.ncx'), 'w', encoding='utf-8') as f:
            f.write(content)


def _escape_html(text):
    if not text:
        return ""
    return html.escape(str(text))


def _strip_head_expansion(head_exp, word):
    """Strip headword repetition and transliteration from head_expansion.

    Input:  "χτυπημένος • (chtypiménos) m (feminine χτυπημένη, neuter χτυπημένο)"
    Output: "m (feminine χτυπημένη, neuter χτυπημένο)"
    """
    text = head_exp
    # Remove "word • " prefix
    bullet_pos = text.find('•')
    if bullet_pos >= 0:
        text = text[bullet_pos + 1:].strip()
    elif text.startswith(word):
        text = text[len(word):].strip()
    # Remove transliteration "(latintext)" at the start
    text = re.sub(r'^\([A-Za-z\u00C0-\u024F\s]+\)\s*', '', text)
    return text.strip()


def _format_head_for_pos(stripped):
    """Format stripped head_expansion for combining with POS display.

    Input:  "f (plural θάλασσες)"
    Output: "feminine (plural θάλασσες)"

    Input:  "m (feminine χτυπημένη, neuter χτυπημένο)"
    Output: "masculine (feminine χτυπημένη, neuter χτυπημένο)"

    Returns None if the pattern is not recognized (e.g. unknown gender '?').
    """
    if not stripped:
        return None

    m = re.match(
        r'^([mfn](?:\s+or\s+[mfn])*)'  # gender code(s)
        r'(\s+(?:pl|sg))?'              # optional number
        r'(\s+\(.*\))?'                 # optional parenthetical
        r'\s*$',
        stripped
    )
    if not m:
        return None

    genders = m.group(1)
    number = (m.group(2) or '').strip()
    parens = (m.group(3) or '').strip()

    for abbrev, full in _GENDER_EXPAND.items():
        genders = re.sub(rf'\b{abbrev}\b', full, genders)

    parts = [genders]
    if number:
        parts.append('plural' if number == 'pl' else 'singular')
    result = ' '.join(parts)
    if parens:
        result += ' ' + parens

    return result


def _breathing_variants(form):
    """Add breathing marks to initial vowel. Returns list of (smooth, rough) variants."""
    if not form or form[0] not in _VOWELS_SET:
        return []

    # Check for diphthong: first vowel (α/ε/ο) + second vowel (ι/υ)
    if len(form) >= 2 and form[0] in _DIPHTHONG_FIRSTS and form[1] in _DIPHTHONG_SECONDS:
        pair = _BREATHING.get(form[1])
        if not pair:
            return []
        smooth, rough = pair
        return [form[0] + smooth + form[2:], form[0] + rough + form[2:]]

    pair = _BREATHING.get(form[0])
    if not pair:
        return []
    smooth, rough = pair
    return [smooth + form[1:], rough + form[1:]]


def _accent_variants(form):
    """Replace the accented vowel with grave/circumflex polytonic equivalents."""
    results = []
    for i, ch in enumerate(form):
        if ch in _ACUTE_VOWELS:
            grave = _ACUTE_TO_GRAVE.get(ch)
            if grave:
                results.append(form[:i] + grave + form[i+1:])
            circ = _ACUTE_TO_CIRCUMFLEX.get(ch)
            if circ:
                results.append(form[:i] + circ + form[i+1:])
            break  # Only one accent per word in Greek
    return results


def _polytonic_variants(form):
    """Generate polytonic variants of a monotonic Greek form.

    Handles three types of polytonic differences:
    1. Breathing marks on initial vowels (smooth + rough)
    2. Grave accent replacing acute (on final-accented words)
    3. Circumflex accent replacing acute (on long vowels)
    Plus combinations of breathing with grave/circumflex.
    """
    results = set()

    # Breathing variants of the original form
    for bv in _breathing_variants(form):
        results.add(bv)

    # Accent variants (grave, circumflex) of the original form
    for av in _accent_variants(form):
        results.add(av)
        # Breathing variants of accent variants
        for bv in _breathing_variants(av):
            results.add(bv)

    results.discard(form)
    return list(results)


def _def_has_tag(definition, tag):
    """Check if a definition string starts with a qualifier containing the tag."""
    m = re.match(r'^\(([^)]+)\)', definition)
    if not m:
        return False
    tags = [t.strip().lower() for t in m.group(1).split(',')]
    return tag in tags


def _clean_etymology(text):
    """Truncate etymology at noise like typological comparisons and bullet lists."""
    for marker in ['Typological comparisons', 'See also', '\n*', '\n•']:
        pos = text.find(marker)
        if pos > 0:
            text = text[:pos]
    return text.strip()


def _strip_transliterations(text):
    """Strip parenthesized transliterations containing accented Latin characters.

    Input:  "accusative masculine singular of όμορφος (ómorfos)"
    Output: "accusative masculine singular of όμορφος"

    Input:  "From θάλασσα (thálassa, \"sea\")"
    Output: "From θάλασσα"

    Only strips groups containing accented Latin, so legitimate
    annotations like (plural) or (indeclinable) are preserved.
    """
    # Strip groups with accented Latin (transliterations)
    # Covers Latin Extended-A/B (U+00C0-U+024F) and Latin Extended Additional (U+1E00-U+1EFF)
    text = re.sub(r'\s*\([^)]*[\u00C0-\u024F\u1E00-\u1EFF][^)]*\)', '', text)
    # Strip groups with quoted glosses like (tis, "of the")
    text = re.sub(r'\s*\([^)"]*"[^)]*\)', '', text)
    return text


def _strip_def_qualifiers(definition):
    """Strip redundant qualifiers and transliterations from definition text.

    Input:  "(masculine, participle) beaten, struck"
    Output: "beaten, struck"

    Input:  "accusative of όμορφος (ómorfos)"
    Output: "accusative of όμορφος"
    """
    # Strip transliterations first
    definition = _strip_transliterations(definition)
    m = re.match(r'^\(([^)]+)\)\s*', definition)
    if not m:
        return definition
    tags = [t.strip() for t in m.group(1).split(',')]
    remaining = [t for t in tags if t.lower() not in _STRIP_TAGS]
    rest = definition[m.end():]
    if remaining:
        return f"({', '.join(remaining)}) {rest}"
    return rest
