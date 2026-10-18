# Reference policy

This file restates section 6 of `docs/DESIGN.md` (v0.4): how the skill decides whether a reference exists, whether its metadata is right, and whether a cited work has been published, retracted or replicated. It governs `pc.py refs`, the reference web check (`agents/reference-web-check.md`) and the refuter's second review (`agents/refuter.md`). The policy is adapted from RefChecker, bib-check-agent, citecheck and Crossref's reference matchers, all MIT-licensed; see `THIRD_PARTY_NOTICES.md` at the skill root.

The guiding principle: **not found is not fake.** A failed or unreachable lookup makes a reference unverified, never fabricated. Calling a real reference non-existent is one of the most damaging errors the skill could make, so that verdict needs three independent failures and a second reviewer.

## Clients

Every lookup goes through a bundled script with a cache, an identifying user agent (`paper-check/<version> (+https://github.com/jiaxinlu1024/paper_check)` plus `mailto:` when a contact email is configured), the service's contact or key parameter, rate limiting and exponential backoff on 429 and 5xx responses. MCP servers are optional extras, never the backbone. The limits below were reported by the survey on 2026-10-17 and must be rechecked when the clients change.

| Service | Access | Limits and notes |
|---|---|---|
| Crossref | Contact email, for the polite pool | 10 requests per second for DOI lookups and 3 for searches, since December 2025. Retractions appear in `update-to` |
| OpenAlex | Free API key, required since February 2026 | Single-DOI lookups are free; other use draws on a daily allowance. Labels each copy of a work as submitted, accepted or published |
| Semantic Scholar | Free API key, issued only to institutional email addresses | 1 request per second |
| DataCite | Contact email | Dataset DOIs |
| Unpaywall | Contact email on every request | Open-access locations by DOI |
| arXiv | None | 3 seconds between requests |
| doi.org | None | Content negotiation for metadata |
| RePEc | API access only on emailed request, with no search | Links working papers to their published versions |
| NBER | None | DOIs of the form `10.3386/w#####` |

Positive results are cached for 7 days and negative results for 24 hours, so a temporary failure is retried soon. Keys and the contact email live in `~/.paper-check/config.yaml`, outside any repository. Only reference metadata and short queries leave the machine, never the paper's text.

## Deciding whether a reference exists (CIT-02, CIT-03)

1. **Identifier first.** Resolve the DOI, arXiv ID, NBER number or SSRN ID when the entry has one. An identifier that resolves to a different work is a warning sign for a chimeric citation.
2. **Search-based matching.** Search Crossref with the raw reference string rather than trusting parsed fields, then validate the candidate field by field: title similarity, author overlap, year and venue.
3. **Two sources for verified.** A reference is verified only when two independent databases agree.
4. **Non-existent only after three failures.** A reference is called non-existent only when its identifier fails, every database fails to match it, and a web search for the exact title finds no page dedicated to the work. A dedicated page is a page about the work itself, such as a publisher page, a repository record or a library catalogue entry; a citation in another paper's reference list does not count. A second reviewer must agree. If any database was unreachable or returned errors, the second condition is not met, and the reference stays unverified.
5. **Severity by kind.**

   | Kind | Example | Severity |
   |---|---|---|
   | Non-existent work | No record anywhere, and no dedicated page | Critical |
   | Chimeric citation | A real NBER number paired with another paper's title | Major |
   | Metadata drift | Year off by one, venue or pages wrong | Minor; Major when the author list is substantially wrong |
   | Status drift | A working paper that has since been published | Suggestion |

6. **Calibrated thresholds.** Start from the MIT tools' values and calibrate them on the evaluation sets (`evals/README.md`). RefChecker uses title similarity 0.8, a year within one, and author overlap 0.6. Crossref's preprint matcher accepts at 0.87, with a year window from one year before to three years after. A year off by one is metadata drift, never a sign of fabrication.
7. **Compare an entry only with the version it cites.** A record of another version says nothing about errors in the entry, so its fields are not compared and the card carries a version note instead:
   - a journal article that the databases know only as its working paper;
   - a working paper that they know only as its later article or chapter (CIT-04 then proposes that version);
   - a copy deposited in a data or document archive (ICPSR, Zenodo, Dataverse and similar), dated by the deposit;
   - a book whose only records are older than the cited year, which may be a later edition. The report asks the author to name the edition (a Suggestion) rather than to change the year.

   Working-paper series names are not compared with an institution's name, because databases record them inconsistently. One entry gets one CIT-03 finding: the parts it leaves out are listed in the finding about the fields that differ.
