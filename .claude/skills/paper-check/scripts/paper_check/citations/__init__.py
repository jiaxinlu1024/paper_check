"""Citation support (CIT-06): the script side.

    prepare.py   `pc.py cite-prepare WORK`: attributed propositions, full text of every
                 cited work through the legal cascade, and a status summary
    fulltext.py  polite cached HTTP, PDF text with page markers, the cascade itself
    terms.py     STW Thesaurus for Economics plus a small glossary, for term expansion
    scan.py      `pc.py scan WORK --ref R --terms ...`: exhaustive term scan and BM25
                 passages, the absence record that judge agents cite

Outputs, all under WORK/citations/:

    propositions.jsonl     one record per citation group in a citing sentence
    by_ref.json            propositions grouped by reference
    sources/<ref>.txt      the cited work's text, with [[page N]] markers ([[abstract]] when only the abstract)
    sources/<ref>.json     where the text came from: url, source, version, pages, abstract_only, fetch date
    sources/<ref>.pdf      the downloaded PDF, when one was downloaded
    status.json            what was found for each reference
    scans/<ref>.jsonl      every scan run on a reference, appended
    cache/                 HTTP responses and the sources-folder index
"""
