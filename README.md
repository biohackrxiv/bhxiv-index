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
