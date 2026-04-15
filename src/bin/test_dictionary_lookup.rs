// Simulate Kindle dictionary lookup against generated dictionary files.
//
// Parses content.html from build directories, builds a lookup index, and
// tests that inflected forms resolve to the correct headwords. Also runs
// position-verification, anchor-link, and MOBI binary-structure checks.
//
// Usage:
//     cargo run --bin test_dictionary_lookup [-- [build_dir_or_glob] [-i]]
//
//     # Latest full build (all volumes):
//     cargo run --bin test_dictionary_lookup
//
//     # Specific dir:
//     cargo run --bin test_dictionary_lookup -- lemma_greek_en_20260411
//
//     # Interactive mode:
//     cargo run --bin test_dictionary_lookup -- -i

use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

use lemma::entry_processor::py_lower;
use lemma::mobi_validator;
use regex::Regex;

// Known inflection -> headword pairs for validation.
// Each tuple: (inflected_form, expected_headword, description)
const KNOWN_LOOKUPS: &[(&str, &str, &str)] = &[
    // Common verbs
    ("τρώει", "τρώω", "present 3sg of 'eat'"),
    ("έτρωγα", "τρώω", "imperfect 1sg of 'eat'"),
    ("φάει", "τρώω", "subjunctive 3sg of 'eat'"),
    ("πήγα", "πηγαίνω", "aorist 1sg of 'go'"),
    ("πηγαίνει", "πηγαίνω", "present 3sg of 'go'"),
    ("είναι", "είμαι", "present 3sg of 'be'"),
    ("ήταν", "είμαι", "imperfect 3sg of 'be'"),
    ("βλέπει", "βλέπω", "present 3sg of 'see'"),
    ("είδα", "βλέπω", "aorist 1sg of 'see'"),
    ("έχει", "έχω", "present 3sg of 'have'"),
    ("είχα", "έχω", "imperfect 1sg of 'have'"),
    ("λέει", "λέω", "present 3sg of 'say'"),
    ("είπε", "λέω", "aorist 3sg of 'say'"),
    ("θέλει", "θέλω", "present 3sg of 'want'"),
    ("ήθελα", "θέλω", "imperfect 1sg of 'want'"),
    ("κάνει", "κάνω", "present 3sg of 'do/make'"),
    ("έκανε", "κάνω", "aorist 3sg of 'do/make'"),
    ("ξέρει", "ξέρω", "present 3sg of 'know'"),
    ("ήξερα", "ξέρω", "imperfect 1sg of 'know'"),
    ("μπορεί", "μπορώ", "present 3sg of 'can'"),
    ("μπορούσα", "μπορώ", "imperfect 1sg of 'can'"),
    ("δίνει", "δίνω", "present 3sg of 'give'"),
    ("έδωσε", "δίνω", "aorist 3sg of 'give'"),
    ("παίρνει", "παίρνω", "present 3sg of 'take'"),
    ("πήρε", "παίρνω", "aorist 3sg of 'take'"),
    ("γράφει", "γράφω", "present 3sg of 'write'"),
    ("έγραψε", "γράφω", "aorist 3sg of 'write'"),
    // Common nouns - case inflections
    ("σπιτιού", "σπίτι", "genitive sg of 'house'"),
    ("σπίτια", "σπίτι", "plural of 'house'"),
    ("ανθρώπου", "άνθρωπος", "genitive sg of 'person'"),
    ("ανθρώπων", "άνθρωπος", "genitive pl of 'person'"),
    ("γυναίκα", "γυναίκα", "headword lookup for 'woman'"),
    ("γυναίκας", "γυναίκα", "genitive sg of 'woman'"),
    ("γυναίκες", "γυναίκα", "plural of 'woman'"),
    ("παιδιού", "παιδί", "genitive sg of 'child'"),
    ("παιδιά", "παιδί", "plural of 'child'"),
    ("χρόνου", "χρόνος", "genitive sg of 'year/time'"),
    (
        "χρόνια",
        "χρόνια",
        "headword lookup 'years/ages' (also plural of χρόνος)",
    ),
    // Adjective inflections
    ("καλή", "καλός", "feminine of 'good'"),
    ("καλό", "καλός", "neuter of 'good'"),
    ("μεγάλη", "μεγάλος", "feminine of 'big'"),
    ("μεγάλο", "μεγάλος", "neuter of 'big'"),
    ("όμορφο", "όμορφος", "neuter of 'beautiful'"),
    ("όμορφη", "όμορφος", "feminine of 'beautiful'"),
    // Headword self-lookup (should always work)
    ("τρώω", "τρώω", "headword self-lookup 'eat'"),
    ("σπίτι", "σπίτι", "headword self-lookup 'house'"),
    ("καλός", "καλός", "headword self-lookup 'good'"),
    ("όμορφος", "όμορφος", "headword self-lookup 'beautiful'"),
    ("ομορφιά", "ομορφιά", "headword self-lookup 'beauty'"),
];

