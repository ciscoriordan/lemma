// Loads Modern Greek inflection data from dilemma's lookup tables.

use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::time::Instant;

pub struct DilemmaInflections {
    pub lemma_to_forms: HashMap<String, Vec<String>>,
    pub form_confidence: HashMap<String, i64>,
    pub form_to_lemma: HashMap<String, String>,
    pub equivalences: HashMap<String, String>,
    pub reverse_equivalences: HashMap<String, Vec<String>>,
    pub ranked_forms: HashMap<String, Vec<String>>,
    pub polytonic_ranked: HashMap<String, Vec<String>>,
}

impl DilemmaInflections {
    pub fn new() -> Self {
        let mut d = Self {
            lemma_to_forms: HashMap::new(),
            form_confidence: HashMap::new(),
            form_to_lemma: HashMap::new(),
            equivalences: HashMap::new(),
            reverse_equivalences: HashMap::new(),
            ranked_forms: HashMap::new(),
            polytonic_ranked: HashMap::new(),
        };
        d.load_ranked_forms();
        d.load_polytonic_ranked();
        d.load_data();
        d.load_equivalences();
        d
    }

    pub fn available(&self) -> bool {
        !self.lemma_to_forms.is_empty()
    }

    pub fn has_ranked_forms(&self) -> bool {
        !self.ranked_forms.is_empty()
    }

    pub fn has_polytonic_ranked(&self) -> bool {
        !self.polytonic_ranked.is_empty()
    }

    pub fn get_polytonic_variants(&self, form: &str) -> &[String] {
        self.polytonic_ranked.get(form).map(|v| v.as_slice()).unwrap_or(&[])
    }

    pub fn get_ranked_forms(&self, lemma: &str) -> Option<&Vec<String>> {
        if self.ranked_forms.is_empty() {
            return None;
        }
        if let Some(v) = self.ranked_forms.get(lemma) {
            return Some(v);
        }
        for eq in self.equivalent_lemmas(lemma) {
            if eq != lemma {
                if let Some(v) = self.ranked_forms.get(&eq) {
                    return Some(v);
                }
            }
        }
        if let Some(dl) = self.form_to_lemma.get(lemma) {
            if let Some(v) = self.ranked_forms.get(dl) {
                return Some(v);
            }
        }
        None
    }

    pub fn get_inflections(&self, lemma: &str) -> Vec<String> {
        let mut forms: Vec<String> = self.lemma_to_forms.get(lemma).cloned().unwrap_or_default();

        let equivs = self.equivalent_lemmas(lemma);
        for eq in &equivs {
            if eq != lemma {
                if let Some(eq_forms) = self.lemma_to_forms.get(eq) {
                    forms.extend(eq_forms.iter().cloned());
                }
                if !forms.contains(eq) {
                    forms.push(eq.clone());
                }
            }
        }

        if forms.is_empty() {
            if let Some(dl) = self.form_to_lemma.get(lemma) {
                if let Some(dl_forms) = self.lemma_to_forms.get(dl) {
                    forms = dl_forms.clone();
                }
            }
        }

        let mut seen = HashSet::new();
        let mut deduped = Vec::new();
        for f in forms {
            if seen.insert(f.clone()) {
                deduped.push(f);
            }
        }
        deduped
    }

    pub fn get_all_lemmas(&self, word: &str) -> Vec<String> {
        let Some(lemma) = self.form_to_lemma.get(word) else { return Vec::new(); };
        self.equivalent_lemmas(lemma)
    }

    pub fn equivalent_lemmas(&self, lemma: &str) -> Vec<String> {
        let canonical = self.equivalences.get(lemma).cloned().unwrap_or_else(|| lemma.to_string());
        let mut result = vec![canonical.clone()];
        if let Some(variants) = self.reverse_equivalences.get(&canonical) {
            for v in variants {
                if *v != canonical {
                    result.push(v.clone());
                }
            }
        }
        if !result.iter().any(|x| x == lemma) {
            result.push(lemma.to_string());
        }
        result
    }

    pub fn confidence_for(&self, form: &str) -> i64 {
        *self.form_confidence.get(form).unwrap_or(&0)
    }

    pub fn free_inflection_table(&mut self) {
        self.lemma_to_forms.clear();
        self.form_to_lemma.clear();
    }

    fn load_ranked_forms(&mut self) {
        let local = PathBuf::from("data/mg_ranked_forms.json");
        if local.exists() {
            self.read_ranked_forms(&local);
            return;
        }
        if let Some(dir) = find_data_dir() {
            let p = dir.join("mg_ranked_forms.json");
            if p.exists() {
                self.read_ranked_forms(&p);
                return;
            }
        }
        println!("mg_ranked_forms.json not found, will fall back to inverted lookup ranking");
    }

    fn read_ranked_forms(&mut self, path: &Path) {
        println!("Loading pre-ranked forms from {}...", path.display());
        let start = Instant::now();
        let Ok(f) = File::open(path) else { return; };
        let rdr = BufReader::new(f);
        if let Ok(data) = serde_json::from_reader::<_, HashMap<String, Vec<String>>>(rdr) {
            self.ranked_forms = data;
        }
        println!("Loaded pre-ranked forms for {} lemmas in {:.1}s", self.ranked_forms.len(), start.elapsed().as_secs_f64());
    }

