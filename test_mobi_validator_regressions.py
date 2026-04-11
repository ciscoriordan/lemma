#!/usr/bin/env python3
"""Regression tests for run_mobi_validation_tests in test_dictionary_lookup.py.

These tests cover two false-positive bugs that were previously blocking deploy:

1. PalmDB name uniqueness check fired across different versions of the same
   dictionary family (e.g. yesterday's and today's build both sitting in
   dist/). Fix: dedupe and key uniqueness by filename family, where a family
   is the basename with its _YYYYMMDD date stamp stripped.

2. INDX record check assumed the record at MOBI header offset 0x50
   ("first non-book record") must start with 'INDX'. In practice Kindle
   dictionaries place cover / HD-image-container records between the text
   and the INDX records, so that record is often a JPEG. Fix: scan the
   post-text record range for any 'INDX' record.

The tests build minimal fake MOBI byte buffers with struct.pack. They do
NOT invoke kindling.
"""

import io
import os
import struct
import sys
import tempfile
import unittest

# Make the validator importable when running this file directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_dictionary_lookup import (  # noqa: E402
    _family_key,
    run_mobi_validation_tests,
)


# A minimal record 0 is 280 bytes (the validator requires rec0_offset + 280
# <= len(data)). We size it to fit a small EXTH section after the MOBI
# header, with two EXTH records (531, 532), each carrying a 4-byte payload.
REC0_SIZE = 512
MOBI_HEADER_LENGTH = 232  # header_length written at rec0[20:24]
EXTH_OFFSET_IN_REC0 = 16 + MOBI_HEADER_LENGTH  # = 248, within REC0_SIZE


def _build_record0(first_non_book):
    """Build a minimal but valid MOBI record 0."""
    rec0 = bytearray(REC0_SIZE)

    # PalmDOC header: compression=1 (no compression). rest zero.
    struct.pack_into('>H', rec0, 0, 1)

    # MOBI header magic at offset 16
    rec0[16:20] = b'MOBI'
    # header_length
    struct.pack_into('>I', rec0, 20, MOBI_HEADER_LENGTH)
    # mobi_type = 2 (MOBI Book)
    struct.pack_into('>I', rec0, 24, 2)
    # text_encoding = 65001 (UTF-8)
    struct.pack_into('>I', rec0, 28, 65001)
    # first_non_book at offset 80
    struct.pack_into('>I', rec0, 80, first_non_book)
    # EXTH flag at offset 128
    struct.pack_into('>I', rec0, 128, 0x40)

    # EXTH header at 16 + header_length
    off = EXTH_OFFSET_IN_REC0
    rec0[off:off + 4] = b'EXTH'
    struct.pack_into('>I', rec0, off + 4, 0)  # header length (unused)
    struct.pack_into('>I', rec0, off + 8, 2)  # count: two records

    # EXTH record 531 (DictionaryInLanguage)
    entry_pos = off + 12
    struct.pack_into('>I', rec0, entry_pos, 531)
    struct.pack_into('>I', rec0, entry_pos + 4, 12)  # rec_len includes header
    rec0[entry_pos + 8:entry_pos + 12] = b'grc\x00'

    # EXTH record 532 (DictionaryOutLanguage)
    entry_pos += 12
    struct.pack_into('>I', rec0, entry_pos, 532)
    struct.pack_into('>I', rec0, entry_pos + 4, 12)
    rec0[entry_pos + 8:entry_pos + 12] = b'en\x00\x00'

    return bytes(rec0)


# JPEG SOI + APP0 marker - the exact bytes the old check misidentified.
JPEG_MAGIC = b'\xff\xd8\xff\xe0'
INDX_MAGIC = b'INDX'


def _build_mobi(
    palmdb_name,
    num_total_records,
    first_non_book,
    post_text_record_magics,
):
    """Build a minimal MOBI file as bytes.

    Records 0..first_non_book-1 are "text" records (all-zero payload, no
    content that the validator looks at). Records from first_non_book onward
    take their leading bytes from post_text_record_magics, in order.

    post_text_record_magics: list of bytes, one per post-text record. Each
    entry is the 4-byte magic that should appear at the start of that
    record. Use e.g. JPEG_MAGIC or INDX_MAGIC.
    """
    assert len(post_text_record_magics) == num_total_records - first_non_book

    # --- Lay out the file ---
    # PalmDB header is 78 bytes, then an 8-byte record-info entry per record.
    header_len = 78 + 8 * num_total_records

    record_data = []

    # Record 0: MOBI header + PalmDOC header (REC0_SIZE bytes).
    record_data.append(_build_record0(first_non_book))

    # Text records 1..first_non_book-1: 8-byte zero payloads.
    for _ in range(1, first_non_book):
        record_data.append(b'\x00' * 8)

    # Post-text records: 8-byte payload each, leading with the requested magic.
    for magic in post_text_record_magics:
        payload = magic + b'\x00' * (8 - len(magic))
        record_data.append(payload)

    # Compute record offsets.
    record_offsets = []
    off = header_len
    for rec in record_data:
        record_offsets.append(off)
        off += len(rec)

    # --- Assemble ---
    buf = bytearray(header_len)

    name_bytes = palmdb_name.encode('latin-1')[:31]
    buf[0:len(name_bytes)] = name_bytes
    # [32:60] attributes/version/etc - zero is fine.
    buf[60:64] = b'BOOK'
    buf[64:68] = b'MOBI'
    # [68:76] zero
    struct.pack_into('>H', buf, 76, num_total_records)

    # Record info list at offset 78. Each entry: 4 bytes offset, 4 bytes
    # attributes + unique id (we zero them).
    for i, rec_off in enumerate(record_offsets):
        struct.pack_into('>I', buf, 78 + 8 * i, rec_off)

    return bytes(buf) + b''.join(record_data)


