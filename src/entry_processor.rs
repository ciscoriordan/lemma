// Processes dictionary entries from JSONL data.

use crate::declension::{expand_declension, is_declension_template, strip_template_prefix};
use crate::dilemma::DilemmaInflections;
use regex::Regex;
use serde_json::Value;
use std::collections::HashSet;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::sync::OnceLock;

const SKIP_POS: &[&str] = &[
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
];

fn greek_re() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"[\u0370-\u03FF\u1F00-\u1FFF]").unwrap())
}

fn latin_re() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"[a-zA-Z]").unwrap())
}

fn non_greek_re() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"[^\u0370-\u03FF\u1F00-\u1FFF0-9\s\-',.:;!?()]").unwrap())
}

fn paren_re() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"^(.+?)\((.+?)\)(.*)$").unwrap())
}

#[derive(Debug, Clone)]
pub struct Example {
    pub text: String,
    pub translation: String,
    pub bold_text_offsets: Option<Vec<(usize, usize)>>,
}

#[derive(Debug, Clone, Default)]
pub struct Entry {
    pub pos: String,
    pub definitions: Vec<String>,
    pub examples: Vec<Option<Example>>,
    pub etymology: Option<String>,
    pub head_expansion: Option<String>,
    pub inflections: Vec<String>,
    pub expanded_from_template: bool,
    pub form_of_targets: Vec<String>,
}

pub type EntryMap = indexmap_lite::IndexMap<String, Vec<Entry>>;

// A lightweight insertion-ordered map (Python-dict semantics).
pub mod indexmap_lite {
    use std::collections::HashMap;

    pub struct IndexMap<K: Eq + std::hash::Hash + Clone, V> {
        keys: Vec<K>,
        map: HashMap<K, V>,
    }

    impl<K: Eq + std::hash::Hash + Clone, V> IndexMap<K, V> {
        pub fn new() -> Self { Self { keys: Vec::new(), map: HashMap::new() } }
        pub fn len(&self) -> usize { self.keys.len() }
        pub fn is_empty(&self) -> bool { self.keys.is_empty() }
        pub fn contains_key(&self, k: &K) -> bool { self.map.contains_key(k) }
        pub fn get(&self, k: &K) -> Option<&V> { self.map.get(k) }
        pub fn get_mut(&mut self, k: &K) -> Option<&mut V> { self.map.get_mut(k) }
        pub fn insert(&mut self, k: K, v: V) {
            if !self.map.contains_key(&k) {
                self.keys.push(k.clone());
            }
            self.map.insert(k, v);
        }
        pub fn remove(&mut self, k: &K) -> Option<V> {
            let v = self.map.remove(k)?;
            if let Some(i) = self.keys.iter().position(|x| x == k) {
                self.keys.remove(i);
            }
            Some(v)
        }
        pub fn keys(&self) -> std::slice::Iter<'_, K> { self.keys.iter() }
        pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
            self.keys.iter().map(move |k| (k, self.map.get(k).unwrap()))
        }
        pub fn iter_mut(&mut self) -> KeysIterMut<'_, K, V> {
            let keys: Vec<K> = self.keys.clone();
            KeysIterMut { keys: keys.into_iter(), map: &mut self.map }
        }
        pub fn truncate_to(&mut self, n: usize) {
            while self.keys.len() > n {
                if let Some(k) = self.keys.pop() {
                    self.map.remove(&k);
                }
            }
        }
    }

    pub struct KeysIterMut<'a, K: Eq + std::hash::Hash + Clone, V> {
        keys: std::vec::IntoIter<K>,
        map: &'a mut HashMap<K, V>,
    }

    impl<'a, K: Eq + std::hash::Hash + Clone, V> Iterator for KeysIterMut<'a, K, V> {
        type Item = (K, &'a mut V);
        fn next(&mut self) -> Option<Self::Item> {
            let k = self.keys.next()?;
            let v = self.map.get_mut(&k)? as *mut V;
            // SAFETY: each key visited at most once; map outlives returned refs
            unsafe { Some((k, &mut *v)) }
        }
    }
}

pub struct EntryProcessor<'a> {
    pub entries: EntryMap,
    pub extraction_date: Option<String>,
    source_lang: String,
    limit_percent: Option<f64>,
    filename: String,
    dilemma: Option<&'a mut DilemmaInflections>,
}