// Expected POS lines - the POS must start with the expected text.
// The unified edition always emits gender/variant info (e.g., "noun,
// feminine (plural ...)"), so starts_with is enough to match.
const KNOWN_POS_FORMATS: &[(&str, &str, &str)] = &[
    ("θάλασσα", "noun", "POS starts with 'noun'"),
    ("σκύλος", "noun", "POS starts with 'noun'"),
    ("Ελλάδα", "name", "POS starts with 'name'"),
];

// Position-verification cases.
// (iform, must_contain, must_not_contain, description)
const POSITION_VERIFICATION_CASES: &[(&str, &str, Option<&str>, &str)] = &[
    (
        "όμορφο",
        "beautiful",
        Some("όμορφος + -ιά"),
        "iform of όμορφος should show 'beautiful', not ομορφιά etymology",
    ),
    (
        "όμορφη",
        "beautiful",
        None,
        "feminine of όμορφος should show 'beautiful'",
    ),
    (
        "ομορφιά",
        "beauty",
        None,
        "headword ομορφιά should show 'beauty'",
    ),
    (
        "καλή",
        "good",
        None,
        "feminine of καλός should show 'good'",
    ),
    (
        "σπιτιού",
        "house",
        None,
        "genitive of σπίτι should show 'house'",
    ),
];

// ----------------- HTML entity unescape (Python html.unescape subset) -----------------
//
// idx:orth and idx:iform values are run through html.escape, so they may
// contain &amp; &lt; &gt; &quot; &#x27; / &#39;. We don't try to handle the
// full HTML entity set; the dictionary content uses only these.
fn html_unescape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'&' {
            if let Some(end) = bytes[i..].iter().position(|&b| b == b';') {
                let entity = &s[i + 1..i + end];
                if let Some(c) = decode_entity(entity) {
                    out.push(c);
                    i += end + 1;
                    continue;
                }
            }
        }
        // Find next char boundary in source string and copy it.
        let ch = s[i..].chars().next().unwrap();
        out.push(ch);
        i += ch.len_utf8();
    }
    out
}

fn decode_entity(name: &str) -> Option<char> {
    match name {
        "amp" => Some('&'),
        "lt" => Some('<'),
        "gt" => Some('>'),
        "quot" => Some('"'),
        "apos" => Some('\''),
        "nbsp" => Some('\u{00a0}'),
        _ => {
            if let Some(rest) = name.strip_prefix('#') {
                let code = if let Some(hex) = rest.strip_prefix('x').or_else(|| rest.strip_prefix('X')) {
                    u32::from_str_radix(hex, 16).ok()
                } else {
                    rest.parse::<u32>().ok()
                };
                code.and_then(char::from_u32)
            } else {
                None
            }
        }
    }
}

// ----------------- DictionaryIndex -----------------

struct DictionaryIndex {
    // word -> list of (headword, definition_preview)
    index: HashMap<String, Vec<(String, String)>>,
    headwords: HashSet<String>,
    total_inflections: usize,
    // headword -> list of POS line strings
    pos_lines: HashMap<String, Vec<String>>,
}

impl DictionaryIndex {
    fn new() -> Self {
        Self {
            index: HashMap::new(),
            headwords: HashSet::new(),
            total_inflections: 0,
            pos_lines: HashMap::new(),
        }
    }

