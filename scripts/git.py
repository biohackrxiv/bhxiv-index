#!/usr/bin/env python3
"""Add or update `git:` lines (the GitHub or GitLab repository) in the posts in _posts/.

The repositories come from the metadata extracted from the PDFs by extractPdfMetadata.py
(cache/metadata/<identifier>.json), and are matched with the posts on the DOI.

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

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts', '*.markdown')
METADATA = os.path.join(HERE, '..', 'cache', 'metadata')
DOI_PREFIX = '10.37044/osf.io/'
GIT_URL = re.compile(r'^https?://(www\.)?(github|gitlab)\.com/[\w.-]+/[\w.-]+(/[\w./%~+-]*)?$')


def normalize_doi(doi):
    doi = doi.strip().lower()
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)


def git_url(url):
    """Return the URL as a clean https://github.com/... or https://gitlab.com/... URL, or None."""
    if not url or not GIT_URL.match(url.strip()):
        return None
    url = re.sub(r'^http://', 'https://', url.strip())
    url = re.sub(r'^https://www\.', 'https://', url)
    url = url.rstrip('/')
    return re.sub(r'\.git$', '', url)


def load_repositories(folder=METADATA):
    """Return {OSF identifier: repository URL} from the metadata files."""
    table = {}
    for path in glob.glob(os.path.join(folder, '*.json')):
        with open(path, encoding='utf-8') as f:
            metadata = json.load(f)
        repository = metadata.get('repository')
        if repository and repository.get('url'):
            table[metadata['id'].lower()] = repository['url']
    return table


def osf_id(path):
    """Return the OSF identifier from the `doi:` of a post, or None."""
    with open(path, encoding='utf-8') as f:
        match = re.search(r'^doi:\s*(\S+)', f.read(), re.MULTILINE)
    doi = normalize_doi(match.group(1)) if match else ''
    return doi[len(DOI_PREFIX):] if doi.startswith(DOI_PREFIX) else None


def update_git(path, table, update_changed=False):
    """Add or correct the `git:` line of a post.

    Return 'added', 'changed' (the URL differs from the PDF; only written when update_changed
    is true), 'skipped' (the PDF has a second link that is not a GitHub or GitLab repository) or None
    (nothing to do).
    """
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return None
    end = lines.index('---', 1)
    front = lines[1:end]
    dois = [normalize_doi(line[4:]) for line in front if line.startswith('doi:')]
    if not dois or not dois[0].startswith(DOI_PREFIX):
        return None
    found = table.get(dois[0][len(DOI_PREFIX):])
    if not found:
        return None
    url = git_url(found)
    if not url:
        return 'skipped'
    new = 'git: ' + url
    existing = [i for i in range(1, end) if lines[i].startswith('git:')]
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
        help='also overwrite git: lines that differ from the PDF '
             '(by default they are only reported)')
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the JSON files (default: cache/metadata)')
    args = parser.parse_args()
    table = load_repositories(args.metadata)
    if not table:
        raise SystemExit('No repositories in %s; run `make extractPdfMetadata` first.'
                         % args.metadata)
    print('PDFs with a second link: %d' % len(table))
    added = changed = skipped = 0
    for path in sorted(glob.glob(POSTS)):
        status = update_git(path, table, args.update_changed)
        name = os.path.basename(path)
        if status == 'added':
            added += 1
        elif status == 'changed':
            changed += 1
            print('%s: git differs from the PDF (%s)' % (
                name, 'updated' if args.update_changed else 'not updated'))
        elif status == 'skipped':
            skipped += 1
            print('%s: second link in the PDF is not a GitHub or GitLab repository: %s' % (
                name, table[osf_id(path)]))
    print('Posts with a new line: %d' % added)
    print('Posts with a changed URL: %d%s' % (
        changed, '' if args.update_changed else ' (use --update-changed to update)'))
    print('Posts skipped (not GitHub or GitLab): %d' % skipped)


if __name__ == '__main__':
    main()