impl<'a> EntryProcessor<'a> {
    pub fn new(
        source_lang: &str,
        limit_percent: Option<f64>,
        filename: &str,
        dilemma: Option<&'a mut DilemmaInflections>,
    ) -> Self {
        Self {
            entries: EntryMap::new(),
            extraction_date: None,
            source_lang: source_lang.to_string(),
            limit_percent,
            filename: filename.to_string(),
            dilemma,
        }
    }

    pub fn process(&mut self) {
        println!("Processing entries...");

        let mut line_count: u64 = 0;
        let mut error_count: u64 = 0;
        let mut processed_count: u64 = 0;

        let f = match File::open(&self.filename) {
            Ok(f) => f,
            Err(e) => {
                eprintln!("Error: could not open {}: {}", self.filename, e);
                return;
            }
        };
        let reader = BufReader::new(f);

        for line in reader.lines() {
            line_count += 1;
            let line = match line {
                Ok(l) => l,
                Err(e) => {
                    error_count += 1;
                    if error_count <= 10 {
                        println!("Error on line {}: {}", line_count, e);
                    }
                    continue;
                }
            };
            let line = line.trim();
            if line.is_empty() { continue; }

            let entry: Value = match serde_json::from_str(line) {
                Ok(v) => v,
                Err(e) => {
                    error_count += 1;
                    if error_count <= 10 {
                        println!("JSON parse error on line {}: {}", line_count, e);
                    }
                    continue;
                }
            };

            if self.extraction_date.is_none() {
                if let Some(meta) = entry.get("meta").and_then(|v| v.as_object()) {
                    for key in ["extracted", "date", "generated", "generation_time", "timestamp", "created"] {
                        if let Some(v) = meta.get(key).and_then(|v| v.as_str()) {
                            self.extraction_date = Some(v.to_string());
                            break;
                        }
                    }
                }
            }

            if !is_greek_entry(&entry) { continue; }

            let word = match entry.get("word").and_then(|v| v.as_str()) {
                Some(w) => w.to_string(),
                None => continue,
            };

            if !contains_greek(&word) { continue; }
            if contains_non_greek_script(&word) { continue; }

            processed_count += 1;

            let pos = entry.get("pos").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();

            if should_skip_pos(&pos) { continue; }
            if word.starts_with('-') || word.ends_with('-') { continue; }

            // Skip very short words that are likely particles/fragments
            if word.chars().count() == 1 {
                let lower: String = word.chars().flat_map(|c| c.to_lowercase()).collect();
                if !matches!(lower.as_str(), "ω" | "ο" | "α" | "η") {
                    continue;
                }
            }

            self.process_single_entry(&entry, &word, &pos);
        }

        println!("Processed {} lines with {} errors", line_count, error_count);
        println!("Found {} unique headwords (processed {} entries)", self.entries.len(), processed_count);
        println!("Note: Prefixes, suffixes, and other non-selectable word types were excluded");

        // Apply limit_percent
        if let Some(pct) = self.limit_percent {
            let total = self.entries.len();
            // ceil division
            let max_entries = ((total as f64 * pct / 100.0).ceil()) as usize;
            self.entries.truncate_to(max_entries);
            println!("Limited dictionary to {} headwords ({}%)", self.entries.len(), pct);
        }

        self.set_inflections();

        if let Some(d) = self.dilemma.as_deref_mut() {
            d.free_inflection_table();
        }

        self.report_statistics();
    }

