#!/usr/bin/env python3
"""Find the Markdown source (paper.md) of each preprint in its git repository.

For each cache/metadata/<identifier>.json with a GitHub or GitLab `repository` (see
extractPdfMetadata.py) this script makes a shallow, blobless clone of the repository, looks for
files named paper.md (in the folder of the repository URL, if it has one, otherwise anywhere) and
checks the YAML header of each against what is already known about the preprint:

  * `title` must match the title of the post in _posts/ (matched on the DOI), and
  * `biohackathon_url` must match the URL of the first link (the event) found in the PDF.

URLs are compared without scheme, `www.` and trailing slash; titles without case, punctuation
and spacing differences. The result is added to the JSON file as `markdown`:

    "markdown": {"path": "paper/paper.md",
                 "url": "https://github.com/owner/repo/blob/<commit>/paper/paper.md",
                 "commit": "<commit>",
                 "alternatives": ["other/paper.md"]}

`alternatives` lists other paper.md files that also match. `markdown` is null when the repository
was searched but no paper.md matches. When the repository cannot be cloned, `markdown` is left
out, so the next run tries again. Preprints that already have `markdown` are skipped unless
--force is given.

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
import concurrent.futures
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile

from git import METADATA, POSTS, git_url, osf_id

PAPER = 'paper.md'
TIMEOUT = 300
ENVIRONMENT = dict(os.environ, GIT_TERMINAL_PROMPT='0')


def run_git(*args, cwd=None):
    return subprocess.run(['git'] + list(args), cwd=cwd, env=ENVIRONMENT, check=True,
                          capture_output=True, text=True, timeout=TIMEOUT).stdout


def parse_url(url):
    """Split a GitHub or GitLab URL into (host, repository URL, rest after tree/blob or '').

    GitLab projects can be in subgroups (any number of path segments); GitLab marks the end of
    the project with `/-/`.
    """
    match = re.match(r'^https://([^/]+)/(.+?)/?$', url)
    if not match:
        return None
    host, path = match.groups()
    rest = ''
    if '/-/' in path:
        path, _, tail = path.partition('/-/')
        rest = re.sub(r'^(tree|blob)/', '', tail)
    else:
        segments = path.split('/')
        if 'gitlab' not in host:
            if len(segments) > 3 and segments[2] in ('tree', 'blob'):
                rest = '/'.join(segments[3:])
            segments = segments[:2]
        path = '/'.join(segments)
    return host, 'https://%s/%s' % (host, path), rest


def split_ref(repo_url, rest):
    """Split 'branch/sub/folder' into (branch, 'sub/folder'); branch names can contain slashes."""
    if not rest:
        return None, ''
    refs = set()
    for line in run_git('ls-remote', '--heads', '--tags', repo_url).splitlines():
        name = line.split('\t')[1]
        refs.add(re.sub(r'^refs/(heads|tags)/', '', name))
    best = max((r for r in refs if rest == r or rest.startswith(r + '/')), key=len, default=None)
    if best:
        return best, rest[len(best):].strip('/')
    # unknown ref: assume the first segment is the branch
    head, _, tail = rest.partition('/')
    return None, tail


def front_matter(text):
    """Return the top-level scalar values of the YAML header as a dict (no YAML library needed)."""
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0].strip() != '---':
        return {}
    values = {}
    i = 1
    while i < len(lines) and lines[i].strip() not in ('---', '...'):
        match = re.match(r'^([A-Za-z_][\w-]*):\s*(.*?)\s*$', lines[i])
        i += 1
        if not match:
            continue
        key, value = match.groups()
        if re.match(r'^[>|][+-]?$', value):  # block scalar
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((' ', '\t'))):
                block.append(lines[i].strip())
                i += 1
            value = ' '.join(b for b in block if b)
        elif value[:1] == '"' and value[-1:] == '"' and len(value) > 1:
            value = value[1:-1].replace('\\"', '"')
        elif value[:1] == "'" and value[-1:] == "'" and len(value) > 1:
            value = value[1:-1].replace("\'\'", "'")
        values[key] = value
    return values


def same_title(a, b):
    def norm(s):
        return re.sub(r'[\W_]+', ' ', html.unescape(s).casefold()).strip()
    return bool(a) and bool(b) and norm(a) == norm(b)


def same_url(a, b):
    def norm(u):
        return re.sub(r'^https?://(www\.)?', '', u.strip().casefold()).rstrip('/')
    return bool(a) and bool(b) and norm(a) == norm(b)


def load_titles(posts=POSTS):
    """Return {OSF identifier (lower case): title} from the posts."""
    titles = {}
    for path in glob.glob(posts):
        identifier = osf_id(path)
        if not identifier:
            continue
        with open(path, encoding='utf-8') as f:
            header = front_matter(f.read())
        if header.get('title'):
            titles[identifier.lower()] = header['title']
    return titles


def blob_url(host, repo_url, commit, path):
    return '%s/%sblob/%s/%s' % (repo_url, '-/' if 'gitlab' in host else '', commit, path)


def find_markdown(repository_url, title, event_url):
    """Return the `markdown` object for a repository, or None when no paper.md matches."""
    parsed = parse_url(repository_url)
    if not parsed:
        raise OSError('unsupported repository URL')
    host, repo_url, rest = parsed
    with tempfile.TemporaryDirectory() as folder:
        ref, subpath = split_ref(repo_url, rest)
        clone = ['clone', '--quiet', '--depth', '1', '--filter=blob:none', '--no-checkout']
        if ref:
            clone += ['--branch', ref]
        run_git(*clone, repo_url, folder)
        commit = run_git('rev-parse', 'HEAD', cwd=folder).strip()
        files = [f for f in run_git('ls-tree', '-r', '-z', '--name-only', 'HEAD',
                                    cwd=folder).split('\0') if f]
        papers = [f for f in files if f.rsplit('/', 1)[-1].casefold() == PAPER]
        if subpath:  # a link to a file or folder: look in that folder first
            folder_path = subpath.rsplit('/', 1)[0] if subpath.endswith('.md') else subpath
            inside = [f for f in papers if f.startswith(folder_path.rstrip('/') + '/')]
            papers = inside or papers
        matching = []
        for path in papers:
            header = front_matter(run_git('show', 'HEAD:' + path, cwd=folder))
            if same_title(header.get('title'), title) and \
                    same_url(header.get('biohackathon_url'), event_url):
                matching.append(path)
    if not matching:
        return None
    matching.sort(key=lambda p: (p.count('/'), p))
    result = {'path': matching[0], 'url': blob_url(host, repo_url, commit, matching[0]),
              'commit': commit}
    if len(matching) > 1:
        result['alternatives'] = matching[1:]
    return result


def process(path, titles, force):
    """Return (status, message). Status: found, missing, skipped, failed."""
    with open(path, encoding='utf-8') as f:
        metadata = json.load(f)
    name = metadata['id']
    if 'markdown' in metadata and not force:
        return 'skipped', None
    url = git_url((metadata.get('repository') or {}).get('url'))
    if not url:
        return 'skipped', None
    title = titles.get(name.lower())
    links = metadata.get('links') or []
    if not title or not links:
        return 'failed', '%s: no post title or event link to compare with' % name
    try:
        markdown = find_markdown(url, title, links[0]['url'])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        detail = (getattr(error, 'stderr', '') or str(error)).strip().splitlines()
        return 'failed', '%s: cannot search %s: %s' % (name, url, detail[-1] if detail else error)
    previous = metadata.get('markdown')
    if markdown and previous and 'figures' in previous and \
            (previous.get('path'), previous.get('commit')) == (markdown['path'], markdown['commit']):
        # added by findFigures.py and checkPdfFigures.py
        markdown['figures'] = previous['figures']
        if 'pdf' in previous:
            markdown['pdf'] = previous['pdf']
    metadata['markdown'] = markdown
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.write('\n')
    if markdown:
        return 'found', '%s: %s%s' % (name, markdown['path'],
                                      ' (+%d more)' % len(markdown['alternatives'])
                                      if 'alternatives' in markdown else '')
    return 'missing', '%s: no paper.md in %s matches the title and biohackathon_url' % (name, url)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the metadata JSON files (default: cache/metadata)')
    parser.add_argument('--force', action='store_true',
                        help='search again for preprints that already have `markdown`')
    parser.add_argument('--jobs', type=int, default=4, help='parallel clones (default: 4)')
    parser.add_argument('ids', nargs='*', help='only these identifiers (default: all)')
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.metadata, '*.json')))
    if args.ids:
        wanted = {i.lower() for i in args.ids}
        paths = [p for p in paths if os.path.basename(p)[:-5].lower() in wanted]
    if not paths:
        sys.exit('No metadata in %s; run `make extractPdfMetadata` first.' % args.metadata)
    titles = load_titles()
    counts = {'found': 0, 'missing': 0, 'skipped': 0, 'failed': 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for status, message in pool.map(lambda p: process(p, titles, args.force), paths):
            counts[status] += 1
            if message and status != 'found':
                print(message)
    print('Found: %(found)d, no match: %(missing)d, skipped: %(skipped)d, failed: %(failed)d'
          % counts)
    return 1 if counts['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
