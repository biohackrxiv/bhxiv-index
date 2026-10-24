#!/usr/bin/env python3
"""Check which figures of the Markdown source (see findFigures.py) are in the submitted PDF.

The PDF is what was submitted to BioHackrXiv, so the PDF is leading: the Markdown in the git
repository may be a different version. For each cache/metadata/<identifier>.json with
`markdown.figures` this script compares the cached PDF (cache/pdfs/) with the metadata:

  * each figure gets `in_pdf`: true when its caption is found in the text of the PDF, false when it
    is not, and null when the caption is too short or generic to tell (such as "Figure 1");
  * the title of the post must be on the first page of the PDF (`title_in_pdf`);
  * the number of raster images in the PDF is counted (`images`), without the logo that is on every
    page and without duplicates. Figures drawn as vector graphics are not counted, so fewer images
    than figures is normal, but more images than figures means the Markdown misses some.

The summary is added to the `markdown` object and the preprints where the Markdown does not seem to
match the PDF are listed:

    "pdf": {"status": "match", "title_in_pdf": true, "images": 3,
            "captions_checked": 3, "captions_found": 3}

`status` is "match" when all captions that can be checked are found and the title is on the first
page, "partial" when at least half of the captions are found, and "mismatch" otherwise (also when
the title is not found and nothing else supports the Markdown). Captions are compared without
Markdown, case, punctuation, hyphenation and line breaks, and only the part before the first
citation or formula, as the PDF shows those differently.

Copyright (c) 2026 Egon Willighagen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import unicodedata

from findMarkdown import METADATA, load_titles

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, '..', 'cache', 'pdfs')
LOGO = (300, 140)  # the BioHackrXiv logo, in the header of every page
MIN_CHARS = 15  # captions with fewer letters and digits cannot be checked
PREFIX = 100  # compare at most this many letters and digits of a caption
CUT = re.compile(r'\[@|\$|\\|\[\^|<[a-z/]')


def squash(text):
    """Letters and digits only, in lower case: robust against hyphenation and line breaks."""
    text = unicodedata.normalize('NFKC', html.unescape(text)).casefold()
    return re.sub(r'[\W_]+', '', text)


def plain_caption(caption):
    """The part of a Markdown caption that the PDF shows as it is."""
    caption = CUT.split(caption, maxsplit=1)[0]
    caption = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', caption)  # links
    caption = re.sub(r'^\s*(figure|fig\.?)\s*\d+\w*\s*[:.]?', '', caption, flags=re.I)
    return caption


def pdf_text(pdf, first_page_only=False):
    command = ['pdftotext', '-q']
    if first_page_only:
        command += ['-f', '1', '-l', '1']
    return subprocess.run(command + [pdf, '-'], check=True, capture_output=True, text=True,
                          timeout=120).stdout


def count_images(pdf):
    """Count the different raster images in the PDF, without the logo and soft masks."""
    output = subprocess.run(['pdfimages', '-list', pdf], check=True, capture_output=True,
                            text=True, timeout=120).stdout
    seen = set()
    for line in output.splitlines()[2:]:
        fields = line.split()
        if len(fields) < 11 or fields[2] != 'image':
            continue
        if (int(fields[3]), int(fields[4])) == LOGO:
            continue
        seen.add(fields[10])  # object ID: the same image on several pages counts once
    return len(seen)


def caption_in_pdf(caption, haystack):
    needle = squash(plain_caption(caption))[:PREFIX]
    if len(needle) < MIN_CHARS:
        return None
    return needle in haystack


def check(metadata, pdf, title):
    markdown = metadata['markdown']
    haystack = squash(pdf_text(pdf))
    results = [caption_in_pdf(f['caption'], haystack) for f in markdown['figures']]
    for figure, result in zip(markdown['figures'], results):
        figure['in_pdf'] = result
    checked = [r for r in results if r is not None]
    found = sum(checked)
    title_found = squash(title)[:PREFIX] in squash(pdf_text(pdf, True)) if title else None
    if checked:
        ratio = found / len(checked)
        status = 'match' if ratio == 1 else 'partial' if ratio >= 0.5 else 'mismatch'
        if title_found is False and status == 'match':
            status = 'partial'
    else:  # no figure to check: only the title can tell
        status = 'match' if title_found else 'mismatch' if title_found is False else 'partial'
    images = count_images(pdf)
    markdown['pdf'] = {'status': status, 'title_in_pdf': title_found, 'images': images,
                       'captions_checked': len(checked), 'captions_found': found}
    return markdown['pdf']


def reasons(summary, markdown):
    problems = []
    if summary['title_in_pdf'] is False:
        problems.append('title not on first page')
    missing = summary['captions_checked'] - summary['captions_found']
    if missing:
        problems.append('%d of %d captions not in the PDF' % (missing, summary['captions_checked']))
    if summary['images'] > len(markdown['figures']):
        problems.append('PDF has %d images, Markdown %d figures'
                        % (summary['images'], len(markdown['figures'])))
    return problems


def report_line(name, summary, markdown):
    """One line for a preprint that does not match the PDF (or has other problems), else None."""
    problems = reasons(summary, markdown)
    if summary['status'] == 'match' and not problems:
        return None
    return '%-8s %s: %s' % (summary['status'], name, '; '.join(problems) or 'no problems found')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the metadata JSON files (default: cache/metadata)')
    parser.add_argument('--pdfs', default=PDFS, help='folder with the PDFs (default: cache/pdfs)')
    parser.add_argument('--verbose', action='store_true',
                        help='also list the figures whose caption is not in the PDF')
    parser.add_argument('ids', nargs='*', help='only these identifiers (default: all)')
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.metadata, '*.json')))
    if args.ids:
        wanted = {i.lower() for i in args.ids}
        paths = [p for p in paths if os.path.basename(p)[:-5].lower() in wanted]
    titles = load_titles()
    counts = {'match': 0, 'partial': 0, 'mismatch': 0}
    skipped = failed = 0
    report = []
    for path in paths:
        with open(path, encoding='utf-8') as f:
            metadata = json.load(f)
        if not (metadata.get('markdown') or {}).get('figures') is not None:
            skipped += 1
            continue
        name = metadata['id']
        pdf = os.path.join(args.pdfs, name + '.pdf')
        try:
            summary = check(metadata, pdf, titles.get(name.lower()))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
            print('FAILED %s: %s' % (name, error))
            failed += 1
            continue
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            f.write('\n')
        counts[summary['status']] += 1
        line = report_line(name, summary, metadata['markdown'])
        if line:
            report.append((summary['status'], name, line, metadata['markdown']['figures']))
    order = {'mismatch': 0, 'partial': 1, 'match': 2}
    for status, name, line, figures in sorted(report, key=lambda r: (order[r[0]], r[1])):
        print(line)
        if args.verbose:
            for figure in figures:
                if figure.get('in_pdf') is False:
                    print('           %s: %s' % (figure['source'], figure['caption'][:80]))
    print('Match: %(match)d, partial: %(partial)d, mismatch: %(mismatch)d' % counts
          + ', no figures metadata: %d, failed: %d' % (skipped, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
