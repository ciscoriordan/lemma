// Processes dictionary entries from JSONL data.

use crate::declension::{expand_declension, is_declension_template, strip_template_prefix};
use crate::dilemma::DilemmaInflections;
use rayon::prelude::*;
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
        /// Remove multiple keys in bulk. Faster than calling `remove` in a
        /// loop when removing many keys because the `keys` vector is
        /// rewritten once instead of linearly compacted per removal.
        pub fn remove_many(&mut self, keys_to_remove: &std::collections::HashSet<K>) {
            for k in keys_to_remove {
                self.map.remove(k);
            }
            self.keys.retain(|k| !keys_to_remove.contains(k));
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

pub struct LineResult {
    pub line_no: usize,
    pub skipped: bool,
    pub parse_error: Option<String>,
    pub word: String,
    pub pos: String,
    pub definitions: Vec<String>,
    pub examples: Vec<Option<Example>>,
    pub inflections: Vec<String>,
    pub etymology: Option<String>,
    pub head_expansion: Option<String>,
    pub expanded_from_template: bool,
    pub form_of_targets: Vec<String>,
}

fn empty_result(line_no: usize) -> LineResult {
    LineResult {
        line_no,
        skipped: true,
        parse_error: None,
        word: String::new(),
        pos: String::new(),
        definitions: Vec::new(),
        examples: Vec::new(),
        inflections: Vec::new(),
        etymology: None,
        head_expansion: None,
        expanded_from_template: false,
        form_of_targets: Vec::new(),
    }
}

fn build_line_result(line_no: usize, raw_line: &str, source_lang: &str) -> Option<LineResult> {
    let line = raw_line.trim();
    if line.is_empty() { return None; }

    let entry: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(e) => {
            return Some(LineResult {
                line_no,
                skipped: false,
                parse_error: Some(e.to_string()),
                ..empty_result(line_no)
            });
        }
    };

    if !is_greek_entry(&entry) { return None; }

    let word = match entry.get("word").and_then(|v| v.as_str()) {
        Some(w) => w.to_string(),
        None => return None,
    };
    if !contains_greek(&word) { return None; }
    if contains_non_greek_script(&word) { return None; }

    // Mark that the line passed the processed-count threshold so the caller
    // can count it (matches Python's `processed_count += 1` placement).
    let mut result_shell = LineResult {
        line_no, skipped: true, parse_error: None, ..empty_result(line_no)
    };
    result_shell.word = word.clone(); // non-empty signals "counted"

    let pos = entry.get("pos").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    if should_skip_pos(&pos) { return Some(result_shell); }
    if word.starts_with('-') || word.ends_with('-') { return Some(result_shell); }
    if word.chars().count() == 1 {
        let lower: String = word.chars().flat_map(|c| c.to_lowercase()).collect();
        if !matches!(lower.as_str(), "ω" | "ο" | "α" | "η") {
            return Some(result_shell);
        }
    }

    // Build the definitions + examples + form_of targets + etymology + inflections.
    let mut definitions: Vec<String> = Vec::new();
    let mut form_of_targets: Vec<String> = Vec::new();
    let mut examples: Vec<Option<Example>> = Vec::new();
    let mut expanded_from_template = false;

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

    let inflections = collect_inflections_from(&entry, &word, source_lang);

    if source_lang == "el" {
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

    Some(LineResult {
        line_no,
        skipped: false,
        parse_error: None,
        word,
        pos,
        definitions,
        examples,
        inflections,
        etymology,
        head_expansion,
        expanded_from_template,
        form_of_targets,
    })
}

pub fn collect_inflections_from(entry: &Value, word: &str, source_lang: &str) -> Vec<String> {
    let mut inflections: Vec<String> = Vec::new();
    let mut inflection_set: HashSet<String> = HashSet::new();

    fn add(form: &str, inflections: &mut Vec<String>, set: &mut HashSet<String>) {
        if set.insert(form.to_string()) {
            inflections.push(form.to_string());
        }
    }

    if let Some(forms) = entry.get("forms").and_then(|v| v.as_array()) {
        for form in forms {
            if let Some(obj) = form.as_object() {
                let form_word = obj.get("form").and_then(|v| v.as_str());
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

    if source_lang == "el" {
        if let Some(templates) = entry.get("head_templates").and_then(|v| v.as_array()) {
            for t in templates {
                if let Some(name) = t.get("name").and_then(|v| v.as_str()) {
                    if is_declension_template(name) {
                        let pattern_name = strip_template_prefix(name);
                        for f in expand_declension(word, pattern_name) {
                            add(&f, &mut inflections, &mut inflection_set);
                        }
                    }
                }
            }
        }
    }
    inflections
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

        let f = match File::open(&self.filename) {
            Ok(f) => f,
            Err(e) => {
                eprintln!("Error: could not open {}: {}", self.filename, e);
                return;
            }
        };
        let reader = BufReader::new(f);

        // Read all lines up front so we can parse in parallel while
        // preserving sequential merge order (which Python relies on for
        // duplicate-POS merging and first-seen form_of target resolution).
        let mut lines: Vec<String> = Vec::new();
        for l in reader.lines() {
            match l {
                Ok(l) => lines.push(l),
                Err(_) => lines.push(String::new()),
            }
        }
        let line_count = lines.len() as u64;

        // Snapshot extraction date from the first line's meta field (pre-parallel).
        if self.extraction_date.is_none() {
            for line in lines.iter().take(5) {
                let trimmed = line.trim();
                if trimmed.is_empty() { continue; }
                if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
                    if let Some(meta) = v.get("meta").and_then(|v| v.as_object()) {
                        for key in ["extracted", "date", "generated", "generation_time", "timestamp", "created"] {
                            if let Some(val) = meta.get(key).and_then(|v| v.as_str()) {
                                self.extraction_date = Some(val.to_string());
                                break;
                            }
                        }
                        if self.extraction_date.is_some() { break; }
                    }
                }
            }
        }

        let source_lang = self.source_lang.clone();

        // Parallel parse + per-line build. Each line produces an Option<LineResult>.
        let results: Vec<Option<LineResult>> = lines
            .par_iter()
            .enumerate()
            .map(|(idx, raw_line)| build_line_result(idx, raw_line, &source_lang))
            .collect();

        let mut error_count: u64 = 0;
        let mut processed_count: u64 = 0;

        for r in results {
            let Some(r) = r else { continue; };
            if let Some(msg) = r.parse_error {
                error_count += 1;
                if error_count <= 10 {
                    println!("JSON parse error on line {}: {}", r.line_no + 1, msg);
                }
                continue;
            }
            // Python increments processed_count after greek-script checks but
            // before the POS/short-word skips. A non-empty word signals the
            // line passed the first set of checks.
            if !r.word.is_empty() {
                processed_count += 1;
            }
            if r.skipped { continue; }
            self.merge_line_result(r);
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

    fn merge_line_result(&mut self, r: LineResult) {
        let word = r.word;
        let pos = r.pos;

        if !self.entries.contains_key(&word) {
            self.entries.insert(word.clone(), Vec::new());
        }
        let list = self.entries.get_mut(&word).unwrap();
        let existing_idx = list.iter().position(|e| e.pos == pos);

        if let Some(idx) = existing_idx {
            let existing = &mut list[idx];
            while existing.examples.len() < existing.definitions.len() {
                existing.examples.push(None);
            }
            let existing_defs_set: HashSet<String> = existing.definitions.iter().cloned().collect();
            let mut seen = existing_defs_set;
            for (d, ex) in r.definitions.into_iter().zip(r.examples.into_iter()) {
                if !seen.contains(&d) {
                    seen.insert(d.clone());
                    existing.definitions.push(d);
                    existing.examples.push(ex);
                }
            }
            existing.inflections.extend(r.inflections);
            let mut seen_inf = HashSet::new();
            existing.inflections.retain(|i| seen_inf.insert(i.clone()));
            if existing.etymology.is_none() {
                existing.etymology = r.etymology;
            }
            if !existing.expanded_from_template {
                existing.expanded_from_template = r.expanded_from_template;
            }
            if existing.head_expansion.is_none() && r.head_expansion.is_some() {
                existing.head_expansion = r.head_expansion;
            }
            for t in r.form_of_targets {
                if !existing.form_of_targets.contains(&t) {
                    existing.form_of_targets.push(t);
                }
            }
        } else {
            list.push(Entry {
                pos,
                definitions: r.definitions,
                examples: r.examples,
                etymology: r.etymology,
                head_expansion: r.head_expansion,
                inflections: r.inflections,
                expanded_from_template: r.expanded_from_template,
                form_of_targets: r.form_of_targets,
            });
        }
    }

    #[allow(dead_code)]
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
        if self.source_lang == "el" {
            if let Some(templates) = entry.get("head_templates").and_then(|v| v.as_array()) {
                for t in templates {
                    if let Some(name) = t.get("name").and_then(|v| v.as_str()) {
                        if is_declension_template(name) {
                            let pattern_name = strip_template_prefix(name);
                            for f in expand_declension(word, pattern_name) {
                                add(&f, &mut inflections, &mut inflection_set);
                            }
                        }
                    }
                }
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
    // Python's str.lower() is context-sensitive for Greek capital sigma (Σ),
    // lowering to ς at the end of a word and σ elsewhere. Rust's stdlib
    // char::to_lowercase() is not context-sensitive, so we replicate the rule.
    py_lower(s)
}

// Mirrors CPython str.lower() Final_Sigma rule (Unicode SpecialCasing.txt, condition Final_Sigma, standard reference D135).
pub fn py_lower(s: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let n = chars.len();
    let mut out = String::with_capacity(s.len());
    for (i, &c) in chars.iter().enumerate() {
        if c == 'Σ' {
            // Final if this is the last cased letter in the word-segment, which
            // Python approximates as: no following cased letter in the string
            // (Σ→ς when it's the final sigma of a "word"). CPython's rule is
            // the Unicode Final_Sigma context: Σ is final if preceded by a
            // cased letter and not followed by a cased letter.
            let before_cased = chars[..i].iter().rev().any(|ch| is_cased(*ch));
            let after_cased = chars[i + 1..].iter().any(|ch| is_cased(*ch));
            let preceded_immediately = i > 0 && is_cased(chars[i - 1]);
            let _ = preceded_immediately;
            let _ = n;
            if before_cased && !after_cased {
                out.push('ς');
            } else {
                out.push('σ');
            }
        } else {
            for lc in c.to_lowercase() {
                out.push(lc);
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::py_lower;

    // Each expected value below was produced by running CPython 3
    // `str.lower()` on the exact input string and pasting the result
    // verbatim. Do not hand-edit expected values: regenerate them from
    // CPython if a fixture changes.
    #[test]
    fn py_lower_matches_cpython_str_lower() {
        let cases: &[(&str, &str, &str)] = &[
            // Word-final sigma: plain capital noun (Σ -> ς).
            ("ΛΟΓΟΣ", "λογος", "word-final sigma"),
            // Two medial sigmas plus one final: ΣΣ mid-word stay as σσ,
            // trailing Σ becomes ς.
            ("ΟΔΥΣΣΕΥΣ", "οδυσσευς", "two medial + final sigma"),
            // Common noun with final sigma.
            ("ΑΝΘΡΩΠΟΣ", "ανθρωπος", "word-final sigma in common noun"),
            // No sigma at all - plural of the above.
            ("ΑΝΘΡΩΠΟΙ", "ανθρωποι", "no sigma present"),
            // Medial sigma + final sigma.
            ("ΚΟΣΜΟΣ", "κοσμος", "medial + final sigma"),
            // Double sigma mid-word, no trailing sigma.
            ("ΘΑΛΑΣΣΑ", "θαλασσα", "double sigma mid-word"),
            // Standalone capital sigma: CPython returns σ (not ς) because
            // Final_Sigma requires a *preceding* cased character, and a
            // lone Σ has none.
            ("Σ", "σ", "single standalone capital sigma"),
            // Initial sigma (medial) plus final sigma.
            ("ΣΟΦΟΣ", "σοφος", "initial + final sigma"),
            // Abbreviation with trailing period: the '.' is not cased, so
            // Final_Sigma still fires and the Σ becomes ς.
            ("ΑΡΣ.", "αρς.", "sigma before non-cased '.' still final"),
            // Already-lowercase polytonic word with final sigma and a
            // trailing period - should be identity (no capitals).
            ("ἀνθρώπους.", "ἀνθρώπους.", "polytonic lowercase + period"),
            // Already-lowercase polytonic word, final sigma preserved.
            ("πολύς", "πολύς", "lowercase polytonic identity"),
            // All-capitals monotonic -> lowercase with final sigma.
            ("ΠΟΛΥΣ", "πολυς", "capital monotonic -> final sigma"),
            // Plain ASCII fast path.
            ("hello", "hello", "plain ASCII lowercase identity"),
            // Mixed-case ASCII with a space.
            ("Hello World", "hello world", "mixed-case ASCII with space"),
            // Capital with accent and final sigma (exercises both the
            // accent fold and the Final_Sigma rule in one word).
            ("ΆΝΘΡΩΠΟΣ", "άνθρωπος", "accented capital + final sigma"),
        ];
        for (input, expected, label) in cases {
            let got = py_lower(input);
            assert_eq!(
                &got, expected,
                "py_lower({:?}) mismatch ({}): expected {:?}, got {:?}",
                input, label, expected, got
            );
        }
    }
}

fn is_cased(c: char) -> bool {
    c.is_alphabetic() && (c.is_lowercase() || c.is_uppercase())
}