    fn process_single_entry(&mut self, entry: &Value, word: &str, pos: &str) {
        let mut definitions: Vec<String> = Vec::new();
        let mut form_of_targets: Vec<String> = Vec::new();
        let mut expanded_from_template = false;
        let mut examples: Vec<Option<Example>> = Vec::new();

        let senses_opt = entry.get("senses").and_then(|v| v.as_array());

        if let Some(senses) = senses_opt {
            for sense in senses {
                if let Some(fol) = sense.get("form_of").and_then(|v| v.as_array()) {
                    for fo in fol {
                        if let Some(target) = fo.get("word").and_then(|v| v.as_str()) {
                            if !target.contains(' ') && !form_of_targets.iter().any(|t| t == target) {
                                form_of_targets.push(target.to_string());
                            }
                        }
                    }
                }
            }
        }

        if let Some(senses) = senses_opt {
            for sense in senses {
                let def = extract_definition_from_sense(sense);
                if !def.trim().is_empty() {
                    definitions.push(def);
                    examples.push(extract_example_from_sense(sense));
                }
            }
        }

        if definitions.is_empty() {
            definitions.push("No definition available".to_string());
            examples.push(None);
        }

        let mut head_expansion: Option<String> = None;
        if let Some(templates) = entry.get("head_templates").and_then(|v| v.as_array()) {
            for t in templates {
                if let Some(expansion) = t.get("expansion").and_then(|v| v.as_str()) {
                    if !expansion.trim().is_empty() {
                        head_expansion = Some(expansion.trim().to_string());
                        break;
                    }
                }
            }
        }

        let inflections = self.collect_inflections(entry, word);

        if self.source_lang == "el" {
            if let Some(templates) = entry.get("head_templates").and_then(|v| v.as_array()) {
                for t in templates {
                    if let Some(name) = t.get("name").and_then(|v| v.as_str()) {
                        if is_declension_template(name) {
                            expanded_from_template = true;
                            break;
                        }
                    }
                }
            }
        }

        let etymology = entry.get("etymology_text").and_then(|v| v.as_str()).map(|s| s.to_string());

        if !self.entries.contains_key(&word.to_string()) {
            self.entries.insert(word.to_string(), Vec::new());
        }

        // Find existing entry with the same POS
        let list = self.entries.get_mut(&word.to_string()).unwrap();
        let existing_idx = list.iter().position(|e| e.pos == pos);

        if let Some(idx) = existing_idx {
            let existing = &mut list[idx];
            // pad examples if shorter
            while existing.examples.len() < existing.definitions.len() {
                existing.examples.push(None);
            }
            let existing_defs_set: HashSet<String> = existing.definitions.iter().cloned().collect();
            let mut seen = existing_defs_set;
            for (d, ex) in definitions.into_iter().zip(examples.into_iter()) {
                if !seen.contains(&d) {
                    seen.insert(d.clone());
                    existing.definitions.push(d);
                    existing.examples.push(ex);
                }
            }
            existing.inflections.extend(inflections);
            let mut seen_inf = HashSet::new();
            existing.inflections.retain(|i| seen_inf.insert(i.clone()));

            if existing.etymology.is_none() {
                existing.etymology = etymology;
            }
            if !existing.expanded_from_template {
                existing.expanded_from_template = expanded_from_template;
            }
            if existing.head_expansion.is_none() && head_expansion.is_some() {
                existing.head_expansion = head_expansion;
            }
            for t in form_of_targets {
                if !existing.form_of_targets.contains(&t) {
                    existing.form_of_targets.push(t);
                }
            }
        } else {
            list.push(Entry {
                pos: pos.to_string(),
                definitions,
                examples,
                etymology,
                head_expansion,
                inflections,
                expanded_from_template,
                form_of_targets,
            });
        }
    }

