#!/usr/bin/env python3
"""Create a post in _posts/ for a BioHackrXiv preprint on OSF.

Usage: updateFromOSF.py <BH_CODE> <DOI>

BH_CODE is the tag of the meeting, which must be in _data/meetings.yml, and DOI is the OSF DOI of
the preprint (10.37044/osf.io/<id>, with or without a version suffix such as `_v1`). The metadata
comes from the DOI itself, as CSL JSON (content negotiation at https://doi.org/). The post is

    _posts/<date the DOI was created>-<id without version suffix>.markdown

with `title:`, `date:`, `tags:` (the meeting tag), `doi:` (in lower case) and `authors:`. An author
gets an `orcid:` only when Crossref marks the ORCID as authenticated. The body is the abstract.

This is a Python version of the earlier _posts/createPostFromDOI.groovy, with the same arguments.
Unlike that script, an existing post is not replaced, unless --force is given; with --dry-run the
post is printed and not written.

Copyright (c) 2025-2026 Egon Willighagen

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
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts')
MEETINGS = os.path.join(HERE, '..', '_data', 'meetings.yml')
DOI_PREFIX = '10.37044/osf.io/'
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'


def read_meeting_tags(path=MEETINGS):
    """{tag: title} of the meetings; the `tag:` and `title:` of an entry may be in any order."""
    tags = {}
    tag = title = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            if re.match(r'^-\s*\S+:', line):  # the start of a new meeting
                if tag and title:
                    tags[tag] = title
                tag = title = None
                continue
            match = re.match(r'^\s*tag:\s*(\S+)', line)
            if match:
                tag = match.group(1)
                continue
            match = re.match(r'^\s*title:\s*"?([^"]*?)"?\s*$', line)
            if match:
                title = match.group(1)
    if tag and title:
        tags[tag] = title
    return tags


def fetch_metadata(doi):
    """The CSL JSON of a DOI."""
    request = urllib.request.Request('https://doi.org/' + doi, headers={
        'Accept': 'application/vnd.citationstyles.csl+json', 'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def quoted(text):
    return '"%s"' % text.replace('\\', '\\\\').replace('"', '\\"')


def build_post(tag, doi, metadata):
    """(file name, text of the post)."""
    local_part = doi.split('/osf.io/')[1].split('_')[0]
    date = metadata['created']['date-time'][:10]
    lines = ['---', 'layout: post',
             'title:  ' + quoted(re.sub(r'\s+', ' ', metadata.get('title', '')).strip()),
             'date:   ' + date, 'tags: ' + tag, 'doi: ' + doi, 'authors:']
    for author in metadata.get('author', []):
        name = ' '.join(part for part in (author.get('given'), author.get('family')) if part)
        lines.append('  - name: ' + (name or author.get('name', '')))
        if author.get('authenticated-orcid') and author.get('ORCID'):
            lines.append('    orcid: ' + re.sub(r'^https?://orcid\.org/', '', author['ORCID']))
    lines += ['---', '', '']
    abstract = (metadata.get('abstract') or '').replace('<p>', '').replace('</p>', '\n\n')
    return '%s-%s.markdown' % (date, local_part), '\n'.join(lines) + abstract


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('tag', metavar='BH_CODE', help='the meeting tag, from _data/meetings.yml')
    parser.add_argument('doi', metavar='DOI', help='the OSF DOI (10.37044/osf.io/<id>)')
    parser.add_argument('--force', action='store_true', help='replace an existing post')
    parser.add_argument('--dry-run', action='store_true', help='print the post, do not write it')
    args = parser.parse_args()

    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', args.doi.strip().lower())
    if not doi.startswith(DOI_PREFIX):
        parser.error('not an OSF DOI (%s<id>): %s' % (DOI_PREFIX, args.doi))
    meetings = read_meeting_tags()
    if args.tag not in meetings:
        sys.exit('Unknown meeting tag: %s (not found in _data/meetings.yml)' % args.tag)
    print('Meeting: ' + meetings[args.tag])

    try:
        metadata = fetch_metadata(doi)
    except urllib.error.HTTPError as error:
        sys.exit('Cannot get the metadata of %s: %s' % (doi, error))
    name, text = build_post(args.tag, doi, metadata)
    if args.dry_run:
        print(text)
        return
    path = os.path.join(POSTS, name)
    if os.path.exists(path) and not args.force:
        sys.exit('%s exists; use --force to replace it' % name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Written: ' + name)


if __name__ == '__main__':
    main()
