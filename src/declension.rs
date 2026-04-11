// Expands Greek declension templates to generate inflected forms.

use std::collections::HashMap;
use std::sync::OnceLock;

type Gen = fn(&str) -> String;

struct Pattern {
    ending: &'static str,
    cases: &'static [(&'static str, Gen)],
}

fn g_phylakas_nom_sg(stem: &str) -> String { format!("{}ας", stem) }
fn g_phylakas_gen_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_phylakas_acc_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_phylakas_voc_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_phylakas_nom_pl(stem: &str) -> String { format!("{}ες", stem) }
fn g_phylakas_gen_pl(stem: &str) -> String { format!("{}ων", add_accent(stem)) }
fn g_phylakas_acc_pl(stem: &str) -> String { format!("{}ες", stem) }
fn g_phylakas_voc_pl(stem: &str) -> String { format!("{}ες", stem) }

fn g_anthropos_nom_sg(stem: &str) -> String { format!("{}ος", stem) }
fn g_anthropos_gen_sg(stem: &str) -> String { format!("{}ου", stem) }
fn g_anthropos_acc_sg(stem: &str) -> String { format!("{}ο", stem) }
fn g_anthropos_voc_sg(stem: &str) -> String { format!("{}ε", stem) }
fn g_anthropos_nom_pl(stem: &str) -> String { format!("{}οι", stem) }
fn g_anthropos_gen_pl(stem: &str) -> String { format!("{}ων", stem) }
fn g_anthropos_acc_pl(stem: &str) -> String { format!("{}ους", stem) }
fn g_anthropos_voc_pl(stem: &str) -> String { format!("{}οι", stem) }

fn g_kafes_nom_sg(stem: &str) -> String { format!("{}ές", stem) }
fn g_kafes_gen_sg(stem: &str) -> String { format!("{}έ", stem) }
fn g_kafes_acc_sg(stem: &str) -> String { format!("{}έ", stem) }
fn g_kafes_voc_sg(stem: &str) -> String { format!("{}έ", stem) }
fn g_kafes_nom_pl(stem: &str) -> String { format!("{}έδες", stem) }
fn g_kafes_gen_pl(stem: &str) -> String { format!("{}έδων", stem) }
fn g_kafes_acc_pl(stem: &str) -> String { format!("{}έδες", stem) }
fn g_kafes_voc_pl(stem: &str) -> String { format!("{}έδες", stem) }

fn g_thalassa_nom_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_thalassa_gen_sg(stem: &str) -> String { format!("{}ας", stem) }
fn g_thalassa_acc_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_thalassa_voc_sg(stem: &str) -> String { format!("{}α", stem) }
fn g_thalassa_nom_pl(stem: &str) -> String { format!("{}ες", stem) }
fn g_thalassa_gen_pl(stem: &str) -> String { format!("{}ων", stem) }
fn g_thalassa_acc_pl(stem: &str) -> String { format!("{}ες", stem) }
fn g_thalassa_voc_pl(stem: &str) -> String { format!("{}ες", stem) }

fn g_poli_nom_sg(stem: &str) -> String { format!("{}η", stem) }
fn g_poli_gen_sg(stem: &str) -> String { format!("{}ης", stem) }
fn g_poli_acc_sg(stem: &str) -> String { format!("{}η", stem) }
fn g_poli_voc_sg(stem: &str) -> String { format!("{}η", stem) }
fn g_poli_nom_pl(stem: &str) -> String { format!("{}εις", stem) }
fn g_poli_gen_pl(stem: &str) -> String { format!("{}εων", stem) }
fn g_poli_acc_pl(stem: &str) -> String { format!("{}εις", stem) }
fn g_poli_voc_pl(stem: &str) -> String { format!("{}εις", stem) }

fn g_paidi_nom_sg(stem: &str) -> String { format!("{}ί", stem) }
fn g_paidi_gen_sg(stem: &str) -> String { format!("{}ιού", stem) }
fn g_paidi_acc_sg(stem: &str) -> String { format!("{}ί", stem) }
fn g_paidi_voc_sg(stem: &str) -> String { format!("{}ί", stem) }
fn g_paidi_nom_pl(stem: &str) -> String { format!("{}ιά", stem) }
fn g_paidi_gen_pl(stem: &str) -> String { format!("{}ιών", stem) }
fn g_paidi_acc_pl(stem: &str) -> String { format!("{}ιά", stem) }
fn g_paidi_voc_pl(stem: &str) -> String { format!("{}ιά", stem) }