def _write_mobi(tmpdir, filename, **kwargs):
    path = os.path.join(tmpdir, filename)
    with open(path, 'wb') as f:
        f.write(_build_mobi(**kwargs))
    return path


def _run_validator(paths):
    """Invoke run_mobi_validation_tests and capture (ok, stdout)."""
    buf = io.StringIO()
    real_stdout = sys.stdout
    try:
        sys.stdout = buf
        ok = run_mobi_validation_tests(paths)
    finally:
        sys.stdout = real_stdout
    return ok, buf.getvalue()


class FamilyKeyTest(unittest.TestCase):
    def test_date_stripped_at_end(self):
        self.assertEqual(
            _family_key('/tmp/lemma_greek_en_20260410.mobi'),
            'lemma_greek_en.mobi',
        )

    def test_date_stripped_before_suffix(self):
        self.assertEqual(
            _family_key('/tmp/lemma_greek_en_20260410_basic.mobi'),
            'lemma_greek_en_basic.mobi',
        )

    def test_no_date_is_unchanged(self):
        self.assertEqual(
            _family_key('/tmp/lemma_latin_en.mobi'),
            'lemma_latin_en.mobi',
        )

    def test_two_dates_same_family(self):
        self.assertEqual(
            _family_key('/tmp/lemma_greek_en_20260409.mobi'),
            _family_key('/tmp/lemma_greek_en_20260410.mobi'),
        )


class PalmDBUniquenessTest(unittest.TestCase):
    def test_same_family_shared_name_is_ok(self):
        """Two date-stamped versions of the same dictionary must NOT error."""
        with tempfile.TemporaryDirectory() as tmp:
            a = _write_mobi(
                tmp,
                'lemma_greek_en_20260409.mobi',
                palmdb_name='Lemma_Greek_Dictionary',
                num_total_records=3,
                first_non_book=1,
                post_text_record_magics=[JPEG_MAGIC, INDX_MAGIC],
            )
            b = _write_mobi(
                tmp,
                'lemma_greek_en_20260410.mobi',
                palmdb_name='Lemma_Greek_Dictionary',
                num_total_records=3,
                first_non_book=1,
                post_text_record_magics=[JPEG_MAGIC, INDX_MAGIC],
            )
            # Make sure 20260410 has a strictly newer mtime so the dedupe
            # keeps it as the "newest" (timestamps can collide on fast FSs).
            os.utime(a, (1000, 1000))
            os.utime(b, (2000, 2000))

            ok, out = _run_validator([a, b])
            self.assertTrue(ok, msg=f"Expected PASS, got FAIL:\n{out}")
            # Dedupe should have kept only the newest file.
            self.assertIn('1 file', out)
            self.assertNotIn('conflicts with', out)

    def test_different_families_shared_name_is_error(self):
        """Genuine collision across dictionaries must still be reported."""
        with tempfile.TemporaryDirectory() as tmp:
            a = _write_mobi(
                tmp,
                'lemma_greek_en_20260410.mobi',
                palmdb_name='Shared_Name',
                num_total_records=3,
                first_non_book=1,
                post_text_record_magics=[JPEG_MAGIC, INDX_MAGIC],
            )
            b = _write_mobi(
                tmp,
                'lemma_latin_en_20260410.mobi',
                palmdb_name='Shared_Name',
                num_total_records=3,
                first_non_book=1,
                post_text_record_magics=[JPEG_MAGIC, INDX_MAGIC],
            )
            ok, out = _run_validator([a, b])
            self.assertFalse(ok, msg=f"Expected FAIL, got PASS:\n{out}")
            self.assertIn('conflicts with', out)


class IndxScanTest(unittest.TestCase):
    def test_jpeg_then_indx_is_ok(self):
        """first_non_book points at a JPEG but there is an INDX record later."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mobi(
                tmp,
                'lemma_greek_en_20260410.mobi',
                palmdb_name='Lemma_Greek_Dictionary',
                num_total_records=4,  # rec0 + 1 text + jpeg + indx
                first_non_book=2,
                post_text_record_magics=[JPEG_MAGIC, INDX_MAGIC],
            )
            ok, out = _run_validator([path])
            self.assertTrue(ok, msg=f"Expected PASS, got FAIL:\n{out}")

    def test_no_indx_anywhere_is_error(self):
        """No INDX record in the post-text range must fail with the new error."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mobi(
                tmp,
                'lemma_greek_en_20260410.mobi',
                palmdb_name='Lemma_Greek_Dictionary',
                num_total_records=4,
                first_non_book=2,
                post_text_record_magics=[JPEG_MAGIC, JPEG_MAGIC],
            )
            ok, out = _run_validator([path])
            self.assertFalse(ok, msg=f"Expected FAIL, got PASS:\n{out}")
            self.assertIn('No INDX record found after text section', out)

    def test_indx_immediately_after_text_is_ok(self):
        """The classic case: first non-book record is itself an INDX."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_mobi(
                tmp,
                'lemma_greek_en_20260410.mobi',
                palmdb_name='Lemma_Greek_Dictionary',
                num_total_records=3,
                first_non_book=1,
                post_text_record_magics=[INDX_MAGIC, b'\x00\x00\x00\x00'],
            )
            ok, out = _run_validator([path])
            self.assertTrue(ok, msg=f"Expected PASS, got FAIL:\n{out}")


if __name__ == '__main__':
    unittest.main()