    fn load_content_html(&mut self, filepath: &Path) {
        let content = match fs::read_to_string(filepath) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("  Cannot read {}: {}", filepath.display(), e);
                return;
            }
        };

        let entry_re = Regex::new(r"(?s)<idx:entry[^>]*>(.+?)</idx:entry>").unwrap();
        let orth_re = Regex::new(r#"<idx:orth\s+value="([^"]*)""#).unwrap();
        let iform_re = Regex::new(r#"<idx:iform\s+value="([^"]*)""#).unwrap();
        let def_re = Regex::new(r"(?s)<div class='def'>(.*?)</div>").unwrap();
        let pos_re = Regex::new(r"(?s)<div><i>(.*?)</i></div>").unwrap();

        for cap in entry_re.captures_iter(&content) {
            let entry_html = &cap[1];

            let Some(orth_match) = orth_re.captures(entry_html) else {
                continue;
            };
            let headword = html_unescape(&orth_match[1]);
            self.headwords.insert(headword.clone());

            for pm in pos_re.captures_iter(entry_html) {
                let pos_text = html_unescape(&pm[1]);
                self.pos_lines
                    .entry(headword.clone())
                    .or_default()
                    .push(pos_text);
            }

            let preview = def_re
                .captures(entry_html)
                .map(|c| {
                    let raw = html_unescape(&c[1]);
                    take_chars(&raw, 80)
                })
                .unwrap_or_else(|| "(no definition)".to_string());

            // Index the headword itself.
            self.index
                .entry(headword.clone())
                .or_default()
                .push((headword.clone(), preview.clone()));

            // Index all inflected forms.
            for im in iform_re.captures_iter(entry_html) {
                let form = html_unescape(&im[1]);
                self.total_inflections += 1;
                self.index
                    .entry(form)
                    .or_default()
                    .push((headword.clone(), preview.clone()));
            }
        }
    }

    fn lookup(&self, word: &str) -> Vec<(String, String)> {
        if let Some(v) = self.index.get(word) {
            return v.clone();
        }
        let lower = py_lower(word);
        if let Some(v) = self.index.get(&lower) {
            return v.clone();
        }
        // Try capitalized (first char upper)
        if let Some(first) = word.chars().next() {
            if first.is_lowercase() {
                let mut cap = String::with_capacity(word.len());
                for (i, c) in word.chars().enumerate() {
                    if i == 0 {
                        for u in c.to_uppercase() {
                            cap.push(u);
                        }
                    } else {
                        cap.push(c);
                    }
                }
                if let Some(v) = self.index.get(&cap) {
                    return v.clone();
                }
            }
        }
        Vec::new()
    }
}

fn take_chars(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

// ----------------- Build dir discovery -----------------
//
// Lemma builds always go to a stable directory name (`lemma_greek_en`),
// so there is no date to group by. We just take the matching dirs and
// let the test loop iterate over them.

/// Collect every `content_NN.html` file in a build directory, sorted.
/// Dictionary content is split across per-letter files; the previous single
/// `content.html` no longer exists.
fn find_content_files(dir: &Path) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = Vec::new();
    if let Ok(entries) = fs::read_dir(dir) {
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if name.starts_with("content_") && name.ends_with(".html") {
                out.push(e.path());
            }
        }
    }
    out.sort();
    out
}

fn has_content_files(dir: &Path) -> bool {
    !find_content_files(dir).is_empty()
}

fn find_build_dirs(pattern: Option<&str>) -> Vec<PathBuf> {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

    if let Some(pat) = pattern {
        // If it's an absolute path or relative path that exists as a dir, use it.
        let direct = if Path::new(pat).is_absolute() {
            PathBuf::from(pat)
        } else {
            cwd.join(pat)
        };
        if direct.is_dir() && has_content_files(&direct) {
            return vec![direct];
        }
        // Otherwise treat the pattern as a name fragment to match against
        // any directory in the cwd that contains content_*.html files.
        let mut out = Vec::new();
        if let Ok(entries) = fs::read_dir(&cwd) {
            for e in entries.flatten() {
                let name = e.file_name().to_string_lossy().into_owned();
                if name.contains(pat) && e.path().is_dir() && has_content_files(&e.path()) {
                    out.push(e.path());
                }
            }
        }
        out.sort();
        return out;
    }

    // No pattern: take every lemma_greek_* dir that has content_*.html files,
    // but skip percentage test builds (`_10pct`, `_1.0pct`, etc.) so the
    // default run only tests the real builds.
    let pct_re = Regex::new(r"_\d+(\.\d+)?pct$").unwrap();

    let mut all_dirs: Vec<PathBuf> = Vec::new();
    if let Ok(entries) = fs::read_dir(&cwd) {
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if !name.starts_with("lemma_greek_") {
                continue;
            }
            if pct_re.is_match(&name) {
                continue;
            }
            let p = e.path();
            if p.is_dir() && has_content_files(&p) {
                all_dirs.push(p);
            }
        }
    }
    all_dirs.sort();
    all_dirs
}

