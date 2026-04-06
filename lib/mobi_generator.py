#
#  lib/mobi_generator.py
#  Handles MOBI file generation using Kindle Previewer / kindlegen
#
#  Created by Francisco Riordan on 4/22/25.
#

import glob
import os
import shutil
import subprocess
import sys


class MobiGenerator:
    def __init__(self, generator, opf_filename=None):
        self.generator = generator
        self.output_dir = generator.output_dir
        self.opf_filename = opf_filename

    def generate(self):
        print("\nGenerating MOBI file...")
        self._run_generation()

    def _find_converter(self):
        """Find a CLI tool that can convert OPF to MOBI.

        Returns (path, tool_type) where tool_type is 'kindlegen' or 'kindlepreviewer'.
        kindlegen uses: kindlegen file.opf
        kindlepreviewer uses: kindlepreviewer file.opf -convert -output .
        """
        if sys.platform == 'win32':
            candidates = self._windows_candidates()
        elif sys.platform == 'darwin':
            candidates = self._macos_candidates()
        else:
            candidates = []

        for path, tool_type in candidates:
            if os.path.exists(path):
                return path, tool_type

        # Fall back to PATH lookup
        for name, tool_type in [
            ('kindlegen', 'kindlegen'),
            ('kindlegen.exe', 'kindlegen'),
            ('kindlepreviewer', 'kindlepreviewer'),
        ]:
            found = shutil.which(name)
            if found:
                return found, tool_type

        return None, None

    def _windows_candidates(self):
        """Return (path, tool_type) pairs for Windows, CLI tools first."""
        candidates = []
        for base in [os.environ.get('LOCALAPPDATA', ''),
                     os.environ.get('PROGRAMFILES', ''),
                     os.environ.get('PROGRAMFILES(X86)', '')]:
            if not base:
                continue
            kp_dir = os.path.join(base, 'Amazon', 'Kindle Previewer 3')
            # Prefer kindlegen (true CLI tool, works headless)
            candidates.append((os.path.join(kp_dir, 'lib', 'fc', 'bin', 'kindlegen.exe'), 'kindlegen'))
        return candidates

    def _macos_candidates(self):
        """Return (path, tool_type) pairs for macOS. Prefer kindlegen (CLI) over kindlepreviewer (GUI wrapper)."""
        candidates = []
        for app_dir in [
            "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin",
            "/Applications/Kindle Previewer.app/Contents/lib/fc/bin",
            os.path.expanduser("~/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin"),
        ]:
            candidates.append((os.path.join(app_dir, 'kindlegen'), 'kindlegen'))
        return candidates

    def _run_generation(self):
        converter, tool_type = self._find_converter()

        if converter:
            original_cwd = os.getcwd()
            try:
                os.chdir(self.output_dir)

                opf_file = self.opf_filename or f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}.opf"
                expected_mobi = opf_file.replace('.opf', '.mobi')

                if os.path.exists(expected_mobi):
                    print(f"Removing existing MOBI file: {expected_mobi}")
                    os.remove(expected_mobi)

                for log_file in glob.glob("*.log"):
                    os.remove(log_file)

                print(f"Running {os.path.basename(converter)} on {opf_file}")
                print("This may take several minutes for large dictionaries...")

                if tool_type == 'kindlegen':
                    cmd = [converter, opf_file, "-o", expected_mobi]
                else:
                    cmd = [converter, opf_file, "-convert", "-output", "."]

                result = subprocess.run(cmd)

                # kindlegen returns 1 for warnings (still produces output), 0 for clean success
                success = result.returncode == 0 or (tool_type == 'kindlegen' and result.returncode == 1)

                if success:
                    mobi_path = self._find_mobi(expected_mobi)
                    if mobi_path:
                        print(f"\nSuccess! Generated {mobi_path}")
                        dict_type = 'Greek-English' if self.generator.source_lang == 'en' else 'Greek-Greek (monolingual)'
                        print(f"Dictionary type: {dict_type}")
                        size_mb = os.path.getsize(mobi_path) / 1024 / 1024
                        print(f"File size: {size_mb:.2f} MB")
                        self._copy_to_dist(mobi_path)
                        print("You can now transfer this file to your Kindle device.")
                    else:
                        print("\nWarning: Command completed but MOBI file not found.")
                        print("Check the output directory for generated files.")
                else:
                    print("\nError: Failed to generate MOBI file.")
                    print(f"You can try opening {os.path.join(self.output_dir, opf_file)} manually in Kindle Previewer.")
            finally:
                os.chdir(original_cwd)
        else:
            print("\nKindle Previewer not found. Please install it from:")
            print("https://www.amazon.com/gp/feature.html?docId=1000765261")
            print("\nOnce installed, you can manually convert the dictionary:")
            print("1. Open Kindle Previewer")
            opf_ref = self.opf_filename or 'lemma_greek_*.opf'
            print(f"2. File > Open > {os.path.join(self.output_dir, opf_ref)}")
            print("3. File > Export > .mobi")

    def _find_mobi(self, expected_mobi):
        """Look for the generated MOBI file."""
        if os.path.exists(expected_mobi):
            return expected_mobi
        # kindlegen may place it in the same directory with the same name
        mobi_files = glob.glob("**/*.mobi", recursive=True)
        if mobi_files:
            return mobi_files[0]
        return None

    def _copy_to_dist(self, mobi_filename):
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dist_dir = os.path.join(project_root, "dist")
            os.makedirs(dist_dir, exist_ok=True)

            mobi_path = os.path.abspath(mobi_filename)
            dest_filename = os.path.basename(mobi_filename)
            dest_path = os.path.join(dist_dir, dest_filename)

            shutil.copy2(mobi_path, dest_path)
            print(f"Copied {dest_filename} to dist/")
        except Exception as e:
            print(f"Warning: Could not copy MOBI file to dist: {e}")
