# Sets the "last modified" date of a preprint to the publication date of its most recent version.
#
# Posts with a `versions:` list keep `date:` (the first version, and part of the URL). This
# generator sets `modified_date` (used by the post layout, the JSON-LD and the feeds) and
# `last_modified_at` (used by jekyll-seo-tag and jekyll-sitemap) to the latest `date` in
# `versions:`, when that is later than `date:`. Dates given in the front matter are kept.
module BioHackrXivVersionDates
  class Generator < Jekyll::Generator
    safe true
    priority :high

    def generate(site)
      site.posts.docs.each do |post|
        versions = post.data['versions']
        next unless versions.is_a?(Array)

        latest = versions.map { |version| to_time(version['date']) if version.is_a?(Hash) }.compact.max
        next unless latest && latest.to_date > post.date.to_date

        post.data['modified_date'] ||= latest
        post.data['last_modified_at'] ||= latest
      end
    end

    private

    def to_time(value)
      case value
      when Time then value
      when Date then Time.new(value.year, value.month, value.day)
      when String then Time.parse(value) rescue nil
      end
    end
  end
end
