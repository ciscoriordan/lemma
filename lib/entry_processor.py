#
#  lib/entry_processor.py
#  Processes dictionary entries from JSONL data
#
#  Created by Francisco Riordan on 4/22/25.
#

import gc
import json
import re
from lib.greek_declension_templates import is_declension_template, expand_declension
from lib.dilemma_inflections import DilemmaInflections


SKIP_POS_KEYWORDS = frozenset([
    "prefix", "suffix", "infix", "circumfix",
    "combining form", "combining_form",
    "interfix", "affix",
    "preverb", "postposition",
    "enclitic", "proclitic", "clitic",
    "particle",
    "diacritical mark", "diacritical_mark",
    "punctuation mark", "punctuation_mark",
    "symbol",
    "letter",
    "character",
    "abbreviation",
    "initialism",
    "contraction",
])

# Regex for Greek Unicode block
_GREEK_RE = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
_LATIN_RE = re.compile(r'[a-zA-Z]')
_NON_GREEK_RE = re.compile(r'[^\u0370-\u03FF\u1F00-\u1FFF0-9\s\-\',.:;!?()]')


class EntryProcessor:
    def __init__(self, generator):
        self.generator = generator
        self.entries = generator.entries
        self.lemma_inflections = generator.lemma_inflections
        self.form_of_entries = {}  # Track which entries are just form-of redirects

    def process(self):
        print("Processing entries...")

        line_count = 0
        error_count = 0
        processed_count = 0

        filename = f"greek_data_{self.generator.source_lang}_{self.generator.download_date}.jsonl"
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line_count += 1

                try:
                    line = line.strip()
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:
                        print(f"Error on line {line_count}: {e}")
                    continue

                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    error_count += 1
                    if error_count <= 10:
                        print(f"JSON parse error on line {line_count}: {e}")
                    continue
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:
                        print(f"Unexpected error on line {line_count}: {type(e).__name__} - {e}")
                    continue

                # Try to extract the extraction date from first entry's meta field
                if self.generator.extraction_date is None and entry.get("meta"):
                    meta = entry["meta"]
                    if meta.get("extracted"):
                        self.generator.set_extraction_date(meta["extracted"])
                    elif meta.get("date"):
                        self.generator.set_extraction_date(meta["date"])

                # Only process Greek entries
                if not self._is_greek_entry(entry):
                    continue

                word = entry.get("word")
                if not word:
                    continue

                # Skip if word doesn't contain Greek characters
                if not self._contains_greek(word):
                    continue

                # Skip if word contains non-Greek scripts (except Latin for loanwords)
                if self._contains_non_greek_script(word):
                    continue

                processed_count += 1

                pos = entry.get("pos", "unknown")

                # Skip non-selectable word types
                if self._should_skip_pos(pos):
                    continue

                # Also skip entries that look like prefixes/suffixes based on the word itself
                if word.startswith('-') or word.endswith('-'):
                    continue

                # Skip very short words that are likely particles or fragments
                if len(word) == 1 and word.lower() not in ["ω", "ο", "α", "η"]:
                    continue

                # Process the entry
                self._process_single_entry(entry, word, pos)

        print(f"Processed {line_count} lines with {error_count} errors")
        print(f"Found {len(self.entries)} unique headwords (processed {processed_count} entries)")
        print("Note: Prefixes, suffixes, and other non-selectable word types were excluded")

        # Apply limit_percent after processing all entries (single pass)
        if self.generator.limit_percent is not None:
            max_entries = int(-(-len(self.entries) * self.generator.limit_percent // 100))  # ceil division
            keys = list(self.entries.keys())
            for k in keys[max_entries:]:
                del self.entries[k]
            print(f"Limited dictionary to {len(self.entries)} headwords ({self.generator.limit_percent}%)")

        # Enhance inflections with dilemma data if available
        self._enhance_with_dilemma()

        # Free dilemma inflection table (confidence data kept for ranking)
        dilemma = self.generator.dilemma_inflections
        if dilemma:
            dilemma.free_inflection_table()

        # Count and merge inflections
        self._merge_inflections()

        # Free intermediate structures no longer needed
        self.form_of_entries.clear()
        self.generator.lemma_inflections.clear()
        gc.collect()

        # Add case variations for all entries
        self._add_case_variations()

        # Report final statistics
        self._report_statistics()

    def _is_greek_entry(self, entry):
        return (entry.get("lang") == "Greek"
                or entry.get("lang") == "Ελληνικά"
                or entry.get("lang_code") == "el")

    def _contains_greek(self, word):
        return bool(_GREEK_RE.search(word))

    def _contains_non_greek_script(self, word):
        # Special cases for accepted Latin-only words
        if word in ["a", "A", "b", "B"]:
            return False

        # Check if word contains any Latin letters
        if _LATIN_RE.search(word):
            return True

        # Check if word contains other non-Greek scripts
        return bool(_NON_GREEK_RE.search(word))

    def _should_skip_pos(self, pos):
        pos_lower = pos.lower()
        return any(skip in pos_lower for skip in SKIP_POS_KEYWORDS)

    def _process_single_entry(self, entry, word, pos):
        # Build definition from senses
        definitions = []
        expanded_from_template = False

        # Check if this entry has form_of at the entry level
        senses = entry.get("senses")
        if senses and isinstance(senses, list) and senses:
            # Check if ALL senses are form_of
            all_form_of = all(
                isinstance(sense.get("form_of"), list) and sense["form_of"]
                for sense in senses
            )

            if all_form_of:
                # This is a pure form-of entry
                self.form_of_entries[word] = True

                # Add to lemma inflections for each form_of target
                for sense in senses:
                    form_of_list = sense.get("form_of")
                    if isinstance(form_of_list, list):
                        for form_of_data in form_of_list:
                            if isinstance(form_of_data, dict) and form_of_data.get("word"):
                                form_of_word = form_of_data["word"]
                                # Skip multi-word lemmas
                                if ' ' in form_of_word:
                                    continue

                                if form_of_word not in self.lemma_inflections:
                                    self.lemma_inflections[form_of_word] = set()
                                self.lemma_inflections[form_of_word].add(word)

                                # Also add case variations of this inflection
                                capitalized = word[0].upper() + word[1:] if word else word
                                if capitalized != word:
                                    self.lemma_inflections[form_of_word].add(capitalized)
                                lowered = word.lower()
                                if lowered != word:
                                    self.lemma_inflections[form_of_word].add(lowered)

                # Don't create a separate entry for pure form-of entries
                return

        # Process definitions from senses
        if senses:
            for sense in senses:
                definition = self._extract_definition_from_sense(sense)
                if definition.strip():
                    definitions.append(definition)

        # Store each definition separately
        if not definitions:
            definitions = ["No definition available"]

        # Handle forms and collect inflections
        inflections = self._collect_inflections(entry, word)

        # Check if we expanded templates
        if self.generator.source_lang == 'el' and entry.get("head_templates"):
            for template in entry["head_templates"]:
                if template.get("name") and is_declension_template(template["name"]):
                    expanded_from_template = True
                    break

        # Store entry with inflections
        if word not in self.entries:
            self.entries[word] = []

        # Check if we already have an entry with the same POS
        existing_entry = None
        for e in self.entries[word]:
            if e['pos'] == pos:
                existing_entry = e
                break

        if existing_entry:
            # Merge definitions and inflections
            existing_entry['definitions'] += definitions
            # Deduplicate definitions
            seen = set()
            unique_defs = []
            for d in existing_entry['definitions']:
                if d not in seen:
                    seen.add(d)
                    unique_defs.append(d)
            existing_entry['definitions'] = unique_defs

            existing_entry['inflections'] += inflections
            # Deduplicate inflections
            seen = set()
            unique_infl = []
            for i in existing_entry['inflections']:
                if i not in seen:
                    seen.add(i)
                    unique_infl.append(i)
            existing_entry['inflections'] = unique_infl

            if not existing_entry.get('etymology'):
                existing_entry['etymology'] = entry.get("etymology_text")
            if not existing_entry.get('expanded_from_template'):
                existing_entry['expanded_from_template'] = expanded_from_template
        else:
            self.entries[word].append({
                'pos': pos,
                'definitions': definitions,
                'etymology': entry.get("etymology_text"),
                'inflections': inflections,
                'expanded_from_template': expanded_from_template,
            })

    def _extract_definition_from_sense(self, sense):
        definition = ""

        if sense.get("glosses"):
            glosses = sense["glosses"]
            if isinstance(glosses, list):
                definition = "; ".join(glosses)
            else:
                definition = str(glosses)

            # Add raw_tags if present
            raw_tags = sense.get("raw_tags")
            if isinstance(raw_tags, list):
                tags = ", ".join(raw_tags)
                definition = f"[{tags}] {definition}"

        elif sense.get("raw_glosses"):
            raw_glosses = sense["raw_glosses"]
            if isinstance(raw_glosses, list):
                definition = "; ".join(raw_glosses)
            else:
                definition = str(raw_glosses)

        return definition

    def _expand_parentheses(self, word):
        """Handle forms like 'πηγαίνο(υ)με' -> ['πηγαίνομε', 'πηγαίνουμε']"""
        if '(' in word and ')' in word:
            m = re.match(r'^(.+?)\((.+?)\)(.*)$', word)
            if m:
                prefix = m.group(1)
                optional = m.group(2)
                suffix = m.group(3)
                return [f"{prefix}{suffix}", f"{prefix}{optional}{suffix}"]
            else:
                return [word]
        else:
            return [word]

    def _collect_inflections(self, entry, word):
        inflections = []
        inflection_set = set()
        template_inflections = set()

        def add_inflection(form):
            if form not in inflection_set:
                inflection_set.add(form)
                inflections.append(form)

        # First, collect explicitly listed forms from the forms array
        if entry.get("forms"):
            for form in entry["forms"]:
                if isinstance(form, dict):
                    form_word = form.get("form")

                    # Skip romanizations
                    tags = form.get("tags")
                    if isinstance(tags, list) and "romanization" in tags:
                        continue

                    # Skip forms with Latin characters (unless it's a loanword)
                    if form_word and _LATIN_RE.search(form_word) and not self._is_loanword(word):
                        continue

                    # Skip prefix/suffix forms
                    if form_word and (form_word.startswith('-') or form_word.endswith('-')):
                        continue

                    # Skip template references
                    if form_word and form_word.startswith('el-'):
                        continue

                    # Skip multi-word forms (containing spaces)
                    if form_word and ' ' in form_word:
                        continue

                    if form_word and form_word != word:
                        expanded_forms = self._expand_parentheses(form_word)
                        for expanded in expanded_forms:
                            add_inflection(expanded)
                            capitalized = expanded[0].upper() + expanded[1:] if expanded else expanded
                            if capitalized != expanded:
                                add_inflection(capitalized)
                            lowered = expanded.lower()
                            if lowered != expanded:
                                add_inflection(lowered)

                elif isinstance(form, str) and form != word and not _LATIN_RE.search(form):
                    if form.startswith('-') or form.endswith('-'):
                        continue
                    if form.startswith('el-'):
                        continue
                    if ' ' in form:
                        continue

                    expanded_forms = self._expand_parentheses(form)
                    for expanded in expanded_forms:
                        add_inflection(expanded)
                        capitalized = expanded[0].upper() + expanded[1:] if expanded else expanded
                        if capitalized != expanded:
                            add_inflection(capitalized)
                        lowered = expanded.lower()
                        if lowered != expanded:
                            add_inflection(lowered)

        # Then check for Greek declension/conjugation templates (Greek Wiktionary)
        if self.generator.source_lang == 'el' and entry.get("head_templates"):
            for template in entry["head_templates"]:
                template_name = template.get("name")
                if template_name and is_declension_template(template_name):
                    pattern_name = re.sub(r'^el-κλίση-', '', template_name)
                    pattern_name = re.sub(r'^el-κλίσ-', '', pattern_name)
                    expanded_forms = expand_declension(word, pattern_name)
                    template_inflections.update(expanded_forms)

        # Process related words last
        if entry.get("related"):
            for related in entry["related"]:
                related_word = related.get("word") if isinstance(related, dict) else None
                if related_word and related_word != word and ' ' not in related_word:
                    expanded_forms = self._expand_parentheses(related_word)
                    for expanded in expanded_forms:
                        add_inflection(expanded)
                        capitalized = expanded[0].upper() + expanded[1:] if expanded else expanded
                        if capitalized != expanded:
                            add_inflection(capitalized)
                        lowered = expanded.lower()
                        if lowered != expanded:
                            add_inflection(lowered)

        # Combine: explicit forms first, then template-generated forms
        template_only = template_inflections - inflection_set
        return inflections + list(template_only)

    def _is_loanword(self, word):
        # Simple check for common loanwords that might have Latin characters
        return False

    def _enhance_with_dilemma(self):
        dilemma = self.generator.dilemma_inflections
        if not dilemma or not dilemma.available():
            return

        enhanced_count = 0
        for word, entries_list in self.entries.items():
            dilemma_forms = dilemma.get_inflections(word)
            if not dilemma_forms:
                continue

            # Filter to single-word Greek forms only
            valid_forms = [f for f in dilemma_forms if ' ' not in f and _GREEK_RE.search(f)]
            if not valid_forms:
                continue

            for entry in entries_list:
                if entry.get('inflections') is None:
                    entry['inflections'] = []
                before = len(entry['inflections'])
                # Combine and deduplicate
                existing = set(entry['inflections'])
                for form in valid_forms:
                    if form not in existing:
                        entry['inflections'].append(form)
                        existing.add(form)
                enhanced_count += len(entry['inflections']) - before

        if enhanced_count > 0:
            print(f"Added {enhanced_count} inflections from dilemma")

    def _merge_inflections(self):
        if not self.lemma_inflections:
            return

        # First, filter out any "inflections" that are actually separate true headwords
        filtered_inflections = {}

        for lemma, inflected_forms in self.lemma_inflections.items():
            # Skip if lemma contains spaces (multi-word)
            if ' ' in lemma:
                continue

            # Convert Set to list for filtering
            forms_list = list(inflected_forms) if isinstance(inflected_forms, set) else inflected_forms

            # Only keep inflected forms that are either:
            # 1. Not in entries at all (pure inflections)
            # 2. In form_of_entries (form-of redirects like έπαψε)
            filtered_forms = []
            for form in forms_list:
                # Skip if it's a prefix/suffix
                if form.startswith('-') or form.endswith('-'):
                    continue
                # Skip multi-word forms
                if ' ' in form:
                    continue
                # Keep if it's not in entries at all (pure inflection)
                # Keep if it's a form-of entry (redirect)
                # Reject if it's a true headword
                if form in self.entries and form not in self.form_of_entries:
                    continue
                filtered_forms.append(form)

            if filtered_forms:
                filtered_inflections[lemma] = filtered_forms

        # Now merge the filtered inflections
        for lemma, inflected_forms in filtered_inflections.items():
            if lemma in self.entries:
                for entry in self.entries[lemma]:
                    if entry.get('inflections') is None:
                        entry['inflections'] = []
                    existing = set(entry['inflections'])
                    for form in inflected_forms:
                        if form not in existing:
                            entry['inflections'].append(form)
                            existing.add(form)

        total_forms = sum(len(forms) for forms in filtered_inflections.values())
        print(f"Added {len(filtered_inflections)} additional inflection mappings from form_of entries")
        print(f"Total inflections: {total_forms}")

    def _add_case_variations(self):
        for word, entries in self.entries.items():
            for entry in entries:
                if entry.get('inflections') is None:
                    entry['inflections'] = []

                existing = set(entry['inflections'])

                # Add case variations of the headword
                capitalized = word[0].upper() + word[1:] if word else word
                if capitalized != word and capitalized not in existing:
                    entry['inflections'].append(capitalized)
                    existing.add(capitalized)

                lowered = word.lower()
                if lowered != word and lowered not in existing:
                    entry['inflections'].append(lowered)
                    existing.add(lowered)

                uppered = word.upper()
                if uppered != word and uppered != capitalized and uppered not in existing:
                    entry['inflections'].append(uppered)
                    existing.add(uppered)

    def _report_statistics(self):
        total_inflections = 0
        for word, entries in self.entries.items():
            for entry in entries:
                total_inflections += len(entry.get('inflections') or [])
        print(f"Total inflections: {total_inflections}")
        if self.generator.extraction_date:
            print(f"Wiktionary extraction date found: {self.generator.extraction_date}")

        # Report template expansion if we're processing Greek source
        if self.generator.source_lang == 'el':
            template_count = 0
            expanded_count = 0

            for word, entries in self.entries.items():
                for entry in entries:
                    if entry.get('expanded_from_template'):
                        template_count += 1
                        expanded_count += len(entry.get('inflections') or [])

            if template_count > 0:
                print(f"Expanded {template_count} declension templates into {expanded_count} forms")
