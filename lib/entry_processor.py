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

                # Try to extract the extraction date from first entry's meta
                # field. This is a last-resort fallback for dumps that embed
                # a metadata record; the downloader's HTTP-header / sidecar
                # cascade is the primary source. Checks several known keys
                # (Kaikki has used different names over time).
                if self.generator.extraction_date is None and entry.get("meta"):
                    meta = entry["meta"]
                    for key in ("extracted", "date", "generated",
                                "generation_time", "timestamp", "created"):
                        value = meta.get(key)
                        if value:
                            self.generator.set_extraction_date(value)
                            break

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

        # Set inflections: Dilemma is primary source, Wiktionary forms are fallback
        self._set_inflections()

        # Free dilemma inflection table (confidence data kept for ranking)
        dilemma = self.generator.dilemma_inflections
        if dilemma:
            dilemma.free_inflection_table()

        gc.collect()

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
        form_of_targets = []
        expanded_from_template = False

        senses = entry.get("senses")

        # Collect form_of targets for cross-referencing
        if senses and isinstance(senses, list):
            for sense in senses:
                form_of_list = sense.get("form_of")
                if isinstance(form_of_list, list):
                    for form_of_data in form_of_list:
                        if isinstance(form_of_data, dict) and form_of_data.get("word"):
                            target = form_of_data["word"]
                            if ' ' not in target and target not in form_of_targets:
                                form_of_targets.append(target)

        # Process definitions from senses, collecting examples alongside
        examples = []
        if senses:
            for sense in senses:
                definition = self._extract_definition_from_sense(sense)
                if definition.strip():
                    definitions.append(definition)
                    # Extract first example for this sense (max 1 per sense)
                    example = self._extract_example_from_sense(sense)
                    examples.append(example)  # May be None; kept aligned with definitions

        # Store each definition separately
        if not definitions:
            definitions = ["No definition available"]
            examples = [None]

        # Extract head_templates expansion
        head_expansion = None
        if entry.get("head_templates"):
            for template in entry["head_templates"]:
                expansion = template.get("expansion")
                if expansion and expansion.strip():
                    head_expansion = expansion.strip()
                    break  # Use the first one

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
            # Merge definitions, examples, and inflections
            existing_defs = existing_entry['definitions']
            existing_examples = existing_entry.get('examples') or []
            # Pad examples list if it was shorter than definitions
            while len(existing_examples) < len(existing_defs):
                existing_examples.append(None)

            # Deduplicate definitions while keeping examples aligned
            seen = set(existing_defs)
            for d, ex in zip(definitions, examples):
                if d not in seen:
                    seen.add(d)
                    existing_defs.append(d)
                    existing_examples.append(ex)
            existing_entry['definitions'] = existing_defs
            existing_entry['examples'] = existing_examples

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
            if not existing_entry.get('head_expansion') and head_expansion:
                existing_entry['head_expansion'] = head_expansion
            # Merge form_of targets
            existing_targets = existing_entry.get('form_of_targets') or []
            for t in form_of_targets:
                if t not in existing_targets:
                    existing_targets.append(t)
            existing_entry['form_of_targets'] = existing_targets
        else:
            self.entries[word].append({
                'pos': pos,
                'definitions': definitions,
                'examples': examples,
                'etymology': entry.get("etymology_text"),
                'head_expansion': head_expansion,
                'inflections': inflections,
                'expanded_from_template': expanded_from_template,
                'form_of_targets': form_of_targets,
            })

    def _extract_definition_from_sense(self, sense):
        definition = ""

        if sense.get("glosses"):
            glosses = sense["glosses"]
            if isinstance(glosses, list):
                definition = "; ".join(glosses)
            else:
                definition = str(glosses)

            # Add sense tags for non-form-of definitions only
            # Form-of definitions already contain the grammatical info in the gloss
            tags = sense.get("tags") or []
            is_form_of = bool(sense.get("form_of")) or "form-of" in tags or "alt-of" in tags
            if not is_form_of:
                raw_tags = sense.get("raw_tags")
                tags = sense.get("tags")
                if isinstance(raw_tags, list) and raw_tags:
                    tag_str = ", ".join(raw_tags)
                    definition = f"({tag_str}) {definition}"
                elif isinstance(tags, list) and tags:
                    formatted_tags = [t.replace("-", " ") for t in tags]
                    tag_str = ", ".join(formatted_tags)
                    definition = f"({tag_str}) {definition}"

        elif sense.get("raw_glosses"):
            raw_glosses = sense["raw_glosses"]
            if isinstance(raw_glosses, list):
                definition = "; ".join(raw_glosses)
            else:
                definition = str(raw_glosses)

        return definition

    def _extract_example_from_sense(self, sense):
        """Extract the first example from a sense, returning a dict with text and translation, or None."""
        examples = sense.get("examples")
        if not isinstance(examples, list) or not examples:
            return None
        for ex in examples:
            if not isinstance(ex, dict):
                continue
            text = ex.get("text", "").strip()
            translation = ex.get("translation", "").strip()
            if text:
                result = {"text": text, "translation": translation}
                if "bold_text_offsets" in ex:
                    result["bold_text_offsets"] = ex["bold_text_offsets"]
                return result
        return None

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

        # Combine: explicit forms first, then template-generated forms
        template_only = template_inflections - inflection_set
        return inflections + list(template_only)

    def _is_loanword(self, word):
        # Simple check for common loanwords that might have Latin characters
        return False

    def _set_inflections(self):
        """Set inflections for all entries. Dilemma is the primary source.
        Wiktionary forms are used as fallback only when Dilemma has nothing.
        Form-of entries get no inflections (their forms belong on the real entry).
        """
        dilemma = self.generator.dilemma_inflections
        has_dilemma = dilemma and dilemma.available()
        dilemma_count = 0
        wiktionary_fallback_count = 0

        for word, entries_list in self.entries.items():
            for entry in entries_list:
                # Form-of entries get no inflections
                if entry.get('form_of_targets'):
                    entry['inflections'] = []
                    continue

                # Try Dilemma first
                if has_dilemma:
                    dilemma_forms = dilemma.get_inflections(word)
                    if dilemma_forms:
                        valid = [f for f in dilemma_forms if ' ' not in f and _GREEK_RE.search(f)]
                        if valid:
                            entry['inflections'] = valid
                            dilemma_count += len(valid)
                            continue

                # Fallback: keep Wiktionary-extracted inflections (already on entry)
                wiktionary_fallback_count += len(entry.get('inflections') or [])

        if has_dilemma:
            print(f"Inflections from dilemma: {dilemma_count}")
        print(f"Inflections from wiktionary (fallback): {wiktionary_fallback_count}")

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
