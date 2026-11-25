#!/usr/bin/env python3
"""Download the PDF of each preprint in _posts/ into a local cache (cache/pdfs/).

The identifier is taken from the `doi:` of each post, which is the latest version:

  * OSF: the OSF identifier (for example `c8jw6_v1` from 10.37044/osf.io/c8jw6_v1). The OSF API
    (https://developer.osf.io/) gives the primary file of the preprint.
  * Zenodo: the record number of the version (for example `24497647` from
    10.5281/zenodo.24497647). The Zenodo API (https://developers.zenodo.org/) gives the files of the
    record; the PDF is `paper.pdf`, or else the only PDF that is not in the `~contrib/` folder.

The PDF is downloaded as cache/pdfs/<identifier>.pdf. PDFs that are already in the cache are not
downloaded again. The cache is not part of the git repository.

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
import sys
import time
import urllib.error
import urllib.request

API_URL = 'https://api.osf.io/v2/preprints/'
DOWNLOAD_URL = 'https://osf.io/download/'
HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts', '*.markdown')
CACHE = os.path.join(HERE, '..', 'cache', 'pdfs')
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'
DOI_PREFIX = '10.37044/osf.io/'
ZENODO_API_URL = 'https://zenodo.org/api/records/'
ZENODO_DOI_PREFIX = '10.5281/zenodo.'


def open_url(url, retries=3):
    """Open a URL, retrying a few times on rate limiting and server errors."""
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            return urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            wait = int(error.headers.get('Retry-After') or 5 * (attempt + 1))
            time.sleep(wait)


def preprint_ids():
    """Return the sorted (identifier, source) of the `doi:` lines of the posts; the source is
    'osf' or 'zenodo'. Posts with another DOI are skipped."""
    ids = set()
    for path in glob.glob(POSTS):
        with open(path, encoding='utf-8') as handle:
            match = re.search(r'^doi:\s*(\S+)', handle.read(), re.MULTILINE)
        if match:
            doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', match.group(1).lower())
            if doi.startswith(DOI_PREFIX):
                ids.add((doi[len(DOI_PREFIX):], 'osf'))
            elif doi.startswith(ZENODO_DOI_PREFIX) and doi[len(ZENODO_DOI_PREFIX):].isdigit():
                ids.add((doi[len(ZENODO_DOI_PREFIX):], 'zenodo'))
            else:
                print('skipped %s: not an OSF or Zenodo DOI (%s)' % (os.path.basename(path), doi))
    return sorted(ids)


def save_pdf(content, target):
    """Write the content to target; raise when it is not a PDF."""
    if not content.startswith(b'%PDF'):
        raise ValueError('the file is not a PDF')
    partial = target + '.part'
    with open(partial, 'wb') as handle:
        handle.write(content)
    os.replace(partial, target)
    return len(content)


def download_pdf(osf_id, target):
    """Download the primary file of an OSF preprint to target; raise on anything but a PDF."""
    with open_url(API_URL + osf_id + '/') as response:
        preprint = json.load(response)
    primary = preprint['data']['relationships'].get('primary_file', {}).get('data')
    if not primary:
        raise ValueError('no primary file')
    with open_url(DOWNLOAD_URL + primary['id'] + '/') as response:
        return save_pdf(response.read(), target)


def download_zenodo_pdf(record, target):
    """Download the PDF of a Zenodo record to target; raise when there is no single PDF."""
    with open_url(ZENODO_API_URL + record) as response:
        files = json.load(response).get('files', [])
    pdfs = [f for f in files if f['key'].lower().endswith('.pdf') and '/' not in f['key']]
    paper = [f for f in pdfs if f['key'] == 'paper.pdf']
    if paper:
        pdfs = paper
    if len(pdfs) != 1:
        raise ValueError('%d PDFs in the record: %s' % (len(pdfs), ', '.join(f['key'] for f in pdfs)))
    with open_url(pdfs[0]['links']['self']) as response:
        return save_pdf(response.read(), target)


DOWNLOADERS = {'osf': download_pdf, 'zenodo': download_zenodo_pdf}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--cache', default=CACHE, help='cache folder (default: cache/pdfs)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='seconds to wait between preprints (default: 1)')
    args = parser.parse_args()

    os.makedirs(args.cache, exist_ok=True)
    ids = preprint_ids()
    downloaded, cached, failed = 0, 0, []
    for identifier, source in ids:
        target = os.path.join(args.cache, identifier + '.pdf')
        if os.path.exists(target):
            cached += 1
            continue
        try:
            size = DOWNLOADERS[source](identifier, target)
        except (urllib.error.URLError, ValueError, KeyError, OSError) as error:
            print('FAILED %s (%s): %s' % (identifier, source, error))
            failed.append(identifier)
        else:
            print('downloaded %s from %s (%d bytes)' % (identifier, source, size))
            downloaded += 1
        time.sleep(args.delay)
    print('%d preprints: %d downloaded, %d already cached, %d failed'
          % (len(ids), downloaded, cached, len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
