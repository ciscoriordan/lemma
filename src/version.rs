// The lemma generator version, sourced from Cargo.toml at compile time.
//
// Used in the stdout banner and embedded into the dictionary's copyright
// page and OPF metadata. NOT used in any filename — lemma's naming
// convention is "no dates and no version numbers in filenames or build
// directories." Versions are content, not naming.

pub const LEMMA_VERSION: &str = env!("CARGO_PKG_VERSION");
