#
#  lib/downloader.py
#  Handles downloading dictionary data
#
#  Created by Francisco Riordan on 4/22/25.
#

import os
import shutil
import time
import urllib.request
import urllib.error
import re


class Downloader:
    KAIKKI_URLS = {
        'en': "https://kaikki.org/dictionary/Greek/kaikki.org-dictionary-Greek.jsonl",
        'el': "https://kaikki.org/elwiktionary/Greek/kaikki.org-dictionary-Greek.jsonl",
    }

    # Paths within a local kaikki dump directory for each source language
    LOCAL_KAIKKI_FILES = {
        'en': 'en-el/kaikki.org-dictionary-Greek-words.jsonl',
        'el': 'el/kaikki.org-dictionary-Greek.jsonl',
    }

    # Local fallback files
    LOCAL_FALLBACK_FILES = {
        'en': 'greek_data_en_20250716.jsonl',
        'el': 'greek_data_el_20250717.jsonl',
    }

    GITHUB_URLS = {
        'en': 'https://raw.githubusercontent.com/fr2019/lemma/main/greek_data_en_20250716.jsonl',
        'el': 'https://raw.githubusercontent.com/fr2019/lemma/main/greek_data_el_20250717.jsonl',
    }

    def __init__(self, source_lang, download_date):
        self.source_lang = source_lang
        self.download_date = download_date

    def download(self):
        lang_desc = 'English' if self.source_lang == 'en' else 'Greek'
        print(f"Downloading Greek data from {lang_desc} Wiktionary via Kaikki...")

        # Primary URL and target filename
        primary_url = self.KAIKKI_URLS[self.source_lang]
        target_filename = f"greek_data_{self.source_lang}_{self.download_date}.jsonl"

        # Use existing file if it's already been downloaded today
        if os.path.exists(target_filename) and os.path.getsize(target_filename) > 0:
            line_count = self._count_lines(target_filename)
            print(f"Using existing file: {target_filename} ({line_count} lines)")
            return (True, target_filename, self.download_date)

        # Try local kaikki dump directory first if configured
        local_path = self._find_local_kaikki_file()
        if local_path:
            print(f"Using local kaikki dump: {local_path}")
            shutil.copy2(local_path, target_filename)
            line_count = self._count_lines(target_filename)
            print(f"Copied {line_count} lines to {target_filename}")
            return (True, target_filename, self.download_date)

        # Try primary URL
        success = self._download_from_url(primary_url, target_filename)

        if success:
            return (True, target_filename, self.download_date)

        # If primary fails, try local fallback file
        local_fallback = self.LOCAL_FALLBACK_FILES[self.source_lang]

        if os.path.exists(local_fallback):
            print(f"Primary download failed. Using local fallback file: {local_fallback}")

            # Extract date from fallback filename
            m = re.search(rf"greek_data_{self.source_lang}_(\d{{8}})\.jsonl", local_fallback)
            fallback_date = m.group(1) if m else self.download_date

            return (True, local_fallback, fallback_date)

        # If local file doesn't exist, try GitHub fallback
        print("Primary download failed and local fallback not found. Attempting GitHub fallback...")

        github_url = self.GITHUB_URLS[self.source_lang]
        m = re.search(rf"greek_data_{self.source_lang}_(\d{{8}})\.jsonl", github_url)
        fallback_date = m.group(1) if m else self.download_date
        fallback_filename = f"greek_data_{self.source_lang}_{fallback_date}.jsonl"

        success = self._download_from_url(github_url, fallback_filename)

        if success:
            print(f"GitHub fallback download successful. Using fallback date: {fallback_date}")
            return (True, fallback_filename, fallback_date)
        else:
            print("Error: All download attempts failed.")
            print(f"Try downloading manually from: {github_url}")
            print(f"Save as: {fallback_filename}")
            return (False, None, None)

    def _find_local_kaikki_file(self):
        kaikki_dir = os.environ.get('KAIKKI_LOCAL_DIR', '')

        # Try loading from .env if not set in environment
        if not kaikki_dir:
            env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == 'KAIKKI_LOCAL_DIR':
                                kaikki_dir = value.strip()

        if not kaikki_dir:
            return None

        relative = self.LOCAL_KAIKKI_FILES.get(self.source_lang)
        if not relative:
            return None

        full_path = os.path.join(kaikki_dir, relative)

        # Resolve symlinks and check the target actually exists
        if not os.path.exists(full_path):
            return None

        return full_path

    def _download_from_url(self, url, filename):
        print(f"Attempting to download from: {url}")
        print("Parsing URL...")

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            print(f"Host: {parsed.hostname}, Port: {parsed.port or 'default'}, SSL: {parsed.scheme == 'https'}")

            # Add timeout and progress reporting
            start_time = time.time()
            bytes_downloaded = 0

            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

            print("Sending request...")

            response = urllib.request.urlopen(req, timeout=300)

            print(f"Response code: {response.status} {response.reason}")

            total_size = int(response.headers.get('Content-Length', 0))
            if total_size > 0:
                print(f"Content-Length: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")

            with open(filename, 'wb') as f:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

                    # Progress update every 5MB
                    if bytes_downloaded % (5 * 1024 * 1024) < len(chunk):
                        elapsed = time.time() - start_time
                        speed = bytes_downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                        print(f"Downloaded: {bytes_downloaded / 1024 / 1024:.2f} MB @ {speed:.2f} MB/s")

            elapsed = time.time() - start_time
            print(f"Download complete: {bytes_downloaded / 1024 / 1024:.2f} MB in {elapsed:.2f} seconds")

            # Count lines
            line_count = self._count_lines(filename)
            print(f"Downloaded {line_count} lines to {filename}")

            return True

        except urllib.error.HTTPError as e:
            print(f"Error: HTTP {e.code} {e.reason}")
            return False
        except TimeoutError:
            print("Timeout error: The download is taking too long. The server might be slow or unresponsive.")
            return False
        except OSError as e:
            print(f"Socket error: {e}")
            print("Cannot connect to host. Check your internet connection.")
            return False
        except Exception as e:
            print(f"Exception during download: {type(e).__name__}: {e}")
            return False

    @staticmethod
    def _count_lines(filename):
        count = 0
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            for _ in f:
                count += 1
        return count
