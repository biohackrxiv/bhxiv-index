# Unlisted posts: a post with `unlisted: true` in its front matter is written as a normal HTML
# page at its usual URL, but nothing on the website links to it, for example for testing.
#
# The post is taken out of `site.posts` before the other generators run, so it is not on the home
# page, the tag, meeting and archive pages, the feeds (feed.xml, feed.json, archive.xml,
# archive.json, and feed2.xml of jekyll-feed), `site.tags`, the JSON API or the sitemap. It is
# kept in a collection of its own that is not output, so Jekyll still renders and writes it (a
# document is written by the rules of the collection it was read from: _posts). The page itself
# gets `<meta name="robots" content="noindex">` (see _includes/head.html).
module BioHackrXivUnlisted
  LABEL = 'unlisted_posts'.freeze

  class Generator < Jekyll::Generator
    safe true
    priority :highest

    def generate(site)
      unlisted = site.posts.docs.select { |post| post.data['unlisted'] }
      return if unlisted.empty?

      site.posts.docs.reject! { |post| post.data['unlisted'] }
      collection = Jekyll::Collection.new(site, LABEL)
      collection.metadata['output'] = false # jekyll-sitemap skips collections that are not output
      unlisted.each do |post|
        post.data['sitemap'] = false
        collection.docs << post
        Jekyll.logger.info 'Unlisted:', post.relative_path
      end
      site.collections[LABEL] = collection
    end
  end
end
