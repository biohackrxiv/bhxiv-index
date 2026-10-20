#!/usr/bin/env python3
"""Create QuickStatements (version 2, CSV) to add missing identifiers to Wikidata.

For each post with a `wikidata:` line, the OpenAlex ID (P10283, from the
`openalex:` line) and the Europe PMC preprint ID (P13529, the `europepmc:`
line without the "PPR" prefix) are added when the Wikidata item has no such
statement yet. Each new statement gets a reference: reference URL (S854) is
the page of the work on index.biohackrxiv.org, retrieved (S813) is today, and
stated in (S248) is BioHackrXiv (Q115450084). A statement that is already
there with a different value (ignoring case) is not touched, but reported on the standard
output.

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
import csv
import datetime
import glob
import json
import os
import re
import urllib.parse
import urllib.request

SPARQL_URL = 'https://query.wikidata.org/sparql'
SITE_URL = 'https://index.biohackrxiv.org'
STATED_IN = 'Q115450084'
# post front matter key -> (Wikidata property, prefix to remove from the value)
PROPERTIES = {'openalex': ('P10283', ''), 'europepmc': ('P13529', 'PPR')}
POSTS = os.path.join(os.path.dirname(__file__), '..', '_posts', '*.markdown')
USER_AGENT = 'bhxiv-index/0.1'


def read_post(path):
    """Return the simple `key: value` lines of the front matter as a dict,
    with the URL of the post on the index site as `url`."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return {}
    post = {}
    for line in lines[1:lines.index('---', 1)]:
        match = re.match(r'^([a-z]+):\s*(\S.*)$', line)
        if match:
            post[match.group(1)] = match.group(2).strip()
    name = re.match(r'^(\d{4})-(\d\d)-(\d\d)-(.+)\.markdown$',
                    os.path.basename(path))
    if name:
        post['url'] = '%s/%s/%s/%s/%s.html' % (SITE_URL, *name.groups())
    return post


def fetch_existing(qids, properties):
    """Return {(qid, property): set of values} of the statements that Wikidata
    already has for the items."""
    values = ' '.join('wd:' + qid for qid in sorted(qids))
    query = 'SELECT ?item ?p ?value WHERE { VALUES ?item { %s } ' \
            'VALUES ?p { %s } ?item ?claim ?value . ' \
            '?p wikibase:directClaim ?claim }' % (
                values, ' '.join('wd:' + p for p in properties))
    request = urllib.request.Request(
        SPARQL_URL, data=urllib.parse.urlencode({'query': query}).encode(),
        headers={'User-Agent': USER_AGENT,
                 'Accept': 'application/sparql-results+json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        bindings = json.load(response)['results']['bindings']
    existing = {}
    for row in bindings:
        key = (row['item']['value'].rsplit('/', 1)[-1],
               row['p']['value'].rsplit('/', 1)[-1])
        existing.setdefault(key, set()).add(row['value']['value'])
    return existing


def quote(value):
    """A string value in QuickStatements."""
    return '"' + value.replace('"', '""') + '"'


def create_statements(posts, existing, today):
    """Return (rows, mismatches): the QuickStatements rows (dicts with the
    CSV columns) for the missing statements and the mismatches (strings)."""
    retrieved = '+%sT00:00:00Z/11' % today.isoformat()
    rows, mismatches = [], []
    for post in posts:
        qid = post.get('wikidata')
        if not qid:
            continue
        for key, (prop, prefix) in PROPERTIES.items():
            value = post.get(key)
            if not value:
                continue
            if prefix:
                if not value.startswith(prefix):
                    mismatches.append('%s: %s %s does not start with %s' % (
                        qid, key, value, prefix))
                    continue
                value = value[len(prefix):]
            current = existing.get((qid, prop), set())
            # OpenAlex IDs are compared ignoring case (W123 is w123)
            if value.lower() in {c.lower() for c in current}:
                continue
            if current:
                mismatches.append('%s: %s is %s in the post but %s in Wikidata' % (
                    qid, prop, value, ', '.join(sorted(current))))
                continue
            rows.append({'qid': qid, prop: quote(value),
                         'S854': quote(post['url']), 'S813': retrieved,
                         'S248': STATED_IN})
    return rows, mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output', default='quickstatements.csv',
                        help='CSV file to write (default: %(default)s)')
    args = parser.parse_args()
    posts = [read_post(path) for path in sorted(glob.glob(POSTS))]
    qids = {post['wikidata'] for post in posts if post.get('wikidata')}
    existing = fetch_existing(qids, [p for p, _ in PROPERTIES.values()])
    rows, mismatches = create_statements(posts, existing, datetime.date.today())
    columns = ['qid'] + [p for p, _ in PROPERTIES.values()] + ['S854', 'S813', 'S248']
    with open(args.output, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, columns, restval='', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    for mismatch in mismatches:
        print('Mismatch: ' + mismatch)
    print('Posts with a Wikidata item: %d' % len(qids))
    print('Statements to add: %d (written to %s)' % (len(rows), args.output))
    print('Mismatches: %d' % len(mismatches))


if __name__ == '__main__':
    main()
