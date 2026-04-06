#
#  lib/greek_declension_templates.py
#  Expands Greek declension templates to generate inflected forms
#
#  Created by Francisco Riordan on 4/22/25.
#

import re


# Define declension patterns for common Greek noun types
DECLENSION_PATTERNS = {
    # Masculine nouns in -ας (like φύλακας, άρχοντας)
    "'φύλακας'": {
        'type': 'masculine',
        'pattern': {
            # Singular
            'nom_sg': lambda stem: stem + 'ας',
            'gen_sg': lambda stem: stem + 'α',
            'acc_sg': lambda stem: stem + 'α',
            'voc_sg': lambda stem: stem + 'α',
            # Plural
            'nom_pl': lambda stem: stem + 'ες',
            'gen_pl': lambda stem: _add_accent(stem) + 'ων',
            'acc_pl': lambda stem: stem + 'ες',
            'voc_pl': lambda stem: stem + 'ες',
        },
    },

    # Masculine nouns in -ος (like άνθρωπος, λόγος)
    "'άνθρωπος'": {
        'type': 'masculine',
        'pattern': {
            'nom_sg': lambda stem: stem + 'ος',
            'gen_sg': lambda stem: stem + 'ου',
            'acc_sg': lambda stem: stem + 'ο',
            'voc_sg': lambda stem: stem + 'ε',
            'nom_pl': lambda stem: stem + 'οι',
            'gen_pl': lambda stem: stem + 'ων',
            'acc_pl': lambda stem: stem + 'ους',
            'voc_pl': lambda stem: stem + 'οι',
        },
    },

    # Masculine nouns in -ής/-ές (like καφές)
    "'καφές'": {
        'type': 'masculine',
        'pattern': {
            'nom_sg': lambda stem: stem + 'ές',
            'gen_sg': lambda stem: stem + 'έ',
            'acc_sg': lambda stem: stem + 'έ',
            'voc_sg': lambda stem: stem + 'έ',
            'nom_pl': lambda stem: stem + 'έδες',
            'gen_pl': lambda stem: stem + 'έδων',
            'acc_pl': lambda stem: stem + 'έδες',
            'voc_pl': lambda stem: stem + 'έδες',
        },
    },

    # Feminine nouns in -α (like θάλασσα, μέρα)
    "'θάλασσα'": {
        'type': 'feminine',
        'pattern': {
            'nom_sg': lambda stem: stem + 'α',
            'gen_sg': lambda stem: stem + 'ας',
            'acc_sg': lambda stem: stem + 'α',
            'voc_sg': lambda stem: stem + 'α',
            'nom_pl': lambda stem: stem + 'ες',
            'gen_pl': lambda stem: stem + 'ων',
            'acc_pl': lambda stem: stem + 'ες',
            'voc_pl': lambda stem: stem + 'ες',
        },
    },

    # Feminine nouns in -η (like πόλη, αγάπη)
    "'πόλη'": {
        'type': 'feminine',
        'pattern': {
            'nom_sg': lambda stem: stem + 'η',
            'gen_sg': lambda stem: stem + 'ης',
            'acc_sg': lambda stem: stem + 'η',
            'voc_sg': lambda stem: stem + 'η',
            'nom_pl': lambda stem: stem + 'εις',
            'gen_pl': lambda stem: stem + 'εων',
            'acc_pl': lambda stem: stem + 'εις',
            'voc_pl': lambda stem: stem + 'εις',
        },
    },

    # Neuter nouns in -ι (like παιδί)
    "'παιδί'": {
        'type': 'neuter',
        'pattern': {
            'nom_sg': lambda stem: stem + 'ί',
            'gen_sg': lambda stem: stem + 'ιού',
            'acc_sg': lambda stem: stem + 'ί',
            'voc_sg': lambda stem: stem + 'ί',
            'nom_pl': lambda stem: stem + 'ιά',
            'gen_pl': lambda stem: stem + 'ιών',
            'acc_pl': lambda stem: stem + 'ιά',
            'voc_pl': lambda stem: stem + 'ιά',
        },
    },

    # Neuter nouns in -ο (like βιβλίο)
    "'βιβλίο'": {
        'type': 'neuter',
        'pattern': {
            'nom_sg': lambda stem: stem + 'ο',
            'gen_sg': lambda stem: stem + 'ου',
            'acc_sg': lambda stem: stem + 'ο',
            'voc_sg': lambda stem: stem + 'ο',
            'nom_pl': lambda stem: stem + 'α',
            'gen_pl': lambda stem: stem + 'ων',
            'acc_pl': lambda stem: stem + 'α',
            'voc_pl': lambda stem: stem + 'α',
        },
    },

    # Neuter nouns in -μα (like πράγμα)
    "'πράγμα'": {
        'type': 'neuter',
        'pattern': {
            'nom_sg': lambda stem: stem + 'μα',
            'gen_sg': lambda stem: stem + 'ματος',
            'acc_sg': lambda stem: stem + 'μα',
            'voc_sg': lambda stem: stem + 'μα',
            'nom_pl': lambda stem: stem + 'ματα',
            'gen_pl': lambda stem: stem + 'μάτων',
            'acc_pl': lambda stem: stem + 'ματα',
            'voc_pl': lambda stem: stem + 'ματα',
        },
    },
}

