# BioHackrXiv Preprints Index

This repository keeps an overview of published preprints of current, registered, and past
BioHackathon events.

## Scripts

### OpenAlex IDs

`scripts/openalex.py` adds the OpenAlex work ID of each preprint to the front matter of the
posts in `_posts/`, as an `openalex:` line (for example `openalex: W7222907300`).

It asks the [OpenAlex API](https://api.openalex.org/) for all works that have a location in the
BioHackrXiv source (`S4306402587`), builds a table of DOI and work ID, and matches the table with the
`doi:` of each post (case-insensitive). Posts that already have an `openalex:` line, or whose DOI is
not in OpenAlex, are left unchanged.

Run it with:

```shell
make updateOpenAlex
```

The script uses only the Python 3 standard library. OpenAlex works without a key, but on a small
shared daily budget; set the optional `OPENALEX_KEY` environment variable to use your own key:

```shell
OPENALEX_KEY=... make updateOpenAlex
```

### Europe PMC identifiers

`scripts/europepmc.py` adds or corrects the `europepmc:` line (for example `europepmc: PPR1343807`)
in the front matter of the posts in `_posts/`.

It asks the [Europe PMC search API](https://europepmc.org/RestfulWebService) for all records with the
publisher `BioHackrXiv` (`PUBLISHER:"BioHackrXiv"`), builds a table of DOI and Europe PMC ID, and
matches the table with the `doi:` of each post (case-insensitive). A post without a `europepmc:` line
gets one. A post with a different ID is not changed by default: it is reported on the standard
output, so the difference can be checked first. Posts that already match, or whose DOI is not in
Europe PMC, are left unchanged.

```shell
make updateEuropePMC
```

After checking the reported posts, add `--update-changed` to also overwrite the differing IDs:

```shell
make updateEuropePMC ARGS=--update-changed
```

The script uses only the Python 3 standard library and needs no key.

### Wikidata IDs

`scripts/wikidata.py` adds the `wikidata:` line (the item ID, for example `wikidata: Q137242577`)
to the front matter of the posts in `_posts/`.

It asks the [Wikidata SPARQL endpoint](https://query.wikidata.org/) for all items with a DOI
(P356) that starts with the BioHackrXiv prefix `10.37044/`, builds a table of DOI and QID, and
matches the table with the `doi:` of each post (case-insensitive, as Wikidata keeps DOIs in upper
case). If several items have the same DOI, the lowest QID is used. As for Europe PMC, a post without
a `wikidata:` line gets one, and a post with a different QID is only reported on the standard output,
unless `--update-changed` is given.

```shell
make updateWikidata
make updateWikidata ARGS=--update-changed
```

The script uses only the Python 3 standard library and needs no key. The query service limits
requests (it may answer with HTTP 429 when it is called more than about once a minute), so wait a
minute before running the script again.

### QuickStatements for Wikidata

`scripts/createQuickstatements.py` creates [QuickStatements](https://quickstatements.toolforge.org/)
(version 2, CSV) that add the identifiers from the posts to Wikidata, for the posts that have a
`wikidata:` line:

* `openalex:` as OpenAlex ID ([P10283](https://www.wikidata.org/wiki/Property:P10283)), and
* `europepmc:`, without the `PPR` prefix, as Europe PMC preprint ID
  ([P13529](https://www.wikidata.org/wiki/Property:P13529)).

* "published in" ([P1433](https://www.wikidata.org/wiki/Property:P1433)) BioHackrXiv, for items that
  do not have that value yet (other P1433 values, such as a meeting, are left alone).

It asks the live Wikidata API (`wbgetentities`) for the statements the items already have, and only
creates a statement where the item has none for that property. Each new statement has a reference with
"reference URL" (S854) the page of the work on index.biohackrxiv.org, "retrieved" (S813) the date of
today, and "stated in" (S248) BioHackrXiv ([Q115450084](https://www.wikidata.org/wiki/Q115450084)).
Where an item already has a different value, nothing is created, and the difference is reported on the
standard output. Case is ignored in the comparison, so `w3133411698` in Wikidata counts as
`W3133411698`.

```shell
make createQuickstatements
make createQuickstatements ARGS="--output other.csv"
```

The CSV (default `quickstatements.csv`) has one row for each statement; load it with "Import
commands" in QuickStatements, choosing the CSV format. Run `make updateOpenAlex`,
`make updateEuropePMC` and `make updateWikidata` first, so the posts are up to date. The live API is
used, not the SPARQL endpoint, because that one can be behind on recent edits, which would make a
statement that was just added look missing.

### PDF cache

`scripts/cachePdfs.py` downloads the PDF of each preprint into a local cache, `cache/pdfs/`, for
example for text mining or checking the content of the preprints. The cache is listed in
`.gitignore` and is not part of the git repository.

The OSF identifier is taken from the `doi:` of each post (for example `c8jw6_v1` from
`10.37044/osf.io/c8jw6_v1`). The script asks the [OSF API](https://developer.osf.io/) for the primary
file of that preprint, which is the PDF offered on the preprint page, and saves it as
`cache/pdfs/<identifier>.pdf`. A download that is not a PDF is not stored, and is reported as failed.

```shell
make cachePdfs
make cachePdfs ARGS="--delay 2"
```

PDFs that are already in the cache are skipped, so the command can be run again to fetch only the
new preprints, or to retry the failed ones; delete a file from the cache to download it again. The
script pauses one second between preprints (`--delay` changes that) and retries when the server
answers with HTTP 429 or a server error. It prints a summary at the end and exits with a non-zero
status when a download failed. Use `--cache` to store the PDFs in another folder.

The script uses only the Python 3 standard library and needs no key. The first run downloads all
preprints and takes a few minutes.

### PDF metadata and Git repositories

`scripts/extractPdfMetadata.py` reads the front page of each cached PDF (see the PDF cache above) and
writes the metadata it finds to `cache/metadata/<identifier>.json`. Like the PDFs, this cache is not
part of the git repository. For now it holds the links of the "BioHackathon series:" section in the
left column of the front page: the first link is the event, the second link is usually the project
or its GitHub repository.

Those links are annotations in the PDF, so a text conversion does not contain them. The script
therefore runs `pdftohtml -xml` (from [Poppler](https://poppler.freedesktop.org/); install the
`poppler-utils` package) on the first page. That gives every text fragment with its position and its
link, so the script can pick the links in the left column between "BioHackathon series:" and the
"Submitted:" or "License:" heading, and ignore the license and BioHackrXiv.org links. (Pandoc cannot
read PDF, and converting to HTML or Markdown first would lose the column positions that separate the
sidebar from the paper text.) Each JSON file has the `links` (text and URL) and the `repository`: the
second link as an object with its `url`, or `null` when the PDF has no second link.

```shell
make cachePdfs
make extractPdfMetadata
```

`scripts/git.py` then adds the `git:` line (for example
`git: https://github.com/708san/biohackathon-2026-zebraseek-paper`) to the front matter of the
posts in `_posts/`. It matches the OSF identifier from the `doi:` of a post with the JSON files. As
for Europe PMC and Wikidata, a post without a `git:` line gets one, and a post with a different
URL is only reported on the standard output, unless `--update-changed` is given.

```shell
make updateGit
make updateGit ARGS=--update-changed
```

A second link is only used when it is a GitHub or GitLab URL (`https://github.com/<owner>/<repo>`
or `https://gitlab.com/<group>/<project>`, with optional subfolder). A trailing `/` or `.git` is removed, and `http://` and `www.` are changed to
`https://`. Posts whose second link is something else (Discord, an unfilled template
placeholder, or only an organization) are listed as skipped, and posts whose PDF has no second link
are left unchanged. The script uses only the Python 3 standard library.

### Markdown source of the preprints

`scripts/findMarkdown.py` looks in the repository of each preprint (the `repository` in
`cache/metadata/<identifier>.json`) for the Markdown source of the paper. It makes a shallow clone
without the file contents (this needs `git`, but no API key and has no API rate limit), and lists the
files named `paper.md`. The file can be in the root folder or in a subfolder, and a repository can
have more than one. If the repository URL points to a folder (`.../tree/<branch>/<folder>`), that
folder is searched first.

Each candidate is confirmed with the YAML header of the file, which must match what is known
already:

* `title` is the title of the post in `_posts/` (matched on the DOI), and
* `biohackathon_url` is the first link of the PDF, the event.

URLs are compared without the scheme, `www.` and trailing slashes, and titles without differences
in case, punctuation and spacing. The result is added to the JSON file as `markdown`:

```json
"markdown": {
  "path": "paper/paper.md",
  "url": "https://github.com/<owner>/<repo>/blob/<commit>/paper/paper.md",
  "commit": "<commit>",
  "alternatives": ["other/paper.md"]
}
```

`alternatives` is only present when more than one `paper.md` matches; the file closest to the root
folder is the main one. `markdown` is `null` when the repository was searched but no `paper.md`
matches (for example because the file has no `biohackathon_url`), and is left out when the
repository could not be cloned, so a next run tries again. Preprints that already have `markdown`
are skipped, unless `--force` is given. Running `make extractPdfMetadata` again keeps the value.

```shell
make findMarkdown
make findMarkdown ARGS="--force"
make findMarkdown ARGS="24jst"
```

Like the other scripts, it uses only the Python 3 standard library.

### Figures of the preprints

`scripts/findFigures.py` reads the `paper.md` found by `findMarkdown.py`, at the recorded commit, and
adds a list `figures` to the `markdown` object in `cache/metadata/<identifier>.json`, in the order
of the paper. It finds the Markdown images (`![caption](path){#fig:label}`), also when the caption
spans lines or contains brackets, and ignores images in code blocks and comments.

```json
"figures": [{
  "source": "./figures/overview.png",
  "path": "paper/figures/overview.png",
  "url": "https://github.com/<owner>/<repo>/blob/<commit>/paper/figures/overview.png",
  "caption": "Overview of the workflow",
  "label": "fig:overview"
}]
```

* `source` is the path as written in `paper.md`; `path` is the path of the image in the repository
  (resolved from the folder of `paper.md`, or from the root of the repository for a leading `/`)
  and `url` its address at the commit. If the image is not in the repository, `path` is `null`, and
  either `remote` is `true` (the source is a web address, which is then the `url`) or `missing` is
  `true` (the file does not exist at this commit).
* `caption` is the text between the brackets, as Markdown, with white space collapsed. If that is
  empty or generic (`Figure 1`, `image`, the file name), the paragraph right after the image that
  starts with `Figure N:` is used instead, and `caption_source` is `text`.
* `label` is the Pandoc identifier or the LaTeX `\label{...}` in the caption, if there is one.

LaTeX `figure` environments (often used for tables) and HTML `<img>` tags are not recognized. A
preprint without images gets an empty list. As for `markdown`, preprints that already have `figures`
are skipped unless `--force` is given, and a repository that cannot be fetched is retried by the next
run. Running `make findMarkdown` again keeps the figures when the file and commit are the same.

```shell
make findFigures
make findFigures ARGS="--force"
make findFigures ARGS="24jst"
```

### Checking the figures against the PDF

The Markdown in the git repository is not necessarily the version that was submitted to BioHackrXiv,
and the PDF is leading. `scripts/checkPdfFigures.py` compares the cached PDF (see the PDF cache above)
with the `markdown.figures` of `cache/metadata/<identifier>.json` (see above), using Poppler's
`pdftotext` and `pdfimages`:

* Each figure gets `in_pdf`: `true` when its caption is in the text of the PDF, `false` when not, and
  `null` when the caption is too short or generic to tell (`Figure 1`). Captions are compared without
  Markdown, case, punctuation, hyphenation and line breaks, and only up to the first citation or
  formula, because the PDF shows those differently.
* The title of the post must be on the first page of the PDF (`title_in_pdf`).
* `images` is the number of different raster images in the PDF, without the BioHackrXiv logo of every
  page. Figures drawn as vector graphics are not counted, so fewer images than figures is normal; more
  images than figures means that the Markdown misses some.

The summary is added to the `markdown` object, with a `status` that is `match` (all captions that can
be checked are found, and the title is on the first page), `partial` (at least half of the captions)
or `mismatch`:

```json
"pdf": {"status": "match", "title_in_pdf": true, "images": 3, "captions_checked": 3, "captions_found": 3}
```

The script lists the preprints that are not a `match`, or that have more images in the PDF than
figures in the Markdown, so the Markdown (and therefore the figure metadata) can be checked by hand.
With `--verbose` it also lists the figures whose caption is not in the PDF. The check is quick and
always runs again. `make findFigures` runs the same check right after it has found the figures of a
preprint, and reports the preprints that do not match on the standard output; `make checkPdfFigures`
repeats the check for all preprints without fetching anything. `make findMarkdown` keeps the `figures` and
`pdf` values when the file and commit are the same.

```shell
make checkPdfFigures
make checkPdfFigures ARGS=--verbose
make checkPdfFigures ARGS="24jst"
```

A caption that is only part of the image itself is not in the text of the PDF, so a `false` points to
a difference to look at, not to a proof of one.

### Figures on the preprint pages

`scripts/exportFigures.py` copies the figures of the preprints that match their PDF to
`assets/images/figures/<identifier>/` (one folder per preprint) and writes the list with the captions
to `_data/figures.json`, which `_layouts/post.html` uses to show a "Figures" section below the text of
the preprint. Unlike `cache/`, both are part of the git repository.

A figure is exported when the `markdown.pdf.status` of its preprint is `match` and the caption of the
figure itself is found in the PDF (`in_pdf` is `true`); see the check above. The images are taken from
the git repository at the commit in the metadata, or downloaded when the Markdown uses a web address.
Only PNG, JPEG, GIF, WebP and SVG files are used, as browsers cannot show PDF or TIFF images; the
others are listed on the standard output. The captions are the Markdown captions, without citations
and HTML.

```json
{"kxqb7_v1": {"commit": "<commit>",
              "figures": [{"file": "assets/images/figures/kxqb7_v1/overview.png",
                           "caption": "Overview of the workflow", "label": "fig:overview"}]}}
```

Preprints that are no longer eligible are removed from the list and their folder is deleted. A
preprint is not fetched again when its commit and files have not changed, unless `--force` is given.

```shell
make findFigures        # and thereby the check against the PDF
make exportFigures
make exportFigures ARGS=--force
```