    fn load_polytonic_ranked(&mut self) {
        let local = PathBuf::from("data/mg_polytonic_ranked.json");
        if local.exists() {
            self.read_polytonic_ranked(&local);
            return;
        }
        if let Some(dir) = find_data_dir() {
            let p = dir.join("mg_polytonic_ranked.json");
            if p.exists() {
                self.read_polytonic_ranked(&p);
                return;
            }
        }
        println!("mg_polytonic_ranked.json not found, polytonic will use blind generation fallback");
    }

    fn read_polytonic_ranked(&mut self, path: &Path) {
        println!("Loading polytonic ranked variants from {}...", path.display());
        let start = Instant::now();
        let Ok(f) = File::open(path) else { return; };
        let rdr = BufReader::new(f);
        if let Ok(data) = serde_json::from_reader::<_, HashMap<String, Vec<String>>>(rdr) {
            self.polytonic_ranked = data;
        }
        println!("Loaded polytonic variants for {} monotonic forms in {:.1}s", self.polytonic_ranked.len(), start.elapsed().as_secs_f64());
    }

    fn load_equivalences(&mut self) {
        let path = PathBuf::from("data/mg_lemma_equivalences.json");
        if !path.exists() { return; }
        let start = Instant::now();
        let Ok(f) = File::open(&path) else { return; };
        let rdr = BufReader::new(f);
        // Parse via serde_json::Value so we get preserve_order semantics
        // (Python dicts are insertion-ordered; we match that so downstream
        // iteration over reverse_equivalences is deterministic).
        let data: Value = match serde_json::from_reader(rdr) {
            Ok(v) => v,
            Err(_) => return,
        };
        let Some(obj) = data.as_object() else { return; };
        for (variant, canonical_v) in obj {
            let Some(canonical) = canonical_v.as_str() else { continue; };
            self.equivalences.insert(variant.clone(), canonical.to_string());
            self.reverse_equivalences
                .entry(canonical.to_string())
                .or_default()
                .push(variant.clone());
        }
        println!("Loaded {} lemma equivalences in {:.1}s", self.equivalences.len(), start.elapsed().as_secs_f64());
    }

    fn load_data(&mut self) {
        let Some(dir) = find_data_dir() else { return; };
        let scored = dir.join("mg_lookup_scored.json");
        let flat = dir.join("mg_lookup.json");
        if scored.exists() {
            self.load_scored(&scored);
        } else if flat.exists() {
            self.load_flat(&flat);
        }
    }

    fn load_scored(&mut self, path: &Path) {
        println!("Loading dilemma MG lookup data (scored)...");
        let start = Instant::now();
        let Ok(f) = File::open(path) else { return; };
        let rdr = BufReader::new(f);
        let data: Value = match serde_json::from_reader(rdr) {
            Ok(v) => v,
            Err(_) => return,
        };
        let obj = match data.as_object() {
            Some(o) => o,
            None => return,
        };
        println!("Parsed {} form-to-lemma entries in {:.1}s", obj.len(), start.elapsed().as_secs_f64());

        let mut scored_index: HashMap<String, Vec<(String, i64)>> = HashMap::new();
        for (form, info) in obj {
            let info_obj = match info.as_object() {
                Some(o) => o,
                None => continue,
            };
            let lemma = match info_obj.get("lemma").and_then(|v| v.as_str()) {
                Some(l) => l.to_string(),
                None => continue,
            };
            let confidence = info_obj.get("confidence").and_then(|v| v.as_i64()).unwrap_or(0);
            self.form_to_lemma.insert(form.clone(), lemma.clone());
            if *form == lemma { continue; }
            if form.contains(' ') { continue; }
            scored_index.entry(lemma).or_default().push((form.clone(), confidence));
            self.form_confidence.insert(form.clone(), confidence);
        }
        drop(data);

        for (lemma, mut form_list) in scored_index {
            form_list.sort_by(|a, b| b.1.cmp(&a.1));
            self.lemma_to_forms.insert(lemma, form_list.into_iter().map(|(f, _)| f).collect());
        }

        println!("Built inflection table for {} lemmas", self.lemma_to_forms.len());
    }

    fn load_flat(&mut self, path: &Path) {
        println!("Loading dilemma MG lookup data...");
        let start = Instant::now();
        let Ok(f) = File::open(path) else { return; };
        let rdr = BufReader::new(f);
        let data: HashMap<String, String> = match serde_json::from_reader(rdr) {
            Ok(v) => v,
            Err(_) => return,
        };
        println!("Parsed {} form-to-lemma entries in {:.1}s", data.len(), start.elapsed().as_secs_f64());

        for (form, lemma) in data {
            self.form_to_lemma.insert(form.clone(), lemma.clone());
            if form == lemma { continue; }
            if form.contains(' ') { continue; }
            self.lemma_to_forms.entry(lemma).or_default().push(form);
        }
        println!("Built inflection table for {} lemmas", self.lemma_to_forms.len());
    }
}

pub fn find_data_dir() -> Option<PathBuf> {
    let mut dir_path = std::env::var("DILEMMA_DATA_DIR").unwrap_or_default();
    if dir_path.is_empty() {
        if let Ok(contents) = fs::read_to_string(".env") {
            for line in contents.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') { continue; }
                if let Some((k, v)) = line.split_once('=') {
                    if k.trim() == "DILEMMA_DATA_DIR" {
                        dir_path = v.trim().to_string();
                    }
                }
            }
        }
    }
    if dir_path.is_empty() { return None; }
    let p = PathBuf::from(dir_path);
    if !p.is_dir() { return None; }
    Some(p)
}
