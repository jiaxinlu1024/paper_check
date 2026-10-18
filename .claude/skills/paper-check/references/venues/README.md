# Venue profiles

One YAML file per journal, holding the submission rules the skill checks: limits, required parts, review type, style and policies. Every rule records where it came from, so a profile can be audited and rechecked.

## Rules for writing a profile

- **Primary sources only.** A rule is `confirmed` only when the journal's own author guidelines, or its publisher's or society's official pages, state it. The `quote` field holds the supporting text, copied verbatim and kept short.
- **No memory.** Never fill a rule from memory or from a third-party summary. Use `unconfirmed` with a `note` saying what was seen and where.
- **Say when a page was blocked.** Some publisher sites refuse automated access. Mark that source `access: blocked`, mark its rules `unconfirmed`, and do not try to get around the block.
- **Use `not_stated`** when a source was read in full and does not address the rule.
- **Date everything.** `checked_on` is the date the sources were read. Journals change their rules, so the skill warns when a profile is older than 180 days.

## Format

```yaml
id: jebo                      # same as the file name
name: Journal of Economic Behavior & Organization
abbreviation: JEBO
publisher: Elsevier
group: field                  # general-top5, general or field
checked_on: "2026-10-17"
sources:
  - id: guide                 # referred to by rules
    url: https://example.org/guide-for-authors
    title: Guide for Authors
    access: read              # read, blocked or search_summary
rules:
  abstract_max_words:
    status: confirmed         # confirmed, unconfirmed or not_stated
    value: 250
    source: guide
    quote: "The abstract should not exceed 250 words."
  highlights:
    status: unconfirmed
    value: {required: true, count_min: 3, count_max: 5, max_chars_each: 85}
    note: "Guide page blocked automated access. Verify in a browser."
```

## Rule keys

| Key | Value |
|---|---|
| `abstract_max_words` | Integer |
| `manuscript_limit` | `{amount, unit}`, where unit is words or pages, plus an optional `scope` such as "main text" |
| `keywords` | `{required, min, max}` |
| `jel_codes` | `{required, min, max}` |
| `highlights` | `{required, count_min, count_max, max_chars_each}` |
| `review_type` | `double_anonymous`, `single_anonymous`, `open` or `unknown` |
| `disclosure_statement` | `{required, detail}` |
| `data_availability_statement` | `{required, detail}` |
| `data_code_policy` | `{summary, url}` |
| `ethics_approval` | `{required, detail}`, for example where the IRB statement goes |
| `trial_registration` | `{required_for, registry, detail}` |
| `deception` | `banned`, `allowed_with_justification` or `not_addressed` |
| `experiment_materials` | `{detail}`, for example instructions in an appendix |
| `ai_use` | `{detail}` |
| `citation_style` | String |
| `submission_fee` | `{amount, currency, detail}` |
| `file_format` | String |
| `other` | A list of `{name, status, value, source, quote, note}` for rules without a key |

## Checking a profile

```bash
python3 tools/validate_venues.py                  # structure only
python3 tools/validate_venues.py --verify-quotes  # also re-fetch each source and find each quote
```
