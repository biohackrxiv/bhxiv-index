#!/usr/bin/env python3
"""Write a report of problems with the BioHackrXiv preprints in OpenAlex to feedback/openalex.md.

The report is meant to be sent to OpenAlex (https://openalex.org/feedback). All OpenAlex works with
a location in the BioHackrXiv source are downloaded and matched with the posts in _posts/ on the
DOIs of the preprint: the top-level `doi:`, the `doi:` of each item of `versions:`, and the DOI
without version suffix. OSF landing pages (https://osf.io/<id>) are matched on the OSF identifier.
The report lists:

  * merged records: a work with a location of a BioHackrXiv preprint that is not of the type
    `preprint`, for example because the preprint was merged with a journal article or with an
    unrelated record;
  * split records: one preprint (all versions of it) spread over more than one work;
  * titles that differ: the title of the work is not the title of any version of the preprint;
  * missing preprints: no work has any of the DOIs of the preprint.

An optional OPENALEX_KEY environment variable is sent as a Bearer token.

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
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from europepmc import item_value, version_items
from openalex import SOURCE_ID, USER_AGENT, WORKS_URL, normalize_doi

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts', '*.markdown')
OUTPUT = os.path.join(HERE, '..', 'feedback', 'openalex.md')
DOI_PREFIX = '10.37044/osf.io/'
SITE = 'https://index.biohackrxiv.org'


def headers():
    result = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
    key = os.environ.get('OPENALEX_KEY', '').strip()
    if key:
        result['Authorization'] = 'Bearer ' + key
    return result


def get_json(url):
    request = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_works(source_id=SOURCE_ID):
    """Return {work ID: work} for all works with a location in an OpenAlex source."""
    works = {}
    cursor = '*'
    while cursor:
        query = urllib.parse.urlencode({
            'filter': 'locations.source.id:' + source_id,
            'select': 'id,doi,type,title,publication_date,locations',
            'per-page': 200, 'cursor': cursor})
        page = get_json(WORKS_URL + '?' + query)
        for work in page['results']:
            works[work['id'].rsplit('/', 1)[-1]] = work
        cursor = page['meta'].get('next_cursor')
        if not page['results']:
            break
    return works


def fetch_work_by_doi(doi):
    """Return the work with this DOI, or None (OpenAlex also finds DOIs of locations this way)."""
    try:
        return get_json(WORKS_URL + '/doi:' + urllib.parse.quote(doi, safe='/'))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def read_post(path):
    """Return the preprint of a post: its OSF id, DOIs, titles and web page."""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    lines = text.split('\n')
    end = lines.index('---', 1)
    top = {}
    for line in lines[1:end]:
        match = re.match(r'^(doi|title):\s*(.*)$', line)
        if match and match.group(1) not in top:
            top[match.group(1)] = match.group(2).strip()
    doi = normalize_doi(top.get('doi', ''))
    if not doi.startswith(DOI_PREFIX):
        return None
    title = top.get('title', '').strip('"')
    dois = [doi]
    titles = [title]
    for first, stop in version_items(lines, end):
        _, version_doi = item_value(lines, first, stop, 'doi')
        if version_doi:
            dois.append(normalize_doi(version_doi))
        _, version_title = item_value(lines, first, stop, 'title')
        if version_title:
            titles.append(version_title.strip('"'))
    osf_id = re.sub(r'_v\d+$', '', doi[len(DOI_PREFIX):])
    dois.append(DOI_PREFIX + osf_id)
    name = os.path.basename(path)
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})-(.*)\.markdown$', name)
    page = '%s/%s/%s/%s/%s.html' % ((SITE,) + match.groups()) if match else None
    return {'id': osf_id, 'doi': doi, 'dois': sorted(set(dois)), 'title': title,
            'titles': titles, 'page': page}


def osf_titles(preprint):
    """Return the titles of all versions of a preprint on OSF (the official titles)."""
    titles = []
    try:
        data = get_json('https://api.osf.io/v2/preprints/%s/versions/' % preprint['id'])
        titles = [version['attributes']['title'] for version in data['data']]
    except (urllib.error.URLError, KeyError, ValueError):
        pass
    return titles


def location_keys(work):
    """Return the DOIs and OSF identifiers of the BioHackrXiv locations of a work."""
    dois, osf_ids = set(), set()
    urls = [work.get('doi')] + [loc.get('landing_page_url') for loc in work.get('locations') or []]
    for url in urls:
        if not url:
            continue
        url = url.lower()
        if re.match(r'^https?://(dx\.)?doi\.org/', url):
            doi = normalize_doi(url)
            dois.add(doi)
            if doi.startswith(DOI_PREFIX):
                osf_ids.add(re.sub(r'_v\d+$', '', doi[len(DOI_PREFIX):]))
        else:
            match = re.match(r'^https?://(?:www\.)?(?:osf\.io|biohackrxiv\.org)/([a-z0-9]{5})(?:_v\d+)?/?$', url)
            if match:
                osf_ids.add(match.group(1))
    return dois, osf_ids


def simplify(title):
    """A title without case, punctuation and spacing differences."""
    title = html.unescape(html.unescape(title or ''))  # also titles escaped twice (&amp;amp;)
    return re.sub(r'[^a-z0-9]', '', title.lower())


def work_line(work):
    identifier = work['id'].rsplit('/', 1)[-1]
    doi = normalize_doi(work['doi']) if work.get('doi') else 'no DOI'
    return '[%s](https://openalex.org/works/%s) (type `%s`, DOI %s, %s): "%s"' % (
        identifier, identifier, work.get('type'), doi, work.get('publication_date'),
        work.get('title'))


def preprint_line(preprint):
    versions = [doi for doi in preprint['dois'] if doi != DOI_PREFIX + preprint['id']] or [preprint['doi']]
    return '"%s" (BioHackrXiv preprint %s, DOI%s %s; %s)' % (
        preprint['title'], preprint['id'], 's' if len(versions) > 1 else '',
        ', '.join('[%s](https://doi.org/%s)' % (doi, doi) for doi in versions), preprint['page'])


def report(preprints, works, missing, not_in_filter, today, source_count):
    by_id = {p['id']: p for p in preprints}
    found = {}  # OSF id -> [work IDs]
    for identifier, work in works.items():
        _, osf_ids = location_keys(work)
        for osf_id in osf_ids:
            found.setdefault(osf_id, []).append(identifier)

    merged, split, titles = [], [], []
    for preprint in preprints:
        identifiers = sorted(set(found.get(preprint['id'], [])))
        for identifier in identifiers:
            work = works[identifier]
            if work.get('type') != 'preprint':
                merged.append((preprint, work))
            elif simplify(work.get('title')) not in {simplify(t) for t in preprint['titles']}:
                # the index may use another title than OSF: only report titles
                # that differ from all official (OSF) titles too
                official = osf_titles(preprint)
                if not official or simplify(work.get('title')) not in {simplify(t) for t in official}:
                    titles.append((preprint, work))
                else:
                    print('%s: the index title differs from OSF: "%s"' % (preprint['id'], preprint['title']))
        preprint_works = [works[i] for i in identifiers if works[i].get('type') == 'preprint']
        if len(preprint_works) > 1:
            split.append((preprint, preprint_works))

    out = ['# BioHackrXiv preprints in OpenAlex: possible problems', '',
           'Generated on %s by `make openalexReport` in the '
           '[BioHackrXiv index](%s), from the OpenAlex works with a location in the source '
           '[BioHackrXiv (OSF Preprints)](https://openalex.org/sources/%s). The index lists '
           '%d preprints; OpenAlex has %d works with a location in this source.' % (
               today, SITE, SOURCE_ID, len(preprints), source_count), '',
           'BioHackrXiv preprints are hosted by OSF. Each version of a preprint has its own '
           'DOI (`10.37044/osf.io/<id>_v1`, `_v2`, ...), and there is also a DOI without version '
           'suffix (`10.37044/osf.io/<id>`). All versions of one preprint are the same work.', '']

    out += ['## Preprints merged with a different record', '',
            'These works contain a location of a BioHackrXiv preprint, but the work itself is not '
            'that preprint (its type is not `preprint`, and usually it has another DOI and title). '
            'If the record is the journal article version of the preprint, the merge may be '
            'intended; otherwise we would expect the preprint to be a separate work of type '
            '`preprint`.', '']
    if merged:
        for preprint, work in merged:
            same = simplify(work.get('title')) in {simplify(t) for t in preprint['titles']}
            out += ['* Preprint: ' + preprint_line(preprint),
                    '  * Merged into: ' + work_line(work),
                    '  * Title %s the title of the preprint.' % ('matches' if same else 'differs from'),
                    '']
    else:
        out += ['None found.', '']

    out += ['## Preprints split over more than one work', '',
            'All versions of a preprint (and its DOI without version suffix, or its OSF page) are '
            'one work, but OpenAlex has more than one work of type `preprint` for these preprints. '
            'We would expect them to be merged into one work.', '']
    landing_only = sum(1 for _, ws in split for w in ws if not w.get('doi') and all(
        not re.match(r'^https?://(dx\.)?doi\.org/', loc.get('landing_page_url') or '')
        for loc in w.get('locations') or []))
    if landing_only:
        out += ['In %d of these cases, one of the works has no DOI and only the OSF page of the '
                'preprint (`https://osf.io/<id>`) as location, while another work has the DOI of the '
                'same preprint.' % landing_only, '']
    if split:
        for preprint, preprint_works in split:
            out += ['* Preprint: ' + preprint_line(preprint)]
            for work in preprint_works:
                dois, _ = location_keys(work)
                urls = sorted({loc.get('landing_page_url') for loc in work.get('locations') or []
                               if loc.get('landing_page_url')})
                out += ['  * ' + work_line(work) + '; locations: ' + ', '.join(urls)]
            out += ['']
    else:
        out += ['None found.', '']

    out += ['## Works with a title that differs from the preprint', '',
            'The title of these works of type `preprint` is not the title of any version of the '
            'preprint on OSF (compared without case, punctuation and spacing).', '']
    if titles:
        for preprint, work in titles:
            out += ['* Preprint: ' + preprint_line(preprint),
                    '  * Work: ' + work_line(work), '']
    else:
        out += ['None found.', '']

    out += ['## Works not returned by the source filter', '',
            'These works have a location in the source BioHackrXiv (OSF Preprints), but the filter '
            '`locations.source.id:%s` does not return them; they were found with their DOI '
            '(`/works/doi:...`).' % SOURCE_ID, '']
    if not_in_filter:
        for osf_id, work in not_in_filter:
            out += ['* Preprint: ' + preprint_line(by_id[osf_id]),
                    '  * Work: ' + work_line(work), '']
    else:
        out += ['None found.', '']

    out += ['## Preprints not in OpenAlex', '',
            'No OpenAlex work has any of the DOIs of these preprints.', '']
    if missing:
        out += ['* ' + preprint_line(by_id[osf_id]) for osf_id in missing] + ['']
    else:
        out += ['None found.', '']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output', default=OUTPUT, help='the report (default: feedback/openalex.md)')
    args = parser.parse_args()

    preprints = [p for p in (read_post(path) for path in sorted(glob.glob(POSTS))) if p]
    works = fetch_works()
    source_count = len(works)
    print('Preprints: %d, OpenAlex works in the source: %d' % (len(preprints), source_count))

    known = set()
    for work in works.values():
        known |= location_keys(work)[1]
    missing, not_in_filter = [], []
    for preprint in preprints:
        if preprint['id'] in known:
            continue
        # not found via the source: look the DOIs up directly
        hits = [work for work in (fetch_work_by_doi(doi) for doi in preprint['dois']) if work]
        for work in hits:
            works[work['id'].rsplit('/', 1)[-1]] = work
            print('%s: found by DOI, but not via the source: %s' % (preprint['id'], work['id']))
            if any((loc.get('source') or {}).get('id', '').endswith('/' + SOURCE_ID)
                   for loc in work.get('locations') or []):
                not_in_filter.append((preprint['id'], work))
        if not hits:
            missing.append(preprint['id'])

    text = report(preprints, works, missing, not_in_filter, datetime.date.today().isoformat(),
                  source_count)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('Written: %s' % os.path.relpath(args.output))


if __name__ == '__main__':
    main()
