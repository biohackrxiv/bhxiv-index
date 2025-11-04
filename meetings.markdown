---
layout: page
title: Meetings
permalink: /meetings/
---

<div class="tag-cloud">
{% for tag in site.tags %}
  {% assign tag_name = tag[0] %}
  <!-- {{ tag_name }} -> {{ site.data.meetings[tag_name].year }} -->
  {% if tag_name contains "doi:" %}
  {% elsif tag_name contains "inchikey:" %}
  {% elsif tag_name contains "cito:" %}
  {% else %}
    <span style="font-size: {{ tag | last | size | times: 250 | divided_by: site.tags.size | plus: 100  }}%">
      <a href="{{ '/tag/' | append: tag_name | relative_url }}">{{ tag | first }}</a>
    </span>
  {% endif %}
{% endfor %}
</div>

## Meetings
<div>
<!-- {{ site.data.meetings }} -->
{% assign grouped_by_year = site.data.meetings.meetings | group_by_exp: "meeting", "meeting.year" %}
<!-- {{ grouped_by_year }} -->
{% assign grouped_by_year_sorted = grouped_by_year | sort: "name" | reverse %}
{% for year in grouped_by_year_sorted %}
<!-- {{ year }} -->
<h3 class="post-title">{{ year.name }}</h3>
<ul>
{% for meeting in year.items %}
<!-- {{ meeting }} -->
<li><a href="{{ '/tag/' | append: meeting.tag | relative_url }}">{{ meeting.title }}</a></li>
{% endfor %}
</ul>
{% endfor %}



