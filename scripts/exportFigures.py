#!/usr/bin/env python3
"""Copy the figures of the preprints to assets/images/figures/ and list them in _data/figures.json.

The post layout (_layouts/post.html) shows the figures with their captions. A figure is exported
when the check against the PDF (see checkPdfFigures.py) has no mismatch: the `markdown.pdf.status`
of the preprint in cache/metadata/<identifier>.json is "match" and the caption of the figure is
found in the PDF (`in_pdf` is true). Figures with a caption that could not be checked are not
shown, as are images that are not PNG, JPEG, GIF, WebP or SVG (browsers cannot show PDF or TIFF).

The images come from the git repository, at the commit of the metadata, or, for images in the
Markdown with a web address, from that address. Each preprint gets its own folder
assets/images/figures/<identifier>/. The list for the layout is _data/figures.json:

    {"kxqb7_v1": {"commit": "<commit>",
                  "figures": [{"file": "assets/images/figures/kxqb7_v1/overview.png",
                               "caption": "Overview of the workflow",
                               "label": "fig:overview"}]}}

Preprints that are not eligible (any more) are removed from the list and their folder is deleted.
A preprint is not fetched again when its commit and files are the same, unless --force is given.

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
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from findFigures import fetch_commit
from findMarkdown import METADATA, parse_url

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
IMAGES = os.path.join('assets', 'images', 'figures')
DATA = os.path.join(ROOT, '_data', 'figures.json')
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = 60
ENVIRONMENT = dict(os.environ, GIT_TERMINAL_PROMPT='0')


def sniff(data):
    """Return the file extension for the image types browsers show, judged from the content."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    head = data[:2048].lstrip().lower()
    if b'<svg' in head or (head.startswith(b'<?xml') and b'<svg' in data[:8192].lower()):
        return '.svg'
    return None


def git_bytes(folder, path):
    return subprocess.run(['git', 'show', 'FETCH_HEAD:' + path], cwd=folder, env=ENVIRONMENT,
                          check=True, capture_output=True, timeout=TIMEOUT).stdout


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(MAX_BYTES + 1)


def clean_caption(caption):
    """Markdown caption without citations, HTML and LaTeX leftovers."""
    caption = re.sub(r'\[@[^\]]*\]', '', caption)
    caption = re.sub(r'<[^>]+>', '', caption)
    caption = re.sub(r'\\label\{[^}]*\}', '', caption)
    return re.sub(r'\s+', ' ', caption).strip()


def file_name(figure, extension, used):
    base = posixpath.splitext(posixpath.basename(urllib.parse.urlparse(figure['source']).path))[0]
    base = re.sub(r'[^\w.-]+', '_', base).strip('._') or 'figure'
    name, n = base + extension, 1
    while name.casefold() in used:
        n += 1
        name = '%s-%d%s' % (base, n, extension)
    used.add(name.casefold())
    return name


def eligible(metadata):
    markdown = metadata.get('markdown') or {}
    if (markdown.get('pdf') or {}).get('status') != 'match':
        return []
    return [f for f in markdown.get('figures', []) if f.get('in_pdf') is True and not f.get('missing')]


def export(metadata, figures, target, problems):
    """Write the images of one preprint to `target`; return the list for _data/figures.json."""
    name = metadata['id']
    parsed = parse_url(metadata['markdown']['url'].split('/blob/')[0].split('/-/blob/')[0])
    entries, used = [], set()
    os.makedirs(target, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        fetched = False
        for figure in figures:
            try:
                if figure.get('remote'):
                    data = download(figure['url'])
                else:
                    if not fetched:
                        fetch_commit(parsed[1], metadata['markdown']['commit'], folder)
                        fetched = True
                    data = git_bytes(folder, figure['path'])
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
                problems.append('%s: cannot get %s: %s' % (name, figure['source'], error))
                continue
            extension = sniff(data) if len(data) <= MAX_BYTES else None
            if not extension:
                problems.append('%s: %s is not a PNG, JPEG, GIF, WebP or SVG image (or is too big)'
                                % (name, figure['source']))
                continue
            image = file_name(figure, extension, used)
            with open(os.path.join(target, image), 'wb') as f:
                f.write(data)
            entry = {'file': posixpath.join(IMAGES.replace(os.sep, '/'), name, image),
                     'caption': clean_caption(figure['caption'])}
            if figure.get('label'):
                entry['label'] = figure['label']
            entries.append(entry)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the metadata JSON files (default: cache/metadata)')
    parser.add_argument('--force', action='store_true', help='fetch all images again')
    args = parser.parse_args()

    previous = {}
    if os.path.exists(DATA):
        with open(DATA, encoding='utf-8') as f:
            previous = json.load(f)
    data, problems = {}, []
    exported = unchanged = 0
    for path in sorted(glob.glob(os.path.join(args.metadata, '*.json'))):
        with open(path, encoding='utf-8') as f:
            metadata = json.load(f)
        figures = eligible(metadata)
        if not figures:
            continue
        name = metadata['id'].lower()
        metadata['id'] = name
        target = os.path.join(ROOT, IMAGES, name)
        old = previous.get(name)
        if old and not args.force and old['commit'] == metadata['markdown']['commit'] and \
                [f['file'] for f in old['figures']] and \
                all(os.path.exists(os.path.join(ROOT, f['file'])) for f in old['figures']):
            # same commit: only the captions can have changed
            wanted = {clean_caption(f['caption']) for f in figures}
            if {f['caption'] for f in old['figures']} <= wanted:
                data[name] = old
                unchanged += 1
                continue
        shutil.rmtree(target, ignore_errors=True)
        entries = export(metadata, figures, target, problems)
        if entries:
            data[name] = {'commit': metadata['markdown']['commit'], 'figures': entries}
            exported += 1
        else:
            shutil.rmtree(target, ignore_errors=True)
    for name in previous:  # no longer eligible
        if name not in data:
            shutil.rmtree(os.path.join(ROOT, IMAGES, name), ignore_errors=True)
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write('\n')
    for problem in problems:
        print(problem)
    count = sum(len(entry['figures']) for entry in data.values())
    print('%d figures of %d preprints in %s (%d preprints fetched, %d unchanged), %d not exported'
          % (count, len(data), os.path.relpath(DATA, ROOT), exported, unchanged, len(problems)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
