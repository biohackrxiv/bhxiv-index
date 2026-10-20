#!/usr/bin/env python3
"""Add `openalex:` lines (the OpenAlex work ID) to the posts in _posts/.

The IDs come from the OpenAlex works of the BioHackrXiv source. An optional
OPENALEX_KEY environment variable is sent as a Bearer token.

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
import glob
import json
import os
import re
import urllib.parse
import urllib.request

SOURCE_ID = 'S4306402587'
WORKS_URL = 'https://api.openalex.org/works'
POSTS = os.path.join(os.path.dirname(__file__), '..', '_posts', '*.markdown')
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'


def normalize_doi(doi):
    doi = doi.strip().lower()
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)


def fetch_doi_to_openalex(source_id=SOURCE_ID):
    """Return {doi: work ID} for all works of an OpenAlex source."""
    headers = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
    key = os.environ.get('OPENALEX_KEY', '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
    table = {}
    cursor = '*'
    while cursor:
        query = urllib.parse.urlencode({
            'filter': 'locations.source.id:' + source_id,
            'select': 'id,doi', 'per-page': 200, 'cursor': cursor})
        request = urllib.request.Request(WORKS_URL + '?' + query, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        for work in page['results']:
            if work.get('doi'):
                table[normalize_doi(work['doi'])] = work['id'].rsplit('/', 1)[-1]
        cursor = page['meta'].get('next_cursor')
        if not page['results']:
            break
    return table


def add_openalex(path, table):
    """Add the `openalex:` line to a post's front matter. True if changed."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return False
    end = lines.index('---', 1)
    front = lines[1:end]
    if any(line.startswith('openalex:') for line in front):
        return False
    dois = [normalize_doi(line[4:]) for line in front if line.startswith('doi:')]
    work = table.get(dois[0]) if dois else None
    if not work:
        return False
    lines.insert(end, 'openalex: ' + work)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return True


def main():
    table = fetch_doi_to_openalex()
    print('OpenAlex works with a DOI: %d' % len(table))
    paths = sorted(glob.glob(POSTS))
    changed = sum(add_openalex(path, table) for path in paths)
    print('Posts updated: %d of %d' % (changed, len(paths)))


if __name__ == '__main__':
    main()
