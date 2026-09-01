#!/usr/bin/env ruby
# frozen_string_literal: true

# Independent statistics recomputation B using Ruby Rational arithmetic.

require "json"

ROOT = File.expand_path("..", __dir__)
SUPPORTED = "SOURCE_SUPPORTED_TEST_PRESENCE"
NEGATIVE = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"

def load_jsonl(path)
  File.readlines(path, chomp: true).reject(&:empty?).map { |line| JSON.parse(line) }
end

def fraction_text(value)
  "#{value.numerator}/#{value.denominator}"
end

def decimal(value)
  format("%.12f", value.to_f)
end

def point(value)
  { "fraction" => fraction_text(value), "decimal" => decimal(value) }
end

def project_groups(rows)
  rows.group_by { |row| row.fetch("project") }.sort.to_h
end

def binary(row, upper)
  row.fetch("category") == SUPPORTED || (upper && row.fetch("category") != NEGATIVE) ? 1 : 0
end

def uncertainty(estimate, variance)
  se = Math.sqrt(variance.to_f)
  low = [0.0, estimate.to_f - 1.96 * se].max
  high = [1.0, estimate.to_f + 1.96 * se].min
  point(estimate).merge({
    "design_variance_fraction" => fraction_text(variance),
    "standard_error_decimal" => format("%.12f", se),
    "wald_95_decimal" => [format("%.12f", low), format("%.12f", high)],
    "uncertainty_scope" => "FINITE_POPULATION_STRATIFIED_SRS_DESIGN_BASED"
  })
end

def metric(rows)
  groups = project_groups(rows)
  project_count = groups.length
  frame_total = groups.values.sum { |group| group.first.fetch("N_j") }
  estimates = {}
  [["lower", false], ["upper", true]].each do |name, upper|
    pb = groups.values.sum(Rational(0, 1)) { |group| Rational(group.sum { |row| binary(row, upper) }, group.length) } / project_count
    weighted_total = groups.values.sum(Rational(0, 1)) { |group| Rational(group.first.fetch("N_j"), group.length) * group.sum { |row| binary(row, upper) } }
    sw = weighted_total / frame_total
    pb_variance = Rational(0, 1)
    sw_total_variance = Rational(0, 1)
    groups.values.each do |group|
      n = group.length
      n_frame = group.first.fetch("N_j")
      count = group.sum { |row| binary(row, upper) }
      p = Rational(count, n)
      sample_variance = n > 1 ? Rational(n, n - 1) * p * (1 - p) : Rational(0, 1)
      fpc = 1 - Rational(n, n_frame)
      pb_variance += Rational(1, project_count * project_count) * fpc * sample_variance / n
      sw_total_variance += n_frame * n_frame * fpc * sample_variance / n
    end
    sw_variance = sw_total_variance / (frame_total * frame_total)
    estimates[name] = {
      "project_balanced" => uncertainty(pb, pb_variance),
      "snapshot_weighted" => uncertainty(sw, sw_variance)
    }
  end
  counts = rows.each_with_object(Hash.new(0)) { |row, memo| memo[row.fetch("category")] += 1 }.sort.to_h
  { "project_count" => project_count, "sample_units" => rows.length, "frame_rows" => frame_total, "category_counts" => counts }.merge(estimates)
end

def simple_points(rows)
  value = metric(rows)
  {
    "project_count" => value.fetch("project_count"),
    "sample_units" => value.fetch("sample_units"),
    "frame_rows" => value.fetch("frame_rows"),
    "project_balanced_lower" => value.fetch("lower").fetch("project_balanced").slice("fraction", "decimal"),
    "project_balanced_upper" => value.fetch("upper").fetch("project_balanced").slice("fraction", "decimal"),
    "snapshot_weighted_lower" => value.fetch("lower").fetch("snapshot_weighted").slice("fraction", "decimal"),
    "snapshot_weighted_upper" => value.fetch("upper").fetch("snapshot_weighted").slice("fraction", "decimal")
  }
end

manifest = JSON.parse(File.read(File.join(ROOT, "V4_1_PROTOCOL_FREEZE/FROZEN_149_UNIT_ORDER_MANIFEST.json"))).fetch("units")
labels = load_jsonl(File.join(ROOT, "REFERENCE_V4_1_SOURCE_LABELS.jsonl")).to_h { |row| [row.fetch("audit_id"), row] }
rows = manifest.map { |unit| unit.merge("category" => labels.fetch(unit.fetch("audit_id")).fetch("category")) }
raise "unit count" unless rows.length == 149

overall = metric(rows)
projects = rows.map { |row| row.fetch("project") }.uniq.sort
lopo = projects.map { |project| { "omitted_project" => project }.merge(simple_points(rows.reject { |row| row.fetch("project") == project })) }
sensitivity = [
  ["EXCLUDE_CLOJURE", ["clojure"]],
  ["EXCLUDE_CANAL", ["canal"]],
  ["EXCLUDE_CLOJURE_AND_CANAL", ["canal", "clojure"]]
].map do |name, excluded|
  { "scenario" => name, "excluded_projects" => excluded.sort }.merge(simple_points(rows.reject { |row| excluded.include?(row.fetch("project").downcase) }))
end
anchor = ["INCLUDED", "EXCLUDED"].to_h { |scope| [scope, metric(rows.select { |row| row.fetch("anchor_downstream_scope") == scope })] }
groups = project_groups(rows)
supported_counts = groups.transform_values { |group| group.count { |row| row.fetch("category") == SUPPORTED } }
supported_total = supported_counts.values.sum
sample_hhi = Rational(supported_counts.values.sum { |count| count * count }, supported_total * supported_total)
ht_contributions = groups.to_h { |project, group| [project, Rational(group.first.fetch("N_j"), group.length) * supported_counts.fetch(project)] }
ht_total = ht_contributions.values.sum(Rational(0, 1))
ht_hhi = ht_contributions.values.sum(Rational(0, 1)) { |value| (value / ht_total)**2 }
concentration = {
  "sample_supported_total" => supported_total,
  "sample_supported_by_project" => supported_counts,
  "sample_max_project" => supported_counts.max_by { |project, count| [count, project] }.first,
  "sample_max_share" => point(Rational(supported_counts.values.max, supported_total)),
  "sample_hhi" => point(sample_hhi),
  "snapshot_weighted_supported_contribution_by_project" => ht_contributions.transform_values { |value| point(value) },
  "snapshot_weighted_max_project" => ht_contributions.max_by { |project, value| [value, project] }.first,
  "snapshot_weighted_max_share" => point(ht_contributions.values.max / ht_total),
  "snapshot_weighted_hhi" => point(ht_hhi)
}
result = {
  "schema" => "PAPER04_N2_REFERENCE_V4_1_STATISTICS_1_0",
  "implementation" => "STATISTICS_B_RUBY_EXACT_RATIONAL",
  "estimand" => "fraction for which collector-zero is contradicted by supported repository test-source evidence",
  "unresolved_interval_rule" => "lower=unresolved_as_0; upper=unresolved_as_1",
  "overall" => overall,
  "lopo" => lopo,
  "project_concentration" => concentration,
  "clojure_canal_sensitivity" => sensitivity,
  "anchor_partition" => anchor
}
File.write(File.join(ROOT, "V4_1_STATISTICS/STATISTICS_B.json"), JSON.pretty_generate(result) + "\n")
puts JSON.pretty_generate({ "overall" => overall, "lopo_projects" => lopo.length, "sensitivity_scenarios" => sensitivity.length })
