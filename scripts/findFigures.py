#!/usr/bin/env python3
"""Find the figures of each preprint in its Markdown source (paper.md) and add them to the metadata.

For each cache/metadata/<identifier>.json with a `markdown` object (see findMarkdown.py) this
script fetches that commit of the repository (shallow, without file contents), reads paper.md and
finds the images: `![caption](path){#fig:label}` (Pandoc Markdown). It adds a list `figures` to the
`markdown` object, in the order of the paper:

    "figures": [{"source": "./figures/overview.png",
                 "path": "paper/figures/overview.png",
                 "url": "https://github.com/owner/repo/blob/<commit>/paper/figures/overview.png",
                 "caption": "Overview of the workflow",
                 "label": "fig:overview"}]

* `source` is the path as written in paper.md. `path` is the path of the image in the repository
  (relative paths are resolved against the folder of paper.md, a leading `/` is the root of the
  repository), and `url` its address at the commit. `path` is null when the image is not in the
  repository: `remote` is true when the source is a web address (the `url`), and `missing` is true
  when the file does not exist at this commit.
* `caption` is the text in the brackets, in Markdown as written, with white space collapsed. When
  that is empty or generic ("Figure 1", "image", the file name), the paragraph right after the
  image that starts with "Figure N:" is used instead, and `caption_source` is "text".
* `label` is the Pandoc identifier (`{#fig:x}`) or the LaTeX `\\label{x}` of the caption, if any.

Preprints that already have `figures` are skipped unless --force is given. When the repository
cannot be fetched, `figures` is left out, so the next run tries again.

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
import concurrent.futures
import glob
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import urllib.parse

from findMarkdown import METADATA, blob_url, parse_url, run_git

GENERIC_CAPTION = re.compile(r'^(figure|fig\.?|image|img|picture|screenshot)?\s*[\d_-]*[a-z]?$', re.I)
FIGURE_TEXT = re.compile(r'^[*_]{0,2}(?:Figure|Fig\.?)\s*\d+\w*\s*[:.]', re.I)
FENCE = re.compile(r'^(```|~~~).*?^\1[^\n]*$', re.M | re.S)
COMMENT = re.compile(r'<!--.*?-->', re.S)


def skipped_spans(text):
    """Spans of fenced code blocks and HTML comments, where images are not figures."""
    return [m.span() for pattern in (FENCE, COMMENT) for m in pattern.finditer(text)]


def match_bracket(text, start, open_char, close_char):
    """Return the index of the bracket closing the one at `start`, or -1."""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_images(text):
    """Return [(alt, destination, attribute text, end index)] for the Markdown images in text."""
    spans = skipped_spans(text)
    images = []
    pos = 0
    while True:
        start = text.find('![', pos)
        if start < 0:
            return images
        pos = start + 2
        if any(a <= start < b for a, b in spans):
            continue
        end = match_bracket(text, start + 1, '[', ']')
        if end < 0 or text[end + 1:end + 2] != '(':
            continue
        close = match_bracket(text, end + 1, '(', ')')
        if close < 0:
            continue
        inner = text[end + 2:close].strip()
        if inner.startswith('<') and '>' in inner:
            destination = inner[1:inner.index('>')]
        else:
            destination = inner.split(None, 1)[0] if inner else ''
        attributes = ''
        match = re.match(r'\{([^}\n]*)\}', text[close + 1:])
        if match:
            attributes = match.group(1)
        images.append((text[start + 2:end], destination, attributes, close + 1))
        pos = close + 1


def clean(caption):
    return re.sub(r'\s+', ' ', caption).strip()


def text_caption(text, end):
    """The paragraph after the image if it starts with "Figure N:", else None."""
    match = re.match(r'[ \t]*(?:\{[^}\n]*\})?[ \t]*\n+', text[end:])
    if not match:
        return None
    paragraph = re.split(r'\n[ \t]*\n', text[end + match.end():], maxsplit=1)[0]
    return clean(paragraph) if FIGURE_TEXT.match(paragraph.lstrip()) else None


def resolve(destination, paper_path, files, lower):
    """Return (repository path or None, flag) for an image destination.

    flag is 'remote' for web addresses, 'missing' for files not in the repository, else None.
    """
    if re.match(r'^[a-z][a-z0-9+.-]*:', destination, re.I):
        return None, 'remote'
    local = urllib.parse.unquote(re.split(r'[?#]', destination)[0])
    if local.startswith('/'):
        path = posixpath.normpath(local.lstrip('/'))
    else:
        path = posixpath.normpath(posixpath.join(posixpath.dirname(paper_path), local))
    if path in files:
        return path, None
    if path.casefold() in lower:
        return lower[path.casefold()], None
    return None, 'missing'


def find_figures(text, paper_path, files, host, repo_url, commit):
    lower = {f.casefold(): f for f in files}
    files = set(files)
    figures = []
    for alt, destination, attributes, end in parse_images(text):
        if not destination:
            continue
        caption = clean(alt)
        label = None
        found = re.search(r'\\label\{([^}]*)\}', caption)
        if found:
            label = found.group(1)
            caption = clean(caption.replace(found.group(0), ''))
        found = re.search(r'#([^\s}]+)', attributes)
        if found:
            label = found.group(1)
        figure = {'source': destination}
        path, flag = resolve(destination, paper_path, files, lower)
        figure['path'] = path
        if path:
            figure['url'] = blob_url(host, repo_url, commit, path)
        elif flag == 'remote':
            figure['url'] = destination
            figure['remote'] = True
        else:
            figure['missing'] = True
        stem = posixpath.splitext(posixpath.basename(destination))[0]
        if not caption or GENERIC_CAPTION.match(caption) or caption == stem:
            below = text_caption(text, end)
            if below:
                caption = below
                figure['caption_source'] = 'text'
        figure['caption'] = caption
        if label:
            figure['label'] = label
        figures.append(figure)
    return figures


def fetch_commit(repo_url, commit, folder):
    """Fetch one commit without file contents into the empty `folder`."""
    run_git('init', '--quiet', folder)
    run_git('remote', 'add', 'origin', repo_url, cwd=folder)
    run_git('fetch', '--quiet', '--depth', '1', '--filter=blob:none', 'origin', commit,
            cwd=folder)


def process(path, force):
    """Return (status, message). Status: done, skipped, failed."""
    with open(path, encoding='utf-8') as f:
        metadata = json.load(f)
    markdown = metadata.get('markdown')
    if not markdown or (not force and 'figures' in markdown):
        return 'skipped', None
    name = metadata['id']
    parsed = parse_url(markdown['url'].split('/blob/')[0].split('/-/blob/')[0])
    if not parsed:
        return 'failed', '%s: unsupported URL %s' % (name, markdown['url'])
    host, repo_url, _ = parsed
    try:
        with tempfile.TemporaryDirectory() as folder:
            fetch_commit(repo_url, markdown['commit'], folder)
            files = [f for f in run_git('ls-tree', '-r', '-z', '--name-only', 'FETCH_HEAD',
                                        cwd=folder).split('\0') if f]
            text = run_git('show', 'FETCH_HEAD:' + markdown['path'], cwd=folder)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        detail = (getattr(error, 'stderr', '') or str(error)).strip().splitlines()
        return 'failed', '%s: cannot fetch %s: %s' % (name, repo_url, detail[-1] if detail else error)
    markdown['figures'] = find_figures(text, markdown['path'], files, host, repo_url,
                                       markdown['commit'])
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.write('\n')
    problems = [fig['source'] for fig in markdown['figures'] if fig.get('missing')]
    if problems:
        return 'done', '%s: image not in the repository: %s' % (name, ', '.join(problems))
    return 'done', None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the metadata JSON files (default: cache/metadata)')
    parser.add_argument('--force', action='store_true',
                        help='search again for preprints that already have `figures`')
    parser.add_argument('--jobs', type=int, default=4, help='parallel fetches (default: 4)')
    parser.add_argument('ids', nargs='*', help='only these identifiers (default: all)')
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.metadata, '*.json')))
    if args.ids:
        wanted = {i.lower() for i in args.ids}
        paths = [p for p in paths if os.path.basename(p)[:-5].lower() in wanted]
    if not paths:
        sys.exit('No metadata in %s; run `make extractPdfMetadata` first.' % args.metadata)
    counts = {'done': 0, 'skipped': 0, 'failed': 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for status, message in pool.map(lambda p: process(p, args.force), paths):
            counts[status] += 1
            if message:
                print(message)
    print('Done: %(done)d, skipped: %(skipped)d, failed: %(failed)d' % counts)
    return 1 if counts['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
