// Generate Modern Greek lemma equivalences from dilemma + Wiktionary data.
//
// Finds cases where Wiktionary and dilemma disagree on canonical lemma forms,
// groups equivalent lemmas, and picks the best canonical form using corpus
// frequency as a tiebreaker.
//
// Output: data/mg_lemma_equivalences.json
//
// Usage:
//     cargo run --release --bin generate_mg_equivalences

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use lemma::dilemma::find_data_dir;
use regex::Regex;
use serde_json::Value;

fn main() -> ExitCode {
    println!("{}", "=".repeat(60));
    println!("MG Lemma Equivalence Generator");
    println!("{}", "=".repeat(60));

    // Step 1: Find dilemma data directory.
    let data_dir = match find_data_dir() {
        Some(d) => d,
        None => {
            eprintln!("Error: DILEMMA_DATA_DIR not set or not found");
            eprintln!("Set it in .env or as an environment variable");
            return ExitCode::from(1);
        }
    };
    println!("Dilemma data dir: {}", data_dir.display());
    println!();

    // Step 2: Load data.
    let frequencies = load_frequency_data();
    println!();
    let WiktData {
        headwords,
        true_headwords,
        form_of_pairs,
        variant_pairs,
    } = match load_wikt_data() {
        Some(d) => d,
        None => return ExitCode::from(1),
    };
    println!();
    let DilemmaLookup {
        form_to_lemma,
        lemma_to_forms,
        dilemma_lemmas,
    } = match load_dilemma_form_to_lemma(&data_dir) {
        Some(d) => d,
        None => return ExitCode::from(1),
    };
    println!();

    // Step 3: Find equivalence pairs.
    let pairs = find_equivalences(
        &headwords,
        &true_headwords,
        &form_of_pairs,
        &variant_pairs,
        &form_to_lemma,
        &dilemma_lemmas,
    );
    println!();

    // Step 4: Build equivalence groups.
    let groups = build_equivalence_groups(&pairs);
    println!("Built {} equivalence groups", groups.len());

    // Group size distribution.
    let mut size_dist: BTreeMap<usize, usize> = BTreeMap::new();
    for g in &groups {
        *size_dist.entry(g.len()).or_insert(0) += 1;
    }
    for (size, count) in &size_dist {
        println!("  Groups of size {}: {}", size, count);
    }
    println!();

    // Step 5: Pick canonical for each group, build variant->canonical map.
    let mut equivalences: BTreeMap<String, String> = BTreeMap::new();
    let mut canonical_set: HashSet<String> = HashSet::new();
    for group in &groups {
        let canonical = pick_canonical(
            group,
            &frequencies,
            &true_headwords,
            &dilemma_lemmas,
            &lemma_to_forms,
        );
        canonical_set.insert(canonical.clone());
        for member in group {
            if member != &canonical {
                equivalences.insert(member.clone(), canonical.clone());
            }
        }
    }

    println!(
        "Generated {} variant -> canonical mappings",
        equivalences.len()
    );
    println!("Covering {} canonical forms", canonical_set.len());
    println!();

    // Step 6: Count recovered inflections.
    let recovered = count_recovered_inflections(&equivalences, &lemma_to_forms);
    println!(
        "Estimated inflections recovered through equivalences: {}",
        recovered
    );
    println!();

    // Step 7: Show top pairs by canonical frequency.
    println!("Top 30 equivalence pairs (by canonical frequency):");
    let mut top_pairs: Vec<(String, String, i64, i64)> = equivalences
        .iter()
        .map(|(variant, canonical)| {
            let can_freq = lookup_freq(&frequencies, canonical);
            let var_freq = lookup_freq(&frequencies, variant);
            (canonical.clone(), variant.clone(), can_freq, var_freq)
        })
        .collect();
    top_pairs.sort_by(|a, b| b.2.cmp(&a.2));
    for (canonical, variant, can_freq, var_freq) in top_pairs.iter().take(30) {
        let var_forms = lemma_to_forms
            .get(variant)
            .map(|v| v.len())
            .unwrap_or(0);
        let can_forms = lemma_to_forms
            .get(canonical)
            .map(|v| v.len())
            .unwrap_or(0);
        println!(
            "  {} -> {}  (freq: {} vs {},  forms: {} vs {})",
            variant,
            canonical,
            format_int(*var_freq),
            format_int(*can_freq),
            var_forms,
            can_forms,
        );
    }
    println!();

    // Step 8: Write output.
    let output_path = PathBuf::from("data").join("mg_lemma_equivalences.json");
    if let Err(e) = write_equivalences(&output_path, &equivalences) {
        eprintln!("Error writing {}: {}", output_path.display(), e);
        return ExitCode::from(1);
    }
    println!(
        "Wrote {} equivalences to {}",
        equivalences.len(),
        output_path.display()
    );

    // Summary.
    println!();
    println!("{}", "=".repeat(60));
    println!("Summary");
    println!("{}", "=".repeat(60));
    println!(
        "  Wikt headwords:        {} ({} true lemmas)",
        format_int(headwords.len() as i64),
        format_int(true_headwords.len() as i64),
    );
    println!(
        "  Dilemma lemmas:        {}",
        format_int(dilemma_lemmas.len() as i64)
    );
    println!(
        "  Equivalence groups:    {}",
        format_int(groups.len() as i64)
    );
    println!(
        "  Variant -> canonical:  {}",
        format_int(equivalences.len() as i64)
    );
    println!(
        "  Inflections recovered: {}",
        format_int(recovered as i64)
    );

    ExitCode::SUCCESS
}

