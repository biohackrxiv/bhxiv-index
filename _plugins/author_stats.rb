# Author statistics for the About page, counted on each build from the `authors:` of the posts:
#
#   site.data['author_stats'] = {
#     'unique'  => number of different ORCIDs,
#     'single'  => number of ORCIDs with one preprint,
#     'top'     => the three ORCIDs with the most preprints:
#                  [{'orcid' => ..., 'name' => ..., 'count' => ...}, ...]
#   }
#
# Authors are counted by ORCID, so authors without an ORCID are not counted. An author counts
# once per preprint. The name is the one in the most recent preprint of the author. Unlisted posts
# are not counted, as _plugins/unlisted.rb takes them out of site.posts before this runs.
module BioHackrXivAuthorStats
  class Generator < Jekyll::Generator
    safe true
    priority :low

    def generate(site)
      counts = Hash.new(0)
      names = {}
      site.posts.docs.sort_by(&:date).each do |post|
        orcids = Array(post.data['authors']).filter_map do |author|
          next unless author.is_a?(Hash)

          orcid = author['orcid'].to_s[/\d{4}-\d{4}-\d{4}-\d{3}[\dX]/]
          names[orcid] = author['name'].to_s if orcid
          orcid
        end
        orcids.uniq.each { |orcid| counts[orcid] += 1 }
      end
      top = counts.sort_by { |orcid, count| [-count, names[orcid]] }.first(3).map do |orcid, count|
        { 'orcid' => orcid, 'name' => names[orcid], 'count' => count }
      end
      site.data['author_stats'] = {
        'unique' => counts.size,
        'single' => counts.count { |_, count| count == 1 },
        'top' => top
      }
    end
  end
end
