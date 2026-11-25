#!/usr/bin/env python3
"""Create posts in _posts/ for BioHackrXiv preprints on Zenodo.

Usage: updateFromZenodo.py [DOI ...]

A DOI is a Zenodo DOI (10.5281/zenodo.<number>, optionally as a https://doi.org/ link) of any
version of a preprint, or its concept DOI. Without DOIs, all records of the BioHackrXiv community
on Zenodo are used (--community; there is no such community yet).

The metadata comes from the Zenodo API (https://developers.zenodo.org/): the record of the latest
version, the list of all versions, and the file `paper.md` of the record when it has one
(BioHackrXiv template). The post is named after the concept record, so its URL does not
change when a new version is posted:

    _posts/<date of version 1>-<concept record>.markdown

with in the front matter:

  * `title:` and `authors:` (with ORCID) of the latest version; Zenodo gives names as
    "Family, Given", which become "Given Family";
  * `date:`, the date version 1 was created on Zenodo (not `publication_date`, which the
    depositor can set to any date);
  * `tags:`: the tag of the event (`event:` in paper.md, matched with the `tag:` of the pages in
    tag/, or `biohackathon_url:` with their `website:`);
  * `doi:` and `zenodo:` (record) of the latest version, and `concept:` with the concept `doi:`
    and `zenodo:`;
  * `git:`, the GitHub or GitLab repository (related identifier "isSupplementedBy", or `git_url:`
    in paper.md);
  * `description:`, the start of the abstract (as setDescription.py);
  * `versions:` when there is more than one version, oldest first, with `version` (the position in
    the list), `doi`, `zenodo` and `date`, plus `title` and `authors` when they differ from the
    latest version.

The body is the abstract (the Zenodo description), converted from HTML to Markdown.

What cannot be found is reported per post: for example authors without ORCID, an event without a
tag page. The other scripts add `image:`, `europepmc:`, `openalex:` and
`wikidata:` later.

Existing posts are not changed: if the post exists, the differences with the new text are printed.
With --dry-run, nothing is written and the posts are printed instead.

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
import difflib
import glob
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request

from git import git_url
from setDescription import plain_text, shorten

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts')
TAGS = os.path.join(HERE, '..', 'tag', '*.markdown')
API_URL = 'https://zenodo.org/api/'
DOI_PREFIX = '10.5281/zenodo.'
COMMUNITY = None  # the slug of the BioHackrXiv community on Zenodo, once it exists
PAGE_SIZE = 25  # the maximum without an access token
USER_AGENT = 'bhxiv-index/0.1 (https://github.com/biohackrxiv/bhxiv-index)'
WIDTH = 120  # line length of the abstract in the post



# --- Zenodo API ------------------------------------------------------------------------------

def open_url(url, retries=4):
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(5 * (attempt + 1))
    return None


def get_json(url):
    return json.loads(open_url(url))


def record_id(doi):
    """The Zenodo record number of a Zenodo DOI, or None when it is not a Zenodo DOI."""
    doi = doi.strip().lower()
    doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:)', '', doi)
    match = re.match(re.escape(DOI_PREFIX) + r'(\d+)$', doi)
    return match.group(1) if match else None


def fetch_record(identifier):
    """The latest version of the record (also for the DOI of an older version or the concept)."""
    record = get_json(API_URL + 'records/' + identifier)
    latest = record.get('links', {}).get('latest')
    return get_json(latest) if latest else record


def fetch_versions(record):
    """All published versions of the record, oldest first."""
    url = record['links']['versions'] + '?' + urllib.parse.urlencode({'size': PAGE_SIZE})
    versions = []
    while url:
        page = get_json(url)
        versions += page['hits']['hits']
        url = page.get('links', {}).get('next')
    unique = {str(v['id']): v for v in versions}
    return sorted(unique.values(), key=lambda v: v['created'])


def fetch_file(record, name):
    """The text of a file of the record (also in the ~contrib/ folder), or None."""
    for file in record.get('files', []):
        if file['key'] in (name, '~contrib/' + name):
            return open_url(file['links']['self']).decode('utf-8', errors='replace')
    return None


def community_records(slug):
    """The record numbers of all records of a community, one per concept."""
    url = API_URL + 'communities/%s/records?%s' % (slug, urllib.parse.urlencode({'size': PAGE_SIZE}))
    concepts = {}
    while url:
        page = get_json(url)
        for hit in page['hits']['hits']:
            concept = str(hit.get('conceptrecid') or hit.get('parent', {}).get('id') or hit['id'])
            concepts.setdefault(concept, str(hit['id']))
        url = page.get('links', {}).get('next')
    return list(concepts.values())


# --- paper.md ------------------------------------------------------------------------------------

def front_matter(markdown):
    """The simple `key: value` lines of the YAML header of paper.md."""
    match = re.match(r'\s*---\s*\n(.*?)\n---', markdown or '', re.S)
    values = {}
    for line in (match.group(1) if match else '').split('\n'):
        found = re.match(r'^([a-z_]+):\s*(\S.*?)\s*$', line)
        if found:
            values[found.group(1)] = re.sub(r'\s+#.*$', '', found.group(2)).strip('"\'')
    return values


# --- the event tag ---------------------------------------------------------------------------

def tag_pages():
    """[{tag, title, website}] of the pages in tag/."""
    pages = []
    for path in sorted(glob.glob(TAGS)):
        with open(path, encoding='utf-8') as f:
            values = front_matter(f.read())
        if values.get('tag'):
            pages.append(values)
    return pages


def simple_url(url):
    return re.sub(r'^https?://(www\.)?', '', (url or '').strip()).rstrip('/').lower()


def event_tag(paper, notes, missing):
    """The tag of the event from paper.md, or from the notes of the record ("... (..., event)")."""
    event = paper.get('event')
    if not event and notes:
        match = re.search(r'\(([^()]*)\)', notes)
        event = match.group(1).split(',')[-1].strip() if match else None
    pages = tag_pages()
    for page in pages:
        if event and page['tag'].lower() == event.lower():
            return page['tag']
    url = simple_url(paper.get('biohackathon_url'))
    for page in pages:
        if url and simple_url(page.get('website')) == url:
            return page['tag']
    name = paper.get('biohackathon_name')
    missing.append('event tag: no page in tag/ for event %s%s%s' % (
        event or '(none given)', ', "%s"' % name if name else '',
        ', ' + paper['biohackathon_url'] if paper.get('biohackathon_url') else ''))
    return None


# --- the post --------------------------------------------------------------------------------

def person_name(name):
    """ "Family, Given" as "Given Family"."""
    name = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', name or ''))).strip()
    parts = [part.strip() for part in name.split(',')]
    return '%s %s' % (parts[1], parts[0]) if len(parts) == 2 and all(parts) else name


def authors(record):
    return [{'name': person_name(c.get('name')), 'orcid': c.get('orcid')}
            for c in record['metadata'].get('creators', [])]


def markdown_abstract(description):
    """The HTML description of a record as Markdown paragraphs of at most WIDTH characters."""
    text = description or ''
    # Zenodo turned the underscores of citation keys into emphasis: [@uses<em>method</em>in:x]
    text = re.sub(r'\[@[^\]]*\]', lambda m: re.sub(r'</?em>', '_', m.group(0)), text)
    text = re.sub(r'<(em|i)>(.*?)</\1>', r'*\2*', text, flags=re.S)
    text = re.sub(r'<(strong|b)>(.*?)</\1>', r'**\2**', text, flags=re.S)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.S)
    text = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.S)
    text = re.sub(r'<li[^>]*>', '\n\n* ', text)
    text = re.sub(r'<br\s*/?>|</p>|</li>|</[uo]l>|<p[^>]*>|<[uo]l[^>]*>', '\n\n', text)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    paragraphs = []
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = re.sub(r'\s+', ' ', paragraph).strip()
        if paragraph:
            indent = '  ' if paragraph.startswith('* ') else ''
            paragraphs.append('\n'.join(textwrap.wrap(
                paragraph, WIDTH, subsequent_indent=indent,
                break_long_words=False, break_on_hyphens=False)))
    return '\n\n'.join(paragraphs)


def quoted(text):
    return '"%s"' % text.replace('\\', '\\\\').replace('"', '\\"')


def author_lines(people, indent=''):
    lines = []
    for person in people:
        lines.append('%s  - name: %s' % (indent, person['name']))
        if person['orcid']:
            lines.append('%s    orcid: %s' % (indent, person['orcid']))
    return lines


def repository(record, paper):
    for related in record['metadata'].get('related_identifiers', []):
        if related.get('relation') == 'isSupplementedBy' and git_url(related.get('identifier')):
            return git_url(related['identifier'])
    return git_url(paper.get('git_url'))


def build_post(record, versions, paper_md):
    """(file name, text of the post, [what could not be found])."""
    missing = []
    metadata = record['metadata']
    concept = str(record['conceptrecid'])
    title = re.sub(r'\s+', ' ', metadata.get('title', '')).strip()
    people = authors(record)
    paper = front_matter(paper_md)
    if paper_md is None:
        missing.append('paper.md: not in the record, so no event tag from it')
    if not versions:
        versions = [record]
    date = versions[0]['created'][:10]

    tag = event_tag(paper, metadata.get('notes'), missing)
    abstract = markdown_abstract(metadata.get('description'))
    git = repository(record, paper)

    lines = ['---', 'layout: post', 'title:  ' + quoted(title), 'date:   ' + date]
    if tag:
        lines.append('tags: ' + tag)
    lines.append('doi: ' + record['doi'])
    lines += ['authors:'] + author_lines(people)
    if git:
        lines.append('git: ' + git)
    else:
        missing.append('git: no GitHub or GitLab repository (related identifier "isSupplementedBy" '
                       'or `git_url:` in paper.md)')
    if abstract:
        lines.append('description: ' + quoted(shorten(plain_text(abstract))))
    else:
        missing.append('abstract: the record has no description, so no body and no `description:`')
    lines.append('zenodo: %s' % record['id'])
    lines += ['concept:', '  doi: ' + record['conceptdoi'], '  zenodo: ' + concept]
    if len(versions) > 1:
        lines.append('versions:')
        for number, version in enumerate(versions, 1):
            lines += ['  - version: %d' % number, '    doi: ' + version['doi'],
                      '    zenodo: %s' % version['id'], '    date: ' + version['created'][:10]]
            version_title = re.sub(r'\s+', ' ', version['metadata'].get('title', '')).strip()
            if version_title != title:
                lines.append('    title: ' + quoted(version_title))
            if authors(version) != people:
                lines += ['    authors:'] + author_lines(authors(version), '    ')
    lines += ['---', '']
    if abstract:
        lines.append(abstract)

    for person in people:
        if not person['orcid']:
            missing.append('ORCID of author %s' % person['name'])
    if re.search(r'\[@', abstract):
        missing.append('the abstract has Pandoc citations ([@key]), which are shown as they are')
    if re.search(r'{[{%]', abstract):
        missing.append('the abstract has {{ or {%, which Jekyll reads as Liquid')
    for key in ('image', 'europepmc', 'openalex', 'wikidata'):
        missing.append('%s: not from Zenodo (see the other scripts in the README)' % key)
    return '%s-%s.markdown' % (date, concept), '\n'.join(lines) + '\n', missing


def existing_post(record):
    """The path of the post of this preprint, if there is one."""
    concept = str(record['conceptrecid'])
    paths = glob.glob(os.path.join(POSTS, '*-%s.markdown' % concept))
    if paths:
        return paths[0]
    dois = {record['doi'].lower(), record['conceptdoi'].lower()}
    for path in glob.glob(os.path.join(POSTS, '*.markdown')):
        with open(path, encoding='utf-8') as f:
            header = f.read().split('\n---', 1)[0]
        if {d.lower() for d in re.findall(r'(?m)^\s*-?\s*doi:\s*(\S+)', header)} & dois:
            return path
    return None


def handle(identifier, dry_run):
    record = fetch_record(identifier)
    if record['metadata'].get('resource_type', {}).get('subtype') != 'preprint':
        print('%s: not a preprint on Zenodo (%s), skipped' % (
            identifier, record['metadata'].get('resource_type', {}).get('title')))
        return
    versions = fetch_versions(record)
    name, text, missing = build_post(record, versions, fetch_file(record, 'paper.md'))
    path = existing_post(record)
    if dry_run:
        print(text)
    elif path:
        with open(path, encoding='utf-8') as f:
            old = f.read()
        if old == text:
            print('%s: exists, no changes' % os.path.basename(path))
        else:
            print('%s: exists, not changed; the differences with Zenodo:' % os.path.basename(path))
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(True), text.splitlines(True), 'post', 'zenodo'))
    else:
        path = os.path.join(POSTS, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        print('%s: created (%d version%s)' % (name, len(versions), '' if len(versions) == 1 else 's'))
    print('%s: not found:' % name)
    for item in dict.fromkeys(missing):
        print('  * ' + item)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('dois', nargs='*', help='Zenodo DOIs (10.5281/zenodo.<number>)')
    parser.add_argument('--community', default=COMMUNITY,
                        help='the Zenodo community, used when no DOIs are given')
    parser.add_argument('--dry-run', action='store_true', help='print the posts, do not write them')
    args = parser.parse_args()

    if args.dois:
        identifiers = []
        for doi in args.dois:
            identifier = record_id(doi)
            if not identifier:
                parser.error('not a Zenodo DOI (%s<number>): %s' % (DOI_PREFIX, doi))
            identifiers.append(identifier)
    elif args.community:
        identifiers = community_records(args.community)
        print('Community %s: %d preprints' % (args.community, len(identifiers)))
    else:
        parser.error('give one or more DOIs; there is no BioHackrXiv community on Zenodo yet')

    for identifier in identifiers:
        try:
            handle(identifier, args.dry_run)
        except urllib.error.HTTPError as error:
            print('FAILED %s: %s' % (identifier, error))


if __name__ == '__main__':
    main()
