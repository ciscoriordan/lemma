// Quick diagnostic: check what inflections a headword has in the built dict.
//
// Usage:
//     cargo run --release --bin diagnose_inflections [-- WORD ...]
//
// With no arguments, runs against a built-in default list of common Greek
// verbs and nouns.

use std::collections::HashSet;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

use lemma::html_escape::escape_html;
use regex::Regex;

const DEFAULT_WORDS: &[&str] = &[
    "τρώω",
    "πηγαίνω",
    "βλέπω",
    "έχω",
    "λέω",
    "δίνω",
    "παίρνω",
    "άνθρωπος",
    "παιδί",
];

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let words: Vec<String> = if args.is_empty() {
        DEFAULT_WORDS.iter().map(|s| s.to_string()).collect()
    } else {
        args
    };

    // Find all content.html files from el-source builds. Match both the
    // bare `lemma_greek_el` directory and any `lemma_greek_el_*` variant
    // (e.g. `_basic`), excluding test-percentage builds.
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let pct_re = Regex::new(r"_\d+(\.\d+)?pct$").unwrap();
    let mut files: Vec<PathBuf> = Vec::new();
    if let Ok(entries) = fs::read_dir(&cwd) {
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            let is_el_build = name == "lemma_greek_el" || name.starts_with("lemma_greek_el_");
            if !is_el_build {
                continue;
            }
            if pct_re.is_match(&name) {
                continue;
            }
            let p = e.path().join("content.html");
            if p.exists() {
                files.push(p);
            }
        }
    }
    files.sort();

    if files.is_empty() {
        println!("No build files found");
        return ExitCode::from(1);
    }

    println!("Loading {} content files...", files.len());
    let mut all_content = String::new();
    for f in &files {
        match fs::read_to_string(f) {
            Ok(s) => all_content.push_str(&s),
            Err(e) => eprintln!("  Cannot read {}: {}", f.display(), e),
        }
    }

    let iform_re = Regex::new(r#"<idx:iform value="([^"]*)""#).unwrap();
    let orth_value_re = Regex::new(r#"<idx:orth value="([^"]*)""#).unwrap();

    for word in &words {
        let escaped = escape_html(word);
        let entry_pattern = format!(
            "(?s)<idx:orth value=\"{}\">(.*?)</idx:entry>",
            regex::escape(&escaped)
        );
        let entry_re = Regex::new(&entry_pattern).unwrap();

        if let Some(caps) = entry_re.captures(&all_content) {
            let entry_html = &caps[1];
            let iforms_decoded: Vec<String> = iform_re
                .captures_iter(entry_html)
                .map(|c| html_unescape(&c[1]))
                .collect();
            // Dedupe while preserving first-seen order, matching the Python
            // diagnostic's intent of showing what's in the entry.
            let mut seen = HashSet::new();
            let mut unique: Vec<String> = Vec::new();
            for f in &iforms_decoded {
                if seen.insert(f.clone()) {
                    unique.push(f.clone());
                }
            }
            println!("\n{}: {} inflections", word, unique.len());
            for f in unique.iter().take(30) {
                println!("  {}", f);
            }
            if unique.len() > 30 {
                println!("  ... and {} more", unique.len() - 30);
            }
        } else {
            println!("\n{}: NOT FOUND as headword", word);
            // Check if it appears as an iform.
            let iform_needle = format!(r#"<idx:iform value="{}""#, regex::escape(&escaped));
            let iform_lookup = Regex::new(&iform_needle).unwrap();
            if let Some(m) = iform_lookup.find(&all_content) {
                let chunk_start = m.start().saturating_sub(5000);
                let chunk = &all_content[chunk_start..m.start()];
                let mut last_orth: Option<String> = None;
                for cap in orth_value_re.captures_iter(chunk) {
                    last_orth = Some(html_unescape(&cap[1]));
                }
                if let Some(hw) = last_orth {
                    println!("  Found as inflection of: {}", hw);
                }
            }
        }
    }

    ExitCode::SUCCESS
}

// Same minimal HTML entity unescape used by test_dictionary_lookup.
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
                let code = if let Some(hex) =
                    rest.strip_prefix('x').or_else(|| rest.strip_prefix('X'))
                {
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
