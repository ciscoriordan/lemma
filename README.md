# Lemma Modern Greek Dictionary for Kindle

A comprehensive Greek dictionary generator for Kindle e-readers, supporting both Greek-English and Greek-Greek (monolingual) dictionaries. This tool processes Wiktionary data to create `.mobi` dictionary files optimized for Kindle devices.

![krybontas](https://github.com/user-attachments/assets/b4720bd2-b3d6-4bbc-9295-5e0944cd0393)

## Quick Install

### Installing Dictionaries on Your Kindle

1. **Connect your Kindle** to your computer via USB cable
2. **Open the Kindle drive** on your computer
3. **Navigate to the `documents/dictionaries` folder** on your Kindle
   - If the `dictionaries` folder doesn't exist, create it inside `documents`
4. **Copy the `.mobi` file(s)** from the `/dist` folder to `documents/dictionaries`
   - For Greek-English: Copy the single `.mobi` file
   - For Greek-Greek: Copy all 8 part files
5. **Safely eject your Kindle** from your computer
6. **Restart your Kindle**:
   - Hold the power button for 40 seconds, or
   - Go to Settings → Device Options → Restart
7. The dictionary will be available after restart

### Setting as Default Greek Dictionary

1. **Open any Greek text** on your Kindle
2. **Select a Greek word** to look up
3. **Tap the dictionary name** at the bottom of the popup
4. **Select "Lemma Greek Dictionary"** from the list
   - For Greek-Greek: The appropriate part will be selected automatically based on the word
5. The dictionary is now your default for Greek lookups

## Pre-built Dictionaries

Ready-to-use dictionary files are available in the `/dist` folder:

### Greek-English Dictionary

- `lemma_greek_en_[date].mobi` - Single file containing all entries

### Greek-Greek (Monolingual) Dictionary

Due to Kindle's size limitations, the Greek monolingual dictionary is split into 5 parts by letter groups:

- `lemma_greek_el_[date]_alpha_beta_gamma_delta_epsilon.mobi` - Part 1: Α-Β-Γ-Δ-Ε
- `lemma_greek_el_[date]_zeta_eta_theta_iota_kappa.mobi` - Part 2: Ζ-Η-Θ-Ι-Κ
- `lemma_greek_el_[date]_lambda_mu_nu_xi_omicron.mobi` - Part 3: Λ-Μ-Ν-Ξ-Ο
- `lemma_greek_el_[date]_pi_rho_sigma_tau_upsilon.mobi` - Part 4: Π-Ρ-Σ-Τ-Υ
- `lemma_greek_el_[date]_phi_chi_psi_omega.mobi` - Part 5: Φ-Χ-Ψ-Ω

**Important**: Install all 5 parts for complete coverage. Kindle will automatically select the correct part based on the word you're looking up. Each part includes inflections that belong to headwords in that part, even if those inflections would alphabetically belong elsewhere, ensuring lookups always work correctly.

## Features

- **Bilingual & Monolingual Support**: Generate Greek-English or Greek-Greek dictionaries
- **Smart Letter-Based Splitting**: Greek monolingual dictionary splits into 8 logical parts by letter groups
- **Inflection Support**: Automatically links inflected forms to their lemmas
- **Inflection Grouping**: Headwords are included in any part where their inflections appear
- **Etymology Information**: Includes word origins where available (English dictionary only)
- **Clean Formatting**: Optimized for Kindle's dictionary popup interface
- **Testing Mode**: Create smaller dictionaries for testing (1-100% of entries)

## Building from Source

### Prerequisites

- Ruby (2.5 or higher)
- Kindle Previewer 3 (for `.mobi` generation)
- Git LFS (for handling large dictionary data files)

### Installation

```bash
# Clone the repository
git clone https://github.com/fr2019/lemma.git
cd lemma

# Install Git LFS if not already installed
git lfs install
git lfs pull

# Run the generator
ruby greek_kindle_dictionary.rb [options]
```

### Options

```bash
# Generate Greek-English dictionary (default)
ruby greek_kindle_dictionary.rb

# Generate Greek-Greek monolingual dictionary (all 5 parts)
ruby greek_kindle_dictionary.rb -s el

# Generate only part 2 (Ζ-Η-Θ-Ι-Κ) of Greek-Greek dictionary
ruby greek_kindle_dictionary.rb -s el -p 2

# Generate a test dictionary with only 10% of entries
ruby greek_kindle_dictionary.rb -l 10

# Combine options
ruby greek_kindle_dictionary.rb -s el -l 5
```

### Command Line Arguments

- `-s, --source LANG`: Source Wiktionary language ('en' for English or 'el' for Greek)
- `-p, --part NUMBER`: For Greek source (-s el), generate specific part (1-5)
- `-l, --limit PERCENT`: Limit to first X% of words (useful for testing)
- `-h, --help`: Show help message with letter ranges for each part

## Data Sources

The dictionaries are built from:

- **Primary Source**: [Kaikki.org](https://kaikki.org/) - Machine-readable Wiktionary data
- **Fallback Data**: Pre-downloaded JSONL files in the repository (via Git LFS)

Data files:

- `greek_data_en_20250716.jsonl` - English Wiktionary Greek entries
- `greek_data_el_20250717.jsonl` - Greek Wiktionary Greek entries

## Dictionary Content

The dictionaries include:

- **Headwords**: Main dictionary entries
- **Inflected Forms**: Automatically redirect to their lemmas
- **Part of Speech**: Grammatical category (abbreviated in Greek for monolingual)
- **Definitions**: Multiple numbered definitions where applicable
- **Etymology**: Word origins and history (English dictionary only)
- **Domain Tags**: Subject area indicators (e.g., γλωσσολογία, γραμματική)

### Excluded Content

The following are filtered out as they cannot be selected in Kindle texts:

- Prefixes and suffixes (e.g., `-ικός`, `προ-`)
- Combining forms and clitics
- Individual letters and symbols
- Abbreviations and contractions

## Understanding the Split Dictionary

The Greek monolingual dictionary contains over 449,000 headwords. To ensure reliable building and optimal performance, the dictionary is split into 5 parts based on Greek letter groups (5 letters per part, except the last):

| Part | Letters   | Example Words                         |
| ---- | --------- | ------------------------------------- |
| 1    | Α-Β-Γ-Δ-Ε | αγάπη, βιβλίο, γάτα, δέντρο, ελπίδα   |
| 2    | Ζ-Η-Θ-Ι-Κ | ζωή, ήλιος, θάλασσα, ιστορία, καρδιά  |
| 3    | Λ-Μ-Ν-Ξ-Ο | λόγος, μητέρα, νερό, ξύλο, ουρανός    |
| 4    | Π-Ρ-Σ-Τ-Υ | πατέρας, ρόδο, σπίτι, τραγούδι, ύπνος |
| 5    | Φ-Χ-Ψ-Ω   | φως, χαρά, ψυχή, ώρα                  |

Each part contains approximately 80,000-100,000 headwords, plus any headwords whose inflected forms start with those letters. This ensures that looking up any inflected form will always find its lemma.

## Troubleshooting

### Dictionary Not Appearing

- Ensure the `.mobi` file(s) are in the `documents/dictionaries` folder
- For Greek-Greek: Make sure all 5 parts are installed
- **Always restart your Kindle** after adding new dictionaries
- If still not appearing, try a hard restart (hold power button for 40 seconds)

### Lookup Not Working

- Make sure you've set the dictionary as default for Greek
- For Greek-Greek: Ensure you have all 5 parts installed
- Some older Kindle models may have limited Greek support

### Building Issues

- **Kindle Previewer not found**: Install from [Amazon's website](https://www.amazon.com/gp/feature.html?docId=1000765261)
- **Download freezes**: Use pre-downloaded data files from the repository
- **Memory issues**: Use the `-l` option to build smaller test dictionaries first
- **Part generation fails**: Ensure you have enough disk space for temporary files

## License

Dictionary content is derived from Wiktionary and is available under the Creative Commons Attribution-ShareAlike License.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- Wiktionary contributors for the source data
- [Kaikki.org](https://kaikki.org/) for providing machine-readable Wiktionary dumps
