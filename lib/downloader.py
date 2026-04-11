#
#  lib/downloader.py
#  Handles downloading dictionary data
#
#  Created by Francisco Riordan on 4/22/25.
#

import datetime
import json
import os
import re
import shutil
import time
import urllib.request
import urllib.error


class Downloader:
    KAIKKI_URLS = {
        'en': "https://kaikki.org/dictionary/Greek/kaikki.org-dictionary-Greek.jsonl",
        'el': "https://kaikki.org/elwiktionary/Greek/kaikki.org-dictionary-Greek.jsonl",
    }

    # Language-index pages on Kaikki that embed a human-readable "extracted on
    # YYYY-MM-DD" line. Used as a fallback when the HTTP Last-Modified header
    # is missing on the JSONL.
    KAIKKI_INDEX_URLS = {
        'en': "https://kaikki.org/dictionary/Greek/",
        'el': "https://kaikki.org/elwiktionary/Greek/",
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
        # Populated by download(); normalized to YYYY-MM-DD or None if the
        # real Kaikki extraction date could not be determined.
        self.extraction_date = None

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
            self.extraction_date = self._load_sidecar(target_filename)
            if self.extraction_date:
                print(f"  Extraction date (from sidecar): {self.extraction_date}")
            return (True, target_filename, self.download_date)

        # Try local kaikki dump directory first if configured
        local_path = self._find_local_kaikki_file()
        if local_path:
            print(f"Using local kaikki dump: {local_path}")
            shutil.copy2(local_path, target_filename)
            line_count = self._count_lines(target_filename)
            print(f"Copied {line_count} lines to {target_filename}")
            # Prefer a sibling sidecar if the kaikki dump has one, otherwise
            # fall back to the source file's mtime. copy2 preserves mtime,
            # so either the source or the copy works here.
            self.extraction_date = (
                self._load_sidecar(local_path)
                or self._mtime_as_iso_date(local_path)
            )
            if self.extraction_date:
                print(f"  Extraction date (local dump): {self.extraction_date}")
                self._write_sidecar(
                    target_filename,
                    source_url=f"file://{os.path.abspath(local_path)}",
                )
            return (True, target_filename, self.download_date)

        # Try primary URL
        success, http_extraction_date = self._download_from_url(primary_url, target_filename)

        if success:
            # Cascade: HTTP Last-Modified, then scrape the index page.
            self.extraction_date = (
                http_extraction_date
                or self._scrape_index_page_date()
            )
            if self.extraction_date:
                print(f"  Extraction date (Kaikki): {self.extraction_date}")
                self._write_sidecar(target_filename, source_url=primary_url)
            else:
                print("  Warning: could not determine Kaikki extraction date")
            return (True, target_filename, self.download_date)

        # If primary fails, try local fallback file
        local_fallback = self.LOCAL_FALLBACK_FILES[self.source_lang]

        if os.path.exists(local_fallback):
            print(f"Primary download failed. Using local fallback file: {local_fallback}")

            # Extract date from fallback filename
            m = re.search(rf"greek_data_{self.source_lang}_(\d{{8}})\.jsonl", local_fallback)
            fallback_date = m.group(1) if m else self.download_date

            self.extraction_date = self._parse_yyyymmdd_as_iso(fallback_date)
            if self.extraction_date:
                print(f"  Extraction date (from fallback filename): {self.extraction_date}")

            return (True, local_fallback, fallback_date)

        # If local file doesn't exist, try GitHub fallback
        print("Primary download failed and local fallback not found. Attempting GitHub fallback...")

        github_url = self.GITHUB_URLS[self.source_lang]
        m = re.search(rf"greek_data_{self.source_lang}_(\d{{8}})\.jsonl", github_url)
        fallback_date = m.group(1) if m else self.download_date
        fallback_filename = f"greek_data_{self.source_lang}_{fallback_date}.jsonl"

        success, _ = self._download_from_url(github_url, fallback_filename)

        if success:
            print(f"GitHub fallback download successful. Using fallback date: {fallback_date}")
            self.extraction_date = self._parse_yyyymmdd_as_iso(fallback_date)
            if self.extraction_date:
                print(f"  Extraction date (from GitHub fallback filename): {self.extraction_date}")
                self._write_sidecar(fallback_filename, source_url=github_url)
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
        """Fetch `url` into `filename`.

        Returns a (success, extraction_date_iso_or_none) tuple. The second
        element is the HTTP Last-Modified header parsed into YYYY-MM-DD when
        available, which is our most reliable source for the real Kaikki
        extraction date.
        """
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

            last_modified_header = response.headers.get('Last-Modified', '')
            if last_modified_header:
                print(f"Last-Modified: {last_modified_header}")
            extraction_date = self._parse_http_date(last_modified_header)

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

            return (True, extraction_date)

        except urllib.error.HTTPError as e:
            print(f"Error: HTTP {e.code} {e.reason}")
            return (False, None)
        except TimeoutError:
            print("Timeout error: The download is taking too long. The server might be slow or unresponsive.")
            return (False, None)
        except OSError as e:
            print(f"Socket error: {e}")
            print("Cannot connect to host. Check your internet connection.")
            return (False, None)
        except Exception as e:
            print(f"Exception during download: {type(e).__name__}: {e}")
            return (False, None)

    # ----- Extraction-date helpers -----

    @staticmethod
    def _parse_http_date(header_value):
        """Parse an HTTP date header (RFC 1123 / RFC 850 / asctime) into
        a YYYY-MM-DD string. Returns None on failure or empty input.
        """
        if not header_value:
            return None
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(header_value)
            if dt is None:
                return None
            return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_yyyymmdd_as_iso(value):
        """Convert a YYYYMMDD string to YYYY-MM-DD, or None if not parseable."""
        if not value:
            return None
        try:
            return datetime.datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _mtime_as_iso_date(path):
        """Return the mtime of `path` formatted as YYYY-MM-DD, or None on
        failure. Used as a fallback for local Kaikki dumps.
        """
        try:
            ts = os.path.getmtime(path)
            return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except OSError:
            return None

    def _scrape_index_page_date(self):
        """Fetch the Kaikki language index page and look for the
        "extracted on YYYY-MM-DD" line in the body. Returns an ISO date or
        None. Used as a fallback when Last-Modified is missing.
        """
        index_url = self.KAIKKI_INDEX_URLS.get(self.source_lang)
        if not index_url:
            return None
        try:
            req = urllib.request.Request(index_url)
            req.add_header(
                'User-Agent',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode('utf-8', errors='replace')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  Could not scrape Kaikki index page: {e}")
            return None

        m = re.search(r'extracted on (\d{4}-\d{2}-\d{2})', body)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _sidecar_path(jsonl_path):
        return f"{jsonl_path}.meta"

    def _write_sidecar(self, jsonl_path, source_url):
        """Write a small JSON sidecar next to the JSONL recording the
        Kaikki extraction date so cached reuses of the dump preserve it.
        """
        if not self.extraction_date:
            return
        meta = {
            "extraction_date": self.extraction_date,
            "source_url": source_url,
            "downloaded_at": datetime.datetime.now().strftime("%Y-%m-%d"),
        }
        try:
            with open(self._sidecar_path(jsonl_path), 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
                f.write("\n")
        except OSError as e:
            print(f"  Warning: could not write sidecar: {e}")

    def _load_sidecar(self, jsonl_path):
        """Read a sidecar if present. Returns the stored extraction_date
        (normalized to YYYY-MM-DD) or None.
        """
        sidecar = self._sidecar_path(jsonl_path)
        if not os.path.exists(sidecar):
            return None
        try:
            with open(sidecar, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, ValueError) as e:
            print(f"  Warning: could not read sidecar {sidecar}: {e}")
            return None
        raw = meta.get("extraction_date")
        if not raw:
            return None
        # Normalize; accept both ISO date and YYYYMMDD just in case.
        for pattern in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.datetime.strptime(raw, pattern).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                continue
        return raw

    @staticmethod
    def _count_lines(filename):
        count = 0
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            for _ in f:
                count += 1
        return count
