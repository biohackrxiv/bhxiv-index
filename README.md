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
