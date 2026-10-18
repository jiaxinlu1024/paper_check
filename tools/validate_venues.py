#!/usr/bin/env python3
"""Validate venue profiles in .claude/skills/paper-check/references/venues/.

    python3 tools/validate_venues.py                  # structure and source links
    python3 tools/validate_venues.py --verify-quotes  # also find every confirmed quote in its source
    python3 tools/validate_venues.py aer jebo         # only these profiles

Structure checks: the JSON Schema, the file name matching `id`, unique source ids,
every rule pointing at a listed source, and every confirmed rule carrying a quote.

Quote checks fetch each source page and look for each confirmed quote after
normalizing case, quote marks and dashes, and ignoring whitespace entirely, so
that markup splitting a word does not matter. A quote may use "..." to skip
text; its parts must then appear in order. Requests to one host are spaced at
least 1.2 seconds apart. A page that is a bot challenge, or a source that is
blocked or unreachable, is reported as not verified, never counted as a pass.
"""

import argparse
import datetime as dt
import html
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
VENUES = ROOT / ".claude" / "skills" / "paper-check" / "references" / "venues"
USER_AGENT = "paper-check/0.1 (+https://github.com/jiaxinlu1024/paper_check)"
MAX_AGE_DAYS = 180
HOST_DELAY_SECONDS = 1.2
CHALLENGE_MARKERS = ("client challenge", "just a moment...", "checking your browser",
                     "enable javascript and cookies to continue", "attention required! | cloudflare")
_last_request = {}


class ChallengePage(Exception):
    """The server answered with a bot challenge instead of the page."""


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}
    BLOCK = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "table", "ul", "ol", "dt", "dd", "pre", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _wait_for_host(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    wait = HOST_DELAY_SECONDS - (time.monotonic() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def _is_challenge(raw_text):
    head = raw_text[:5000].lower()
    return any(marker in head for marker in CHALLENGE_MARKERS)


def normalize(text):
    text = html.unescape(text)
    table = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
             "−": "-", " ": " ", "­": "", "…": "..."}
    for k, v in table.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip().lower()


def _download(url, timeout):
    _wait_for_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def _download_with_curl(url, timeout):
    """Some servers challenge Python's HTTP client but serve curl normally.
    curl sends the same honest user agent; nothing here imitates a browser."""
    if not shutil.which("curl"):
        return None
    _wait_for_host(url)
    result = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", USER_AGENT, url],
                            capture_output=True, timeout=timeout + 10)
    return result.stdout if result.returncode == 0 else None


def _to_text(body, ctype):
    if "pdf" in ctype or body[:5] == b"%PDF-":
        import pdfplumber  # imported lazily: only PDF sources need it
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            return " ".join((page.extract_text() or "") for page in pdf.pages)
    parser = _Text()
    parser.feed(body.decode("utf-8", errors="replace"))
    return "".join(parser.parts)


def fetch_text(url, timeout=40):
    body, ctype = _download(url, timeout)
    text = _to_text(body, ctype)
    if _is_challenge(text):
        body = _download_with_curl(url, timeout)
        text = _to_text(body, "") if body else ""
        if not body or _is_challenge(text):
            raise ChallengePage("server answered with a bot challenge")
    return text


def quote_found(quote, text_norm):
    """True if every part of the quote appears in order, ignoring all whitespace."""
    squeezed = re.sub(r"\s+", "", text_norm)
    parts = [re.sub(r"\s+", "", normalize(p)) for p in re.split(r"\.\.\.|\u2026", quote)]
    parts = [p for p in parts if p]
    pos = 0
    for part in parts:
        idx = squeezed.find(part, pos)
        if idx < 0:
            return False
        pos = idx + len(part)
    return bool(parts)


def iter_rules(rules):
    for key, rule in rules.items():
        if key == "other":
            for item in rule:
                yield f"other:{item.get('name', '?')}", item
        else:
            yield key, rule


