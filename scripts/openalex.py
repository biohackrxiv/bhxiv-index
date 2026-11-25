#!/usr/bin/env python3
"""Add or update `openalex:` lines (the OpenAlex work ID) in the posts in _posts/.

The IDs come from the OpenAlex works of the BioHackrXiv source. An optional
OPENALEX_KEY environment variable is sent as a Bearer token.

OpenAlex usually merges the versions of a preprint into one work, with the DOI
of each version as one of its locations; the `doi` of the work is then just one
of them (a version, or the DOI without version suffix). Works are therefore
matched on the DOIs of all their locations:

  * the top-level `openalex:` is the work of the top-level `doi:` (the latest
    version), which for a merged work also covers the other versions;
  * an item of `versions:` only gets its own `openalex:` when OpenAlex has a
    separate work for that version;
  * when OpenAlex has a separate work for the DOI without version suffix, it is
    added as `concept:` with `doi:` and `openalex:`.

Only works of the type `preprint` are used: OpenAlex sometimes merges a
preprint with its journal article, and that work is the article.

A missing line is added; a line that differs from OpenAlex is only reported,
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

from europepmc import item_value, version_items

SOURCE_ID = 'S4306402587'
WORKS_URL = 'https://api.openalex.org/works'
POSTS = os.path.join(os.path.dirname(__file__), '..', '_posts', '*.markdown')
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'


def normalize_doi(doi):
    doi = doi.strip().lower()
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)


def fetch_doi_to_openalex(source_id=SOURCE_ID):
    """Return {doi: work ID} for the DOIs of all locations of the preprints of an OpenAlex source."""
    headers = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
    key = os.environ.get('OPENALEX_KEY', '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
    table = {}
    cursor = '*'
    while cursor:
        query = urllib.parse.urlencode({
            'filter': 'locations.source.id:' + source_id,
            'select': 'id,doi,type,locations', 'per-page': 200, 'cursor': cursor})
        request = urllib.request.Request(WORKS_URL + '?' + query, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        for work in page['results']:
            # OpenAlex also merges preprints with their journal article (or
            # other records); those works are not the preprint, so skip them
            if work.get('type') != 'preprint':
                continue
            identifier = work['id'].rsplit('/', 1)[-1]
            urls = [work.get('doi')] + [loc.get('landing_page_url') for loc in work.get('locations') or []]
            for url in urls:
                if url and re.match(r'^https?://(dx\.)?doi\.org/', url):
                    table.setdefault(normalize_doi(url), identifier)
        cursor = page['meta'].get('next_cursor')
        if not page['results']:
            break
    return table


def set_line(lines, line, new, results, where, update_changed):
    """Compare an existing line with `new`; return True when it was changed."""
    if lines[line].strip() == new.strip():
        return False
    results.append((where, 'changed'))
    if update_changed:
        lines[line] = new
        return True
    return False


def update_openalex(path, table, update_changed=False):
    """Add or correct the `openalex:` lines of a post (top level, `versions:`
    items and `concept:`).

    Return a list of (where, status) pairs, with `where` 'openalex',
    'version N' or 'concept', and status 'added' or 'changed' (only written
    when update_changed is true).
    """
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return []
    end = lines.index('---', 1)
    dois = [normalize_doi(lines[i][4:]) for i in range(1, end) if lines[i].startswith('doi:')]
    if not dois:
        return []
    top = table.get(dois[0])
    results = []
    write = False

    # `concept:`: only for a separate work of the DOI without version suffix
    concept_doi = re.sub(r'_v\d+$', '', dois[0])
    concept = table.get(concept_doi) if concept_doi != dois[0] else None
    if concept and concept != top:
        start = [i for i in range(1, end) if lines[i].startswith('concept:')]
        if not start:
            lines[end:end] = ['concept:', '  doi: ' + concept_doi, '  openalex: ' + concept]
            results.append(('concept', 'added'))
            write = True
        else:
            stop = start[0] + 1
            while stop < end and lines[stop].startswith(' '):
                stop += 1
            line, _ = item_value(lines, start[0] + 1, stop, 'openalex')
            if line is None:
                lines.insert(stop, '  openalex: ' + concept)
                results.append(('concept', 'added'))
                write = True
            else:
                write |= set_line(lines, line, '  openalex: ' + concept, results, 'concept', update_changed)
        end = lines.index('---', 1)

    # the items of `versions:`, from the last one up (inserted lines do not
    # shift the items still to do)
    for first, stop in reversed(version_items(lines, end)):
        _, doi = item_value(lines, first, stop, 'doi')
        work = table.get(normalize_doi(doi)) if doi else None
        if not work or work == top:
            continue
        _, version = item_value(lines, first, stop, 'version')
        where = 'version %s' % version
        indent = ' ' * (len(lines[first]) - len(lines[first].lstrip()) + 2)
        new = indent + 'openalex: ' + work
        line, _ = item_value(lines, first, stop, 'openalex')
        if line is None:
            after = None
            for key in ('europepmc', 'date', 'doi'):
                after = item_value(lines, first, stop, key)[0]
                if after is not None:
                    break
            lines.insert(after + 1, new)
            results.append((where, 'added'))
            write = True
        else:
            write |= set_line(lines, line, new, results, where, update_changed)
    end = lines.index('---', 1)

    if top:
        new = 'openalex: ' + top
        existing = [i for i in range(1, end) if lines[i].startswith('openalex:')]
        if not existing:
            blocks = [i for i in range(1, end) if lines[i].startswith(('versions:', 'concept:'))]
            lines.insert(blocks[0] if blocks else end, new)
            results.append(('openalex', 'added'))
            write = True
        else:
            write |= set_line(lines, existing[0], new, results, 'openalex', update_changed)

    if write:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--update-changed', action='store_true', default=False,
        help='also overwrite openalex: lines that differ from OpenAlex '
             '(by default they are only reported)')
    args = parser.parse_args()
    table = fetch_doi_to_openalex()
    print('DOIs of OpenAlex works: %d' % len(table))
    paths = sorted(glob.glob(POSTS))
    added = changed = 0
    for path in paths:
        for where, status in update_openalex(path, table, args.update_changed):
            if status == 'added':
                added += 1
                print('%s (%s): openalex added' % (os.path.basename(path), where))
            else:
                changed += 1
                print('%s (%s): openalex differs from OpenAlex (%s)' % (
                    os.path.basename(path), where,
                    'updated' if args.update_changed else 'not updated'))
    print('New openalex lines: %d' % added)
    print('Changed openalex IDs: %d%s' % (
        changed, '' if args.update_changed else ' (use --update-changed to update)'))


if __name__ == '__main__':
    main()
