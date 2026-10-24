#!/usr/bin/env python3
"""Add or update `image:` lines in the posts in _posts/ with the most colorful figure.

Only preprints with figures that match the PDF get an image: the figures in _data/figures.json
(see exportFigures.py). From these the figure with the most color is picked, as the home page shows
the `image:` of a post next to its title. Color is measured with the colorfulness of Hasler and
Suesstrunk (2003) on a small version of the image made with ImageMagick (`magick`), so grey
diagrams and screenshots with a white background get a low score. Images less than 400 pixels wide
are only used when there is no larger one, and SVG images are not considered.

The value is the path of the original image, for example
`image: /assets/images/figures/kxqb7_v1/overview.png`. A post without an `image:` line gets one, and
a post with a different `image:` is only reported on the standard output, unless --update-changed
is given.

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
import math
import os
import subprocess
import sys

from git import POSTS, osf_id

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
DATA = os.path.join(ROOT, '_data', 'figures.json')
MIN_WIDTH = 400
SAMPLE = 64  # the image is scaled to SAMPLE x SAMPLE pixels to measure the color


def run_magick(*args):
    return subprocess.run(['magick'] + list(args), check=True, capture_output=True,
                          timeout=60).stdout


def width(path):
    return int(run_magick(path + '[0]', '-format', '%w', 'info:'))


def colorfulness(path):
    """Colorfulness (Hasler and Suesstrunk) of an image: 0 for grey, about 100 for vivid."""
    data = run_magick(path + '[0]', '-background', 'white', '-alpha', 'remove', '-resize',
                      '%dx%d!' % (SAMPLE, SAMPLE), '-depth', '8', 'rgb:-')
    rg, yb = [], []
    for i in range(0, len(data) - 2, 3):
        r, g, b = data[i], data[i + 1], data[i + 2]
        rg.append(r - g)
        yb.append(0.5 * (r + g) - b)

    def mean_std(values):
        mean = sum(values) / len(values)
        return mean, math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

    (mean_rg, std_rg), (mean_yb, std_yb) = mean_std(rg), mean_std(yb)
    return math.hypot(std_rg, std_yb) + 0.3 * math.hypot(mean_rg, mean_yb)


def pick(figures):
    """Return the file of the most colorful figure, or None."""
    scored = []
    for figure in figures:
        path = os.path.join(ROOT, figure['file'])
        if path.lower().endswith('.svg') or not os.path.exists(path):
            continue
        try:
            scored.append((width(path) >= MIN_WIDTH, colorfulness(path), figure['file']))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
            continue
    if not scored:
        return None
    return max(scored, key=lambda s: (s[0], s[1], s[2]))[2]


def update_image(path, value, update_changed=False):
    """Add or correct the `image:` line of a post. Return 'added', 'changed' or None."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if lines[0] != '---':
        return None
    end = lines.index('---', 1)
    new = 'image: ' + value
    existing = [i for i in range(1, end) if lines[i].startswith('image:')]
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
                        help='also overwrite image: lines that differ from the pick '
                             '(by default they are only reported)')
    args = parser.parse_args()

    if not os.path.exists(DATA):
        sys.exit('No %s; run `make exportFigures` first.' % os.path.relpath(DATA, ROOT))
    with open(DATA, encoding='utf-8') as f:
        exported = json.load(f)
    counts = {'added': 0, 'changed': 0, 'unchanged': 0, 'no pick': 0}
    for path in sorted(glob.glob(POSTS)):
        identifier = osf_id(path)
        entry = exported.get((identifier or '').lower())
        if not entry:
            continue
        chosen = pick(entry['figures'])
        if not chosen:
            counts['no pick'] += 1
            continue
        status = update_image(path, '/' + chosen, args.update_changed)
        if status == 'changed' and not args.update_changed:
            print('%s: image differs from the most colorful figure (%s)'
                  % (os.path.basename(path), chosen))
        counts[status or 'unchanged'] += 1
    print('Posts with a new image line: %(added)d' % counts)
    print('Posts with a changed image: %(changed)d (use --update-changed to update)' % counts)
    print('Posts unchanged: %(unchanged)d, without a usable image: %(no pick)d' % counts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
