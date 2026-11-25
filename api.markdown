---
layout: page
title: API
permalink: /api/
---

The metadata of all preprints in this index is available as static JSON files. They are
regenerated each time the website is updated. There is no rate limit and no API key.

## List of preprints

[`/api/v1/listArticles.json`](/api/v1/listArticles.json) lists all preprints, oldest first:

```json
{
  "api_version": "1",
  "count": 175,
  "articles": [
    {
      "id": "8qdse",
      "doi": "10.37044/osf.io/8qdse",
      "title": "Data validation and schema interoperability",
      "date": "2020-04-07",
      "url": "https://index.biohackrxiv.org/api/v1/articles/8qdse.json"
    }
  ]
}
```

* `id`: the OSF identifier of the preprint, without the version suffix (`_v1`, `_v2`, ...)
* `doi`: the DOI of the version shown on this website (the latest version)
* `date`: the date of the earliest version (YYYY-MM-DD)
* `url`: the address of the full metadata of the preprint

## One preprint

`/api/v1/articles/<id>.json` gives all metadata of one preprint, for example
[`/api/v1/articles/8qdse.json`](/api/v1/articles/8qdse.json). The address does not change when a
new version of the preprint is posted. Besides the fields of the list, it has:

* `html_url`, `doi_url` and `pdf_url`: the page on this website, the DOI as a link, and the PDF
* `description`: a short summary of the abstract
* `authors`: a list with the `name` and, when known, the `orcid` of each author
* `tags`: the tags of the preprint, such as the BioHackathon
* `relations`: works that the preprint cites, each with a `doi` and a `type` (`cites`, or a
  [CiTO](https://sparontologies.github.io/cito/current/cito.html) property such as `usesMethodIn`)
* `molecules`: InChIKeys of the molecules the preprint is about
* `identifiers`: the `europepmc`, `openalex` and `wikidata` identifiers (`null` when unknown)
* `git`: the source repository of the preprint
* `image` and `figures`: the image shown on the home page and the figures with their captions

Fields without a value are `null` or an empty list.
