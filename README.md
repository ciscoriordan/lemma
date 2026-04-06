# Lemma Modern Greek Dictionary for Kindle

A comprehensive Greek dictionary generator for Kindle e-readers, supporting both Greek-English and Greek-Greek (monolingual) dictionaries. This tool processes Wiktionary data to create `.mobi` dictionary files for sideloading onto Kindle devices.

![krybontas](https://github.com/user-attachments/assets/b4720bd2-b3d6-4bbc-9295-5e0944cd0393)

## Quick Install

### Installing Dictionaries on Your Kindle

1. **Connect your Kindle** to your computer via USB cable
2. **Open the Kindle drive** on your computer
3. **Navigate to the `documents/dictionaries` folder** on your Kindle
   - If the `dictionaries` folder doesn't exist, create it inside `documents`
4. **Copy the `.mobi` file(s)** from the `/dist` folder to `documents/dictionaries`
   - To generate `.mobi` files for sideloading, run with the `-m` flag (see below)
5. **Safely eject your Kindle** from your computer
6. **Restart your Kindle**:
   - Hold the power button for 40 seconds, or
   - Go to Settings > Device Options > Restart
7. The dictionary will be available after restart

### Setting as Default Greek Dictionary

1. **Open any Greek text** on your Kindle
2. **Select a Greek word** to look up
3. **Tap the dictionary name** at the bottom of the popup
4. **Select "Lemma Greek Dictionary"** from the list
5. The dictionary is now your default for Greek lookups

## Pre-built Dictionaries

Ready-to-use dictionary files are available in the `/dist` folder:

### Greek-English Dictionary

- `lemma_greek_en_[date].mobi` - MOBI for sideloading (generated with `-m` flag)

### Greek-Greek (Monolingual) Dictionary

- `lemma_greek_el_[date].mobi` - MOBI for sideloading (generated with `-m` flag)

## Features

- **Bilingual & Monolingual Support**: Generate Greek-English or Greek-Greek dictionaries
- **Inflection Support**: Automatically links inflected forms to their lemmas, with 2.76M form-to-lemma mappings from [Dilemma](https://github.com/fcsriordan/dilemma) when available
- **Lemma Equivalences**: Bridges cases where Wiktionary and Dilemma use different canonical forms for the same word (e.g., `τρώω`/`τρώγω`, `λέω`/`λέγω`), recovering ~742K additional inflections via 6,281 auto-generated equivalence pairs
- **Pre-Ranked Inflections**: When [Dilemma](https://github.com/fcsriordan/dilemma)'s `mg_ranked_forms.json` is available (from [HuggingFace Hub](https://huggingface.co/datasets/ciscoriordan/dilemma-data) or locally), inflections arrive pre-ranked by corpus frequency and case-deduplicated. Case variants (φας/Φας) are added after the inflection cap, not before, so each slot goes to a unique form. Falls back to local ranking via [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles 2018) if ranked forms aren't available
- **Cross-References**: Entries that are forms of other headwords include "see also" references, optionally as clickable links (`--links`)
- **Etymology Information**: Includes word origins where available (English dictionary, enabled with `--etymology`)
- **Clean Formatting**: Optimized for Kindle's dictionary popup interface
- **Testing Mode**: Create smaller dictionaries for testing (1-100% of entries)

## Building from Source

### Prerequisites

- Python 3.8+
- [kindling](https://pypi.org/project/kindling/) (optional, only needed for `.mobi` generation with `-m` flag): `pip install kindling`
- Works on macOS, Linux, and Windows

### Installation

```bash
# Clone the repository
git clone https://github.com/fr2019/lemma.git
cd lemma

# Run the generator (produces EPUB by default)
python3 greek_kindle_dictionary.py [options]
# On Windows, use: python greek_kindle_dictionary.py [options]
```

### Options

```bash
# Generate Greek-English dictionary (default, EPUB output)
python3 greek_kindle_dictionary.py

# Generate Greek-Greek monolingual dictionary
python3 greek_kindle_dictionary.py -s el

# Also generate .mobi for sideloading
python3 greek_kindle_dictionary.py -m

# Generate a test dictionary with only 10% of entries
python3 greek_kindle_dictionary.py -l 10

# Enable clickable cross-references between entries
python3 greek_kindle_dictionary.py --links

# Include etymology information (English dictionary)
python3 greek_kindle_dictionary.py --etymology

# Combine options
python3 greek_kindle_dictionary.py -s el -l 5 -m --links
```

### Command Line Arguments

- `-s, --source LANG`: Source Wiktionary language ('en' for English or 'el' for Greek)
- `-l, --limit PERCENT`: Limit to first X% of words (useful for testing)
- `-m, --mobi`: Also generate `.mobi` via kindling (for sideloading)
- `-i, --inflections N`: Max inflections per headword (default: 30)
- `--links`: Enable clickable cross-references between entries (default: off)
- `--etymology`: Include etymology information in entries (default: off)
- `-h, --help`: Show help message

## Data Sources

The dictionaries are built from:

- **Primary Source**: [Kaikki.org](https://kaikki.org/) - Machine-readable Wiktionary data (definitions, POS, etymology)
- **Inflection Data** (optional): [Dilemma](https://github.com/fcsriordan/dilemma) - Greek lemmatizer with 2.76M Modern Greek form-to-lemma mappings compiled from English and Greek Wiktionary, treebank corpora, and LSJ expansion
- **Ranked Inflections** (optional): Dilemma's `mg_ranked_forms.json` from the [`ciscoriordan/dilemma-data`](https://huggingface.co/datasets/ciscoriordan/dilemma-data) HuggingFace dataset provides pre-ranked, case-deduplicated inflection lists per lemma. Downloaded automatically if `huggingface_hub` is installed.
- **Frequency Data** (fallback): [FrequencyWords](https://github.com/hermitdave/FrequencyWords) - Word frequency lists derived from OpenSubtitles 2018 corpus, used to rank inflections when pre-ranked forms are not available
- **Fallback Data**: Pre-downloaded JSONL files in the repository

### Optional Configuration

To use local kaikki dumps or Dilemma inflection data, create a `.env` file in the project root:

```
KAIKKI_LOCAL_DIR=/path/to/kaikki/dumps
DILEMMA_DATA_DIR=/path/to/dilemma/data
```

When `DILEMMA_DATA_DIR` is set and `mg_lookup_scored.json` (or `mg_lookup.json`) is found, the generator will supplement kaikki-derived inflections with Dilemma's more comprehensive mappings. Without it, inflections are extracted from kaikki data only.

The generator also automatically looks for `mg_ranked_forms.json` (pre-ranked inflections) in three locations: `data/` in this project, the `DILEMMA_DATA_DIR`, or the [`ciscoriordan/dilemma-data`](https://huggingface.co/datasets/ciscoriordan/dilemma-data) HuggingFace dataset (requires `pip install huggingface_hub`).

#### Lemma Equivalences

Wiktionary and Dilemma sometimes disagree on the canonical lemma for a word (e.g., Wiktionary uses `τρώω` for "eat" while Dilemma files all 165 inflections under `τρώγω`). To bridge this, run:

```bash
python3 generate_mg_equivalences.py
```

This cross-references the two data sources, uses corpus frequency as a tiebreaker, and writes `data/mg_lemma_equivalences.json`. The dictionary generator loads this automatically. Without it, inflections filed under a different canonical form in Dilemma will be missed.

### Related Projects

- [Dilemma](https://github.com/fcsriordan/dilemma) - Greek lemmatizer. Provides the inflection lookup tables used by Lemma.
- [Opla](https://github.com/fcsriordan/opla) - Greek POS tagger and dependency parser, built on Dilemma for lemmatization.

## Dictionary Content

The dictionaries include:

- **Headwords**: Main dictionary entries
- **Inflected Forms**: Automatically redirect to their lemmas
- **Part of Speech**: Grammatical category (abbreviated in Greek for monolingual)
- **Definitions**: Multiple numbered definitions where applicable
- **Etymology**: Word origins and history (English dictionary only)
- **Domain Tags**: Subject area indicators (e.g., γλωσσολογία, γραμματική)

### Inflection Limit

Each headword includes up to 30 unique inflected forms (`MAX_INFLECTIONS` in `lib/html_generator.py`). When pre-ranked forms from Dilemma are available, these 30 slots are filled with case-deduplicated forms in corpus frequency order. Without pre-ranked forms, a local FrequencyRanker handles ranking. Testing against a real Greek ebook showed that 30 unique inflections per headword covers ~95% of inflected form lookups. At 50 the coverage reaches ~98%, at 100 it's ~99.9%.

Note: *kindlegen* has an undocumented limit of 255 inflection rules per entry. Since [kindling](https://github.com/ciscoriordan/kindling) uses orth-index-only encoding (no inflection INDX), this limit does not apply. The 30-form cap is a practical choice for file size and lookup performance, not a format constraint. Use `-i N` to adjust.

### Excluded Content

The following are filtered out as they cannot be selected in Kindle texts:

- Prefixes and suffixes (e.g., `-ικός`, `προ-`)
- Combining forms and clitics
- Individual letters and symbols
- Abbreviations and contractions

## Troubleshooting

### Dictionary Not Appearing

- Ensure the `.mobi` file(s) are in the `documents/dictionaries` folder
- **Always restart your Kindle** after adding new dictionaries
- If still not appearing, try a hard restart (hold power button for 40 seconds)

### Lookup Not Working

- Make sure you've set the dictionary as default for Greek
- Some older Kindle models may have limited Greek support

### Building Issues

- **kindling not found**: Only needed for `.mobi` generation (`-m` flag). Install with `pip install kindling`
- **Download freezes**: Use pre-downloaded data files from the repository
- **Memory issues**: Use the `-l` option to build smaller test dictionaries first

## License

- **Code**: [MIT License](LICENSE)
- **Dictionary content and data**: [Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/) (derived from Wiktionary)
- **Frequency data** (`data/el_full.txt`): [MIT License](https://github.com/hermitdave/FrequencyWords/blob/master/LICENSE) (from FrequencyWords/OpenSubtitles)

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- Wiktionary contributors for the source data
- [Kaikki.org](https://kaikki.org/) for providing machine-readable Wiktionary dumps
- [Dilemma](https://github.com/fcsriordan/dilemma) for Greek lemmatization and inflection data
- [FrequencyWords](https://github.com/hermitdave/FrequencyWords) for corpus frequency data (MIT license)
- [Opla](https://github.com/fcsriordan/opla) for Greek NLP infrastructure
