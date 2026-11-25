"""Functions for BioHackrXiv preprints on Zenodo, shared by the scripts.

A preprint on Zenodo has a record for each version, with its own DOI (10.5281/zenodo.<record>).
The files of a record cannot change, so a record number identifies one version of the Markdown
source and the figures. The source repository of the preprint is copied into the record, in the
`~contrib/` folder (for example `~contrib/paper.md` and `~contrib/overview.png`).

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
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = 'https://zenodo.org/api/records/'
RECORD_URL = 'https://zenodo.org/records/'
DOI_PREFIX = '10.5281/zenodo.'
COMMUNITIES_URL = 'https://zenodo.org/api/communities/'
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'
PAGE_SIZE = 25  # the maximum without an access token
MAX_BYTES = 50 * 1024 * 1024


def is_record(identifier):
    """True for the identifier of a Zenodo preprint (a record number), False for an OSF one."""
    return bool(re.fullmatch(r'\d+', identifier or ''))


def record_number(doi):
    """The record number of a Zenodo DOI, or None when it is not a Zenodo DOI."""
    doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', (doi or '').strip().lower())
    match = re.fullmatch(re.escape(DOI_PREFIX) + r'(\d+)', doi)
    return match.group(1) if match else None


def get(url, retries=4):
    """The content of a URL, retrying on rate limiting and server errors."""
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('more than %d bytes: %s' % (MAX_BYTES, url))
            return data
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(5 * (attempt + 1))
    return None


def get_json(url):
    return json.loads(get(url))


def fetch_record(record):
    """The JSON of a record (of that version, not the latest). For a concept record, Zenodo
    answers with the latest version."""
    return get_json(API_URL + str(record))


def fetch_latest(record):
    """The JSON of the latest version of the preprint of a record (any version, or the concept)."""
    record_json = fetch_record(record)
    latest = record_json.get('links', {}).get('latest')
    return get_json(latest) if latest else record_json


def versions(record_json):
    """The JSON of all published versions of the preprint of a record, oldest first."""
    url = record_json['links']['versions'] + '?' + urllib.parse.urlencode({'size': PAGE_SIZE})
    found = []
    while url:
        page = get_json(url)
        found += page['hits']['hits']
        url = page.get('links', {}).get('next')
    unique = {str(v['id']): v for v in found}
    return sorted(unique.values(), key=lambda v: v['created'])


def community_records(slug):
    """The record numbers of the records of a community, one per concept."""
    url = COMMUNITIES_URL + '%s/records?%s' % (slug, urllib.parse.urlencode({'size': PAGE_SIZE}))
    concepts = {}
    while url:
        page = get_json(url)
        for hit in page['hits']['hits']:
            concept = str(hit.get('conceptrecid') or hit.get('parent', {}).get('id') or hit['id'])
            concepts.setdefault(concept, str(hit['id']))
        url = page.get('links', {}).get('next')
    return list(concepts.values())


def latest_record(record_json):
    """The record number of the latest version of the preprint of a record."""
    for relation in record_json.get('metadata', {}).get('relations', {}).get('version', []):
        if relation.get('is_last'):
            return str(record_json['id'])
    latest = record_json.get('links', {}).get('latest')
    return str(get_json(latest)['id']) if latest else str(record_json['id'])


def file_keys(record_json):
    """The names (keys) of the files of a record, for example `~contrib/paper.md`."""
    return [f['key'] for f in record_json.get('files', [])]


def file_url(record, key):
    """The web address of a file of a record."""
    return RECORD_URL + '%s/files/%s' % (record, urllib.parse.quote(key))


def content_url(record, key):
    """The API address of the content of a file of a record."""
    return API_URL + '%s/files/%s/content' % (record, urllib.parse.quote(key))


def file_bytes(record, key):
    return get(content_url(record, key))


def find_file(record_json, name):
    """The key of the file `name` of a record, also when it is in the `~contrib/` folder, or None."""
    for key in file_keys(record_json):
        if key in (name, '~contrib/' + name):
            return key
    return None
