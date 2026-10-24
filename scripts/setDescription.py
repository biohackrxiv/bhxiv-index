#!/usr/bin/env python3
"""Add or update `description:` lines (a short summary for search results) in the posts in _posts/.

The body of a post is the abstract of the preprint, which is much longer than the 120 to 160
characters that search engines and social media show. The meta description, `og:description` and
`twitter:description` (jekyll-seo-tag) use the `description:` of the post, so this script writes
the first sentences of the abstract, cut at a sentence end when that gives at least 70 characters
and otherwise at a word with an ellipsis, in at most 160 characters. Markdown, HTML and Liquid are
removed from the text first. The abstract itself, and the JSON-LD description of the article,
which uses the whole abstract, are not changed.

A post without a `description:` line gets one, and a post with a different `description:` is only
reported on the standard output, unless --update-changed is given. A `description:` that was written
by hand would therefore be kept; use --update-changed to replace them.

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

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, '..', '_posts', '*.markdown')
MAX_LENGTH = 160
MIN_SENTENCE = 70
ABBREVIATIONS = ('e.g.', 'i.e.', 'et al.', 'vs.', 'cf.', 'approx.', 'fig.', 'no.', 'dr.')


def plain_text(markdown):
    """The text of the first paragraph of a post, without Markdown, HTML and Liquid."""
    for paragraph in re.split(r'\n\s*\n', markdown.strip()):
        paragraph = paragraph.strip()
        if not paragraph or paragraph[0] in '#!<{|>' or paragraph.startswith(('```', '---')):
            continue
        text = re.sub(r'{%.*?%}|{{.*?}}', '', paragraph, flags=re.S)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)  # links and images
        text = re.sub(r'[*_`]+', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            return text
    return ''


def shorten(text, maximum=MAX_LENGTH):
    """At most `maximum` characters: whole sentences if possible, otherwise whole words and ..."""
    if len(text) <= maximum:
        return text
    best = 0
    for match in re.finditer(r'[.!?](?=\s+[A-Z0-9])', text[:maximum + 1]):
        end = match.end()
        if end <= maximum and not text[:end].lower().endswith(ABBREVIATIONS):
            best = end
    if best >= MIN_SENTENCE:
        return text[:best]
    cut = text[:maximum - 1].rsplit(' ', 1)[0]
    if cut.count('(') > cut.count(')'):  # do not stop inside a parenthesis
        cut = cut[:cut.rindex('(')]
    cut = cut.rstrip(' ,;:-')
    return cut + '\u2026'


def update_description(path, update_changed=False):
    """Add or correct the `description:` line of a post. Return 'added', 'changed' or None."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return None
    end = lines.index('---', 1)
    if not any(line.startswith('doi:') for line in lines[1:end]):
        return None
    description = shorten(plain_text('\n'.join(lines[end + 1:])))
    if not description:
        return None
    new = 'description: ' + json.dumps(description, ensure_ascii=False)
    existing = [i for i in range(1, end) if lines[i].startswith('description:')]
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
    parser.add_argument('--update-changed', action='store_true',
                        help='also overwrite description: lines that differ from the abstract '
                             '(by default they are only reported)')
    args = parser.parse_args()

    counts = {'added': 0, 'changed': 0, 'unchanged': 0}
    for path in sorted(glob.glob(POSTS)):
        status = update_description(path, args.update_changed)
        if status == 'changed' and not args.update_changed:
            print('%s: description differs from the start of the abstract' % os.path.basename(path))
        counts[status or 'unchanged'] += 1
    print('Posts with a new description line: %(added)d' % counts)
    print('Posts with a changed description: %(changed)d (use --update-changed to update)' % counts)
    print('Posts unchanged: %(unchanged)d' % counts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