// ----------------- Tests -----------------

fn run_lookup_tests(index: &DictionaryIndex, label: &str) -> bool {
    let cases = KNOWN_LOOKUPS;
    let mut passed = 0usize;
    let mut failed = 0usize;
    let mut missing_headword = 0usize;

    println!("\nRunning {} {} tests...\n", cases.len(), label);

    for (form, expected_headword, desc) in cases {
        let results = index.lookup(form);
        let headwords: Vec<String> = results.iter().map(|(hw, _)| hw.clone()).collect();

        if !index.headwords.contains(*expected_headword) {
            missing_headword += 1;
            println!("  SKIP  {} -> {} ({})", form, expected_headword, desc);
            println!(
                "        headword '{}' not in dictionary",
                expected_headword
            );
            continue;
        }

        if headwords.iter().any(|hw| hw == expected_headword) {
            passed += 1;
        } else {
            failed += 1;
            if !results.is_empty() {
                let found = headwords
                    .iter()
                    .take(3)
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(", ");
                println!(
                    "  FAIL  {} -> expected '{}', got: {} ({})",
                    form, expected_headword, found, desc
                );
            } else {
                println!(
                    "  FAIL  {} -> expected '{}', not found ({})",
                    form, expected_headword, desc
                );
            }
        }
    }

    let total_run = passed + failed;
    print!("\nResults: {}/{} passed", passed, total_run);
    if missing_headword > 0 {
        print!(", {} skipped (headword not in build)", missing_headword);
    }
    if failed > 0 {
        print!(", {} FAILED", failed);
    }
    println!();

    failed == 0
}

fn run_pos_tests(index: &DictionaryIndex) -> bool {
    let cases = KNOWN_POS_FORMATS;
    let mut passed = 0usize;
    let mut failed = 0usize;
    let mut skipped = 0usize;

    println!("\nRunning {} POS format tests...\n", cases.len());

    for (headword, expected_pos, desc) in cases {
        if !index.headwords.contains(*headword) {
            skipped += 1;
            println!("  SKIP  {} ({})", headword, desc);
            println!("        headword not in dictionary");
            continue;
        }

        let actual_lines = index.pos_lines.get(*headword).cloned().unwrap_or_default();
        if actual_lines.iter().any(|line| line.starts_with(*expected_pos)) {
            passed += 1;
        } else {
            failed += 1;
            let actual = actual_lines
                .first()
                .cloned()
                .unwrap_or_else(|| "(no POS line)".to_string());
            println!(
                "  FAIL  {}: expected POS starting with '{}'",
                headword, expected_pos
            );
            println!("        got: '{}' ({})", actual, desc);
        }
    }

    let total_run = passed + failed;
    print!("\nPOS format results: {}/{} passed", passed, total_run);
    if skipped > 0 {
        print!(", {} skipped", skipped);
    }
    if failed > 0 {
        print!(", {} FAILED", failed);
    }
    println!();

    failed == 0
}

fn interactive_mode(index: &DictionaryIndex) {
    println!("\nInteractive lookup mode. Type a Greek word to look it up.");
    println!("Type 'q' to quit.\n");

    let stdin = io::stdin();
    let mut stdout = io::stdout();
    loop {
        print!("lookup> ");
        let _ = stdout.flush();
        let mut line = String::new();
        if stdin.lock().read_line(&mut line).unwrap_or(0) == 0 {
            println!();
            break;
        }
        let word = line.trim();
        if word.is_empty() || word == "q" {
            break;
        }

        let results = index.lookup(word);
        if results.is_empty() {
            println!("  (not found)");
        } else {
            let mut seen = HashSet::new();
            for (hw, preview) in results {
                if seen.insert(hw.clone()) {
                    println!("  {}: {}", hw, preview);
                }
            }
        }
    }
}