fn g_vivlio_nom_sg(stem: &str) -> String { format!("{}ο", stem) }
fn g_vivlio_gen_sg(stem: &str) -> String { format!("{}ου", stem) }
fn g_vivlio_acc_sg(stem: &str) -> String { format!("{}ο", stem) }
fn g_vivlio_voc_sg(stem: &str) -> String { format!("{}ο", stem) }
fn g_vivlio_nom_pl(stem: &str) -> String { format!("{}α", stem) }
fn g_vivlio_gen_pl(stem: &str) -> String { format!("{}ων", stem) }
fn g_vivlio_acc_pl(stem: &str) -> String { format!("{}α", stem) }
fn g_vivlio_voc_pl(stem: &str) -> String { format!("{}α", stem) }

fn g_pragma_nom_sg(stem: &str) -> String { format!("{}μα", stem) }
fn g_pragma_gen_sg(stem: &str) -> String { format!("{}ματος", stem) }
fn g_pragma_acc_sg(stem: &str) -> String { format!("{}μα", stem) }
fn g_pragma_voc_sg(stem: &str) -> String { format!("{}μα", stem) }
fn g_pragma_nom_pl(stem: &str) -> String { format!("{}ματα", stem) }
fn g_pragma_gen_pl(stem: &str) -> String { format!("{}μάτων", stem) }
fn g_pragma_acc_pl(stem: &str) -> String { format!("{}ματα", stem) }
fn g_pragma_voc_pl(stem: &str) -> String { format!("{}ματα", stem) }

const PHYLAKAS: Pattern = Pattern {
    ending: "ας",
    cases: &[
        ("nom_sg", g_phylakas_nom_sg), ("gen_sg", g_phylakas_gen_sg),
        ("acc_sg", g_phylakas_acc_sg), ("voc_sg", g_phylakas_voc_sg),
        ("nom_pl", g_phylakas_nom_pl), ("gen_pl", g_phylakas_gen_pl),
        ("acc_pl", g_phylakas_acc_pl), ("voc_pl", g_phylakas_voc_pl),
    ],
};
const ANTHROPOS: Pattern = Pattern {
    ending: "ος",
    cases: &[
        ("nom_sg", g_anthropos_nom_sg), ("gen_sg", g_anthropos_gen_sg),
        ("acc_sg", g_anthropos_acc_sg), ("voc_sg", g_anthropos_voc_sg),
        ("nom_pl", g_anthropos_nom_pl), ("gen_pl", g_anthropos_gen_pl),
        ("acc_pl", g_anthropos_acc_pl), ("voc_pl", g_anthropos_voc_pl),
    ],
};
const KAFES: Pattern = Pattern {
    ending: "ές",
    cases: &[
        ("nom_sg", g_kafes_nom_sg), ("gen_sg", g_kafes_gen_sg),
        ("acc_sg", g_kafes_acc_sg), ("voc_sg", g_kafes_voc_sg),
        ("nom_pl", g_kafes_nom_pl), ("gen_pl", g_kafes_gen_pl),
        ("acc_pl", g_kafes_acc_pl), ("voc_pl", g_kafes_voc_pl),
    ],
};
const THALASSA: Pattern = Pattern {
    ending: "α",
    cases: &[
        ("nom_sg", g_thalassa_nom_sg), ("gen_sg", g_thalassa_gen_sg),
        ("acc_sg", g_thalassa_acc_sg), ("voc_sg", g_thalassa_voc_sg),
        ("nom_pl", g_thalassa_nom_pl), ("gen_pl", g_thalassa_gen_pl),
        ("acc_pl", g_thalassa_acc_pl), ("voc_pl", g_thalassa_voc_pl),
    ],
};
const POLI: Pattern = Pattern {
    ending: "η",
    cases: &[
        ("nom_sg", g_poli_nom_sg), ("gen_sg", g_poli_gen_sg),
        ("acc_sg", g_poli_acc_sg), ("voc_sg", g_poli_voc_sg),
        ("nom_pl", g_poli_nom_pl), ("gen_pl", g_poli_gen_pl),
        ("acc_pl", g_poli_acc_pl), ("voc_pl", g_poli_voc_pl),
    ],
};
const PAIDI: Pattern = Pattern {
    ending: "ί",
    cases: &[
        ("nom_sg", g_paidi_nom_sg), ("gen_sg", g_paidi_gen_sg),
        ("acc_sg", g_paidi_acc_sg), ("voc_sg", g_paidi_voc_sg),
        ("nom_pl", g_paidi_nom_pl), ("gen_pl", g_paidi_gen_pl),
        ("acc_pl", g_paidi_acc_pl), ("voc_pl", g_paidi_voc_pl),
    ],
};
const VIVLIO: Pattern = Pattern {
    ending: "ο",
    cases: &[
        ("nom_sg", g_vivlio_nom_sg), ("gen_sg", g_vivlio_gen_sg),
        ("acc_sg", g_vivlio_acc_sg), ("voc_sg", g_vivlio_voc_sg),
        ("nom_pl", g_vivlio_nom_pl), ("gen_pl", g_vivlio_gen_pl),
        ("acc_pl", g_vivlio_acc_pl), ("voc_pl", g_vivlio_voc_pl),
    ],
};
const PRAGMA: Pattern = Pattern {
    ending: "μα",
    cases: &[
        ("nom_sg", g_pragma_nom_sg), ("gen_sg", g_pragma_gen_sg),
        ("acc_sg", g_pragma_acc_sg), ("voc_sg", g_pragma_voc_sg),
        ("nom_pl", g_pragma_nom_pl), ("gen_pl", g_pragma_gen_pl),
        ("acc_pl", g_pragma_acc_pl), ("voc_pl", g_pragma_voc_pl),
    ],
};

