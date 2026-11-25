# Static JSON API (version 1) of the BioHackrXiv index, generated on each Jekyll build.
#
#   /api/v1/listArticles.json      all preprints: id, DOI, title, date of the earliest version
#   /api/v1/articles/<id>.json     all metadata of one preprint
#
# <id> is the OSF identifier without the version suffix (`92bc5` for 10.37044/osf.io/92bc5_v2),
# so the URL of a preprint does not change when a new version is posted. See api.markdown.
#
# Copyright (c) 2026 Egon Willighagen
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

require 'json'

module BioHackrXivApi
  API_DIR = 'api/v1'.freeze
  DOI_PATTERN = %r{\A10\.37044/osf\.io/([a-z0-9]+?)(?:_v(\d+))?\z}.freeze

  class Generator < Jekyll::Generator
    safe true
    priority :low

    def generate(site)
      @base = site.config['url'].to_s + site.config['baseurl'].to_s
      @figures = site.data['figures'] || {}
      articles = []
      seen = {}
      site.posts.docs.sort_by { |post| [earliest_date(post), post.data['doi'].to_s] }.each do |post|
        doi = post.data['doi'].to_s.strip.downcase
        match = DOI_PATTERN.match(doi)
        unless match
          Jekyll.logger.warn 'API:', "skipped #{post.relative_path}: no BioHackrXiv DOI"
          next
        end
        id = match[1]
        if seen[id]
          raise "API: #{post.relative_path} and #{seen[id]} are both preprint #{id}"
        end
        seen[id] = post.relative_path
        article = article(post, id, doi)
        articles << article.slice('id', 'doi', 'title', 'date', 'url')
        site.pages << json_page(site, "#{API_DIR}/articles", "#{id}.json", article)
      end
      list = { 'api_version' => '1', 'count' => articles.size, 'articles' => articles }
      site.pages << json_page(site, API_DIR, 'listArticles.json', list)
    end

    private

    def article(post, id, doi)
      data = post.data
      osf_id = doi.sub('10.37044/osf.io/', '')
      tags = Array(data['tags']).map(&:to_s)
      article = {
        'id' => id,
        'doi' => doi,
        'title' => data['title'].to_s,
        'date' => earliest_date(post),
        'url' => "#{@base}/#{API_DIR}/articles/#{id}.json",
        'html_url' => @base + post.url,
        'doi_url' => "https://doi.org/#{doi}",
        'pdf_url' => "https://osf.io/download/#{osf_id}/",
        'description' => data['description'],
        'authors' => Array(data['authors']).map { |author| author_json(author) },
        'tags' => tags.reject { |tag| tag.include?(':') },
        'relations' => relations(tags),
        'molecules' => tags.filter_map { |tag| tag.split(':', 2)[1] if tag.start_with?('inchikey:') },
        'identifiers' => {
          'europepmc' => data['europepmc'],
          'openalex' => data['openalex'],
          'wikidata' => data['wikidata']
        },
        'git' => data['git'],
        'image' => data['image'] ? @base + data['image'].to_s : nil,
        'figures' => figures(osf_id)
      }
      article['versions'] = versions(data['versions']) if data['versions'].is_a?(Array)
      article['concept'] = data['concept'].to_h { |key, value| [key.to_s, value] } if data['concept'].is_a?(Hash)
      article
    end

    # The date of the earliest version: from `versions:` when the post has it, else `date:`.
    def earliest_date(post)
      dates = Array(post.data['versions']).filter_map { |v| v.is_a?(Hash) && v['date'] && iso_date(v['date']) }
      dates.min || iso_date(post.date)
    end

    def iso_date(value)
      value.respond_to?(:strftime) ? value.strftime('%Y-%m-%d') : value.to_s[0, 10]
    end

    def author_json(author)
      return { 'name' => author.to_s } unless author.is_a?(Hash)
      json = { 'name' => author['name'].to_s }
      json['orcid'] = author['orcid'].to_s if author['orcid']
      json
    end

    # `doi:` and `justdoi:` tags are plain citations, `cito:<type>:<doi>` typed ones.
    def relations(tags)
      tags.filter_map do |tag|
        prefix, rest = tag.split(':', 2)
        case prefix
        when 'doi', 'justdoi' then { 'type' => 'cites', 'doi' => rest }
        when 'cito'
          type, target = rest.to_s.split(':', 2)
          { 'type' => type, 'doi' => target } if target
        end
      end
    end

    def figures(osf_id)
      entry = @figures[osf_id]
      return [] unless entry.is_a?(Hash)
      Array(entry['figures']).map do |figure|
        { 'url' => "#{@base}/#{figure['file']}", 'caption' => figure['caption'] }
      end
    end

    def versions(list)
      list.select { |v| v.is_a?(Hash) }.map do |version|
        version.to_h { |key, value| [key.to_s, value.respond_to?(:strftime) ? iso_date(value) : value] }
      end
    end

    def json_page(site, dir, name, object)
      page = Jekyll::PageWithoutAFile.new(site, site.source, dir, name)
      page.content = JSON.pretty_generate(object) + "\n"
      page.data['layout'] = nil
      page.data['render_with_liquid'] = false
      page.data['sitemap'] = false
      page
    end
  end
end
