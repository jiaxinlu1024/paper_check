#!/usr/bin/env python3
"""Check that the services the paper-check skill uses are reachable.

Run it from any machine: a cloud session, or a laptop with Claude Code desktop.
It uses only the Python standard library and honours HTTPS_PROXY and SSL_CERT_FILE.

    python3 tools/check_network.py            # test every host
    python3 tools/check_network.py --required # test only the hosts the core checks need

A host counts as reachable when it returns any HTTP response, even an error code
such as 401, 403 or 404, because that proves the network path is open. A host is
blocked when the proxy refuses the connection or the name does not resolve.
"""

import argparse
import concurrent.futures as futures
import socket
import ssl
import sys
import urllib.error
import urllib.request

# (group, required, label, url)
HOSTS = [
    # Reference existence, metadata and retractions: CIT-01 to CIT-05.
    ("Reference metadata", True, "Crossref API", "https://api.crossref.org/works?rows=0"),
    ("Reference metadata", True, "DOI resolver", "https://doi.org/api/handles/10.2307/1914185"),
    ("Reference metadata", True, "OpenAlex API", "https://api.openalex.org/works?per_page=1&search=prospect%20theory"),
    ("Reference metadata", True, "Semantic Scholar API", "https://api.semanticscholar.org/graph/v1/paper/search?query=prospect+theory&limit=1&fields=title"),
    ("Reference metadata", True, "arXiv API", "https://export.arxiv.org/api/query?search_query=all:nudge&max_results=1"),
    ("Reference metadata", True, "DataCite API", "https://api.datacite.org/dois?page%5Bsize%5D=1"),
    ("Reference metadata", False, "Crossref Labs (Retraction Watch data)", "https://api.labs.crossref.org/"),
    # Open-access full text, needed to test whether a source supports a claim: CIT-06.
    ("Open-access full text", True, "Unpaywall API", "https://api.unpaywall.org/v2/10.2307/1914185?email=paper-check@example.com"),
    ("Open-access full text", True, "arXiv papers", "https://arxiv.org/"),
    ("Open-access full text", True, "Semantic Scholar PDFs", "https://pdfs.semanticscholar.org/"),
    ("Open-access full text", False, "CORE API", "https://api.core.ac.uk/v3/search/works?q=nudge&limit=1"),
    ("Open-access full text", False, "Europe PMC API", "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=nudge&format=json&pageSize=1"),
    ("Open-access full text", False, "PubMed E-utilities", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=nudge&retmax=1"),
    # Economics working papers: the free versions of most paywalled econ articles.
    ("Economics working papers", True, "NBER", "https://www.nber.org/"),
    ("Economics working papers", True, "RePEc IDEAS", "https://ideas.repec.org/"),
    ("Economics working papers", False, "RePEc EconPapers", "https://econpapers.repec.org/"),
    ("Economics working papers", False, "SSRN", "https://papers.ssrn.com/"),
    ("Economics working papers", False, "IZA", "https://www.iza.org/"),
    ("Economics working papers", False, "CEPR", "https://cepr.org/"),
    ("Economics working papers", False, "EconStor", "https://www.econstor.eu/"),
    ("Economics working papers", False, "OSF API (PsyArXiv, SocArXiv)", "https://api.osf.io/v2/"),
    ("Economics working papers", False, "OSF", "https://osf.io/"),
    # Preregistration and replication data: MTH-03 and MTH-07.
    ("Registries and replication data", False, "AEA RCT Registry", "https://www.socialscienceregistry.org/"),
    ("Registries and replication data", False, "AsPredicted", "https://aspredicted.org/"),
    ("Registries and replication data", False, "openICPSR", "https://www.openicpsr.org/"),
    ("Registries and replication data", False, "Harvard Dataverse", "https://dataverse.harvard.edu/"),
    ("Registries and replication data", False, "Zenodo API", "https://zenodo.org/api/records?size=1"),
    # Journal and publisher pages: abstracts, and full text when open access.
    ("Journals and publishers", False, "AEA journals", "https://www.aeaweb.org/"),
    ("Journals and publishers", False, "Oxford Academic", "https://academic.oup.com/"),
    ("Journals and publishers", False, "Wiley", "https://onlinelibrary.wiley.com/"),
    ("Journals and publishers", False, "ScienceDirect", "https://www.sciencedirect.com/"),
    ("Journals and publishers", False, "Elsevier DOI links", "https://linkinghub.elsevier.com/"),
    ("Journals and publishers", False, "Springer", "https://link.springer.com/"),
    ("Journals and publishers", False, "Cambridge", "https://www.cambridge.org/"),
    ("Journals and publishers", False, "INFORMS (Management Science)", "https://pubsonline.informs.org/"),
    ("Journals and publishers", False, "University of Chicago Press (JPE)", "https://www.journals.uchicago.edu/"),
    ("Journals and publishers", False, "Econometric Society", "https://www.econometricsociety.org/"),
    ("Journals and publishers", False, "JSTOR", "https://www.jstor.org/"),
    ("Journals and publishers", False, "SAGE", "https://journals.sagepub.com/"),
    ("Journals and publishers", False, "Taylor & Francis", "https://www.tandfonline.com/"),
    ("Journals and publishers", False, "PNAS", "https://www.pnas.org/"),
    ("Journals and publishers", False, "Science", "https://www.science.org/"),
    ("Journals and publishers", False, "Nature", "https://www.nature.com/"),
    # General reference for fact checks: FACT-01.
    ("General reference", False, "Wikipedia", "https://en.wikipedia.org/wiki/Prospect_theory"),
]

USER_AGENT = "paper-check-network-test/0.1 (+https://github.com/jiaxinlu1024/paper_check)"


def probe(url, timeout):
    """Return (status, detail) where status is 'ok', 'blocked' or 'error'."""
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return "ok", f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:  # The server answered, so the path is open.
        return "ok", f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        reason = exc.reason
        text = str(reason)
        if "Tunnel connection failed" in text or "403" in text:
            return "blocked", "proxy refused the connection"
        if isinstance(reason, socket.gaierror) or "Name or service not known" in text:
            return "blocked", "name did not resolve"
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in text:
            return "error", "timed out"
        if isinstance(reason, ssl.SSLError):
            return "error", f"TLS error: {text[:80]}"
        return "error", text[:80]
    except (socket.timeout, TimeoutError):
        return "error", "timed out"
    except Exception as exc:  # Report anything else rather than crash.
        return "error", f"{type(exc).__name__}: {str(exc)[:80]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--required", action="store_true", help="test only the hosts the core checks need")
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds per request (default 20)")
    args = parser.parse_args()

    hosts = [h for h in HOSTS if h[1] or not args.required]
    with futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda h: probe(h[3], args.timeout), hosts))

    marks = {"ok": "OK     ", "blocked": "BLOCKED", "error": "ERROR  "}
    current_group = None
    for (group, required, label, url), (status, detail) in zip(hosts, results):
        if group != current_group:
            print(f"\n{group}")
            current_group = group
        need = "required" if required else "optional"
        print(f"  {marks[status]}  {label:<40} {need:<9} {detail}")

    failed_required = [h[2] for h, r in zip(hosts, results) if h[1] and r[0] != "ok"]
    reachable = sum(1 for r in results if r[0] == "ok")
    print(f"\n{reachable} of {len(hosts)} hosts reachable.")
    if failed_required:
        print("Required hosts not reachable: " + ", ".join(failed_required))
        print("See docs/network-setup.md for how to open network access.")
        return 1
    print("All required hosts are reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