fn patterns() -> &'static HashMap<&'static str, &'static Pattern> {
    static M: OnceLock<HashMap<&'static str, &'static Pattern>> = OnceLock::new();
    M.get_or_init(|| {
        let mut m = HashMap::new();
        m.insert("'φύλακας'", &PHYLAKAS);
        m.insert("'άνθρωπος'", &ANTHROPOS);
        m.insert("'καφές'", &KAFES);
        m.insert("'θάλασσα'", &THALASSA);
        m.insert("'πόλη'", &POLI);
        m.insert("'παιδί'", &PAIDI);
        m.insert("'βιβλίο'", &VIVLIO);
        m.insert("'πράγμα'", &PRAGMA);
        m
    })
}

fn aliases() -> &'static HashMap<&'static str, &'static str> {
    static M: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();
    M.get_or_init(|| {
        let mut m = HashMap::new();
        m.insert("'φύλαξ'", "'φύλακας'");
        m.insert("'άρχων'", "'φύλακας'");
        m.insert("'γέροντας'", "'φύλακας'");
        m.insert("'λέων'", "'φύλακας'");
        m.insert("'λόγος'", "'άνθρωπος'");
        m.insert("'δρόμος'", "'άνθρωπος'");
        m.insert("'ουρανός'", "'άνθρωπος'");
        m.insert("'γυναίκα'", "'θάλασσα'");
        m.insert("'καρδιά'", "'θάλασσα'");
        m.insert("'νίκη'", "'πόλη'");
        m.insert("'αρχή'", "'πόλη'");
        m.insert("'μωρό'", "'παιδί'");
        m.insert("'δέντρο'", "'βιβλίο'");
        m.insert("'νερό'", "'βιβλίο'");
        m
    })
}

fn resolve_pattern_name(name: &str) -> &str {
    aliases().get(name).copied().unwrap_or(name)
}

pub fn is_declension_template(template_name: &str) -> bool {
    if template_name.is_empty() {
        return false;
    }
    if template_name.starts_with("el-κλίση-") || template_name.starts_with("el-κλίσ-") {
        return true;
    }
    let clean = template_name.strip_prefix("el-κλίση-").unwrap_or(template_name);
    patterns().contains_key(clean) || aliases().contains_key(clean)
}

