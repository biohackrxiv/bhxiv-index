---
layout: page
title: Archive
permalink: /archive/
---

{% assign grouped_by_year = site.posts | group_by_exp: "post", "post.date | date: '%Y'" %}
{% for year in grouped_by_year %}
### {{ year.name }}
  {% assign grouped_by_month = year.items | group_by_exp: "post", "post.date | date: '%B'" %}
  {% for month in grouped_by_month %}
#### {{ month.name }}
{% for post in month.items %}* [{{ post.title }}]({{ post.url | prepend: site.baseurl | prepend: site.url }})
{% endfor %}
  {% endfor %}
{% endfor %}