8. **Evidence card for every reference.** The closest record found, the similarity of each field, every query made, and which databases were reached or failed. The cards are in `WORK/references/cards.json`, and the report prints them as an appendix. A card's `verdict` is one of: `verified` (two independent databases agree), `single_source` (one database matches), `metadata_drift`, `chimeric`, `not_found_in_databases` (no database matches; a web check is needed, so `needs_web_check` is true), and `unverified` (no database could be searched at all, so nothing is concluded).

## The web check and the second review

A script cannot do step 4's web search. Every card the scripts cannot settle carries `needs_web_check: true`, and an agent following `agents/reference-web-check.md` then:

- searches the exact title in quotation marks, the title with the first author, distinctive title words with the authors and year, and every identifier, at least three searches before concluding that no dedicated page exists;
- re-checks the cited title, authors, year and venue against any dedicated page it finds, because a database can match the wrong edition or a similarly titled work;
- treats a similar work with other authors or identifiers as a possible intended reference, never as the same work;
- takes every corrected value from a page it opened, never from memory, and never proposes a different paper as a replacement without the citation-support check;
- records each reference's queries and outcome in `WORK/references/web_checks_<n>.json`.

The outcomes are: exists but not indexed (the reference is cleared); metadata drift; chimeric citation; likely non-existent; and unverified, when the lookups were not conclusive. A likely non-existent reference becomes non-existent only when the refuter, acting as the second reviewer, searches independently and also finds no dedicated page.

## Working papers and published versions (CIT-04)

No open tool handles economics working papers, so this part is new.

1. Extract NBER, SSRN, IZA and CEPR identifiers from each entry, and resolve NBER DOIs.
2. Search Crossref for journal articles, OpenAlex for other locations of the same work, and RePEc for linked versions once access is granted.
3. Use a wide year window, and weight the author set above the title, because titles often change between versions. A changed title must still keep half of its content words, because the same authors often write several papers together.
4. Report a published version as a Suggestion. Pass the version actually read on to the citation support and baseline checks, because findings and numbers can change between versions.

## Retractions and replications (CIT-05, CIT-14)

1. Cache the daily Retraction Watch file and the FORRT Replication Database (FReD) locally.
2. Confirm every hit with Crossref's `update-to` field and OpenAlex's `is_retracted` flag, and list every notice for a DOI.
3. Never filter by subject. The behavioral cases that matter most are tagged Psychology, Ethics or Sociology, not Economics.
4. Match notices that have no DOI by title and authors.
5. Report each replication with its outcome label and a quote of the replication's own conclusion. Never call a finding false: a failed replication is evidence about a finding, reported in the replication's own words.
6. Use Institute for Replication (I4R) reports as a second source.

## Sources

- RefChecker: https://github.com/markrussinovich/refchecker
- bib-check-agent: https://github.com/nnicholas-c/bib-check-agent
- citecheck: https://github.com/sunami-lab/citecheck
- cite-verify, for NBER DOI handling: https://github.com/jonckr/cite-verify
- Crossref search-based matcher: https://gitlab.com/crossref/search_based_reference_matcher
- Crossref preprint matcher: https://gitlab.com/crossref/data-science/matching-tools
- Crossref rate limits: https://community.crossref.org/t/announcing-changes-to-rest-api-rate-limits-crossref/14726
- OpenAlex changelog: https://help.openalex.org/hc/en-us/articles/38868153578263-Changelog
- OpenAlex location versions: https://docs.openalex.org/api-entities/works/work-object/location-object
- Semantic Scholar API release notes: https://github.com/allenai/s2-folks/blob/HEAD/API_RELEASE_NOTES.md
- RePEc IDEAS API: https://ideas.repec.org/api.html
- Retraction Watch data: https://gitlab.com/crossref/retraction-watch-data
- FORRT Replication Database: https://github.com/forrtproject/FReD