    fn collect_inflections(&self, entry: &Value, word: &str) -> Vec<String> {
        let mut inflections: Vec<String> = Vec::new();
        let mut inflection_set: HashSet<String> = HashSet::new();

        let add = |form: &str, inflections: &mut Vec<String>, set: &mut HashSet<String>| {
            if set.insert(form.to_string()) {
                inflections.push(form.to_string());
            }
        };

        // Collect explicitly listed forms
        if let Some(forms) = entry.get("forms").and_then(|v| v.as_array()) {
            for form in forms {
                if let Some(obj) = form.as_object() {
                    let form_word = obj.get("form").and_then(|v| v.as_str());
                    // Skip romanizations
                    if let Some(tags) = obj.get("tags").and_then(|v| v.as_array()) {
                        if tags.iter().any(|t| t.as_str() == Some("romanization")) { continue; }
                    }
                    let fw = match form_word {
                        Some(f) if !f.is_empty() => f,
                        _ => continue,
                    };
                    if latin_re().is_match(fw) && !is_loanword(word) { continue; }
                    if fw.starts_with('-') || fw.ends_with('-') { continue; }
                    if fw.starts_with("el-") { continue; }
                    if fw.contains(' ') { continue; }
                    if fw == word { continue; }

                    for expanded in expand_parentheses(fw) {
                        add(&expanded, &mut inflections, &mut inflection_set);
                        let capitalized = capitalize_first(&expanded);
                        if capitalized != expanded {
                            add(&capitalized, &mut inflections, &mut inflection_set);
                        }
                        let lowered = lower_first(&expanded);
                        if lowered != expanded {
                            add(&lowered, &mut inflections, &mut inflection_set);
                        }
                    }
                } else if let Some(s) = form.as_str() {
                    if s == word { continue; }
                    if latin_re().is_match(s) { continue; }
                    if s.starts_with('-') || s.ends_with('-') { continue; }
                    if s.starts_with("el-") { continue; }
                    if s.contains(' ') { continue; }
                    for expanded in expand_parentheses(s) {
                        add(&expanded, &mut inflections, &mut inflection_set);
                        let capitalized = capitalize_first(&expanded);
                        if capitalized != expanded {
                            add(&capitalized, &mut inflections, &mut inflection_set);
                        }
                        let lowered = lower_first(&expanded);
                        if lowered != expanded {
                            add(&lowered, &mut inflections, &mut inflection_set);
                        }
                    }
                }
            }
        }

        // Greek declension templates
        let mut template_inflections: HashSet<String> = HashSet::new();
        if self.source_lang == "el" {
            if let Some(templates) = entry.get("head_templates").and_then(|v| v.as_array()) {
                for t in templates {
                    if let Some(name) = t.get("name").and_then(|v| v.as_str()) {
                        if is_declension_template(name) {
                            let pattern_name = strip_template_prefix(name);
                            for f in expand_declension(word, pattern_name) {
                                template_inflections.insert(f);
                            }
                        }
                    }
                }
            }
        }

        // template forms that weren't already added
        for tf in &template_inflections {
            if !inflection_set.contains(tf) {
                inflections.push(tf.clone());
            }
        }

        inflections
    }

    fn set_inflections(&mut self) {
        let has_dilemma = self.dilemma.as_deref().map(|d| d.available()).unwrap_or(false);
        let mut dilemma_count: usize = 0;
        let mut wiktionary_fallback_count: usize = 0;

        // Borrow dilemma immutably via raw pointer dance: we only need read access to it
        // while iterating over self.entries mutably.
        let dilemma_ptr: Option<*const DilemmaInflections> =
            self.dilemma.as_deref().map(|d| d as *const DilemmaInflections);

        for (word, list) in self.entries.iter_mut() {
            for entry in list.iter_mut() {
                if !entry.form_of_targets.is_empty() {
                    entry.inflections.clear();
                    continue;
                }
                if has_dilemma {
                    let dilemma = unsafe { &*dilemma_ptr.unwrap() };
                    let forms = dilemma.get_inflections(&word);
                    if !forms.is_empty() {
                        let valid: Vec<String> = forms
                            .into_iter()
                            .filter(|f| !f.contains(' ') && greek_re().is_match(f))
                            .collect();
                        if !valid.is_empty() {
                            dilemma_count += valid.len();
                            entry.inflections = valid;
                            continue;
                        }
                    }
                }
                wiktionary_fallback_count += entry.inflections.len();
            }
        }

        if has_dilemma {
            println!("Inflections from dilemma: {}", dilemma_count);
        }
        println!("Inflections from wiktionary (fallback): {}", wiktionary_fallback_count);
    }

    fn report_statistics(&self) {
        let total: usize = self.entries.iter()
            .map(|(_, es)| es.iter().map(|e| e.inflections.len()).sum::<usize>())
            .sum();
        println!("Total inflections: {}", total);
        if let Some(d) = &self.extraction_date {
            println!("Wiktionary extraction date found: {}", d);
        }
        if self.source_lang == "el" {
            let mut template_count = 0usize;
            let mut expanded_count = 0usize;
            for (_, es) in self.entries.iter() {
                for e in es {
                    if e.expanded_from_template {
                        template_count += 1;
                        expanded_count += e.inflections.len();
                    }
                }
            }
            if template_count > 0 {
                println!("Expanded {} declension templates into {} forms", template_count, expanded_count);
            }
        }
    }
}

