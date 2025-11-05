# Documentation Meeting YAML metadata

This document described the YAML model for metadata for meeting pages.

## Required information

The minimal information to include in the YAML are the fields
`layout:`, `tag:`, `title:`, `location:`, and `website:`.

For example, for 

```yaml
---
layout: tagpage
tag: BH25JP
title: "DBCLS BioHackathon 2025"
website: https://2025.biohackathon.org/
location: Mie, Japan
---
```

## Recommended information

To help the reader, the following information can be provided too:
`contact_url:`, `image:`, `startDate:`, and `endDate:`

For example, for 

```yaml
---
layout: tagpage
tag: BioHackEU25
title: "BioHackathon Europe"
location: "Berlin, Germany, 2025"
website: "https://biohackathon-europe.org/"
contact_url: "https://biohackathon-europe.org/about/biohackrxiv/"
---
```


## Optional information

Optionally, if there is a Wikidata for the meeting (thus it was deemed notable),
the `wikidata:` field can be added to give the Q-identifier.