// ----------------- Frequency loading -----------------

fn load_frequency_data() -> HashMap<String, i64> {
    let path = PathBuf::from("data").join("el_full.txt");
    let mut freq = HashMap::new();
    if !path.exists() {
        println!("Warning: frequency file not found at {}", path.display());
        return freq;
    }
    let start = Instant::now();
    let f = match File::open(&path) {
        Ok(f) => f,
        Err(_) => return freq,
    };
    let rdr = BufReader::new(f);
    for line in rdr.lines().map_while(Result::ok) {
        let parts: Vec<&str> = line.trim().splitn(2, ' ').collect();
        if parts.len() != 2 {
            continue;
        }
        let word = parts[0];
        if let Ok(count) = parts[1].parse::<i64>() {
            freq.insert(word.to_string(), count);
        }
    }
    println!(
        "Loaded {} frequency entries in {:.1}s",
        freq.len(),
        start.elapsed().as_secs_f64()
    );
    freq
}

fn lookup_freq(freq: &HashMap<String, i64>, word: &str) -> i64 {
    if let Some(v) = freq.get(word) {
        return *v;
    }
    // Match Python: also try .lower(). Use py_lower for Final_Sigma rule.
    let lower = lemma::entry_processor::py_lower(word);
    *freq.get(&lower).unwrap_or(&0)
}

// ----------------- Wiktionary loading -----------------

struct WiktData {
    headwords: HashSet<String>,
    true_headwords: HashSet<String>,
    form_of_pairs: Vec<(String, String, String)>, // (form_word, target, pos)
    variant_pairs: HashSet<(String, String)>,     // (form_word, target) where gloss says variant
}

