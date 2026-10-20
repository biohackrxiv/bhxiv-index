#!/usr/bin/env python3
"""Add or update `europepmc:` lines (the Europe PMC identifier) in the posts in _posts/.

The identifiers come from the Europe PMC preprints with the publisher
BioHackrXiv (search API: https://europepmc.org/RestfulWebService).

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
import re
import urllib.parse
import urllib.request

SEARCH_URL = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
QUERY = 'PUBLISHER:"BioHackrXiv"'
POSTS = os.path.join(os.path.dirname(__file__), '..', '_posts', '*.markdown')
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'


def normalize_doi(doi):
    doi = doi.strip().lower()
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)


def fetch_doi_to_europepmc(query=QUERY):
    """Return {doi: Europe PMC ID} for all results of a Europe PMC query."""
    table = {}
    cursor = '*'
    while cursor:
        params = urllib.parse.urlencode({
            'query': query, 'format': 'json', 'resultType': 'lite',
            'pageSize': 1000, 'cursorMark': cursor})
        request = urllib.request.Request(
            SEARCH_URL + '?' + params, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        results = page['resultList']['result']
        for record in results:
            if record.get('doi') and record.get('id'):
                table[normalize_doi(record['doi'])] = record['id']
        next_cursor = page.get('nextCursorMark')
        cursor = next_cursor if results and next_cursor != cursor else None
    return table


def update_europepmc(path, table, update_changed=False):
    """Add or correct the `europepmc:` line of a post.

    Return 'added', 'changed' (the ID differs from the table; only written
    when update_changed is true) or None (nothing to do).
    """
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return None
    end = lines.index('---', 1)
    front = lines[1:end]
    dois = [normalize_doi(line[4:]) for line in front if line.startswith('doi:')]
    identifier = table.get(dois[0]) if dois else None
    if not identifier:
        return None
    new = 'europepmc: ' + identifier
    existing = [i for i in range(1, end) if lines[i].startswith('europepmc:')]
    if not existing:
        lines.insert(end, new)
        status = 'added'
    elif lines[existing[0]].strip() == new:
        return None
    elif update_changed:
        lines[existing[0]] = new
        status = 'changed'
    else:
        return 'changed'
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--update-changed', action='store_true', default=False,
        help='also overwrite europepmc: lines that differ from Europe PMC '
             '(by default they are only reported)')
    args = parser.parse_args()
    table = fetch_doi_to_europepmc()
    print('Europe PMC records with a DOI: %d' % len(table))
    paths = sorted(glob.glob(POSTS))
    added = changed = 0
    for path in paths:
        status = update_europepmc(path, table, args.update_changed)
        if status == 'added':
            added += 1
        elif status == 'changed':
            changed += 1
            print('%s: europepmc differs from Europe PMC (%s)' % (
                os.path.basename(path),
                'updated' if args.update_changed else 'not updated'))
    print('Posts with a new line: %d' % added)
    print('Posts with a changed ID: %d%s' % (
        changed, '' if args.update_changed else ' (use --update-changed to update)'))


if __name__ == '__main__':
    main()