// ----------------- Position verification -----------------
//
// Strip idx:* tags exactly the same way kindling does, then locate
// `<b>headword</b>` boundaries to verify which entry text an iform points at.
// Catches the bug where etymologies/definitions containing a headword cause
// `find_entry_positions` to map an iform to the wrong location.

fn strip_idx_markup(html_text: &str) -> String {
    let mut result = html_text.to_string();
    let xml_re = Regex::new(r"(?s)<\?xml[^?]*\?>\s*").unwrap();
    result = xml_re.replace_all(&result, "").into_owned();
    let xmlns_re = Regex::new(r#"\s+xmlns:\w+="[^"]*""#).unwrap();
    result = xmlns_re.replace_all(&result, "").into_owned();
    let head_re = Regex::new(r"(?s)<head>.*?</head>").unwrap();
    result = head_re
        .replace_all(&result, "<head><guide></guide></head>")
        .into_owned();
    let iform_re = Regex::new(r"<idx:iform[^/]*/>\s*").unwrap();
    result = iform_re.replace_all(&result, "").into_owned();
    let infl_empty_re = Regex::new(r"<idx:infl>\s*</idx:infl>\s*").unwrap();
    result = infl_empty_re.replace_all(&result, "").into_owned();
    let infl_re = Regex::new(r"(?s)\s*<idx:infl>.*?</idx:infl>\s*").unwrap();
    result = infl_re.replace_all(&result, "").into_owned();
    let orth_self_re = Regex::new(r"<idx:orth[^>]*/>").unwrap();
    result = orth_self_re.replace_all(&result, "").into_owned();
    let orth_open_re = Regex::new(r"<idx:orth[^>]*>").unwrap();
    result = orth_open_re.replace_all(&result, "").into_owned();
    result = result.replace("</idx:orth>", "");
    let short_open_re = Regex::new(r"<idx:short>\s*").unwrap();
    result = short_open_re.replace_all(&result, "").into_owned();
    let short_close_re = Regex::new(r"\s*</idx:short>").unwrap();
    result = short_close_re.replace_all(&result, "").into_owned();
    let entry_open_re = Regex::new(r"<idx:entry[^>]*>\s*").unwrap();
    result = entry_open_re.replace_all(&result, "").into_owned();
    let entry_close_re = Regex::new(r"\s*</idx:entry>").unwrap();
    result = entry_close_re.replace_all(&result, "").into_owned();
    let ws_re = Regex::new(r"\s+").unwrap();
    result = ws_re.replace_all(&result, " ").into_owned();
    let gap_re = Regex::new(r">\s+<").unwrap();
    result = gap_re.replace_all(&result, "><").into_owned();
    result = result.replace("</b><", "</b> <");
    result = result.replace("</p><hr", "</p> <hr");
    result = result.replace("/><b>", "/> <b>");
    result.trim().to_string()
}

struct ParsedEntry {
    headword: String,
    inflections: Vec<String>,
}

fn parse_entries(content: &str) -> Vec<ParsedEntry> {
    let orth_re = Regex::new(r#"<idx:orth\s+value="([^"]*)""#).unwrap();
    let iform_re = Regex::new(r#"<idx:iform\s+value="([^"]*)""#).unwrap();
    let entry_open_tag = "<idx:entry";
    let entry_close_tag = "</idx:entry>";
    let mut search_pos = 0usize;
    let mut entries = Vec::new();

    let bytes = content.as_bytes();
    while let Some(rel_start) = content[search_pos..].find(entry_open_tag) {
        let start = search_pos + rel_start;
        // Find '>' after the open tag.
        let after_open = match content[start..].find('>') {
            Some(g) => start + g + 1,
            None => break,
        };
        let close_pos = match content[after_open..].find(entry_close_tag) {
            Some(c) => after_open + c,
            None => break,
        };
        let entry_inner = &content[after_open..close_pos];
        if let Some(m) = orth_re.captures(entry_inner) {
            let hw = html_unescape(&m[1]);
            let infs: Vec<String> = iform_re
                .captures_iter(entry_inner)
                .map(|c| html_unescape(&c[1]))
                .collect();
            entries.push(ParsedEntry {
                headword: hw,
                inflections: infs,
            });
        }
        search_pos = close_pos + entry_close_tag.len();
        let _ = bytes; // silence unused
    }
    entries
}

fn run_position_verification_tests(content_html_paths: &[PathBuf]) -> bool {
    let mut passed = 0usize;
    let mut failed = 0usize;
    let mut skipped = 0usize;

    println!(
        "\nRunning {} MOBI position verification tests...\n",
        POSITION_VERIFICATION_CASES.len()
    );

    // The position scanner expects a single `<html>…<body>…</body></html>`
    // document. Entries now live across per-letter files, so extract each
    // file's body and concatenate so every headword is reachable by the
    // positional searches below.
    let body_inner_re = Regex::new(r"(?s)<body[^>]*>(.*?)</body>").unwrap();
    let head_re = Regex::new(r"(?s)<head[^>]*>.*?</head>").unwrap();
    let mut combined_body = String::new();
    let mut first_head: Option<String> = None;
    let mut combined_raw = String::new();
    for path in content_html_paths {
        let raw = match fs::read_to_string(path) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Cannot read {}: {}", path.display(), e);
                return false;
            }
        };
        if first_head.is_none() {
            if let Some(c) = head_re.captures(&raw) {
                first_head = Some(c[0].to_string());
            }
        }
        if let Some(c) = body_inner_re.captures(&raw) {
            combined_body.push_str(c[1].trim());
            combined_body.push('\n');
        }
        combined_raw.push_str(&raw);
    }
    // Parse entries from the concatenation so every headword is present.
    let content = combined_raw;
    let entries = parse_entries(&content);

    let stripped_body = strip_idx_markup(&combined_body);
    let head = first_head.unwrap_or_else(|| "<head><guide></guide></head>".to_string());
    let text = format!("<html>{}<body>{}  <mbp:pagebreak/></body></html>", head, stripped_body);
    let text_bytes = text.as_bytes();

    // Simulate find_entry_positions with entry-boundary check.
    let mut entry_positions: HashMap<String, (usize, usize)> = HashMap::new();
    let mut search_start = 0usize;
    for entry in &entries {
        let hw_bytes = entry.headword.as_bytes();
        let mut bold_needle = Vec::with_capacity(hw_bytes.len() + 7);
        bold_needle.extend_from_slice(b"<b>");
        bold_needle.extend_from_slice(hw_bytes);
        bold_needle.extend_from_slice(b"</b>");

        let mut found: Option<(usize, usize)> = None;
        let mut scan_from = search_start;
        loop {
            let Some(rel) = find_subslice(&text_bytes[scan_from..], &bold_needle) else {
                break;
            };
            let bold_pos = scan_from + rel;
            // Boundary check: preceded by `<hr/>` or near start.
            if bold_pos < 200 {
                found = Some((bold_pos, bold_pos + 3));
                break;
            }
            let check_start = bold_pos.saturating_sub(8);
            let preceding = &text_bytes[check_start..bold_pos];
            if preceding.ends_with(b"<hr/> ")
                || preceding.ends_with(b"<hr/>")
                || preceding.ends_with(b"/> ")
            {
                found = Some((bold_pos, bold_pos + 3));
                break;
            }
            scan_from = bold_pos + bold_needle.len();
        }

        if let Some((block_start, pos)) = found {
            let hr_pos = find_subslice(&text_bytes[pos..], b"<hr/>").map(|x| pos + x);
            let text_len = match hr_pos {
                Some(p) => p - block_start,
                None => text_bytes.len() - block_start,
            };
            entry_positions
                .entry(entry.headword.clone())
                .or_insert((block_start, text_len));
            for inf in &entry.inflections {
                entry_positions
                    .entry(inf.clone())
                    .or_insert((block_start, text_len));
            }
            search_start = pos + hw_bytes.len();
        }
    }

    for (iform, must_contain, must_not_contain, desc) in POSITION_VERIFICATION_CASES {
        let Some(&(start_pos, text_len)) = entry_positions.get(*iform) else {
            skipped += 1;
            println!("  SKIP  '{}' not in index ({})", iform, desc);
            continue;
        };
        let entry_text = String::from_utf8_lossy(&text_bytes[start_pos..start_pos + text_len])
            .into_owned();

        let mut ok = true;
        if !must_contain.is_empty() && !entry_text.contains(*must_contain) {
            ok = false;
            println!(
                "  FAIL  '{}': expected '{}' in definition ({})",
                iform, must_contain, desc
            );
            println!("        got: {}...", take_chars(&entry_text, 120));
        }
        if let Some(forbidden) = must_not_contain {
            if entry_text.contains(forbidden) {
                ok = false;
                println!(
                    "  FAIL  '{}': found forbidden '{}' in definition ({})",
                    iform, forbidden, desc
                );
                println!("        got: {}...", take_chars(&entry_text, 120));
            }
        }

        if ok {
            passed += 1;
        } else {
            failed += 1;
        }
    }

    let total = passed + failed;
    print!("\nPosition verification results: {}/{} passed", passed, total);
    if skipped > 0 {
        print!(", {} skipped", skipped);
    }
    if failed > 0 {
        print!(", {} FAILED", failed);
    }
    println!();
    failed == 0
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() {
        return Some(0);
    }
    if needle.len() > haystack.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|w| w == needle)
}

