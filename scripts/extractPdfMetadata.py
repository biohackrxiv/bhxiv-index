#!/usr/bin/env python3
"""Extract metadata from the cached preprint PDFs (see cachePdfs.py) into cache/metadata/.

The front page of a BioHackrXiv PDF has a left column with a "BioHackathon series:" section. It
lists the event as the first link and, usually, the project or the GitHub repository as the second
link. The links are annotations in the PDF, so plain text extraction does not find them. This
script runs `pdftohtml -xml` (Poppler) on the first page, which gives each text fragment with its
position and link, and keeps the links in the left column between "BioHackathon series:" and the
"Submitted:" or "License:" heading. For each PDF it writes cache/metadata/<identifier>.json:

    {"id": "kxqb7_v1",
     "links": [{"text": "DBCLS BioHackathon 2026", "url": "https://2026.biohackathon.org/"},
               {"text": "ZebraSeek", "url": "https://github.com/..."}],
     "repository": {"url": "https://github.com/..."}}

`repository` describes the source repository of the preprint; its `url` is the URL of the second
link. It is null when there is no second link. The cache is not part of
the git repository.

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

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, '..', 'cache', 'pdfs')
METADATA = os.path.join(HERE, '..', 'cache', 'metadata')
SIDEBAR_MAX_LEFT = 240   # text fragments left of this (in PDF points) are in the sidebar
IGNORED_LINKS = ('creativecommons.org', 'biohackrxiv.org')
FRAGMENT = re.compile(r'<text top="(\d+)" left="(\d+)"[^>]*>(.*?)</text>', re.DOTALL)
HREF = re.compile(r'href="([^"]+)"')


def first_page_fragments(pdf):
    """Return [(top, left, text, [urls])] for the text fragments on the first page."""
    xml = subprocess.run(
        ['pdftohtml', '-xml', '-stdout', '-i', '-f', '1', '-l', '1', pdf],
        check=True, capture_output=True, text=True, encoding='utf-8').stdout
    fragments = []
    for match in FRAGMENT.finditer(xml):
        top, left, content = int(match.group(1)), int(match.group(2)), match.group(3)
        text = html.unescape(re.sub(r'<[^>]+>', '', content)).strip()
        urls = [html.unescape(url) for url in HREF.findall(content)]
        fragments.append((top, left, text, urls))
    return fragments


def series_links(fragments):
    """Return the distinct links, in page order, of the "BioHackathon series:" section."""
    sidebar = sorted((f for f in fragments if f[1] < SIDEBAR_MAX_LEFT), key=lambda f: (f[0], f[1]))
    start = next((f[0] for f in sidebar if f[2].startswith('BioHackathon series')), None)
    if start is None:
        return []
    end = next((f[0] for f in sidebar
                if f[0] > start and f[2].startswith(('Submitted', 'License'))), float('inf'))
    links = []
    for top, _, text, urls in sidebar:
        if not start < top < end:
            continue
        for url in urls:
            if any(ignored in url for ignored in IGNORED_LINKS):
                continue
            existing = next((link for link in links if link['url'] == url), None)
            if existing:
                if text and text not in existing['text']:
                    existing['text'] = (existing['text'] + ' ' + text).strip()
            else:
                links.append({'text': text, 'url': url})
    return links


def extract(pdf):
    links = series_links(first_page_fragments(pdf))
    return {
        'id': os.path.splitext(os.path.basename(pdf))[0],
        'links': links,
        'repository': {'url': links[1]['url']} if len(links) > 1 else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--pdfs', default=PDFS, help='folder with the PDFs (default: cache/pdfs)')
    parser.add_argument('--output', default=METADATA,
                        help='folder for the JSON files (default: cache/metadata)')
    args = parser.parse_args()

    pdfs = sorted(glob.glob(os.path.join(args.pdfs, '*.pdf')))
    if not pdfs:
        sys.exit('No PDFs in %s; run `make cachePdfs` first.' % args.pdfs)
    os.makedirs(args.output, exist_ok=True)
    with_repository = failed = 0
    for pdf in pdfs:
        try:
            metadata = extract(pdf)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as error:
            print('FAILED %s: %s' % (os.path.basename(pdf), error))
            failed += 1
            continue
        with open(os.path.join(args.output, metadata['id'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            f.write('\n')
        if metadata['repository']:
            with_repository += 1
    print('%d PDFs: %d with a second link, %d without, %d failed'
          % (len(pdfs), with_repository, len(pdfs) - with_repository - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
