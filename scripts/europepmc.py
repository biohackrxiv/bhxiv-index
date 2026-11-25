#!/usr/bin/env python3
"""Add or update `europepmc:` lines (the Europe PMC identifier) in the posts in _posts/.

The identifiers come from the Europe PMC preprints with the publisher
BioHackrXiv (search API: https://europepmc.org/RestfulWebService).

Europe PMC has a separate identifier for each version of a preprint. The
top-level `europepmc:` is that of the top-level `doi:` (the latest version),
and each item of a `versions:` list gets the identifier of its own `doi:`:

    versions:
      - version: 1
        doi: 10.37044/osf.io/xqe8h_v1
        date: 2025-05-04
        europepmc: PPR1013743

A missing line is added; a line that differs from Europe PMC is only reported,
unless --update-changed is given.

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


def version_items(lines, end):
    """Return the (first, stop) line ranges of the items of the `versions:` list."""
    starts = [i for i in range(1, end) if lines[i].startswith('versions:')]
    if not starts:
        return []
    items = []
    i = starts[0] + 1
    while i < end and lines[i].startswith(' '):
        if lines[i].lstrip().startswith('- '):
            items.append([i, i + 1])
        elif items:
            items[-1][1] = i + 1
        i += 1
    return [tuple(item) for item in items]


def item_value(lines, first, stop, key):
    """Return (line number, value) of `key:` in a list item, or (None, None)."""
    for i in range(first, stop):
        text = lines[i].strip()
        if text.startswith('- '):
            text = text[2:].strip()
        if text.startswith(key + ':'):
            return i, text[len(key) + 1:].strip()
    return None, None


def update_europepmc(path, table, update_changed=False):
    """Add or correct the `europepmc:` lines of a post: the top-level one and
    those of the items of a `versions:` list.

    Return a list of (where, status) pairs, with `where` 'europepmc' or
    'version N', and status 'added' or 'changed' (the ID differs from the
    table; only written when update_changed is true). Lines that are correct
    or have no Europe PMC record are not listed.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return []
    end = lines.index('---', 1)
    results = []
    write = False

    # the items of `versions:`, from the last one up, so that inserted lines
    # do not shift the line numbers of the items still to do
    for first, stop in reversed(version_items(lines, end)):
        _, doi = item_value(lines, first, stop, 'doi')
        identifier = table.get(normalize_doi(doi)) if doi else None
        if not identifier:
            continue
        _, version = item_value(lines, first, stop, 'version')
        where = 'version %s' % version
        indent = ' ' * (len(lines[first]) - len(lines[first].lstrip()) + 2)
        new = indent + 'europepmc: ' + identifier
        line, value = item_value(lines, first, stop, 'europepmc')
        if line is None:
            # right after `date:` (or `doi:`), keeping version, doi, date, europepmc
            after = item_value(lines, first, stop, 'date')[0]
            if after is None:
                after = item_value(lines, first, stop, 'doi')[0]
            lines.insert(after + 1, new)
            results.append((where, 'added'))
            write = True
        elif value != identifier:
            results.append((where, 'changed'))
            if update_changed:
                lines[line] = new
                write = True
    end = lines.index('---', 1)

    front = lines[1:end]
    dois = [normalize_doi(line[4:]) for line in front if line.startswith('doi:')]
    identifier = table.get(dois[0]) if dois else None
    if identifier:
        new = 'europepmc: ' + identifier
        existing = [i for i in range(1, end) if lines[i].startswith('europepmc:')]
        if not existing:
            versions = [i for i in range(1, end) if lines[i].startswith('versions:')]
            lines.insert(versions[0] if versions else end, new)
            results.append(('europepmc', 'added'))
            write = True
        elif lines[existing[0]].strip() != new:
            results.append(('europepmc', 'changed'))
            if update_changed:
                lines[existing[0]] = new
                write = True

    if write:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return results


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
        for where, status in update_europepmc(path, table, args.update_changed):
            if status == 'added':
                added += 1
            elif status == 'changed':
                changed += 1
                print('%s (%s): europepmc differs from Europe PMC (%s)' % (
                    os.path.basename(path), where,
                    'updated' if args.update_changed else 'not updated'))
    print('New europepmc lines: %d' % added)
    print('Changed europepmc IDs: %d%s' % (
        changed, '' if args.update_changed else ' (use --update-changed to update)'))


if __name__ == '__main__':
    main()
