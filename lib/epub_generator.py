#
#  lib/epub_generator.py
#  Packages the output directory into a valid EPUB file
#
#  Created by Francisco Riordan on 4/4/26.
#

import os
import shutil
import zipfile


class EpubGenerator:
    def __init__(self, generator, opf_filename=None):
        self.generator = generator
        self.output_dir = generator.output_dir
        self.opf_filename = opf_filename

    def generate(self):
        print("\nGenerating EPUB file...")

        vol_suffix = f"_{self.generator.volume_suffix}" if self.generator.volume_suffix else ""
        epub_name = f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}{vol_suffix}.epub"
        epub_path = os.path.join(self.output_dir, epub_name)

        with zipfile.ZipFile(epub_path, 'w') as zf:
            # mimetype must be the first entry, stored without compression
            zf.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)

            # META-INF/container.xml
            container_xml = """\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
            zf.writestr('META-INF/container.xml', container_xml, compress_type=zipfile.ZIP_DEFLATED)

            # Add OPF file as OEBPS/content.opf
            opf_file = self.opf_filename or f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}.opf"
            opf_path = os.path.join(self.output_dir, opf_file)
            zf.write(opf_path, 'OEBPS/content.opf', compress_type=zipfile.ZIP_DEFLATED)

            # Add the other content files into OEBPS/
            content_files = ['toc.ncx', 'cover.html', 'usage.html', 'copyright.html', 'content.html']
            for filename in content_files:
                filepath = os.path.join(self.output_dir, filename)
                if os.path.exists(filepath):
                    zf.write(filepath, f'OEBPS/{filename}', compress_type=zipfile.ZIP_DEFLATED)
                else:
                    print(f"  Warning: expected file not found: {filename}")

        size_mb = os.path.getsize(epub_path) / 1024 / 1024
        print(f"  Created {epub_name} ({size_mb:.2f} MB)")

        # Copy to dist folder
        self._copy_to_dist(epub_path, epub_name)

        return epub_path

    def _copy_to_dist(self, epub_path, epub_name):
        try:
            # Project root is one level up from lib/
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dist_dir = os.path.join(project_root, "dist")
            os.makedirs(dist_dir, exist_ok=True)

            dest_path = os.path.join(dist_dir, epub_name)
            shutil.copy2(epub_path, dest_path)
            print(f"  Copied {epub_name} to dist/")
        except Exception as e:
            print(f"  Warning: Could not copy EPUB file to dist: {e}")
