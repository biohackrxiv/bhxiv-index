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

The body is the abstract (the Zenodo description) as plain text: HTML, Markdown and Pandoc
annotations, including citations ([@key]), are removed.

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
import os
import re
import sys
import textwrap
import urllib.error

import zenodo
from git import git_url
from setDescription import plain_text, shorten

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts')
TAGS = os.path.join(HERE, '..', 'tag', '*.markdown')
COMMUNITY = None  # the slug of the BioHackrXiv community on Zenodo, once it exists
WIDTH = 120  # line length of the abstract in the post


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


# Pandoc citations: [@key] and [see @key, p. 3; @intention:key2]
CITATION = r'\s*\[[^\[\]]*@[^\[\]]*\]'


def strip_markdown(text):
    """The text without Markdown and Pandoc annotations: citations, images and footnotes are
    removed, of links, emphasis and code only the text is kept, and headings, block quotes and
    list markers are removed from the start of lines. Line breaks are kept."""
    text = re.sub(CITATION, '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)               # images
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)            # links
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)                # automatic links
    text = re.sub(r'\[\^[^\]]+\]', '', text)                         # footnotes
    text = re.sub(r'\{[#.][^{}]*\}', '', text)                         # {#fig:x} and {.class}
    text = re.sub(r'(?m)^[ \t]{0,3}(#{1,6}\s+|>\s?|[*+-]\s+|\d+[.)]\s+)', '', text)
    for mark in (r'\*\*\*', r'\*\*', r'\*', '___', '__', '_', '~~'):  # emphasis, strikethrough
        text = re.sub(r'(?<![\w*_~])%s(?=\S)(.+?)(?<=\S)%s(?![\w*_~])' % (mark, mark), r'\1', text)
    text = re.sub(r'`+([^`]+)`+', r'\1', text)                        # code
    text = re.sub(r'\\([\\`*_{}\[\]()#+\-.!|~<>])', r'\1', text)       # escaped characters
    return text


def plain_abstract(description):
    """The HTML description of a record as plain text paragraphs of at most WIDTH characters,
    without HTML, Markdown and Pandoc annotations, and the Pandoc citations that were removed."""
    text = description or ''
    # Zenodo may have turned the underscores of citation keys into emphasis:
    # [@uses<em>method</em>in:x]; list the citations before the HTML is removed
    removed = [re.sub(r'</?em>', '_', c).strip() for c in re.findall(CITATION, text)]
    text = re.sub(CITATION, '', text)
    # HTML: keep the text, one paragraph per paragraph, line break and list item
    text = re.sub(r'<br\s*/?>|</?p[^>]*>|</?li[^>]*>|</?[uo]l[^>]*>|</?h\d[^>]*>', '\n\n', text)
    text = strip_markdown(html.unescape(re.sub(r'<[^>]+>', '', text)))
    paragraphs = []
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = re.sub(r'\s+', ' ', paragraph).strip()
        paragraph = re.sub(r'\s+([.,;:!?)])', r'\1', paragraph)         # left by removed citations
        if paragraph:
            paragraphs.append('\n'.join(textwrap.wrap(
                paragraph, WIDTH, break_long_words=False, break_on_hyphens=False)))
    return '\n\n'.join(paragraphs), removed


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
    abstract, citations = plain_abstract(metadata.get('description'))
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
    if citations:
        missing.append('citations removed from the abstract: ' + ' '.join(citations))
    if re.search(r'(?<![\w.])@\w', abstract):
        missing.append('the abstract may have Pandoc citations in the text (@key), which are kept')
    if re.search(r'\\[a-zA-Z]+', abstract):
        missing.append('the abstract has LaTeX commands (\\name), which are kept')
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


def read_paper(record):
    """The text of the paper.md of a record (also in the ~contrib/ folder), or None."""
    key = zenodo.find_file(record, 'paper.md')
    if not key:
        return None
    return zenodo.file_bytes(record['id'], key).decode('utf-8', errors='replace')


def handle(identifier, dry_run):
    record = zenodo.fetch_latest(identifier)
    if record['metadata'].get('resource_type', {}).get('subtype') != 'preprint':
        print('%s: not a preprint on Zenodo (%s), skipped' % (
            identifier, record['metadata'].get('resource_type', {}).get('title')))
        return
    versions = zenodo.versions(record)
    name, text, missing = build_post(record, versions, read_paper(record))
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
            identifier = zenodo.record_number(doi)
            if not identifier:
                parser.error('not a Zenodo DOI (%s<number>): %s' % (zenodo.DOI_PREFIX, doi))
            identifiers.append(identifier)
    elif args.community:
        identifiers = zenodo.community_records(args.community)
        print('Community %s: %d preprints' % (args.community, len(identifiers)))
    else:
        parser.error('give one or more DOIs; there is no BioHackrXiv community on Zenodo yet')

    for identifier in identifiers:
        try:
            handle(identifier, args.dry_run)
        except (urllib.error.URLError, ValueError) as error:
            print('FAILED %s: %s' % (identifier, error))


if __name__ == '__main__':
    main()