def check_structure(path, data, validator):
    errors, warnings = [], []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(top)"
        errors.append(f"schema: {loc}: {err.message}")
    if errors:
        return errors, warnings
    if data["id"] != path.stem:
        errors.append(f"id '{data['id']}' does not match file name '{path.stem}'")
    ids = [s["id"] for s in data["sources"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate source ids")
    source_ids = set(ids)
    for key, rule in iter_rules(data["rules"]):
        src = rule.get("source")
        if src and src not in source_ids:
            errors.append(f"{key}: source '{src}' is not listed under sources")
        if rule["status"] == "confirmed":
            if not src:
                errors.append(f"{key}: confirmed without a source")
            if not rule.get("quote", "").strip():
                errors.append(f"{key}: confirmed without a quote")
            if "value" not in rule:
                errors.append(f"{key}: confirmed without a value")
        if rule["status"] == "unconfirmed" and not rule.get("note"):
            warnings.append(f"{key}: unconfirmed without a note saying why")
        if len(rule.get("quote", "")) > 500:
            warnings.append(f"{key}: quote longer than 500 characters; keep quotes short")
    checked = dt.date.fromisoformat(data["checked_on"])
    today = dt.date.today()
    if checked > today:
        errors.append(f"checked_on {checked} is in the future")
    elif (today - checked).days > MAX_AGE_DAYS:
        warnings.append(f"checked_on {checked} is older than {MAX_AGE_DAYS} days; recheck the sources")
    return errors, warnings


def check_quotes(data, cache):
    errors, warnings = [], []
    by_id = {s["id"]: s for s in data["sources"]}
    for key, rule in iter_rules(data["rules"]):
        if rule["status"] != "confirmed":
            continue
        src = by_id[rule["source"]]
        if src["access"] != "read":
            errors.append(f"{key}: confirmed from a source with access '{src['access']}'; only read sources can confirm")
            continue
        url = src["url"]
        if url not in cache:
            try:
                cache[url] = ("ok", normalize(fetch_text(url)))
            except urllib.error.HTTPError as exc:
                cache[url] = ("fail", f"HTTP {exc.code}")
            except ChallengePage as exc:
                cache[url] = ("fail", str(exc))
            except Exception as exc:  # report, never pass
                cache[url] = ("fail", f"{type(exc).__name__}: {str(exc)[:80]}")
        state, text = cache[url]
        if state != "ok":
            warnings.append(f"{key}: could not re-fetch {url} ({text}); quote not verified")
        elif not quote_found(rule["quote"], text):
            errors.append(f"{key}: quote not found in {url}")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="profile ids to check (default: all)")
    parser.add_argument("--verify-quotes", action="store_true", help="fetch sources and find each confirmed quote")
    args = parser.parse_args()

    validator = Draft202012Validator(json.loads((VENUES / "schema.json").read_text()))
    paths = sorted(VENUES.glob("*.yaml"))
    if args.ids:
        paths = [p for p in paths if p.stem in set(args.ids)]
    if not paths:
        print("No profiles found.")
        return 1

    cache, failed = {}, 0
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            print(f"FAIL {path.name}: YAML error: {exc}")
            failed += 1
            continue
        errors, warnings = check_structure(path, data, validator)
        if args.verify_quotes and not errors:
            qe, qw = check_quotes(data, cache)
            errors += qe
            warnings += qw
        rules = data.get("rules") if isinstance(data, dict) and isinstance(data.get("rules"), dict) else {}
        listed = [r for _, r in iter_rules(rules) if isinstance(r, dict)]
        confirmed = sum(1 for r in listed if r.get("status") == "confirmed")
        total = len(listed)
        print(f"{'FAIL' if errors else 'OK  '} {path.name}: {confirmed} of {total} rules confirmed")
        for e in errors:
            print(f"     error: {e}")
        for w in warnings:
            print(f"     warning: {w}")
        failed += bool(errors)
    print(f"\n{len(paths) - failed} of {len(paths)} profiles passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
