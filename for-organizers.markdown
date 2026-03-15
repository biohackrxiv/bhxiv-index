---
layout: page
title: For Event Organizers
permalink: /for-organizers/
---

## Register Your Event with BioHackrXiv

BioHackrXiv publishes preprints from hackathons, codefests, and similar collaborative coding events in the life sciences. To allow participants to submit reports from your event, you need to register it here first.

### What events are eligible?

Your event should be a hands-on, collaborative working meeting such as a hackathon, codefest, sprint, or symposium with coding/hacking components in the biomedical or life sciences domain.

### How to register

1. **Open an issue** on the [bhxiv-index repository](https://github.com/biohackrxiv/bhxiv-index/issues/new) with the following information:

   - **Event name** (e.g., "BioHackathon Europe 2025")
   - **Location** (city, country)
   - **Start and end dates** (YYYY-MM-DD)
   - **Event website URL**
   - **Hashtag / tag code** (a short code like `BH25EU` — if you don't have one, we will assign one)
   - **Event logo or banner image URL** (optional)

2. A BioHackrXiv maintainer will review your request and create the event page.

3. Once approved, your event will appear on the [Meetings page]({{ '/meetings' | relative_url }}) and participants can reference it in their paper submissions.

### What happens after registration?

Once your event is listed, the event page will display:

- Event metadata (location, dates, website)
- Links to any preprints submitted from your event
- YAML metadata snippet that paper authors should use in their `paper.md`

For example, your event page will show authors which values to use for `biohackathon_name`, `biohackathon_url`, and `biohackathon_location` in their paper metadata.

### Questions?

Contact us at [biohackrxiv@googlegroups.com](mailto:biohackrxiv@googlegroups.com) or open an issue on the [bhxiv-index repository](https://github.com/biohackrxiv/bhxiv-index/issues).