pub fn expand_declension(word: &str, template_name: &str) -> Vec<String> {
    let pat_name = resolve_pattern_name(template_name);
    let pat = match patterns().get(pat_name) {
        Some(p) => *p,
        None => return Vec::new(),
    };

    let stem = match extract_stem(word, pat.ending) {
        Some(s) => s,
        None => return Vec::new(),
    };

    let mut forms: Vec<String> = Vec::new();
    for (_case, gen_fn) in pat.cases {
        let form = gen_fn(&stem);
        if !form.is_empty() && form != word {
            forms.push(form);
        }
    }

    let variations = generate_variations(&forms);
    forms.extend(variations);

    let mut seen = std::collections::HashSet::new();
    let mut unique = Vec::new();
    for f in forms {
        if seen.insert(f.clone()) {
            unique.push(f);
        }
    }
    unique
}

fn extract_stem(word: &str, ending: &str) -> Option<String> {
    if word.ends_with(ending) {
        Some(word[..word.len() - ending.len()].to_string())
    } else {
        None
    }
}

fn generate_variations(forms: &[String]) -> Vec<String> {
    let accented_chars: &[char] = &['ά', 'έ', 'ή', 'ί', 'ό', 'ύ', 'ώ'];
    let mut variations = Vec::new();
    for form in forms {
        // Capitalize first char
        let capitalized = capitalize_first(form);
        if capitalized != *form {
            variations.push(capitalized);
        }
        // Accent removal for -ων without -ών
        if form.chars().any(|c| accented_chars.contains(&c))
            && form.ends_with("ων")
            && !form.ends_with("ών")
        {
            let alt = move_accent_to_antepenult(form);
            if alt != *form {
                variations.push(alt);
            }
        }
    }
    variations
}

fn capitalize_first(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        None => String::new(),
        Some(c) => {
            let upper: String = c.to_uppercase().collect();
            format!("{}{}", upper, chars.as_str())
        }
    }
}

fn move_accent_to_antepenult(word: &str) -> String {
    word.chars()
        .map(|c| match c {
            'ά' => 'α', 'έ' => 'ε', 'ή' => 'η', 'ί' => 'ι',
            'ό' => 'ο', 'ύ' => 'υ', 'ώ' => 'ω',
            _ => c,
        })
        .collect()
}

fn add_accent(stem: &str) -> String {
    let chars: Vec<char> = stem.chars().collect();
    if chars.len() < 3 {
        return stem.to_string();
    }
    const VOWELS: &str = "αεηιουωΑΕΗΙΟΥΩ";
    let vowel_positions: Vec<usize> = chars
        .iter()
        .enumerate()
        .filter(|(_, c)| VOWELS.contains(**c))
        .map(|(i, _)| i)
        .collect();

    if vowel_positions.len() >= 3 {
        let pos = vowel_positions[vowel_positions.len() - 3];
        let mut result: Vec<char> = chars;
        if let Some(accented) = add_accent_to_vowel(result[pos]) {
            result[pos] = accented;
        }
        result.into_iter().collect()
    } else {
        stem.to_string()
    }
}

fn add_accent_to_vowel(c: char) -> Option<char> {
    Some(match c {
        'α' => 'ά', 'ε' => 'έ', 'η' => 'ή', 'ι' => 'ί',
        'ο' => 'ό', 'υ' => 'ύ', 'ω' => 'ώ',
        'Α' => 'Ά', 'Ε' => 'Έ', 'Η' => 'Ή', 'Ι' => 'Ί',
        'Ο' => 'Ό', 'Υ' => 'Ύ', 'Ω' => 'Ώ',
        _ => return None,
    })
}

/// Strip the `el-κλίση-` (or `el-κλίσ-`) prefix from a template name.
pub fn strip_template_prefix(name: &str) -> &str {
    if let Some(rest) = name.strip_prefix("el-κλίση-") {
        return rest;
    }
    if let Some(rest) = name.strip_prefix("el-κλίσ-") {
        return rest;
    }
    name
}
