#!/usr/bin/env python3
"""Write a report of problems with the BioHackrXiv preprints in Europe PMC to feedback/europepmc.md.

The report is meant to be sent to Europe PMC (https://europepmc.org/ContactUs). All Europe PMC
records with the publisher BioHackrXiv are downloaded (search API:
https://europepmc.org/RestfulWebService) and matched on their DOI with the preprints in _posts/:
the top-level `doi:`, the `doi:` of each item of `versions:`, and the DOI without version suffix.
The report lists:

  * versions that are not linked: preprints with a separate record for each version, without
    anything that links these records;
  * records for the DOI without version suffix, which is the same preprint as one of the versions;
  * versions of preprints that are not in Europe PMC;
  * titles that differ: the title of the record is not the title of any version on OSF.

Records with a DOI that is not a preprint in the index are only printed on the standard output.

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
import datetime
import glob
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from europepmc import QUERY, SEARCH_URL, USER_AGENT, normalize_doi
from openalexReport import DOI_PREFIX, SITE, osf_titles, read_post, simplify

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts', '*.markdown')
OUTPUT = os.path.join(HERE, '..', 'feedback', 'europepmc.md')
RECORD_URL = 'https://europepmc.org/article/PPR/'


def get_json(url, retries=4):
    """GET a JSON document; Europe PMC sometimes answers with an HTML error page, so retry."""
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except (urllib.error.URLError, ValueError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return None


def fetch_records(query=QUERY):
    """Return all Europe PMC records (lite) of a query."""
    records = []
    cursor = '*'
    while cursor:
        params = urllib.parse.urlencode({
            'query': query, 'format': 'json', 'resultType': 'lite',
            'pageSize': 1000, 'cursorMark': cursor})
        page = get_json(SEARCH_URL + '?' + params)
        results = page['resultList']['result']
        records += results
        next_cursor = page.get('nextCursorMark')
        cursor = next_cursor if results and next_cursor != cursor else None
    return records


def record_line(record):
    return '[%s](%s%s) (DOI %s, first published %s): "%s"' % (
        record['id'], RECORD_URL, record['id'], record.get('doi'),
        record.get('firstPublicationDate'), (record.get('title') or '').rstrip('.'))


def preprint_line(preprint):
    versions = [doi for doi in preprint['dois'] if doi != DOI_PREFIX + preprint['id']] or [preprint['doi']]
    return '"%s" (BioHackrXiv preprint %s, DOI%s %s; %s)' % (
        preprint['title'], preprint['id'], 's' if len(versions) > 1 else '',
        ', '.join('[%s](https://doi.org/%s)' % (doi, doi) for doi in versions), preprint['page'])


def version_number(doi):
    match = re.search(r'_v(\d+)$', doi)
    return int(match.group(1)) if match else 0


def report(preprints, records, today):
    by_doi = {}
    for record in records:
        if record.get('doi'):
            by_doi.setdefault(normalize_doi(record['doi']), []).append(record)

    unlinked, concept, missing, titles = [], [], [], []
    for preprint in preprints:
        concept_doi = DOI_PREFIX + preprint['id']
        version_dois = sorted((d for d in preprint['dois'] if d != concept_doi), key=version_number)
        if not version_dois:  # an older preprint, with only the DOI without suffix
            version_dois = [concept_doi]
        version_records = [r for doi in version_dois for r in by_doi.get(doi, [])]
        if len(version_records) > 1:
            unlinked.append((preprint, version_records))
        if concept_doi not in version_dois and by_doi.get(concept_doi):
            concept.append((preprint, by_doi[concept_doi], version_records))
        absent = [doi for doi in version_dois if not by_doi.get(doi)]
        if absent:
            missing.append((preprint, absent))
        own = {simplify(t) for t in preprint['titles']}
        candidates = [r for doi in preprint['dois'] for r in by_doi.get(doi, [])
                      if simplify(r.get('title')) not in own]
        if candidates:
            # the index may use another title than OSF: only report titles that
            # differ from all official (OSF) titles too
            official = {simplify(t) for t in osf_titles(preprint)}
            wrong = [r for r in candidates if not official or simplify(r.get('title')) not in official]
            if wrong:
                titles.append((preprint, wrong))
            elif candidates:
                print('%s: the index title differs from OSF: "%s"' % (preprint['id'], preprint['title']))

    out = ['# BioHackrXiv preprints in Europe PMC: possible problems', '',
           'Generated on %s by `make europepmcReport` in the [BioHackrXiv index](%s), from the '
           'Europe PMC records found with the query `%s`. The index lists %d preprints; Europe PMC '
           'has %d records for this query.' % (today, SITE, QUERY, len(preprints), len(records)), '',
           'BioHackrXiv preprints are hosted by OSF. Each version of a preprint has its own DOI '
           '(`10.37044/osf.io/<id>_v1`, `_v2`, ...), and there is also a DOI without version suffix '
           '(`10.37044/osf.io/<id>`) that resolves to the latest version. Older preprints (before '
           '2025) only have the DOI without suffix.', '']

    out += ['## Versions of a preprint that are not linked', '',
            'Europe PMC has a separate record for each version of these preprints. The records '
            'have no version number and nothing links them to each other, so on Europe PMC they '
            'look like different preprints with the same title. We would expect them to be shown '
            'as versions of one preprint.', '']
    if unlinked:
        for preprint, version_records in unlinked:
            out += ['* Preprint: ' + preprint_line(preprint)]
            out += ['  * ' + record_line(r) for r in version_records] + ['']
    else:
        out += ['None found.', '']

    out += ['## Records for the DOI without version suffix', '',
            'These records have the DOI without version suffix. That DOI resolves to the latest '
            'version of the preprint, which Europe PMC also has as a record with the DOI of that '
            'version, so the preprint is in Europe PMC twice.', '']
    if concept:
        for preprint, concept_records, version_records in concept:
            out += ['* Preprint: ' + preprint_line(preprint)]
            out += ['  * Without suffix: ' + record_line(r) for r in concept_records]
            out += ['  * Version: ' + record_line(r) for r in version_records] + ['']
    else:
        out += ['None found.', '']

    out += ['## Versions not in Europe PMC', '',
            'No Europe PMC record has the DOI of these preprint versions.', '']
    if missing:
        for preprint, absent in missing:
            out += ['* Preprint: ' + preprint_line(preprint),
                    '  * Missing: ' + ', '.join('[%s](https://doi.org/%s)' % (d, d) for d in absent), '']
    else:
        out += ['None found.', '']

    out += ['## Records with a title that differs from the preprint', '',
            'The title of these records is not the title of any version of the preprint on OSF '
            '(compared without case, punctuation and spacing).', '']
    if titles:
        for preprint, wrong in titles:
            out += ['* Preprint: ' + preprint_line(preprint)]
            out += ['  * Record: ' + record_line(r) for r in wrong] + ['']
    else:
        out += ['None found.', '']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output', default=OUTPUT, help='the report (default: feedback/europepmc.md)')
    args = parser.parse_args()

    preprints = [p for p in (read_post(path) for path in sorted(glob.glob(POSTS))) if p]
    records = fetch_records()
    print('Preprints: %d, Europe PMC records: %d' % (len(preprints), len(records)))
    known = {doi for preprint in preprints for doi in preprint['dois']}
    for record in records:
        doi = normalize_doi(record.get('doi') or '')
        if doi not in known:
            print('%s: not a preprint in the index (DOI %s): %s' % (
                record['id'], doi or None, record.get('title')))

    text = report(preprints, records, datetime.date.today().isoformat())
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('Written: %s' % os.path.relpath(args.output))


if __name__ == '__main__':
    main()