fn load_wikt_data() -> Option<WiktData> {
    // Look for the Greek-source Wiktionary dump in the project root. Prefer
    // the canonical undated filename `greek_data_el.jsonl`; if it isn't
    // there, fall through to any legacy `greek_data_el_*.jsonl` (older
    // dated dumps from before the no-dates rule).
    let canonical = PathBuf::from("greek_data_el.jsonl");
    let latest: PathBuf = if canonical.exists() {
        canonical
    } else {
        let mut legacy: Vec<PathBuf> = match fs::read_dir(".") {
            Ok(it) => it
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| {
                    p.file_name()
                        .map(|n| {
                            let n = n.to_string_lossy();
                            n.starts_with("greek_data_el_") && n.ends_with(".jsonl")
                        })
                        .unwrap_or(false)
                })
                .collect(),
            Err(_) => Vec::new(),
        };
        if legacy.is_empty() {
            eprintln!("Error: no greek_data_el.jsonl (or legacy greek_data_el_*.jsonl) file found");
            return None;
        }
        legacy.sort();
        legacy.pop().unwrap()
    };

    println!(
        "Loading Wiktionary data from {}...",
        latest.file_name().unwrap().to_string_lossy()
    );
    let start = Instant::now();

    // Pattern matching "another form of X" in Greek Wiktionary glosses.
    // Distinguishes genuine variant/alternative forms from paradigm inflections.
    let variant_re = Regex::new(
        r"(?i)(άλλη μορφή|εναλλακτικός τύπος|εναλλακτική μορφή|παραλλαγή|variant|alternative)",
    )
    .unwrap();

    let mut headwords: HashSet<String> = HashSet::new();
    let mut true_headwords: HashSet<String> = HashSet::new();
    let mut form_of_pairs: Vec<(String, String, String)> = Vec::new();
    let mut variant_pairs: HashSet<(String, String)> = HashSet::new();
    let mut line_count = 0usize;

    let f = match File::open(latest) {
        Ok(f) => f,
        Err(_) => return None,
    };
    let rdr = BufReader::new(f);
    for line in rdr.lines().map_while(Result::ok) {
        line_count += 1;
        let trimmed = line.trim();
        let entry: Value = match serde_json::from_str(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let obj = match entry.as_object() {
            Some(o) => o,
            None => continue,
        };

        // Filter to Greek entries.
        let lang_code = obj.get("lang_code").and_then(|v| v.as_str()).unwrap_or("");
        let lang = obj.get("lang").and_then(|v| v.as_str()).unwrap_or("");
        if lang_code != "el" && lang != "Greek" && lang != "Ελληνικά" {
            continue;
        }

        let word = match obj.get("word").and_then(|v| v.as_str()) {
            Some(w) if !w.contains(' ') && !w.is_empty() => w.to_string(),
            _ => continue,
        };

        let senses = match obj.get("senses").and_then(|v| v.as_array()) {
            Some(s) if !s.is_empty() => s,
            _ => continue,
        };

        let has_gloss = senses
            .iter()
            .any(|s| s.get("glosses").and_then(|g| g.as_array()).map(|a| !a.is_empty()).unwrap_or(false));
        if !has_gloss {
            continue;
        }

        headwords.insert(word.clone());
        let pos = obj
            .get("pos")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        // Check if ALL senses are form_of.
        let all_form_of = senses.iter().all(|s| {
            s.get("form_of")
                .and_then(|f| f.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false)
        });

        if !all_form_of {
            true_headwords.insert(word.clone());
        }

        // Collect form_of relationships from each sense.
        for sense in senses {
            let Some(fof_list) = sense.get("form_of").and_then(|v| v.as_array()) else {
                continue;
            };
            let glosses = sense.get("glosses").and_then(|v| v.as_array());
            let gloss = glosses
                .and_then(|a| a.first())
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let is_variant = variant_re.is_match(gloss);

            for (i, fof) in fof_list.iter().enumerate() {
                let target = match fof.get("word").and_then(|v| v.as_str()) {
                    Some(t) => t,
                    None => continue,
                };
                if target == word || target.contains(' ') || target.is_empty() {
                    continue;
                }
                form_of_pairs.push((word.clone(), target.to_string(), pos.clone()));
                // For variant glosses, only pair with the first form_of target
                // (the one the variant refers to). Later targets are paradigm
                // references.
                if is_variant && i == 0 {
                    variant_pairs.insert((word.clone(), target.to_string()));
                }
            }
        }
    }

    println!(
        "Found {} headwords ({} true lemmas), {} form_of pairs ({} variant), from {} lines in {:.1}s",
        headwords.len(),
        true_headwords.len(),
        form_of_pairs.len(),
        variant_pairs.len(),
        line_count,
        start.elapsed().as_secs_f64()
    );

    Some(WiktData {
        headwords,
        true_headwords,
        form_of_pairs,
        variant_pairs,
    })
}

