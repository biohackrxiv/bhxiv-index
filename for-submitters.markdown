---
layout: page
title: For Paper Submitters
permalink: /for-submitters/
---

## Write and Submit a BioHackrXiv Preprint

BioHackrXiv preprints are written in Markdown and converted to PDF. Follow the steps below to write, preview, and submit your paper.

### Prerequisites

- Your event must be registered with BioHackrXiv. Check the [Meetings page]({{ '/meetings' | relative_url }}) to see if your event is listed. If not, ask your event organizer to [register it]({{ '/for-organizers' | relative_url }}).

### Step 1: Create your paper repository

1. Go to the [publication-template](https://github.com/biohackrxiv/publication-template) on GitHub
2. Click **"Use this template"** → **"Create a new repository"**
3. Name your repository (e.g., `biohackeu25-paper-projectname`)
4. change the CC0 license to CC-BY 4.0 International (for example)

### Step 2: Write your paper

Edit `paper/paper.md` in your repository. The template includes detailed comments explaining each section.

#### Required YAML metadata

Your paper must include the following fields in the YAML front matter:

```yaml
---
title: "Your Paper Title"
title_short: "Short Title \\emph{et al.}"
tags:
  - tag1
  - tag2
authors:
  - name: First Author
    affiliation: 1
    orcid: 0000-0000-0000-0000
  - name: Second Author
    affiliation: 2
affiliations:
  - name: First Affiliation
    index: 1
  - name: Second Affiliation
    index: 2
date: 1 January 2026
cito-bibliography: paper.bib
event: BH25EU
biohackathon_name: "BioHackathon Europe 2025"
biohackathon_url: "https://biohackathon-europe.org/"
biohackathon_location: "Berlin, Germany, 2025"
group: "Project 1"
git_url: https://github.com/yourusername/your-paper-repo
authors_short: "First Author \\emph{et al.}"
---
```

**Tip:** Find the correct values for `event`, `biohackathon_name`, `biohackathon_url`, and `biohackathon_location` on your event's page at the [Meetings page]({{ '/meetings' | relative_url }}). Each event page shows the exact YAML snippet to use.

#### References

Add your references to `paper/paper.bib` in BibTeX format. Cite them in your text using `[@citationkey]`.

BioHackrXiv supports [CiTO](http://www.sparontologies.net/ontologies/cito) (Citation Typing Ontology) annotations. You can specify the type of citation:

```markdown
[@usesMethodIn:citationkey]
[@extends:citationkey]
[@citesAsAuthority:citationkey]
```

#### Optional metadata

- **ORCID**: Add `orcid` field for each author
- **ROR**: Add `ror` field for each affiliation
- **CRediT roles**: Add `role` field for each author (e.g., "Conceptualization, Writing – original draft")

### Step 3: Preview your PDF

You have two options:

#### Option A: GitHub Actions (recommended)

Push your changes to the `main` branch of your repository. GitHub Actions will automatically build the PDF.

1. Go to the **Actions** tab of your repository
2. Click the latest workflow run
3. Download the PDF from the **Artifacts** section

#### Option B: Preview server

Visit [preview.biohackrxiv.org](https://preview.biohackrxiv.org/) and either:
- Paste your repository URL, or
- Upload a ZIP file containing your `paper.md` and `paper.bib`

### Step 4: Submit to BioHackrXiv

Once your PDF is ready, submit it through the [BioHackrXiv submission portal on OSF](https://osf.io/preprints/biohackrxiv/submit).

### Questions?

- Browse [existing publications](https://index.biohackrxiv.org/) for examples
- Contact us at [biohackrxiv@googlegroups.com](mailto:biohackrxiv@googlegroups.com)
- Report issues on the [publication-template repository](https://github.com/biohackrxiv/publication-template/issues)
