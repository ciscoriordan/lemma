// Ranks inflected forms by corpus frequency.
// Frequency data from FrequencyWords (OpenSubtitles 2018).

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::time::Instant;

pub struct FrequencyRanker {
    frequencies: HashMap<String, i64>,
}

impl FrequencyRanker {
    pub fn new() -> Self {
        let mut ranker = Self { frequencies: HashMap::new() };
        ranker.load();
        ranker
    }

    pub fn available(&self) -> bool {
        !self.frequencies.is_empty()
    }

    pub fn frequency(&self, word: &str) -> i64 {
        if let Some(v) = self.frequencies.get(word) {
            if *v != 0 {
                return *v;
            }
        }
        let lower: String = word.chars().flat_map(|c| c.to_lowercase()).collect();
        *self.frequencies.get(&lower).unwrap_or(&0)
    }

    fn load(&mut self) {
        // Find project root - walk up from exe if needed, but default to CWD's data/
        let candidates = [
            Path::new("data/el_full.txt").to_path_buf(),
        ];

        for path in &candidates {
            if path.exists() {
                self.load_from(path);
                return;
            }
        }
    }

    fn load_from(&mut self, path: &Path) {
        let start = Instant::now();
        let file = match File::open(path) {
            Ok(f) => f,
            Err(_) => return,
        };
        let reader = BufReader::new(file);
        for line in reader.lines().map_while(Result::ok) {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let mut parts = line.splitn(2, ' ');
            let word = match parts.next() {
                Some(w) => w,
                None => continue,
            };
            let count = match parts.next() {
                Some(c) => c,
                None => continue,
            };
            if let Ok(n) = count.parse::<i64>() {
                self.frequencies.insert(word.to_string(), n);
            }
        }
        let elapsed = start.elapsed().as_secs_f64();
        println!("Loaded {} frequency entries in {:.1}s", self.frequencies.len(), elapsed);
    }
}