// ----------------- Dilemma loading -----------------

struct DilemmaLookup {
    form_to_lemma: HashMap<String, String>,
    lemma_to_forms: HashMap<String, Vec<String>>,
    dilemma_lemmas: HashSet<String>,
}

fn load_dilemma_form_to_lemma(data_dir: &std::path::Path) -> Option<DilemmaLookup> {
    let scored_path = data_dir.join("mg_lookup_scored.json");
    if !scored_path.exists() {
        eprintln!("Error: {} not found", scored_path.display());
        return None;
    }

    println!("Loading dilemma lookup data...");
    let start = Instant::now();
    let f = match File::open(&scored_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Cannot open {}: {}", scored_path.display(), e);
            return None;
        }
    };
    let rdr = BufReader::new(f);
    let raw: Value = match serde_json::from_reader(rdr) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Error parsing {}: {}", scored_path.display(), e);
            return None;
        }
    };
    let obj = match raw {
        Value::Object(m) => m,
        _ => return None,
    };
    println!(
        "Loaded {} entries in {:.1}s",
        obj.len(),
        start.elapsed().as_secs_f64()
    );

    let mut form_to_lemma: HashMap<String, String> = HashMap::with_capacity(obj.len());
    for (form, info) in obj {
        let info_obj = match info.as_object() {
            Some(o) => o,
            None => continue,
        };
        if let Some(lemma) = info_obj.get("lemma").and_then(|v| v.as_str()) {
            form_to_lemma.insert(form, lemma.to_string());
        }
    }

    // Build lemma -> forms (excluding lemma==form and multi-word forms).
    let mut lemma_to_forms: HashMap<String, Vec<String>> = HashMap::new();
    for (form, lemma) in &form_to_lemma {
        if form != lemma && !form.contains(' ') {
            lemma_to_forms
                .entry(lemma.clone())
                .or_default()
                .push(form.clone());
        }
    }

    let dilemma_lemmas: HashSet<String> = form_to_lemma.values().cloned().collect();
    println!("Unique dilemma lemmas: {}", dilemma_lemmas.len());

    Some(DilemmaLookup {
        form_to_lemma,
        lemma_to_forms,
        dilemma_lemmas,
    })
}

// ----------------- Equivalence pair finding -----------------

fn find_equivalences(
    headwords: &HashSet<String>,
    _true_headwords: &HashSet<String>,
    form_of_pairs: &[(String, String, String)],
    variant_pairs: &HashSet<(String, String)>,
    form_to_lemma: &HashMap<String, String>,
    dilemma_lemmas: &HashSet<String>,
) -> HashSet<(String, String)> {
    let mut pairs: HashSet<(String, String)> = HashSet::new();

    // Approach 1: Variant form cross-reference (Wikt variant + dilemma agree).
    let mut variant_cross_ref = 0usize;
    for (form_word, target) in variant_pairs {
        let dilemma_lemma = match form_to_lemma.get(form_word) {
            Some(l) => l,
            None => continue,
        };
        if dilemma_lemma != target {
            continue;
        }
        if !headwords.contains(target) {
            continue;
        }
        if pairs.insert((form_word.clone(), target.clone())) {
            variant_cross_ref += 1;
        }
    }

    // Approach 2: Wiktionary form_of between dilemma lemmas (verb/adj only).
    let mut wikt_based = 0usize;
    let equiv_pos: HashSet<&str> = ["verb", "adj"].into_iter().collect();
    for (form_word, target, pos) in form_of_pairs {
        if !equiv_pos.contains(pos.as_str()) {
            continue;
        }
        if !headwords.contains(form_word) || !headwords.contains(target) {
            continue;
        }
        let form_is_dilemma_lemma = form_to_lemma.get(form_word) == Some(form_word);
        let target_is_dilemma_lemma = form_to_lemma.get(target) == Some(target);
        if form_is_dilemma_lemma && target_is_dilemma_lemma {
            if pairs.insert((form_word.clone(), target.clone())) {
                wikt_based += 1;
            }
        }
    }

    // Approach 3: Variant form without dilemma confirmation.
    let mut variant_only = 0usize;
    for (form_word, target) in variant_pairs {
        if pairs.contains(&(form_word.clone(), target.clone())) {
            continue;
        }
        if !headwords.contains(form_word) || !headwords.contains(target) {
            continue;
        }
        if !dilemma_lemmas.contains(target) {
            continue;
        }
        if pairs.insert((form_word.clone(), target.clone())) {
            variant_only += 1;
        }
    }

    println!(
        "Found {} equivalence pairs ({} variant+dilemma, {} wikt-form_of, {} variant-only)",
        pairs.len(),
        variant_cross_ref,
        wikt_based,
        variant_only
    );
    pairs
}

