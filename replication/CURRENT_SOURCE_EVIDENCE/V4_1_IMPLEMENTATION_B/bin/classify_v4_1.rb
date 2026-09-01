#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "optparse"
require_relative "../lib/reference_v4_b"

options = {}
OptionParser.new do |parser|
  parser.on("--archive PATH") { |value| options[:archive] = value }
  parser.on("--audit-id ID") { |value| options[:audit_id] = value }
  parser.on("--expected-sha256 SHA") { |value| options[:expected_sha256] = value }
  parser.on("--expected-bytes N", Integer) { |value| options[:expected_bytes] = value }
  parser.on("--registry PATH") { |value| options[:registry] = value }
end.parse!

required = %i[archive audit_id expected_sha256 expected_bytes registry]
missing = required.reject { |key| options.key?(key) }
abort("missing options: #{missing.join(', ')}") unless missing.empty?

registry = JSON.parse(File.read(options.fetch(:registry)))
classifier = ReferenceV4B::Classifier.new(registry)
result = classifier.classify(
  archive_path: options.fetch(:archive),
  audit_id: options.fetch(:audit_id),
  expected_sha256: options.fetch(:expected_sha256),
  expected_bytes: options.fetch(:expected_bytes)
)
STDOUT.write(JSON.generate(result))
STDOUT.write("\n")
