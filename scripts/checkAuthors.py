#!/usr/bin/env python3
"""Check the authors of the posts in _posts/ against the PDF and the Markdown source of the preprint.

For each post, the PDF of its `doi:` (the latest version) is read from cache/pdfs/ (see
cachePdfs.py). The authors are on the first page, below the title: the names, with their ORCID as
links on the name or on the ORCID icon after it. The PDF metadata has no authors. The page is read
with `pdftohtml -xml` (Poppler), as in extractPdfMetadata.py.

When the source of the preprint is known (the `markdown` in cache/metadata/<identifier>.json, see
findMarkdown.py), the `authors:` in the YAML header of paper.md are compared too: from the git
repository at the commit of the metadata for OSF preprints, and from the Zenodo record for Zenodo
preprints. The paper.md files are kept in cache/markdown/<identifier>.md.

Reported per post:

  * authors that are in the PDF but not in the post, or the other way around, and a different order
    (names are compared without case, accents and punctuation);
  * ORCIDs that differ between the post and the PDF, and ORCIDs that are not valid (wrong format or
    check digit);
  * differences between the Markdown and the PDF.

The posts are updated: an author of the post without an ORCID gets the ORCID that the PDF has for the
same name, or else the one the Markdown has. An ORCID is not added when another post has it for an
author with another family name, or when another author of the post has it; these are reported.
With --update-changed, the author list of the post
is also replaced with that of the PDF: the authors and their order as in the PDF, with the ORCID
of the PDF, or else that of the Markdown or the post. Some PDFs miss letters that their font does
not have (for example "Seró" as "Ser"), so the names are taken from the Markdown when it has as
many authors as the PDF, and from the PDF otherwise. Without --update-changed, these differences
are only reported. With --dry-run, no post is changed.

The findings that are left after the update are written to feedback/biohackrxiv.md, a report for
the BioHackrXiv team, grouped by kind (feedback/biohackrxiv.html shows it on the website). The
report is only written when all posts are checked, and leaves out unlisted posts.

Usage: checkAuthors.py [--update-changed] [--dry-run] [--no-markdown] [identifier ...]

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
import datetime
import difflib
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

import zenodo
from extractPdfMetadata import SIDEBAR_MAX_LEFT
from findFigures import fetch_commit
from findMarkdown import parse_url, run_git
from git import METADATA, POSTS, preprint_id

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, '..', 'cache', 'pdfs')
MARKDOWN = os.path.join(HERE, '..', 'cache', 'markdown')
OUTPUT = os.path.join(HERE, '..', 'feedback', 'biohackrxiv.md')
SITE = 'https://index.biohackrxiv.org'
# the kinds of findings, in the order of the report: (key, heading, explanation)
SECTIONS = [
    ('orcid-invalid', 'ORCIDs that are not valid',
     'These ORCIDs do not have the format of an ORCID or have a wrong check digit. Some PDFs and '
     'Markdown sources use `0000-0000-0000-0000` for an author without ORCID.'),
    ('orcid-differs', 'ORCIDs that differ between the index and the PDF',
     'The index and the PDF give the same author a different ORCID.'),
    ('orcid-conflict', 'ORCIDs that were not added',
     'The PDF or the Markdown source has an ORCID for an author who has none in the index, but '
     'the ORCID was not added: other preprints have it for someone with another family name, or '
     'another author of the same preprint has it. The ORCID in the PDF or Markdown is probably '
     'wrong.'),
    ('missing', 'Authors in the PDF but not in the index, or the other way around',
     'Some of these are the same person with a very different spelling of the name.'),
    ('name', 'Names that differ',
     'The first or the family name differs between the index and the PDF, which can be a typing '
     'error in either.'),
    ('name-variant', 'Names with other middle names or initials',
     'The first and family names are the same, but the index and the PDF differ in middle names, '
     'initials or accents. These are listed for completeness.'),
    ('order', 'Authors in a different order',
     'The PDF is leading for the order of the authors. Either the index and the PDF have the same '
     'authors in a different order, or, when the author lists also differ in other ways, the '
     'authors that are in both are in a different order; then the authors that are in another '
     'place are listed.'),
    ('markdown', 'Differences between the PDF and the Markdown source',
     'The authors in the YAML header of the Markdown source (paper.md) of the preprint differ from '
     'the PDF. The PDF is what was published; the Markdown may have been changed later.'),
    ('pdf', 'PDFs that could not be checked', ''),
]
ORCID = re.compile(r'(\d{4}-\d{4}-\d{4}-\d{3}[\dX])')
FRAGMENT = re.compile(r'<text top="(\d+)" left="(\d+)" width="\d+" height="(\d+)" font="(\d+)">(.*?)</text>')


# --- ORCIDs and names --------------------------------------------------------------------------

def orcid_checksum_ok(orcid):
    """True when the check digit of an ORCID is right (ISO 7064 MOD 11-2)."""
    digits = orcid.replace('-', '')
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ('X' if check == 10 else str(check))


def clean_orcid(value):
    """The ORCID in a value (a bare ORCID, a URL, with a leading slash, ...), or None."""
    match = ORCID.search(value or '')
    return match.group(1) if match else None


def valid_orcid(value):
    """True for a bare, valid ORCID as used in the posts (0000-0002-1825-0097)."""
    return bool(value) and re.fullmatch(ORCID.pattern, value) is not None and orcid_checksum_ok(value)


def clean_name(name):
    name = html.unescape(re.sub(r'<[^>]+>', '', name or ''))
    name = name.replace(' ', ' ').replace('~', ' ')
    name = re.sub(r'[*†‡§¶]+', '', name)  # markers for corresponding authors
    return re.sub(r'\s+', ' ', name).strip(' ,;')


def name_key(name):
    """A name without case, accents, punctuation and spacing differences."""
    name = unicodedata.normalize('NFKD', name.casefold())
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return re.sub(r'[\W_]+', ' ', name).strip()


def family_key(name):
    words = name_key(name).split()
    return words[-1] if words else ''


# --- authors in the PDF ------------------------------------------------------------------------

def pdf_fragments(pdf):
    """[(top, left, height, font, inner XML)] of the text on the first page."""
    xml = subprocess.run(['pdftohtml', '-xml', '-i', '-q', '-f', '1', '-l', '1', '-stdout', pdf],
                         check=True, capture_output=True, text=True, timeout=120).stdout
    return [(int(t), int(l), int(h), f, inner) for t, l, h, f, inner in FRAGMENT.findall(xml)]


def pdf_authors(pdf):
    """[{'name', 'orcid'}] of the author block below the title, or None when it is not found."""
    fragments = pdf_fragments(pdf)
    if not fragments:
        return None
    # the main column has the title, the authors and the text; the sidebar on the left has the
    # event, the dates and the license
    main = sorted((f for f in fragments if f[1] >= SIDEBAR_MAX_LEFT), key=lambda f: (f[0], f[1]))
    if not main:
        return None
    title_font = main[0][3]
    position = 0
    while position < len(main) and main[position][3] == title_font:
        position += 1
    # the names are bold; the affiliation numbers next to them can be a bit higher on the page
    while position < len(main) and '<b>' not in main[position][4]:
        position += 1
    if position == len(main):
        return None
    author_font, height = main[position][3], main[position][2]
    lines = [main[position][0]]
    for fragment in main[position:]:
        if fragment[3] == author_font and fragment[0] not in lines:
            if fragment[0] - lines[-1] > 1.8 * height:
                break
            lines.append(fragment[0])
    top, bottom = lines[0] - height // 2, lines[-1] + height
    block = [f for f in main[position:] if top <= f[0] <= bottom and f[3] != title_font]
    # reading order: by line (fragments within half a line height are on the same line), then left
    ordered = sorted(block, key=lambda f: (min(lines, key=lambda line: abs(line - f[0])), f[1]))

    tokens, previous_line = [], None
    for fragment in ordered:
        line = min(lines, key=lambda l: abs(l - fragment[0]))
        for orcid_part, text in re.findall(r'<a href="[^"]*orcid\.org/([^"]*)"[^>]*>|([^<]+|<[^>]*>)',
                                           fragment[4]):
            if orcid_part:
                tokens.append(('orcid', clean_orcid(orcid_part)))
            elif fragment[3] == author_font and not text.startswith('<'):
                texts = [value for kind, value in tokens if kind == 'text']
                if previous_line is not None and line != previous_line and texts and \
                        not texts[-1].endswith('-'):
                    tokens.append(('text', ' '))  # a new line, also after an ORCID link
                tokens.append(('text', html.unescape(text)))
                previous_line = line
            elif not text.startswith('<') and not text.strip():
                tokens.append(('text', ' '))  # a space in another font, between two names
    authors, current = [], None
    for kind, value in tokens:
        if kind == 'orcid':
            if current is not None and value and not current['orcid']:
                current['orcid'] = value
            continue
        parts = re.split(r',|\s+and\s+|^and\s+', value)
        for index, part in enumerate(parts):
            if index > 0 or current is None:
                current = {'name': '', 'orcid': None}
                authors.append(current)
            current['name'] += part
    authors = [{'name': clean_name(a['name']), 'orcid': a['orcid']} for a in authors]
    authors = [a for a in authors if a['name'] and a['name'].casefold() != 'and']
    for author in authors:
        author['name'] = re.sub(r'^and\s+', '', author['name'])
    return authors or None


# --- authors in the Markdown source ------------------------------------------------------------

def markdown_text(identifier, metadata, folder=MARKDOWN):
    """The text of paper.md of a preprint (cached in folder), or None when it is not known."""
    markdown = metadata.get('markdown') or {}
    if not markdown.get('path'):
        return None
    cached = os.path.join(folder, identifier + '.md')
    if os.path.exists(cached):
        with open(cached, encoding='utf-8') as f:
            return f.read()
    if markdown.get('source') == 'zenodo':
        text = zenodo.file_bytes(markdown['record'], markdown['path']).decode('utf-8', 'replace')
    else:
        parsed = parse_url(markdown['url'].split('/blob/')[0].split('/-/blob/')[0])
        if not parsed:
            return None
        with tempfile.TemporaryDirectory() as clone:
            fetch_commit(parsed[1], markdown['commit'], clone)
            text = run_git('show', 'FETCH_HEAD:' + markdown['path'], cwd=clone)
    os.makedirs(folder, exist_ok=True)
    with open(cached, 'w', encoding='utf-8') as f:
        f.write(text)
    return text


def unquote(value):
    value = value.strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in '"\'':
        value = value[1:-1]
    return value


def markdown_authors(text):
    """[{'name', 'orcid'}] of the `authors:` in the YAML header of paper.md, or None."""
    match = re.match(r'﻿?\s*---\s*\n(.*?)\n(---|\.\.\.)\s*\n', text or '', re.S)
    if not match:
        return None
    lines = match.group(1).split('\n')
    start = next((i for i, line in enumerate(lines) if re.match(r'^authors:\s*$', line)), None)
    if start is None:
        return None
    authors, current = [], None
    for line in lines[start + 1:]:
        if re.match(r'^\S', line):  # the next top-level key
            break
        item = re.match(r'^\s*-\s*(\S.*)$', line)
        if item:
            current = {}
            authors.append(current)
            line = item.group(1)
        found = re.match(r'^\s*([\w-]+):\s*(.*)$', line)
        if current is not None and found:
            current[found.group(1).lower()] = unquote(found.group(2))
    result = []
    for author in authors:
        name = author.get('name') or ' '.join(
            author.get(key, '') for key in ('given-names', 'given', 'non-dropping-particle',
                                            'surname', 'family-names', 'family'))
        if clean_name(name):
            result.append({'name': clean_name(name), 'orcid': clean_orcid(author.get('orcid'))})
    return result or None


# --- authors in the post -----------------------------------------------------------------------

def post_authors(lines):
    """(first line, end line, [{'name', 'orcid', 'raw_orcid'}]) of the top-level `authors:`."""
    end = lines.index('---', 1)
    start = next((i for i in range(1, end) if lines[i] == 'authors:'), None)
    if start is None:
        return None, None, []
    authors, stop = [], start + 1
    while stop < end and lines[stop].startswith(' '):
        item = re.match(r'^  - name:\s*(.*)$', lines[stop])
        orcid = re.match(r'^    orcid:\s*(.*)$', lines[stop])
        if item:
            authors.append({'name': unquote(item.group(1)), 'orcid': None, 'raw_orcid': None})
        elif orcid and authors:
            authors[-1]['raw_orcid'] = orcid.group(1).strip()
            authors[-1]['orcid'] = clean_orcid(orcid.group(1))
        stop += 1
    return start, stop, authors


def author_lines(authors):
    lines = []
    for author in authors:
        name = author['name']
        if re.search(r'^[\'"&*!|>%@`{\[]|: | #', name):
            name = '"%s"' % name.replace('"', '\\"')
        lines.append('  - name: ' + name)
        if author.get('orcid'):
            lines.append('    orcid: ' + author['orcid'])
    return lines


# --- comparing ---------------------------------------------------------------------------------

def pairs(first, second):
    """[(index in first, index in second)] of the same authors: the same name, or, at the same
    place in a list of the same length, the same family name."""
    matcher = difflib.SequenceMatcher(None, [name_key(a['name']) for a in first],
                                      [name_key(a['name']) for a in second], autojunk=False)
    found = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if tag == 'equal' or family_key(first[i]['name']) == family_key(second[j]['name']):
                    found.append((i, j))
    return found


def same_first_and_family(a, b):
    words_a, words_b = name_key(a).split(), name_key(b).split()
    return bool(words_a and words_b) and words_a[0] == words_b[0] and words_a[-1] == words_b[-1]


def moved_authors(first, second):
    """The authors of `first` that are in another place relative to the others in `second`,
    for lists that only partly match. Authors are matched on the whole name, or else on a family
    name that occurs once in both lists; the authors outside the longest sequence in the same
    order in both lists are the ones that moved."""
    keys2 = [name_key(a['name']) for a in second]
    families1 = [family_key(a['name']) for a in first]
    families2 = [family_key(a['name']) for a in second]
    matched, used = [], set()
    for i, author in enumerate(first):
        key = name_key(author['name'])
        j = keys2.index(key) if key in keys2 and keys2.index(key) not in used else None
        if j is None and families1.count(families1[i]) == 1 and families2.count(families1[i]) == 1:
            j = families2.index(families1[i])
            j = None if j in used else j
        if j is not None:
            matched.append((i, j))
            used.add(j)
    # the longest increasing sequence of the places in `second`
    best = []
    for index, (_, j) in enumerate(matched):
        best.append(max((best[k] for k in range(index) if matched[k][1] < j), key=len, default=[])
                    + [index])
    keep = set(max(best, key=len, default=[]))
    return [first[i]['name'] for index, (i, _) in enumerate(matched) if index not in keep]


def differences(label, first, second, first_label='post'):
    """[(kind, text)] describing how the author list `second` (from `label`) differs from
    `first`; kind is order, name, name-variant, missing or orcid-differs."""
    found = []
    keys1 = [name_key(a['name']) for a in first]
    keys2 = [name_key(a['name']) for a in second]
    if keys1 == keys2:
        pass
    elif sorted(keys1) == sorted(keys2):
        found.append(('order', 'the order of the authors differs from the %s' % label))
    else:
        matched = pairs(first, second)
        same1, same2 = {i for i, _ in matched}, {j for _, j in matched}
        for i, j in matched:
            if keys1[i] != keys2[j]:
                kind = 'name-variant' if same_first_and_family(first[i]['name'], second[j]['name']) \
                    else 'name'
                found.append((kind, 'name in the %s: "%s", in the %s: "%s"'
                              % (first_label, first[i]['name'], label, second[j]['name'])))
        only1 = [first[i]['name'] for i in range(len(first)) if i not in same1]
        only2 = [second[j]['name'] for j in range(len(second)) if j not in same2]
        moved = moved_authors(first, second)
        if moved:
            found.append(('order', 'the authors that are in both are in another order in the %s; '
                                   'moved: %s' % (label, '; '.join(moved))))
        if only1:
            found.append(('missing', 'not in the %s: %s' % (label, '; '.join(only1))))
        if only2:
            found.append(('missing', 'only in the %s: %s' % (label, '; '.join(only2))))
    for i, j in pairs(first, second):
        a, b = first[i]['orcid'], second[j]['orcid']
        if a and b and a != b and orcid_checksum_ok(a) and orcid_checksum_ok(b):  # else: not valid
            found.append(('orcid-differs', 'ORCID of %s in the %s: %s, in the %s: %s'
                          % (first[i]['name'], first_label, a, label, b)))
    return found


def known_orcids(paths):
    """{ORCID: {family names}} of the authors in the posts."""
    known = {}
    for path in paths:
        with open(path, encoding='utf-8') as f:
            _, _, authors = post_authors(f.read().split('\n'))
        for author in authors:
            if author['orcid']:
                known.setdefault(author['orcid'], set()).add(family_key(author['name']))
    return known


def check_post(path, metadata_folder, pdf_folder, use_markdown, update_changed, dry_run=False,
               known=None):
    """(status, [(kind, message)]); status is one of: ok, updated, differs, no pdf, failed.
    The kinds are those of SECTIONS, and `info` for the changes made."""
    identifier = preprint_id(path)
    if not identifier:
        return 'no pdf', []
    pdf = os.path.join(pdf_folder, identifier + '.pdf')
    if not os.path.exists(pdf):
        return 'no pdf', [('pdf', 'no cached PDF (%s.pdf); run `make cachePdfs`' % identifier)]
    try:
        from_pdf = pdf_authors(pdf)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        return 'failed', [('pdf', 'cannot read the PDF: %s' % error)]
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    start, stop, in_post = post_authors(lines)
    messages = []
    if not from_pdf:
        return 'failed', [('pdf', 'cannot find the authors in the PDF')]

    from_markdown = None
    if use_markdown:
        metadata_path = os.path.join(metadata_folder, identifier + '.json')
        if os.path.exists(metadata_path):
            with open(metadata_path, encoding='utf-8') as f:
                metadata = json.load(f)
            try:
                from_markdown = markdown_authors(markdown_text(identifier, metadata))
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError,
                    ValueError) as error:
                messages.append(('markdown', 'cannot read paper.md: %s' % error))

    for author in in_post:
        if author['raw_orcid'] and not valid_orcid(author['raw_orcid']):
            messages.append(('orcid-invalid', 'ORCID of %s in the post is not valid: %s'
                             % (author['name'], author['raw_orcid'])))
    for label, authors in (('PDF', from_pdf), ('Markdown', from_markdown or [])):
        for author in authors:
            if author['orcid'] and not orcid_checksum_ok(author['orcid']):
                messages.append(('orcid-invalid', 'ORCID of %s in the %s is not valid: %s'
                                 % (author['name'], label, author['orcid'])))
    messages += differences('PDF', in_post, from_pdf)
    if from_markdown:
        messages.append(('compared-markdown', ''))
        messages += [('markdown', text)
                     for _, text in differences('Markdown', from_pdf, from_markdown, 'PDF')]

    # the update: missing ORCIDs, or with --update-changed the author list of the PDF
    new = [dict(a) for a in in_post]
    added = []
    pdf_pairs = dict(pairs(in_post, from_pdf))
    markdown_pairs = dict(pairs(in_post, from_markdown)) if from_markdown else {}
    for i, author in enumerate(new):
        if author['orcid']:
            continue
        candidate = from_pdf[pdf_pairs[i]]['orcid'] if i in pdf_pairs else None
        if not candidate and i in markdown_pairs:
            candidate = from_markdown[markdown_pairs[i]]['orcid']
        if not candidate or not orcid_checksum_ok(candidate):
            continue
        others = (known or {}).get(candidate, set()) - {family_key(author['name'])}
        if others and family_key(author['name']) not in (known or {}).get(candidate, set()):
            messages.append(('orcid-conflict', 'ORCID of %s not added: %s is the ORCID of another '
                             'family name in other posts (%s)'
                             % (author['name'], candidate, ', '.join(sorted(others)))))
            continue
        if any(a['orcid'] == candidate for a in new):
            messages.append(('orcid-conflict', 'ORCID of %s not added: another author of the post '
                             'has %s' % (author['name'], candidate)))
            continue
        author['orcid'] = candidate
        added.append('%s (%s)' % (author['name'], candidate))
    if update_changed and start is not None:
        by_pdf = {j: i for i, j in pairs(in_post, from_pdf)}
        same_length = bool(from_markdown) and len(from_markdown) == len(from_pdf)
        replaced = []
        for j, author in enumerate(from_pdf):
            candidates = [author['orcid'], from_markdown[j]['orcid'] if same_length else None,
                          new[by_pdf[j]]['orcid'] if j in by_pdf else None]
            orcid = next((c for c in candidates if c and orcid_checksum_ok(c)), None)
            name = from_markdown[j]['name'] if same_length else author['name']
            replaced.append({'name': name, 'orcid': orcid})
        new = replaced
    else:
        for author, old in zip(new, in_post):
            if author['orcid'] == old['orcid'] and old['raw_orcid'] and old['orcid'] and \
                    old['raw_orcid'] != old['orcid'] and not update_changed:
                author['orcid'] = old['raw_orcid']  # malformed values are only fixed on request

    status = 'differs' if any(kind != 'compared-markdown' for kind, _ in messages) else 'ok'
    if start is not None and author_lines(new) != lines[start + 1:stop]:
        lines[start + 1:stop] = author_lines(new)
        if not dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        status = 'updated'
        if added:
            messages.append(('info', 'ORCID added: ' + '; '.join(added)))
        if update_changed:
            messages.append(('info', 'authors replaced with those of the PDF'))
    return status, messages


def post_info(path):
    """(title, URL on the website, identifier, unlisted) of a post."""
    with open(path, encoding='utf-8') as f:
        header = f.read().split('\n---', 1)[0]
    title = re.search(r'(?m)^title:\s*(.*)$', header)
    title = unquote(title.group(1)).replace('\\"', '"') if title else os.path.basename(path)
    match = re.match(r'^(\d{4})-(\d\d)-(\d\d)-(.+)\.markdown$', os.path.basename(path))
    url = '%s/%s/%s/%s/%s.html' % ((SITE,) + match.groups()) if match else None
    unlisted = re.search(r'(?m)^unlisted:\s*true\s*$', header) is not None
    return title, url, preprint_id(path), unlisted


def markdown_escape(text):
    return re.sub(r'([\\`*_\[\]<>])', r'\\\1', text)


NAME_DIFFERENCE = re.compile(r'^name in the (\w+): "(.*)", in the (\w+): "(.*)"$')


def mark(kind, text):
    """Text marked as removed (`del`) or added (`ins`), coloured by the website CSS."""
    return '<%s class="name-diff">%s</%s>' % (kind, markdown_escape(html.escape(text)), kind)


def name_diff(old, new):
    """The difference between two names, as Markdown with inline HTML: words (or, for words that
    are only spelled differently, letters) that are only in `old` are marked as removed, those only
    in `new` as added."""
    words_old, words_new = old.split(), new.split()
    out = []
    matcher = difflib.SequenceMatcher(None, words_old, words_new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            out += [markdown_escape(html.escape(w)) for w in words_old[i1:i2]]
            continue
        if tag == 'replace' and i2 - i1 == j2 - j1:
            for a, b in zip(words_old[i1:i2], words_new[j1:j2]):
                letters = difflib.SequenceMatcher(None, a, b, autojunk=False)
                if letters.ratio() < 0.5:  # another word: show it as a whole
                    out.append(mark('del', a) + mark('ins', b))
                    continue
                word = ''
                for t, a1, a2, b1, b2 in letters.get_opcodes():
                    if t == 'equal':
                        word += markdown_escape(html.escape(a[a1:a2]))
                    else:
                        word += (mark('del', a[a1:a2]) if a2 > a1 else '') + \
                            (mark('ins', b[b1:b2]) if b2 > b1 else '')
                out.append(word)
            continue
        if i2 > i1:
            out.append(mark('del', ' '.join(words_old[i1:i2])))
        if j2 > j1:
            out.append(mark('ins', ' '.join(words_new[j1:j2])))
    return ' '.join(out)


def report_line(text):
    """A finding as a Markdown list item; name differences also get the marked difference."""
    text = text.replace(' the post', ' the index')
    match = NAME_DIFFERENCE.match(text)
    if not match:
        return '  * ' + markdown_escape(text)
    first, old, second, new = match.groups()
    first = 'index' if first == 'post' else first
    return '  * %s (%s: "%s", %s: "%s")' % (name_diff(old, new), first, markdown_escape(old),
                                           second, markdown_escape(new))


def report(results, today):
    """The text of feedback/biohackrxiv.md: the findings per kind, per preprint."""
    listed = [(path, findings) for path, findings in results if not post_info(path)[3]]
    out = ['# Author metadata of BioHackrXiv preprints: possible problems', '',
           'Generated on %s by `make checkAuthors` in the [BioHackrXiv index](%s), for the '
           'BioHackrXiv team. For each of the %d preprints in the index, the authors on the page of '
           'the preprint in the index are compared with the first page of the PDF of its latest '
           'version, and, for %d preprints, with the `authors:` in the YAML header of its Markdown '
           'source (paper.md). Names are compared without case, accents and punctuation. In the '
           'name differences, what is only in the index (or the PDF, compared with the Markdown) is '
           'shown as <del class="name-diff">removed</del>, and what the PDF (or the Markdown) has '
           'instead as <ins class="name-diff">added</ins>.'
           % (today, SITE, len(listed),
              sum(1 for _, f in listed if ('compared-markdown', '') in f)), '']
    for key, heading, explanation in SECTIONS:
        entries = [(path, [t for k, t in findings if k == key]) for path, findings in listed]
        entries = [(path, texts) for path, texts in entries if texts]
        out += ['## %s' % heading, '']
        if explanation:
            out += [explanation, '']
        if not entries:
            out += ['None found.', '']
            continue
        out += ['%d preprints.' % len(entries), '']
        for path, texts in entries:
            title, url, identifier, _ = post_info(path)
            out.append('* [%s](%s) (%s)' % (markdown_escape(title), url, identifier))
            out += [report_line(text) for text in texts]
        out.append('')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--update-changed', action='store_true',
                        help='replace the authors of the post with those of the PDF (by default, '
                             'only missing ORCIDs are added and the differences are reported)')
    parser.add_argument('--dry-run', action='store_true', help='report only, do not change posts')
    parser.add_argument('--no-markdown', action='store_true',
                        help='do not compare with the Markdown source (paper.md)')
    parser.add_argument('--metadata', default=METADATA,
                        help='folder with the metadata JSON files (default: cache/metadata)')
    parser.add_argument('--pdfs', default=PDFS, help='folder with the PDFs (default: cache/pdfs)')
    parser.add_argument('--jobs', type=int, default=4, help='parallel fetches (default: 4)')
    parser.add_argument('--output', default=OUTPUT,
                        help='the report (default: feedback/biohackrxiv.md)')
    parser.add_argument('ids', nargs='*', help='only these identifiers (default: all)')
    args = parser.parse_args()

    paths = sorted(glob.glob(POSTS))
    if args.ids:
        wanted = {i.lower() for i in args.ids}
        paths = [p for p in paths if (preprint_id(p) or '').lower() in wanted]
    known = known_orcids(glob.glob(POSTS))
    counts = {'ok': 0, 'updated': 0, 'differs': 0, 'no pdf': 0, 'failed': 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = pool.map(lambda p: check_post(p, args.metadata, args.pdfs, not args.no_markdown,
                                                args.update_changed, args.dry_run, known),
                           paths)
        collected = []
        for path, (status, messages) in zip(paths, results):
            counts[status] += 1
            collected.append((path, messages))
            for kind, message in messages:
                if kind != 'compared-markdown':
                    print('%s: %s' % (os.path.basename(path), message))
    print('Posts: %(ok)d as the PDF, %(updated)d updated, %(differs)d with differences, '
          '%(no pdf)d without PDF, %(failed)d failed' % counts)
    if args.ids:
        print('Not written: %s (only for a check of all posts)' % os.path.relpath(args.output))
    else:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report(collected, datetime.date.today().isoformat()) + '\n')
        print('Written: %s' % os.path.relpath(args.output))
    return 1 if counts['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
