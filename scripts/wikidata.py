#!/usr/bin/env python3
"""Add or update `wikidata:` lines (the Wikidata item ID) in the posts in _posts/.

The QIDs come from the Wikidata SPARQL endpoint: the items with a DOI (P356)
in the BioHackrXiv DOI prefix. Without --update-changed, a differing
`wikidata:` line is only reported.

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

SPARQL_URL = 'https://query.wikidata.org/sparql'
DOI_PREFIX = '10.37044/'
# Wikidata stores DOIs in upper case; they are compared in lower case.
QUERY = '''SELECT ?item ?doi WHERE {
  ?item wdt:P356 ?doi .
  FILTER(STRSTARTS(?doi, "%s"))
}''' % DOI_PREFIX.upper()
POSTS = os.path.join(os.path.dirname(__file__), '..', '_posts', '*.markdown')
USER_AGENT = 'bhxiv-index/0.1'


def normalize_doi(doi):
    doi = doi.strip().lower()
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)


def fetch_doi_to_wikidata(query=QUERY):
    """Return {doi: QID} for the results of a SPARQL query (?item, ?doi).
    If several items have the same DOI, the lowest QID is used."""
    request = urllib.request.Request(
        SPARQL_URL + '?' + urllib.parse.urlencode({'query': query}),
        headers={'User-Agent': USER_AGENT,
                 'Accept': 'application/sparql-results+json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        bindings = json.load(response)['results']['bindings']
    table = {}
    for row in bindings:
        doi = normalize_doi(row['doi']['value'])
        qid = row['item']['value'].rsplit('/', 1)[-1]
        if doi not in table or int(qid[1:]) < int(table[doi][1:]):
            table[doi] = qid
    return table


def update_wikidata(path, table, update_changed=False):
    """Add or correct the `wikidata:` line of a post.

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
    qid = table.get(dois[0]) if dois else None
    if not qid:
        return None
    new = 'wikidata: ' + qid
    existing = [i for i in range(1, end) if lines[i].startswith('wikidata:')]
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
        help='also overwrite wikidata: lines that differ from Wikidata '
             '(by default they are only reported)')
    args = parser.parse_args()
    table = fetch_doi_to_wikidata()
    print('Wikidata items with a DOI: %d' % len(table))
    paths = sorted(glob.glob(POSTS))
    added = changed = 0
    for path in paths:
        status = update_wikidata(path, table, args.update_changed)
        if status == 'added':
            added += 1
        elif status == 'changed':
            changed += 1
            print('%s: wikidata differs from Wikidata (%s)' % (
                os.path.basename(path),
                'updated' if args.update_changed else 'not updated'))
    print('Posts with a new line: %d' % added)
    print('Posts with a changed ID: %d%s' % (
        changed, '' if args.update_changed else ' (use --update-changed to update)'))


if __name__ == '__main__':
    main()