// ----------------- Equivalence grouping (union-find) -----------------

fn build_equivalence_groups(pairs: &HashSet<(String, String)>) -> Vec<Vec<String>> {
    let mut parent: HashMap<String, String> = HashMap::new();

    fn find(parent: &mut HashMap<String, String>, x: &str) -> String {
        let mut current = x.to_string();
        while let Some(p) = parent.get(&current) {
            if p == &current {
                break;
            }
            let next = p.clone();
            // Path compression: jump to grandparent.
            if let Some(grand) = parent.get(&next).cloned() {
                parent.insert(current.clone(), grand);
            }
            current = next;
        }
        parent.entry(current.clone()).or_insert(current.clone());
        current
    }

    fn union(parent: &mut HashMap<String, String>, a: &str, b: &str) {
        let ra = find(parent, a);
        let rb = find(parent, b);
        if ra != rb {
            parent.insert(ra, rb);
        }
    }

    for (a, b) in pairs {
        if !parent.contains_key(a) {
            parent.insert(a.clone(), a.clone());
        }
        if !parent.contains_key(b) {
            parent.insert(b.clone(), b.clone());
        }
        union(&mut parent, a, b);
    }

    let mut groups: HashMap<String, HashSet<String>> = HashMap::new();
    let all_words: HashSet<String> = pairs
        .iter()
        .flat_map(|(a, b)| [a.clone(), b.clone()])
        .collect();
    for w in &all_words {
        let root = find(&mut parent, w);
        groups.entry(root).or_default().insert(w.clone());
    }

    const MAX_GROUP_SIZE: usize = 10;
    let mut group_list: Vec<Vec<String>> = Vec::new();
    let mut oversized = 0usize;
    for members in groups.into_values() {
        if members.len() <= MAX_GROUP_SIZE {
            let mut sorted: Vec<String> = members.into_iter().collect();
            sorted.sort();
            group_list.push(sorted);
        } else {
            oversized += 1;
        }
    }
    if oversized > 0 {
        println!(
            "  Dropped {} oversized groups (>{} members)",
            oversized, MAX_GROUP_SIZE
        );
    }
    group_list.sort_by(|a, b| a[0].cmp(&b[0]));
    group_list
}

// ----------------- Canonical picking -----------------

fn pick_canonical(
    group: &[String],
    frequencies: &HashMap<String, i64>,
    true_headwords: &HashSet<String>,
    dilemma_lemmas: &HashSet<String>,
    lemma_to_forms: &HashMap<String, Vec<String>>,
) -> String {
    // Priority (highest first):
    // 1. Is a true Wikt headword (independent definitions)
    // 2. Is a dilemma lemma (maps to itself in dilemma)
    // 3. Has more inflection forms in dilemma (bigger paradigm)
    // 4. Higher corpus frequency (tiebreaker)
    // 5. Alphabetically first (final tiebreaker)
    let mut ranked: Vec<&String> = group.iter().collect();
    ranked.sort_by(|a, b| {
        let key_a = sort_key(a, frequencies, true_headwords, dilemma_lemmas, lemma_to_forms);
        let key_b = sort_key(b, frequencies, true_headwords, dilemma_lemmas, lemma_to_forms);
        key_a.cmp(&key_b)
    });
    ranked[0].clone()
}

