# frozen_string_literal: true

require "json"

module ReferenceV4B
  class SchemaValidator
    def initialize(schema)
      @schema = schema
    end

    def validate(value)
      errors = []
      validate_node(@schema, value, "$", errors)
      errors
    end

    private

    def validate_node(schema, value, path, errors)
      return unless schema.is_a?(Hash)

      if schema.key?("const") && value != schema["const"]
        errors << "#{path}: expected const #{schema['const'].inspect}"
      end
      if schema.key?("enum") && !schema["enum"].include?(value)
        errors << "#{path}: value is outside enum"
      end

      type = schema["type"]
      if type && !type_match?(type, value)
        errors << "#{path}: expected #{type}, got #{ruby_type(value)}"
        return
      end

      if value.is_a?(Hash)
        required = schema.fetch("required", [])
        required.each { |key| errors << "#{path}: missing #{key}" unless value.key?(key) }
        properties = schema.fetch("properties", {})
        if schema["additionalProperties"] == false
          (value.keys - properties.keys).sort.each { |key| errors << "#{path}: unexpected #{key}" }
        end
        value.each do |key, child|
          validate_node(properties[key], child, "#{path}.#{key}", errors) if properties.key?(key)
        end
      elsif value.is_a?(Array)
        value.each_with_index { |child, index| validate_node(schema["items"], child, "#{path}[#{index}]", errors) }
      elsif value.is_a?(String)
        if schema["pattern"] && !(Regexp.new(schema["pattern"]) =~ value)
          errors << "#{path}: string does not match pattern"
        end
      elsif value.is_a?(Integer)
        errors << "#{path}: below minimum" if schema.key?("minimum") && value < schema["minimum"]
      end
    end

    def type_match?(type, value)
      case type
      when "object" then value.is_a?(Hash)
      when "array" then value.is_a?(Array)
      when "string" then value.is_a?(String)
      when "integer" then value.is_a?(Integer)
      when "boolean" then value == true || value == false
      when "null" then value.nil?
      else false
      end
    end

    def ruby_type(value)
      return "boolean" if value == true || value == false
      return "null" if value.nil?

      value.class.name
    end
  end
end
