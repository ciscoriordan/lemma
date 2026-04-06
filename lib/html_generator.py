#
#  lib/html_generator.py
#  Generates HTML files for the dictionary
#
#  Created by Francisco Riordan on 4/22/25.
#

import html
import os
import re
import shutil
import time
from lib.frequency_ranker import FrequencyRanker


MAX_INFLECTIONS = 30

ACCENT_FROM = 'άέήίόύώΐΰϊϋΆΈΉΊΌΎΏ'
ACCENT_TO   = 'αεηιουωιυιυαεηιουω'
_ACCENT_TABLE = str.maketrans(ACCENT_FROM, ACCENT_TO)

POS_MAP = {
    "noun": "ουσ.",
    "verb": "ρ.",
    "adj": "επίθ.",
    "adjective": "επίθ.",
    "adv": "επίρρ.",
    "adverb": "επίρρ.",
    "num": "αριθμ.",
    "numeral": "αριθμ.",
    "name": "κύρ.όν.",
    "proper noun": "κύρ.όν.",
    "article": "άρθρ.",
}


class HtmlGenerator:
    _shared_frequency_ranker = None

    def __init__(self, generator):
        self.generator = generator
        self.entries = generator.entries
        self.output_dir = generator.output_dir
        if HtmlGenerator._shared_frequency_ranker is None:
            HtmlGenerator._shared_frequency_ranker = FrequencyRanker()
        self.frequency_ranker = HtmlGenerator._shared_frequency_ranker
        self._opf_filename = None

    @property
    def opf_filename(self):
        return self._opf_filename

    def create_output_files(self):
        # Initialize with base output dir
        self._update_output_dir()

        # Clean up existing directory if it exists
        if os.path.isdir(self.output_dir):
            print(f"Removing existing directory: {self.output_dir}")
            shutil.rmtree(self.output_dir)

        os.makedirs(self.output_dir, exist_ok=True)

        self._create_content_html()
        self._create_cover_html()
        self._create_copyright_html()
        self._create_usage_html()
        self._create_opf_file()
        self._create_toc_ncx()

    def _update_output_dir(self):
        if not self.output_dir:
            print("Error: Output directory is nil or empty!")
            self.output_dir = f"lemma_greek_{time.strftime('%Y%m%d')}"
            print(f"Using fallback directory: {self.output_dir}")

        if self.generator.limit_percent is not None:
            self.output_dir = f"{self.output_dir}_{self.generator.limit_percent}pct"

        self.generator.update_output_dir(self.output_dir)

    def _rank_inflections(self, forms):
        """Three-tier ranking: frequency > confidence >= 3 > the rest."""
        dilemma = self.generator.dilemma_inflections
        freq = self.frequency_ranker

        tier1 = []  # attested in corpus, ranked by frequency
        tier2 = []  # not in corpus, but has Wiktionary page (confidence >= 3)
        tier3 = []  # table-only or unknown

        for form in forms:
            f = freq.frequency(form)
            c = dilemma.confidence_for(form) if dilemma else 0
            if f > 0:
                tier1.append((form, f))
            elif c >= 3:
                tier2.append((form, c))
            else:
                tier3.append((form, c))

        tier1.sort(key=lambda x: -x[1])
        tier2.sort(key=lambda x: -x[1])
        tier3.sort(key=lambda x: -x[1])

        return [form for form, _ in tier1 + tier2 + tier3]

    def _normalize_for_sorting(self, word):
        normalized = word.lower().translate(_ACCENT_TABLE)
        # Remove non-Greek, non-Latin, non-digit characters
        return re.sub(r'[^\u0370-\u03FF\u1F00-\u1FFFA-Za-z0-9]', '', normalized)

    def _create_content_html(self):
        print("Creating content.html...")

        # Sort keys only to avoid copying all entry data
        sorted_keys = sorted(self.entries.keys(), key=self._normalize_for_sorting)
        total = len(sorted_keys)

        # Write HTML directly to file
        content_file = open(os.path.join(self.output_dir, 'content.html'), 'w', encoding='utf-8')

        # Write header
        content_file.write(self._html_header())

        # Process entries
        entry_count = 0

        for word in sorted_keys:
            self._write_entry(content_file, word, self.entries[word])
            entry_count += 1

            # Progress indicator
            if entry_count % 10000 == 0:
                print(f"  Processed {entry_count}/{total} entries...")

        # Write footer
        content_file.write(self._html_footer())
        content_file.close()

        print(f"  Created content.html with {entry_count} entries")

    def _html_header(self):
        return """\
<html xmlns:math="http://exslt.org/math" xmlns:svg="http://www.w3.org/2000/svg"
      xmlns:tl="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:saxon="http://saxon.sf.net/" xmlns:xs="http://www.w3.org/2001/XMLSchema"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:cx="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:mbp="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:mmc="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf"
      xmlns:idx="https://kindlegen.s3.amazonaws.com/AmazonKindlePublishingGuidelines.pdf">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <style>
      body { font-family: Arial, sans-serif; }
      h5 { font-size: 1em; margin: 0; }
      p { margin: 0.2em 0; }
      b { font-weight: bold; }
      i { font-style: italic; }
      .pos { font-style: italic; color: #666; }
      .def { margin-left: 20px; }
      .etym { font-size: 0.9em; color: #444; margin-top: 0.3em; }
      hr { margin: 5px 0; border: none; border-top: 1px solid #ccc; }
    </style>
  </head>
  <body>
    <mbp:frameset>
"""

    def _html_footer(self):
        return """\
    </mbp:frameset>
  </body>
</html>
"""

    def _write_entry(self, io, word, entries):
        # Limit inflections to reduce complexity
        max_inflections = self.generator.max_inflections or MAX_INFLECTIONS

        # Combine all inflections from all entries for this word
        all_inflections = []
        seen = set()
        for e in entries:
            for inf in (e.get('inflections') or []):
                if inf not in seen:
                    seen.add(inf)
                    all_inflections.append(inf)

        # Filter out multi-word inflections (containing spaces)
        single_word_inflections = [inf for inf in all_inflections if ' ' not in inf]

        # Check if this is a proper noun
        is_proper_noun = any(
            e.get('pos') and ('proper' in e['pos'].lower() or 'name' in e['pos'].lower())
            for e in entries
        )

        if is_proper_noun:
            # For proper nouns, keep original order
            all_variations = single_word_inflections[:max_inflections]
        else:
            all_variations = self._rank_inflections(single_word_inflections)[:max_inflections]

        escaped_word = _escape_html(word)
        io.write(f"""\
<idx:entry name="default" scriptable="yes" spell="yes">
  <idx:short>
    <idx:orth value="{escaped_word}"><b>{escaped_word}</b>
""")

        # Add inflections if any exist
        if all_variations:
            io.write("      <idx:infl>\n")
            for variation in all_variations:
                io.write(f'        <idx:iform value="{_escape_html(variation)}" exact="yes" />\n')
            io.write("      </idx:infl>\n")

        io.write("    </idx:orth>\n")
        io.write("  </idx:short>\n")

        # Simplify entries for Greek to reduce size
        if self.generator.source_lang == 'el':
            # Combine all definitions by POS
            pos_groups = {}
            pos_order = []
            for e in entries:
                pos_key = e.get('pos', 'unknown')
                if pos_key not in pos_groups:
                    pos_groups[pos_key] = []
                    pos_order.append(pos_key)
                pos_groups[pos_key].append(e)

            for idx, pos in enumerate(pos_order):
                pos_entries = pos_groups[pos]
                pos_display = self._format_pos(pos)
                io.write(f"  <p><i>{_escape_html(pos_display)}</i></p>\n")

                # Combine all definitions for this POS
                all_definitions = []
                def_seen = set()
                for e in pos_entries:
                    for d in e.get('definitions', []):
                        if d not in def_seen:
                            def_seen.add(d)
                            all_definitions.append(d)

                # Limit definitions
                for def_idx, definition in enumerate(all_definitions[:5]):
                    if len(all_definitions) > 1:
                        io.write(f"  <p class='def'>{def_idx + 1}. {_escape_html(definition)}</p>\n")
                    else:
                        io.write(f"  <p class='def'>{_escape_html(definition)}</p>\n")

                # Add separator between POS groups
                if len(pos_order) > 1 and idx < len(pos_order) - 1:
                    io.write("  <hr />\n")
        else:
            # Keep full format for English
            for idx, entry in enumerate(entries):
                pos_display = self._format_pos(entry.get('pos'))
                io.write(f"  <p><i>{_escape_html(pos_display)}</i></p>\n")

                defs = entry.get('definitions', [])
                if len(defs) > 1:
                    for def_idx, definition in enumerate(defs):
                        io.write(f"  <p class='def'>{def_idx + 1}. {_escape_html(definition)}</p>\n")
                else:
                    for definition in defs:
                        io.write(f"  <p class='def'>{_escape_html(definition)}</p>\n")

                etym = entry.get('etymology')
                if etym and etym.strip() and self.generator.source_lang == 'en':
                    io.write(f"  <p class='etym'>[Etymology: {_escape_html(etym)}]</p>\n")

                if len(entries) > 1 and idx < len(entries) - 1:
                    io.write("  <hr />\n")

        io.write("""\
</idx:entry>
<hr/>
""")

    def _format_pos(self, pos):
        pos_display = pos or "unknown"

        if self.generator.source_lang == 'el':
            mapped = POS_MAP.get(pos_display.lower())
            if mapped:
                return mapped

        return pos_display

    def _create_cover_html(self):
        source_desc = 'English Wiktionary' if self.generator.source_lang == 'en' else 'Greek Wiktionary (Monolingual)'
        if self.generator.extraction_date:
            date_info = f"Wiktionary data from: {self.generator.extraction_date}"
        else:
            date_info = f"Downloaded: {self.generator.download_date}"

        volume_info = f"<h3>Volume: {self.generator.volume_label}</h3>" if self.generator.volume_label else ""

        content = f"""\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
  </head>
  <body>
    <h1>Lemma Greek Dictionary</h1>
    <h3>From {source_desc}</h3>
    {volume_info}
    <h3>A Lemma Project</h3>
    <p>{date_info}</p>
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'cover.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_copyright_html(self):
        from datetime import datetime
        year = datetime.now().year
        extraction_date = self.generator.extraction_date or 'Unknown'

        content = f"""\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
  </head>
  <body>
    <h2>Copyright Notice</h2>
    <p>This dictionary is created from Wiktionary data processed by Kaikki.</p>
    <p>Wiktionary content is available under the Creative Commons Attribution-ShareAlike License.</p>
    <p>Dictionary compilation by Lemma, {year}</p>
    <p>Wiktionary data extracted: {extraction_date}</p>
    <p>Dictionary created: {self.generator.download_date}</p>
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'copyright.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_usage_html(self):
        if self.generator.source_lang == 'en':
            dict_type = 'Greek-English'
        else:
            dict_type = 'Greek-Greek (monolingual)'

        source_desc = 'English' if self.generator.source_lang == 'en' else 'Greek'

        content = f"""\
<html>
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type">
  </head>
  <body>
    <h2>How to Use Lemma Greek Dictionary</h2>
    <p>This is a {dict_type} dictionary with Modern Greek words from {source_desc} Wiktionary.</p>
    <h3>Features:</h3>
    <ul>
      <li>Look up any Greek word while reading</li>
      <li>Inflected forms automatically redirect to their lemma</li>
      <li>Includes part of speech information</li>
    </ul>
    <h3>To set as default Greek dictionary:</h3>
    <ol>
      <li>Look up any Greek word in your book</li>
      <li>Tap the dictionary name in the popup</li>
      <li>Select "Lemma Greek Dictionary"</li>
    </ol>
  </body>
</html>
"""
        with open(os.path.join(self.output_dir, 'usage.html'), 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_opf_file(self):
        source_name = 'en-el' if self.generator.source_lang == 'en' else 'el-el'
        vol_suffix = f"_{self.generator.volume_suffix}" if self.generator.volume_suffix else ""
        vol_desc = f" ({self.generator.volume_label})" if self.generator.volume_label else ""

        unique_id = f"LemmaGreek{source_name.upper().replace('-', '')}{vol_suffix.replace('_', '')}"
        display_title = f"Lemma Greek Dictionary {source_name.upper()}{vol_desc}"

        date_str = self.generator.extraction_date or self.generator.download_date
        title_with_date = f"{display_title} ({date_str})"
        out_lang = 'en' if self.generator.source_lang == 'en' else 'el'

        opf_filename = f"lemma_greek_{self.generator.source_lang}_{self.generator.download_date}{vol_suffix}.opf"

        content = f"""\
<?xml version="1.0"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId">
  <metadata>
    <dc:title>{title_with_date}</dc:title>
    <dc:creator opf:role="aut">Lemma</dc:creator>
    <dc:language>el</dc:language>
    <dc:date>{self.generator.download_date}</dc:date>
    <dc:identifier id="BookId" opf:scheme="UUID">{unique_id}-{self.generator.download_date}</dc:identifier>
    <meta name="wiktionary-extraction-date" content="{self.generator.extraction_date or 'Unknown'}" />
    <meta name="dictionary-name" content="{display_title}" />
    <x-metadata>
      <DictionaryInLanguage>el</DictionaryInLanguage>
      <DictionaryOutLanguage>{out_lang}</DictionaryOutLanguage>
      <DefaultLookupIndex>default</DefaultLookupIndex>
    </x-metadata>
  </metadata>
  <manifest>
    <item id="ncx"
          href="toc.ncx"
          media-type="application/x-dtbncx+xml" />
    <item id="cover"
          href="cover.html"
          media-type="application/xhtml+xml" />
    <item id="usage"
          href="usage.html"
          media-type="application/xhtml+xml" />
    <item id="copyright"
          href="copyright.html"
          media-type="application/xhtml+xml" />
    <item id="content"
          href="content.html"
          media-type="application/xhtml+xml" />
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover" />
    <itemref idref="usage" />
    <itemref idref="copyright"/>
    <itemref idref="content"/>
  </spine>
  <guide>
    <reference type="index" title="IndexName" href="content.html"/>
  </guide>
</package>
"""
        with open(os.path.join(self.output_dir, opf_filename), 'w', encoding='utf-8') as f:
            f.write(content)

        # Store the OPF filename for use by MobiGenerator
        self._opf_filename = opf_filename

    def _create_toc_ncx(self):
        source_name = 'en-el' if self.generator.source_lang == 'en' else 'el-el'
        vol_suffix = f"_{self.generator.volume_suffix}" if self.generator.volume_suffix else ""
        vol_desc = f" ({self.generator.volume_label})" if self.generator.volume_label else ""
        unique_id = f"LemmaGreek{source_name.upper().replace('-', '')}{vol_suffix.replace('_', '')}"
        display_title = f"Lemma Greek Dictionary {source_name.upper()}{vol_desc}"

        content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{unique_id}-{self.generator.download_date}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{display_title}</text>
  </docTitle>
  <navMap>
    <navPoint id="cover" playOrder="1">
      <navLabel><text>Cover</text></navLabel>
      <content src="cover.html"/>
    </navPoint>
    <navPoint id="usage" playOrder="2">
      <navLabel><text>Usage</text></navLabel>
      <content src="usage.html"/>
    </navPoint>
    <navPoint id="copyright" playOrder="3">
      <navLabel><text>Copyright</text></navLabel>
      <content src="copyright.html"/>
    </navPoint>
    <navPoint id="content" playOrder="4">
      <navLabel><text>Dictionary</text></navLabel>
      <content src="content.html"/>
    </navPoint>
  </navMap>
</ncx>
"""
        with open(os.path.join(self.output_dir, 'toc.ncx'), 'w', encoding='utf-8') as f:
            f.write(content)


def _escape_html(text):
    if not text:
        return ""
    return html.escape(str(text))
