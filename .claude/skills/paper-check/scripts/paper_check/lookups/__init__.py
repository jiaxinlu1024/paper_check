"""Reference lookups: existence, metadata, versions, retractions, replications, links.

Modules:
    http             one HTTP client for every service: user agent, rate limits, backoff,
                     disk cache (positive 7 days, negative 24 hours), offline mode
    records          Record (one database's view of a work) and Query (one logged request)
    crossref, openalex, semanticscholar, doiorg, datacite, arxiv, nber
                     one client per service, each returning Records plus a Query
    services         the clients for one run, built from config.Credentials
    identifiers      DOI, arXiv, NBER, SSRN, IZA and CEPR identifiers and URLs in an entry
    matching         string similarity for titles, author names, venues, pages
    policy           the reference policy of DESIGN section 6 and its thresholds
    versions         working paper or preprint to published version (CIT-04)
    retractions      retraction, correction and concern notices (CIT-05)
    replications     FORRT Replication Database records (CIT-14)
    links            DOIs and URLs resolve (CIT-12)
    findings         evidence cards to findings and coverage
    run              `pc.py refs`: run_reference_checks(work, offline, limit)
"""
