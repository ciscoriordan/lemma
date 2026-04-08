#
#  lib/mobi_generator.py
#  Handles MOBI file generation using kindling
#
#  Created by Francisco Riordan on 4/22/25.
#

import os
import shutil
import subprocess


class MobiGenerator:
    def __init__(self, generator, opf_filename=None):
        self.generator = generator
        self.output_dir = generator.output_dir
        self.opf_filename = opf_filename

    def generate(self):
        print("\nGenerating MOBI file...")
        self._run_generation()

    def _run_generation(self):
        kindling = shutil.which('kindling')

        if not kindling:
            print("\nkindling not found on PATH. Please install it from:")
            print("https://github.com/ciscoriordan/kindling/releases")
            return

        opf_file = self.opf_filename or f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}.opf"
        opf_path = os.path.join(self.output_dir, opf_file)
        mobi_filename = opf_file.replace('.opf', '.mobi')
        mobi_path = os.path.join(self.output_dir, mobi_filename)

        if os.path.exists(mobi_path):
            print(f"Removing existing MOBI file: {mobi_filename}")
            os.remove(mobi_path)

        print(f"Running kindling on {opf_file}")
        print("This may take several minutes for large dictionaries...")

        cmd = [kindling, "build", opf_path, "-o", mobi_path]
        result = subprocess.run(cmd)

        if result.returncode == 0 and os.path.exists(mobi_path):
            print(f"\nSuccess! Generated {mobi_filename}")
            dict_type = 'Greek-English'
            print(f"Dictionary type: {dict_type}")
            size_mb = os.path.getsize(mobi_path) / 1024 / 1024
            print(f"File size: {size_mb:.2f} MB")
            self._copy_to_dist(mobi_path)
            print("You can now transfer this file to your Kindle device.")
        elif result.returncode == 0:
            print("\nWarning: kindling reported success but MOBI file not found.")
        else:
            print(f"\nError: kindling failed with exit code {result.returncode}.")

    def _copy_to_dist(self, mobi_path):
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dist_dir = os.path.join(project_root, "dist")
            os.makedirs(dist_dir, exist_ok=True)

            dest_filename = os.path.basename(mobi_path)
            dest_path = os.path.join(dist_dir, dest_filename)

            shutil.copy2(mobi_path, dest_path)
            print(f"Copied {dest_filename} to dist/")
        except Exception as e:
            print(f"Warning: Could not copy MOBI file to dist: {e}")
