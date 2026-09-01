# frozen_string_literal: true

require "digest"
require "json"
require "zlib"
require "unicode_normalize/normalize"

module ReferenceV4B
  IMPLEMENTATION_ID = "REFERENCE_V4_1_IMPLEMENTATION_B_RUBY_1_0".freeze
  RESULT_SCHEMA = "PAPER04_N2_REFERENCE_V4_1_SOURCE_RESULT_1_0".freeze

  class TarFormatError < StandardError; end

  class TarStreamReader
    BLOCK_SIZE = 512
    METADATA_TYPES = ["x", "g", "L", "K"].freeze

    def initialize(path)
      @path = path
    end

    def each_entry
      return enum_for(:each_entry) unless block_given?

      global_pax = {}
      local_pax = {}
      long_name = nil
      long_link = nil
      zero_blocks = 0

      Zlib::GzipReader.open(@path) do |gzip|
        loop do
          header = read_exact(gzip, BLOCK_SIZE, allow_eof: true)
          break if header.nil?

          if header.bytes.all?(&:zero?)
            zero_blocks += 1
            next
          end
          raise TarFormatError, "nonzero tar data after end marker" if zero_blocks >= 2

          zero_blocks = 0
          verify_checksum!(header)
          raw_name = header_name(header)
          typeflag = header.getbyte(156).to_i.zero? ? "0" : header.byteslice(156, 1)
          size = parse_number(header.byteslice(124, 12))
          link_name = c_string(header.byteslice(157, 100))
          payload = read_exact(gzip, size)
          padding = (BLOCK_SIZE - (size % BLOCK_SIZE)) % BLOCK_SIZE
          read_exact(gzip, padding) if padding.positive?

          case typeflag
          when "x"
            local_pax.merge!(parse_pax(payload))
          when "g"
            global_pax.merge!(parse_pax(payload))
          when "L"
            long_name = c_string(payload)
          when "K"
            long_link = c_string(payload)
          else
            pax = global_pax.merge(local_pax)
            effective_name = pax.fetch("path", long_name || raw_name)
            effective_link = pax.fetch("linkpath", long_link || link_name)
            yield({
              "name_bytes" => effective_name.dup.force_encoding(Encoding::BINARY),
              "link_bytes" => effective_link.dup.force_encoding(Encoding::BINARY),
              "typeflag" => typeflag,
              "size" => size,
              "payload" => payload
            })
            local_pax = {}
            long_name = nil
            long_link = nil
          end
        end
      end
    rescue Zlib::Error, EOFError => error
      raise TarFormatError, error.message
    end

    private

    def read_exact(io, length, allow_eof: false)
      return "".b if length.zero?

      data = io.read(length)
      return nil if allow_eof && data.nil?
      raise EOFError, "truncated tar stream" if data.nil? || data.bytesize != length

      data
    end

    def c_string(bytes)
      bytes.to_s.split("\0", 2).first.to_s
    end

    def header_name(header)
      name = c_string(header.byteslice(0, 100))
      prefix = c_string(header.byteslice(345, 155))
      prefix.empty? ? name : "#{prefix}/#{name}"
    end

    def parse_number(bytes)
      raw = bytes.to_s.b
      if raw.getbyte(0).to_i & 0x80 != 0
        number_bytes = raw.bytes
        number_bytes[0] &= 0x7f
        number_bytes.reduce(0) { |value, byte| (value << 8) | byte }
      else
        text = raw.delete("\0 ")
        text.empty? ? 0 : Integer(text, 8)
      end
    rescue ArgumentError
      raise TarFormatError, "invalid tar numeric field"
    end

    def verify_checksum!(header)
      stored = parse_number(header.byteslice(148, 8))
      bytes = header.bytes
      8.times { |index| bytes[148 + index] = 32 }
      raise TarFormatError, "tar header checksum mismatch" unless bytes.sum == stored
    end

    def parse_pax(payload)
      result = {}
      offset = 0
      while offset < payload.bytesize
        space = payload.index(" ", offset)
        raise TarFormatError, "invalid PAX length" unless space

        length = Integer(payload.byteslice(offset, space - offset), 10)
        record = payload.byteslice(offset, length)
        raise TarFormatError, "truncated PAX record" unless record && record.bytesize == length

        body = record.byteslice(space - offset + 1, length - (space - offset + 1)).to_s
        body = body.byteslice(0, body.bytesize - 1) if body.end_with?("\n")
        key, value = body.split("=", 2)
        raise TarFormatError, "invalid PAX record" unless key && value

        result[key] = value
        offset += length
      end
      result
    rescue ArgumentError
      raise TarFormatError, "invalid PAX record"
    end
  end

  class Classifier
    REGULAR_TYPES = ["0", "\0", "7"].freeze
    DIRECTORY_TYPE = "5".freeze
    INVALID_PATH_REASON = "ARCHIVE_PATH_INTEGRITY_FAILURE".freeze

    def initialize(registry)
      @registry = registry
      @supported_extensions = registry.fetch("supported_extensions")
      @unsupported_extensions = registry.fetch("unsupported_test_extensions")
      @test_segments = registry.fetch("test_path_segments").map(&:downcase)
      @filename_patterns = registry.fetch("test_filename_patterns")
      @generated_markers = registry.fetch("generated_markers")
      @canonical_rule_ids = registry.fetch("canonical_rule_ids")
    end

    def classify(archive_path:, audit_id:, expected_sha256:, expected_bytes:)
      observed_bytes = File.size(archive_path)
      observed_sha256 = Digest::SHA256.file(archive_path).hexdigest
      identity_ok = observed_bytes == expected_bytes && observed_sha256 == expected_sha256

      unless identity_ok
        return result(audit_id, observed_sha256, observed_bytes, "INVALID", [], ["ARCHIVE_IDENTITY_FAILURE"], [], completeness(false, false))
      end

      entries, tar_error = read_entries(archive_path)
      if tar_error
        return result(audit_id, observed_sha256, observed_bytes, "INVALID", [], ["ARCHIVE_READ_FAILURE"], [], completeness(true, false))
      end

      prepared, path_error = prepare_paths(entries)
      if path_error
        return result(audit_id, observed_sha256, observed_bytes, "INVALID", [], [INVALID_PATH_REASON], [], completeness(true, false))
      end

      collision_paths = decisive_collision_paths(prepared)
      decoded_supported = true
      suspicious = false
      decisive_nonregular = false
      generated_marker = false
      generated_static_source = false
      unsupported_test_intent = false
      positive_rules = Hash.new { |hash, key| hash[key] = [] }

      prepared.each do |entry|
        path = entry.fetch("canonical_path")
        intent = test_intent?(path)
        extension = File.extname(path).downcase
        decisive = @supported_extensions.include?(extension) || @unsupported_extensions.include?(extension) || intent

        unless regular?(entry.fetch("typeflag"))
          decisive_nonregular ||= decisive && entry.fetch("typeflag") != DIRECTORY_TYPE
          next
        end

        bytes = entry.fetch("payload")
        generated_marker ||= generation_config?(path) && @generated_markers.any? { |marker| bytes.include?(marker.b) }

        if @supported_extensions.include?(extension)
          text = strict_utf8(bytes)
          unless text
            decoded_supported = false
            next
          end

          generated_static_source ||= generated_path?(path)
          cleaned = lexical_source(text, extension)
          implementation_source = framework_implementation_source?(cleaned, path, extension)
          rules = implementation_source ? [] : strong_rules(cleaned, path, extension)
          token_rules = intent && !implementation_source ? framework_token_rules(cleaned) : []

          if collision_paths.include?(collision_key(path))
            next
          else
            (rules + token_rules).uniq.each do |rule|
              positive_rules[[path.unicode_normalize(:nfc), Digest::SHA256.hexdigest(bytes)]] << rule
            end
          end
          if intent && !implementation_source && rules.empty? && token_rules.empty?
            suspicious = true
          end
        elsif @unsupported_extensions.include?(extension) && intent
          unsupported_test_intent = true
        end
      end

      positive = positive_rules.sort_by { |(path, sha256), _rules| [path.b, sha256] }.map do |(path, sha256), rules|
        { "path" => path, "sha256" => sha256, "supporting_rules" => rules.uniq.sort }
      end
      generated_unresolved = generated_marker && !generated_static_source
      unresolved = []
      unresolved << "SUPPORTED_SOURCE_DECODE_FAILURE" unless decoded_supported
      unresolved << "SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK" if suspicious
      unresolved << "DECISIVE_NONREGULAR_MEMBER" if decisive_nonregular
      unresolved << "DECISIVE_CASE_UNICODE_COLLISION" unless collision_paths.empty?
      unresolved << "GENERATED_TEST_SOURCE_NOT_STATICALLY_PRESENT" if generated_unresolved
      unresolved << "UNSUPPORTED_LANGUAGE_TEST_INTENT" if unsupported_test_intent
      unresolved.sort!

      checks = {
        "archive_identity" => true,
        "path_boundary" => true,
        "supported_sources_decoded" => decoded_supported,
        "no_positive" => positive.empty?,
        "no_suspicious_test_intent" => !suspicious,
        "no_decisive_nonregular" => !decisive_nonregular,
        "no_decisive_collision" => collision_paths.empty?,
        "no_generated_marker" => !generated_unresolved,
        "no_unsupported_test_intent" => !unsupported_test_intent
      }

      if !positive.empty?
        category = "SOURCE_SUPPORTED_TEST_PRESENCE"
        blocking = []
        warnings = unresolved
      elsif unresolved.empty? && checks.values.all?
        category = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"
        blocking = []
        warnings = []
      else
        category = "SOURCE_EVIDENCE_UNRESOLVED"
        blocking = unresolved.empty? ? ["NEGATIVE_COMPLETENESS_FAILURE"] : unresolved
        warnings = []
      end

      archive_validity = decisive_nonregular || !collision_paths.empty? ? "UNRESOLVED" : "VALID"
      result(audit_id, observed_sha256, observed_bytes, archive_validity, positive, blocking, warnings, checks, category)
    end

    private

    def read_entries(path)
      entries = []
      TarStreamReader.new(path).each_entry { |entry| entries << entry }
      [entries, nil]
    rescue TarFormatError => error
      [[], error]
    end

    def prepare_paths(entries)
      prepared = []
      entries.each do |entry|
        normalized = normalize_path(entry.fetch("name_bytes"))
        return [[], true] unless normalized

        copy = entry.dup
        copy["normalized_path"] = normalized
        prepared << copy
      end

      root = removable_root(prepared)
      prepared.each do |entry|
        path = entry.fetch("normalized_path")
        path = path.split("/", 2)[1].to_s if root && (path == root || path.start_with?("#{root}/"))
        entry["canonical_path"] = path.sub(%r{/+\z}, "")
      end
      prepared.reject! { |entry| entry.fetch("canonical_path").empty? && entry.fetch("typeflag") == DIRECTORY_TYPE }
      [prepared, false]
    end

    def normalize_path(raw)
      text = raw.dup.force_encoding(Encoding::UTF_8)
      return nil unless text.valid_encoding?
      return nil if text.include?("\0") || text.include?("\\")
      return nil if text.start_with?("/") || text.match?(/\A[A-Za-z]:/)

      components = []
      text.split("/").each do |component|
        next if component.empty? || component == "."
        return nil if component == ".."

        components << component.unicode_normalize(:nfc)
      end
      return nil if components.empty?

      components.join("/")
    end

    def removable_root(entries)
      explicit_roots = entries.select { |entry| entry.fetch("typeflag") == DIRECTORY_TYPE }
                              .map { |entry| entry.fetch("normalized_path").split("/").first }
                              .uniq
      return nil unless explicit_roots.length == 1

      root = explicit_roots.first
      return nil unless entries.all? { |entry| entry.fetch("normalized_path") == root || entry.fetch("normalized_path").start_with?("#{root}/") }

      root
    end

    def decisive_collision_paths(entries)
      grouped = entries.group_by { |entry| collision_key(entry.fetch("canonical_path")) }
      grouped.each_with_object([]) do |(key, group), result|
        next if group.length < 2
        next if group.map { |entry| entry.fetch("canonical_path") }.uniq.length == 1 &&
                group.map { |entry| [entry.fetch("typeflag"), Digest::SHA256.hexdigest(entry.fetch("payload"))] }.uniq.length == 1
        next unless group.any? { |entry| decisive_path?(entry.fetch("canonical_path")) }

        result << key
      end
    end

    def collision_key(path)
      path.unicode_normalize(:nfc).downcase
    end

    def decisive_path?(path)
      extension = File.extname(path).downcase
      @supported_extensions.include?(extension) || @unsupported_extensions.include?(extension) || test_intent?(path)
    end

    def regular?(typeflag)
      REGULAR_TYPES.include?(typeflag)
    end

    def strict_utf8(bytes)
      text = bytes.dup.force_encoding(Encoding::UTF_8)
      text.valid_encoding? ? text : nil
    end

    def test_intent?(path)
      parts = path.split("/")
      segments = parts[0...-1].map(&:downcase)
      stem = File.basename(path, File.extname(path))
      segments.any? { |segment| @test_segments.include?(segment) } ||
        @filename_patterns.any? { |pattern| File.fnmatch?(pattern, stem, File::FNM_CASEFOLD) }
    end

    def generated_path?(path)
      lowered = path.downcase
      lowered.include?("generated") && lowered.include?("test")
    end

    def generation_config?(path)
      name = File.basename(path).downcase
      extension = File.extname(path).downcase
      %w[pom.xml build.gradle build.gradle.kts settings.gradle settings.gradle.kts].include?(name) ||
        %w[.xml .gradle .sh .bash .yml .yaml .properties].include?(extension)
    end

    def lexical_source(text, extension)
      extension == ".clj" ? strip_clojure(text) : strip_c_like(text)
    end

    def strip_c_like(text)
      output = +""
      index = 0
      state = :code
      quote = nil
      while index < text.length
        char = text[index]
        pair = text[index, 2]
        case state
        when :code
          if pair == "//"
            state = :line_comment
            output << "  "
            index += 2
            next
          elsif pair == "/*"
            state = :block_comment
            output << "  "
            index += 2
            next
          elsif char == '"' || char == "'"
            state = :string
            quote = char
            output << " "
          else
            output << char
          end
        when :line_comment
          if char == "\n"
            state = :code
            output << "\n"
          else
            output << " "
          end
        when :block_comment
          if pair == "*/"
            state = :code
            output << "  "
            index += 2
            next
          else
            output << (char == "\n" ? "\n" : " ")
          end
        when :string
          if char == "\\"
            output << "  "
            index += 2
            next
          elsif char == quote
            state = :code
          end
          output << (char == "\n" ? "\n" : " ")
        end
        index += 1
      end
      output
    end

    def strip_clojure(text)
      output = +""
      in_string = false
      escaped = false
      text.each_line do |line|
        index = 0
        while index < line.length
          char = line[index]
          if in_string
            if escaped
              escaped = false
            elsif char == "\\"
              escaped = true
            elsif char == '"'
              in_string = false
            end
            output << (char == "\n" ? "\n" : " ")
          elsif char == '"'
            in_string = true
            output << " "
          elsif char == ";"
            output << " " * (line.length - index)
            break
          else
            output << char
          end
          index += 1
        end
      end
      output
    end

    def strong_rules(text, path, extension)
      rules = []
      junit_token = text.include?("org.junit") || text.include?("junit.framework")
      testng_token = text.include?("org.testng")

      if text.match?(/@org\.junit\.Test\b/)
        rules << canonical_rule("junit_at_test")
      elsif junit_token && text.match?(/@Test\b/)
        rules << canonical_rule("junit_at_test")
      end
      rules << canonical_rule("junit_testcase_inheritance") if junit_token && text.match?(/\bextends\s+TestCase\b/)
      rules << canonical_rule("testng_at_test") if testng_token && text.match?(/@Test\b/)
      rules << canonical_rule("spock_specification") if text.include?("spock.lang") && text.match?(/\bextends\s+Specification\b/)
      if text.include?("org.scalatest")
        rules << canonical_rule("scalatest_anyfunsuite_or_suite") if text.match?(/\bextends\s+(?:AnyFunSuite|Suite)\b/)
        rules << canonical_rule("scalatest_funsuite") if text.match?(/\bextends\s+FunSuite\b/)
      end
      if text.include?("clojure.test") && !framework_implementation_source?(text, path, extension)
        if text.include?("clojure.test/deftest")
          rules << canonical_rule("clojure_qualified_deftest")
        elsif text.match?(/(?<![\w\/.])deftest\b/)
          rules << canonical_rule("clojure_deftest")
        end
      end
      rules << canonical_rule("cucumber_runner") if cucumber_token?(text) && text.match?(/@RunWith\s*\(\s*Cucumber\.class\s*\)/)
      rules << canonical_rule("cucumber_options") if cucumber_token?(text) && text.match?(/@CucumberOptions\b/)
      rules
    end

    def framework_token_rules(text)
      @registry.fetch("frameworks").sort_by { |name, _| name }.each_with_object([]) do |(name, config), rules|
        rules << canonical_rule(config.fetch("path_b_rule_key")) if config.fetch("tokens").any? { |token| text.include?(token) }
      end
    end

    def canonical_rule(key)
      @canonical_rule_ids.fetch(key)
    end

    def cucumber_token?(text)
      text.include?("io.cucumber") || text.include?("cucumber.api")
    end

    def framework_implementation_path?(path)
      path.downcase.end_with?("clojure/test.clj")
    end

    def framework_implementation_source?(text, path, extension)
      return false unless extension == ".clj"

      framework_implementation_path?(path) || text.match?(/\(ns\s+clojure\.test(?:\s|\))/)
    end

    def completeness(identity, boundary)
      {
        "archive_identity" => identity,
        "path_boundary" => boundary,
        "supported_sources_decoded" => false,
        "no_positive" => true,
        "no_suspicious_test_intent" => false,
        "no_decisive_nonregular" => false,
        "no_decisive_collision" => false,
        "no_generated_marker" => false,
        "no_unsupported_test_intent" => false
      }
    end

    def result(audit_id, sha256, bytes, validity, positive, blocking, warnings, checks, category = "SOURCE_EVIDENCE_UNRESOLVED")
      {
        "schema" => RESULT_SCHEMA,
        "implementation_id" => IMPLEMENTATION_ID,
        "audit_id" => audit_id,
        "archive" => { "sha256" => sha256, "bytes" => bytes, "validity" => validity },
        "category" => category,
        "positive_evidence" => positive,
        "decision_blocking_unresolved_reasons" => blocking.sort,
        "nondecisive_warnings" => warnings.sort,
        "negative_decision_completeness" => checks
      }
    end
  end
end
