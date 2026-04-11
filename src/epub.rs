// Packages the output directory into a valid EPUB file.

use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipWriter};

pub struct EpubGenerator<'a> {
    pub output_dir: &'a Path,
    pub source_lang: &'a str,
    pub download_date: &'a str,
    pub opf_filename: &'a str,
}

impl<'a> EpubGenerator<'a> {
    pub fn generate(&self) -> std::io::Result<PathBuf> {
        println!("\nGenerating EPUB file...");

        let epub_name = format!("lemma_greek_{}_{}.epub", self.source_lang, self.download_date);
        let epub_path = self.output_dir.join(&epub_name);

        let file = File::create(&epub_path)?;
        let mut zw = ZipWriter::new(file);

        // mimetype first, stored uncompressed
        let stored = SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
        zw.start_file("mimetype", stored)?;
        zw.write_all(b"application/epub+zip")?;

        let deflated = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);

        let container_xml = "<?xml version=\"1.0\"?>\n<container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">\n  <rootfiles>\n    <rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\"/>\n  </rootfiles>\n</container>\n";
        zw.start_file("META-INF/container.xml", deflated)?;
        zw.write_all(container_xml.as_bytes())?;

        // OPF -> OEBPS/content.opf
        let opf_path = self.output_dir.join(self.opf_filename);
        let mut opf_bytes = Vec::new();
        File::open(&opf_path)?.read_to_end(&mut opf_bytes)?;
        zw.start_file("OEBPS/content.opf", deflated)?;
        zw.write_all(&opf_bytes)?;

        let content_files = ["toc.ncx", "cover.jpg", "cover.html", "usage.html", "copyright.html", "content.html"];
        for filename in &content_files {
            let fp = self.output_dir.join(filename);
            if fp.exists() {
                let mut buf = Vec::new();
                File::open(&fp)?.read_to_end(&mut buf)?;
                zw.start_file(format!("OEBPS/{}", filename), deflated)?;
                zw.write_all(&buf)?;
            } else {
                println!("  Warning: expected file not found: {}", filename);
            }
        }

        zw.finish()?;

        let size_mb = fs::metadata(&epub_path)?.len() as f64 / 1024.0 / 1024.0;
        println!("  Created {} ({:.2} MB)", epub_name, size_mb);

        self.copy_to_dist(&epub_path, &epub_name);

        Ok(epub_path)
    }

    fn copy_to_dist(&self, epub_path: &Path, epub_name: &str) {
        let dist_dir = PathBuf::from("dist");
        if fs::create_dir_all(&dist_dir).is_err() { return; }
        let dest = dist_dir.join(epub_name);
        if fs::copy(epub_path, &dest).is_ok() {
            println!("  Copied {} to dist/", epub_name);
        }
    }
}
