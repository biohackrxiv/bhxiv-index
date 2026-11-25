# Adds the width and height in pixels of a post's `image:` as `image_width` and `image_height`,
# used for the og:image:width and og:image:height tags in _includes/head.html.
#
# The size is read from the header of the PNG or JPEG file, so no image library is needed.
# Images that cannot be read are skipped with a warning.
module BioHackrXivImageSize
  class Generator < Jekyll::Generator
    safe true
    priority :low

    def generate(site)
      site.posts.docs.each do |post|
        image = post.data['image']
        next unless image.is_a?(String) && image.start_with?('/')

        path = File.join(site.source, image)
        size = File.file?(path) ? ImageSize.read(path) : nil
        if size
          post.data['image_width'], post.data['image_height'] = size
        else
          Jekyll.logger.warn 'Image size:', "cannot read the size of #{image} (#{post.relative_path})"
        end
      end
    end
  end

  module ImageSize
    PNG_SIGNATURE = "\x89PNG\r\n\x1A\n".b
    # JPEG start-of-frame markers: C0-CF, except DHT (C4), JPG (C8) and DAC (CC)
    JPEG_SOF = ((0xC0..0xCF).to_a - [0xC4, 0xC8, 0xCC]).freeze

    module_function

    # Returns [width, height], or nil when the file is not a PNG or JPEG that can be read.
    def read(path)
      File.open(path, 'rb') do |file|
        header = file.read(24) || ''
        if header.start_with?(PNG_SIGNATURE) && header[12, 4] == 'IHDR'
          header[16, 8].unpack('NN')
        elsif header.start_with?("\xFF\xD8".b)
          file.seek(2)
          jpeg_size(file)
        end
      end
    end

    def jpeg_size(file)
      loop do
        byte = file.read(1)
        return nil unless byte
        next unless byte.ord == 0xFF

        marker = file.read(1)&.ord
        marker = file.read(1)&.ord while marker == 0xFF # fill bytes
        return nil unless marker
        next if marker == 0x01 || (0xD0..0xD9).cover?(marker) # markers without a length

        length = file.read(2)&.unpack1('n')
        return nil unless length

        if JPEG_SOF.include?(marker)
          height, width = file.read(5)&.unpack('Cnn')&.drop(1)
          return width && height ? [width, height] : nil
        end
        file.seek(length - 2, IO::SEEK_CUR)
      end
    end
  end
end