// ----------------- Anchor link tests -----------------

/// Aggregate-anchor-link test across every `content_NN.html` in a build dir.
///
/// Cross-reference links are file-qualified (`content_11.html#hw_λέγω`), so
/// validation has two parts: (1) every `id="hw_X"` across all bucket files
/// is mapped to the file it lives in, then (2) every `<a href="FILE#hw_X">`
/// is checked against that map so we catch links that point at the wrong
/// bucket as well as links with no matching anchor at all.
fn run_anchor_link_tests_dir(build_dir: &Path, content_files: &[PathBuf]) -> bool {
    let mut passed = 0usize;
    let mut failed = 0usize;
    let dir_name = build_dir
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    println!(
        "\nRunning anchor link tests on {} ({} content files)...\n",
        dir_name,
        content_files.len()
    );

    let id_re = Regex::new(r##"id="(hw_[^"]+)""##).unwrap();
    let link_re = Regex::new(r##"<a href="(content_[0-9]+\.html)#(hw_[^"]+)""##).unwrap();

    // anchor_id -> owning filename
    let mut anchor_owner: HashMap<String, String> = HashMap::new();
    // filename -> all links emitted from that file
    let mut per_file_links: Vec<(String, Vec<(String, String)>)> = Vec::new();

    for cf in content_files {
        let content = match fs::read_to_string(cf) {
            Ok(s) => s,
            Err(_) => return false,
        };
        let filename = cf
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        for cap in id_re.captures_iter(&content) {
            anchor_owner.insert(cap[1].to_string(), filename.clone());
        }
        let links: Vec<(String, String)> = link_re
            .captures_iter(&content)
            .map(|c| (c[1].to_string(), c[2].to_string()))
            .collect();
        per_file_links.push((filename, links));
    }

    let total_links: usize = per_file_links.iter().map(|(_, v)| v.len()).sum();
    if total_links == 0 {
        println!("  (no cross-reference links found, skipping)");
        return true;
    }

    let mut missing: Vec<String> = Vec::new();
    let mut wrong_file: Vec<String> = Vec::new();
    for (src_file, links) in &per_file_links {
        for (target_file, anchor_id) in links {
            match anchor_owner.get(anchor_id) {
                None => {
                    missing.push(format!("{} -> {}#{}", src_file, target_file, anchor_id));
                }
                Some(owner) if owner != target_file => {
                    wrong_file.push(format!(
                        "{} -> {}#{} (anchor actually in {})",
                        src_file, target_file, anchor_id, owner
                    ));
                }
                _ => {}
            }
        }
    }

    if missing.is_empty() && wrong_file.is_empty() {
        passed += 1;
        println!("  {} links all resolve to valid anchors in the expected files", total_links);
    } else {
        failed += 1;
        if !missing.is_empty() {
            println!("  FAIL  {} links have no matching anchor ID", missing.len());
            for m in missing.iter().take(5) {
                println!("        {}", m);
            }
            if missing.len() > 5 {
                println!("        ... and {} more", missing.len() - 5);
            }
        }
        if !wrong_file.is_empty() {
            println!(
                "  FAIL  {} links point at the wrong content file",
                wrong_file.len()
            );
            for w in wrong_file.iter().take(5) {
                println!("        {}", w);
            }
            if wrong_file.len() > 5 {
                println!("        ... and {} more", wrong_file.len() - 5);
            }
        }
    }

    let total = passed + failed;
    print!("\nAnchor link results: {}/{} passed", passed, total);
    if failed > 0 {
        print!(", {} FAILED", failed);
    }
    println!();
    failed == 0
}

// ----------------- main -----------------

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let interactive = args.iter().any(|a| a == "-i");
    let pattern: Option<&str> = args
        .iter()
        .find(|a| *a != "-i")
        .map(|s| s.as_str());

    let dirs = find_build_dirs(pattern);
    if dirs.is_empty() {
        println!("No build directories found. Run the generator first.");
        return ExitCode::from(1);
    }

    let mut index = DictionaryIndex::new();

    println!("Loading {} build dir(s)...", dirs.len());
    let start = Instant::now();
    for d in &dirs {
        let name = d
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        let content_files = find_content_files(d);
        for cf in &content_files {
            index.load_content_html(cf);
        }
        println!(
            "  {}: {} content files, {} headwords so far",
            name,
            content_files.len(),
            index.headwords.len()
        );
    }
    let elapsed = start.elapsed().as_secs_f64();
    println!(
        "\nLoaded {} headwords, {} inflections, {} unique lookup keys in {:.1}s",
        index.headwords.len(),
        index.total_inflections,
        index.index.len(),
        elapsed
    );

    let mut all_passed = true;
    all_passed &= run_lookup_tests(&index, "lookup");
    all_passed &= run_pos_tests(&index);

    // Position verification runs per content file. Anchor link tests are
    // aggregated across the whole build dir so file-qualified cross-refs
    // (e.g. `content_11.html#hw_λέγω`) can be validated against all anchors.
    for d in &dirs {
        let content_files = find_content_files(d);
        if !content_files.is_empty() {
            all_passed &= run_position_verification_tests(&content_files);
        }
        let has_cross_refs = content_files.iter().any(|cf| {
            if let Ok(mut head_buf) = read_first_n_bytes(cf, 100_000) {
                head_buf.make_ascii_lowercase();
                find_subslice(&head_buf, b"<a href=\"content_").is_some()
            } else {
                false
            }
        });
        if has_cross_refs {
            all_passed &= run_anchor_link_tests_dir(d, &content_files);
        }
    }

    // MOBI validation.
    let mut mobi_files: Vec<PathBuf> = Vec::new();
    for d in &dirs {
        if let Ok(entries) = fs::read_dir(d) {
            for e in entries.flatten() {
                let p = e.path();
                if p.extension().map(|x| x == "mobi").unwrap_or(false) {
                    mobi_files.push(p);
                }
            }
        }
    }
    if mobi_files.is_empty() {
        // Check dist/ as a fallback.
        let dist_dir = std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join("dist");
        if dist_dir.is_dir() {
            if let Ok(entries) = fs::read_dir(&dist_dir) {
                for e in entries.flatten() {
                    let p = e.path();
                    if p.extension().map(|x| x == "mobi").unwrap_or(false) {
                        mobi_files.push(p);
                    }
                }
            }
        }
    }
    if !mobi_files.is_empty() {
        let report = mobi_validator::validate_mobi_files(&mobi_files);
        all_passed &= mobi_validator::print_report(&report);
    }

    if interactive {
        interactive_mode(&index);
    }

    if all_passed {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

fn read_first_n_bytes(path: &Path, n: usize) -> std::io::Result<Vec<u8>> {
    use std::io::Read;
    let f = fs::File::open(path)?;
    let mut buf = Vec::with_capacity(n);
    let mut handle = f.take(n as u64);
    handle.read_to_end(&mut buf)?;
    Ok(buf)
}
