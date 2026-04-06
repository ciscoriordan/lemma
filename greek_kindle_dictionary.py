#!/usr/bin/env python3
#
#  greek_kindle_dictionary.py
#  Lemma - Greek Kindle Dictionary Generator
#
#  Created by Francisco Riordan on 4/22/25.
#

import argparse
import sys
from lib.greek_dictionary_generator import GreekDictionaryGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Lemma - Greek Dictionary Generator. Produces EPUB and optional MOBI for sideloading.",
        usage="python3 greek_kindle_dictionary.py [options]",
    )

    parser.add_argument(
        "-s", "--source",
        choices=["en", "el"],
        default="en",
        help="Source Wiktionary language: 'en' (English) or 'el' (Greek). Default: en",
    )

    parser.add_argument(
        "-l", "--limit",
        type=float,
        default=None,
        help="Limit to first PERCENT%% of words (for testing). Default: 100",
    )

    parser.add_argument(
        "-i", "--inflections",
        type=int,
        default=None,
        help="Max inflections per headword. Default: 30",
    )

    parser.add_argument(
        "-m", "--mobi",
        action="store_true",
        default=False,
        help="Also generate .mobi via kindling (for sideloading)",
    )

    parser.add_argument(
        "--links",
        action="store_true",
        default=False,
        help="Enable clickable cross-references between entries (default: off)",
    )

    parser.add_argument(
        "--etymology",
        action="store_true",
        default=False,
        help="Include etymology information in entries (default: off)",
    )

    args = parser.parse_args()

    if args.limit is not None:
        if args.limit <= 0 or args.limit > 100:
            print("Error: Limit must be between 0 and 100")
            sys.exit(1)

    generator = GreekDictionaryGenerator(
        args.source, args.limit,
        generate_mobi=args.mobi,
        max_inflections=args.inflections,
        enable_links=args.links,
        enable_etymology=args.etymology,
    )
    generator.generate()


if __name__ == "__main__":
    main()