fn is_greek_entry(entry: &Value) -> bool {
    let lang = entry.get("lang").and_then(|v| v.as_str());
    let lang_code = entry.get("lang_code").and_then(|v| v.as_str());
    lang == Some("Greek") || lang == Some("Ελληνικά") || lang_code == Some("el")
}

fn contains_greek(word: &str) -> bool {
    greek_re().is_match(word)
}

fn contains_non_greek_script(word: &str) -> bool {
    if matches!(word, "a" | "A" | "b" | "B") { return false; }
    if latin_re().is_match(word) { return true; }
    non_greek_re().is_match(word)
}

fn should_skip_pos(pos: &str) -> bool {
    let pos_lower: String = pos.chars().flat_map(|c| c.to_lowercase()).collect();
    SKIP_POS.iter().any(|s| pos_lower.contains(s))
}

fn extract_definition_from_sense(sense: &Value) -> String {
    let mut definition = String::new();

    if let Some(glosses) = sense.get("glosses") {
        if let Some(arr) = glosses.as_array() {
            let strs: Vec<&str> = arr.iter().filter_map(|v| v.as_str()).collect();
            definition = strs.join("; ");
        } else if let Some(s) = glosses.as_str() {
            definition = s.to_string();
        }

        // form-of detection
        let tags = sense.get("tags").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        let is_form_of = sense.get("form_of").is_some()
            || tags.iter().any(|t| t.as_str() == Some("form-of"))
            || tags.iter().any(|t| t.as_str() == Some("alt-of"));
        if !is_form_of {
            let raw_tags = sense.get("raw_tags").and_then(|v| v.as_array()).cloned();
            if let Some(rt) = raw_tags {
                if !rt.is_empty() {
                    let parts: Vec<String> = rt.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect();
                    if !parts.is_empty() {
                        definition = format!("({}) {}", parts.join(", "), definition);
                    }
                }
            } else if !tags.is_empty() {
                let parts: Vec<String> = tags
                    .iter()
                    .filter_map(|v| v.as_str().map(|s| s.replace('-', " ")))
                    .collect();
                if !parts.is_empty() {
                    definition = format!("({}) {}", parts.join(", "), definition);
                }
            }
        }
    } else if let Some(raw) = sense.get("raw_glosses") {
        if let Some(arr) = raw.as_array() {
            let strs: Vec<&str> = arr.iter().filter_map(|v| v.as_str()).collect();
            definition = strs.join("; ");
        } else if let Some(s) = raw.as_str() {
            definition = s.to_string();
        }
    }

    definition
}

fn extract_example_from_sense(sense: &Value) -> Option<Example> {
    let examples = sense.get("examples")?.as_array()?;
    for ex in examples {
        let obj = match ex.as_object() {
            Some(o) => o,
            None => continue,
        };
        let text = obj.get("text").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        let translation = obj.get("translation").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        if text.is_empty() { continue; }
        let bold = obj.get("bold_text_offsets").and_then(|v| v.as_array()).map(|arr| {
            arr.iter().filter_map(|pair| {
                let p = pair.as_array()?;
                let s = p.first()?.as_u64()? as usize;
                let e = p.get(1)?.as_u64()? as usize;
                Some((s, e))
            }).collect::<Vec<(usize, usize)>>()
        });
        return Some(Example { text, translation, bold_text_offsets: bold });
    }
    None
}

fn expand_parentheses(word: &str) -> Vec<String> {
    if word.contains('(') && word.contains(')') {
        if let Some(caps) = paren_re().captures(word) {
            let prefix = caps.get(1).unwrap().as_str();
            let optional = caps.get(2).unwrap().as_str();
            let suffix = caps.get(3).unwrap().as_str();
            return vec![
                format!("{}{}", prefix, suffix),
                format!("{}{}{}", prefix, optional, suffix),
            ];
        }
    }
    vec![word.to_string()]
}

fn is_loanword(_word: &str) -> bool { false }

pub fn capitalize_first(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        None => String::new(),
        Some(c) => {
            let upper: String = c.to_uppercase().collect();
            format!("{}{}", upper, chars.as_str())
        }
    }
}

pub fn lower_first(s: &str) -> String {
    // Python's str.lower() lowers all chars; to match "lowered = expanded.lower()"
    s.chars().flat_map(|c| c.to_lowercase()).collect()
}