# Additional pattern aliases
PATTERN_ALIASES = {
    "'φύλαξ'": "'φύλακας'",
    "'άρχων'": "'φύλακας'",
    "'γέροντας'": "'φύλακας'",
    "'λέων'": "'φύλακας'",
    "'λόγος'": "'άνθρωπος'",
    "'δρόμος'": "'άνθρωπος'",
    "'ουρανός'": "'άνθρωπος'",
    "'γυναίκα'": "'θάλασσα'",
    "'καρδιά'": "'θάλασσα'",
    "'νίκη'": "'πόλη'",
    "'αρχή'": "'πόλη'",
    "'μωρό'": "'παιδί'",
    "'δέντρο'": "'βιβλίο'",
    "'νερό'": "'βιβλίο'",
}


def expand_declension(word, template_name):
    """Expand a declension template to generate inflected forms."""
    # Extract the stem by removing the ending
    stem = _extract_stem(word, template_name)
    if stem is None:
        return []

    # Get the pattern name, resolving aliases
    pattern_name = PATTERN_ALIASES.get(template_name, template_name)
    pattern = DECLENSION_PATTERNS.get(pattern_name)

    if pattern is None:
        return []

    # Generate all forms
    forms = []
    for case_name, generator in pattern['pattern'].items():
        form = generator(stem)
        if form and form != word:
            forms.append(form)

    # Add some common variations
    forms.extend(_generate_variations(forms))

    # Deduplicate while preserving order
    seen = set()
    unique_forms = []
    for form in forms:
        if form not in seen:
            seen.add(form)
            unique_forms.append(form)

    return unique_forms


def _extract_stem(word, template_name):
    """Extract the stem from a word based on the template pattern."""
    # Get the pattern to determine what to remove
    pattern_name = PATTERN_ALIASES.get(template_name, template_name)

    endings = {
        "'φύλακας'": 'ας',
        "'άνθρωπος'": 'ος',
        "'καφές'": 'ές',
        "'θάλασσα'": 'α',
        "'πόλη'": 'η',
        "'παιδί'": 'ί',
        "'βιβλίο'": 'ο',
        "'πράγμα'": 'μα',
    }

    ending = endings.get(pattern_name)
    if ending is None:
        return None

    if word.endswith(ending):
        return word[:-len(ending)]
    return None


def _generate_variations(forms):
    """Generate common variations of inflected forms."""
    variations = []

    for form in forms:
        # Add capitalized version
        capitalized = form[0].upper() + form[1:] if form else form
        if capitalized != form:
            variations.append(capitalized)

        # Add version with moved accent (common in Greek)
        accented_chars = 'άέήίόύώ'
        if any(c in form for c in accented_chars):
            # Simple accent movement for genitive plural
            if form.endswith('ων') and not form.endswith('ών'):
                alt_form = _move_accent_to_antepenult(form)
                if alt_form != form:
                    variations.append(alt_form)

    return variations


def _add_accent(stem):
    """For genitive plural, often need to add accent to antepenultimate syllable."""
    if len(stem) >= 3:
        result = list(stem)
        vowels = "αεηιουωΑΕΗΙΟΥΩ"
        vowel_positions = []

        for i, char in enumerate(stem):
            if char in vowels:
                vowel_positions.append(i)

        if len(vowel_positions) >= 3:
            pos = vowel_positions[-3]
            accented = _add_accent_to_vowel(result[pos])
            if accented:
                result[pos] = accented

        return ''.join(result)
    else:
        return stem


def _move_accent_to_antepenult(word):
    """Simplified accent movement - remove all accents."""
    accent_map = str.maketrans('άέήίόύώ', 'αεηιουω')
    return word.translate(accent_map)


def _add_accent_to_vowel(vowel):
    """Add an accent to a Greek vowel."""
    accents = {
        'α': 'ά', 'ε': 'έ', 'η': 'ή', 'ι': 'ί',
        'ο': 'ό', 'υ': 'ύ', 'ω': 'ώ',
        'Α': 'Ά', 'Ε': 'Έ', 'Η': 'Ή', 'Ι': 'Ί',
        'Ο': 'Ό', 'Υ': 'Ύ', 'Ω': 'Ώ',
    }
    return accents.get(vowel, vowel)


def is_declension_template(template_name):
    """Check if a template is a declension template."""
    if not template_name:
        return False

    # Check if it starts with el-κλίση- (noun declension) or el-κλίσ- (verb conjugation)
    if template_name.startswith('el-κλίση-') or template_name.startswith('el-κλίσ-'):
        return True

    # Check if it's in our patterns or aliases
    clean_name = re.sub(r'^el-κλίση-', '', template_name)
    return clean_name in DECLENSION_PATTERNS or clean_name in PATTERN_ALIASES


def extract_template_info(template_text):
    """Extract template name from text like {{el-κλίση-'φύλακας'}}."""
    m = re.search(r'\{\{(el-κλίση-[^}|]+)', template_text)
    if m:
        template_name = m.group(1)
        pattern_name = re.sub(r'^el-κλίση-', '', template_name)
        return (template_name, pattern_name)
    return None