// Build a sort key matching Python's pick_canonical:
//   (-is_true_hw, -is_dilemma_lemma, -n_forms, -freq, word)
// Negate the integer fields so smaller key sorts first while preferring larger
// values.
fn sort_key(
    word: &str,
    frequencies: &HashMap<String, i64>,
    true_headwords: &HashSet<String>,
    dilemma_lemmas: &HashSet<String>,
    lemma_to_forms: &HashMap<String, Vec<String>>,
) -> (i64, i64, i64, i64, String) {
    let is_true_hw = if true_headwords.contains(word) { 1 } else { 0 };
    let is_dilemma_lemma = if dilemma_lemmas.contains(word) { 1 } else { 0 };
    let n_forms = lemma_to_forms.get(word).map(|v| v.len() as i64).unwrap_or(0);
    let freq = lookup_freq(frequencies, word);
    (-is_true_hw, -is_dilemma_lemma, -n_forms, -freq, word.to_string())
}

// ----------------- Recovered inflection counting -----------------

fn count_recovered_inflections(
    equivalences: &BTreeMap<String, String>,
    lemma_to_forms: &HashMap<String, Vec<String>>,
) -> usize {
    let mut recovered = 0usize;
    for (variant, canonical) in equivalences {
        let variant_forms: HashSet<&String> = lemma_to_forms
            .get(variant)
            .map(|v| v.iter().collect())
            .unwrap_or_default();
        let canonical_forms: HashSet<&String> = lemma_to_forms
            .get(canonical)
            .map(|v| v.iter().collect())
            .unwrap_or_default();
        let new_forms: HashSet<&&String> = variant_forms.difference(&canonical_forms).collect();
        recovered += new_forms.len();
    }
    recovered
}

// ----------------- Output writing -----------------
//
// Match Python's `json.dump(..., ensure_ascii=False, indent=2, sort_keys=True)`
// byte-for-byte:
//   - 2-space indent
//   - keys sorted (BTreeMap iteration is sorted)
//   - non-ASCII passed through as UTF-8 (no \uXXXX escaping)
//   - trailing newline omitted (Python's json.dump does not add one)

fn write_equivalences(
    path: &std::path::Path,
    equivalences: &BTreeMap<String, String>,
) -> std::io::Result<()> {
    let mut f = File::create(path)?;
    write!(f, "{{")?;
    let mut first = true;
    for (k, v) in equivalences {
        if !first {
            write!(f, ",")?;
        }
        first = false;
        write!(f, "\n  ")?;
        write_json_string(&mut f, k)?;
        write!(f, ": ")?;
        write_json_string(&mut f, v)?;
    }
    if !equivalences.is_empty() {
        write!(f, "\n")?;
    }
    write!(f, "}}")?;
    Ok(())
}

fn write_json_string(w: &mut impl Write, s: &str) -> std::io::Result<()> {
    write!(w, "\"")?;
    for c in s.chars() {
        match c {
            '"' => write!(w, "\\\"")?,
            '\\' => write!(w, "\\\\")?,
            '\n' => write!(w, "\\n")?,
            '\r' => write!(w, "\\r")?,
            '\t' => write!(w, "\\t")?,
            '\u{08}' => write!(w, "\\b")?,
            '\u{0c}' => write!(w, "\\f")?,
            c if (c as u32) < 0x20 => write!(w, "\\u{:04x}", c as u32)?,
            c => write!(w, "{}", c)?,
        }
    }
    write!(w, "\"")?;
    Ok(())
}

// ----------------- Misc -----------------

fn format_int(n: i64) -> String {
    // Match Python's `f"{n:,}"` thousands separator.
    let s = n.abs().to_string();
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    if n < 0 {
        out.push('-');
    }
    let len = bytes.len();
    for (i, &b) in bytes.iter().enumerate() {
        if i > 0 && (len - i) % 3 == 0 {
            out.push(',');
        }
        out.push(b as char);
    }
    out
}
