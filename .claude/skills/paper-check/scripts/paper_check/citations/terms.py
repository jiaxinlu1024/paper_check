"""Term expansion for the citation scan: the STW Thesaurus for Economics plus a small glossary.

    expand("hyperbolic discounting") -> {"term", "terms": [{"term", "relation", "source", ...}], "matches",
                                         "sources", "attribution", "notes", "relations"}

Every expanded term carries its relation to the claimed concept, because the relation decides the
verdict (DESIGN section 7): a related concept is not a synonym.

STW Thesaurus for Economics, by ZBW - Leibniz Information Centre for Economics. It is downloaded
once from ZBW's official download page (https://www.zbw.eu/stw/version/latest/download/about.en.html,
file stw.nt.zip) and cached in ~/.paper-check/cache/stw/:

    stw.nt.zip        the file as published
    stw_index.json    the parsed concepts and labels
    stw_meta.json     version, issue date, license and attribution, as stated in the data itself

It is never committed or redistributed with the skill. Version 9.20 (2025-12-16) states CC BY 4.0;
earlier versions such as 9.10 were ODbL 1.0. The attribution text is built from the downloaded data.
STW has few behavioral-economics concepts (no "present bias", for example), so a short glossary,
written for this skill, adds the core ones with model names and parameter symbols. When the
download is unavailable, expand() says so and returns the glossary terms only.

    python -m paper_check.citations.terms "present bias" "loss aversion"     # prints JSON
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from .. import __version__
from ..config import HOME

STW_PAGE = "https://www.zbw.eu/stw/version/latest/download/about.en.html"
STW_FILE = "https://www.zbw.eu/stw/version/latest/download/stw.nt.zip"
CACHE_DIR = HOME / "cache" / "stw"
SCHEME = "http://zbw.eu/stw"
INDEX_FORMAT = 1
MIN_CONCEPTS = 100   # a real STW download has thousands; fewer means a broken file

SKOS = "http://www.w3.org/2004/02/skos/core#"
ZBWEXT = "http://zbw.eu/namespaces/zbw-extensions/"
_PRED = {
    SKOS + "prefLabel": "pref", SKOS + "altLabel": "alt", SKOS + "hiddenLabel": "hid",
    ZBWEXT + "altLabelNarrower": "altn", ZBWEXT + "altLabelRelated": "altr",
    SKOS + "broader": "b", SKOS + "narrower": "n", SKOS + "related": "r",
    SKOS + "scopeNote": "note", "http://purl.org/dc/terms/isReplacedBy": "rep",
    "http://www.w3.org/2002/07/owl#deprecated": "dep", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": "type",
}
_SCHEME_PRED = {
    "http://www.w3.org/2002/07/owl#versionInfo": "version", "http://purl.org/dc/terms/issued": "issued",
    "http://creativecommons.org/ns#license": "license", "http://creativecommons.org/ns#attributionName": "attribution_name",
    "http://creativecommons.org/ns#attributionURL": "attribution_url", "http://purl.org/dc/terms/title": "title",
}
LICENSE_NAMES = {
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0", "http://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
    "http://opendatacommons.org/licenses/odbl/1.0/": "ODbL 1.0", "https://opendatacommons.org/licenses/odbl/1.0/": "ODbL 1.0",
}
RELATIONS = {
    "synonym": "the same concept: a passage naming it can support the claim. STW synonyms are thesaurus entry "
               "terms, which can include near-synonyms and opposites; confirm each before treating it as approved",
    "model": "a formal model of the concept: supports when the source uses or estimates it for this concept",
    "symbol": "the concept's parameter or symbol: supports when the source estimates it, such as beta below 1 for present bias",
    "narrower": "a special case: evidence for the special case only partly supports a general claim",
    "broader": "a more general concept: at most partly supports",
    "related": "a different concept: at most partly supports, and sharing the topic is not support",
    "category": "an STW subject category: context only, never support",
}
_RANK = {r: i for i, r in enumerate(("synonym", "model", "symbol", "narrower", "broader", "related", "category"))}

# Seed glossary written for this skill: core behavioral concepts that STW lacks or covers thinly.
# Relations are deliberately conservative: only variants and established equivalent names are synonyms.
GLOSSARY = {
    "present bias": {
        "aliases": ["present bias", "present-biased preferences", "present biased", "present-bias"],
        "synonym": ["present-biased", "present-bias", "present-biased preferences"],
        "model": ["quasi-hyperbolic", "quasi-hyperbolic discounting", "beta-delta", "β-δ", "(β, δ) preferences"],
        "symbol": ["β", "beta", "present-bias parameter"],
        "related": ["hyperbolic discounting", "time inconsistency", "dynamic inconsistency", "self-control",
                    "procrastination", "immediate gratification", "temptation", "commitment device"],
        "broader": ["time preference", "intertemporal choice", "time discounting"],
    },
    "hyperbolic discounting": {
        "aliases": ["hyperbolic discounting", "hyperbolic discount function", "hyperbolic discount"],
        "synonym": ["hyperbolic discount function", "hyperbolic discounters"],
        "narrower": ["quasi-hyperbolic discounting", "beta-delta"],
        "related": ["present bias", "time inconsistency", "preference reversal", "declining discount rate"],
        "broader": ["time preference", "intertemporal choice", "time discounting"],
    },
    "time inconsistency": {
        "aliases": ["time inconsistency", "dynamic inconsistency", "time-inconsistent preferences"],
        "synonym": ["dynamic inconsistency", "time-inconsistent", "dynamically inconsistent"],
        "related": ["present bias", "hyperbolic discounting", "preference reversal", "commitment", "self-control"],
        "broader": ["time preference", "intertemporal choice"],
    },
    "self-control": {
        "aliases": ["self-control", "self-control problems", "self control"],
        "synonym": ["self-control problem*"],
        "related": ["present bias", "temptation", "willpower", "commitment device", "procrastination",
                    "time inconsistency"],
    },
    "procrastination": {
        "aliases": ["procrastination", "procrastinate"],
        "synonym": ["procrastinat*"],
        "related": ["present bias", "self-control", "delay", "deadline*", "inertia", "time inconsistency"],
    },
    "loss aversion": {
        "aliases": ["loss aversion", "loss-averse", "loss averse"],
        "synonym": ["loss-averse", "loss averse"],
        "symbol": ["λ", "lambda", "coefficient of loss aversion", "loss aversion coefficient"],
        "related": ["reference dependence", "reference point", "prospect theory", "value function",
                    "endowment effect", "status quo bias"],
    },
    "reference dependence": {
        "aliases": ["reference dependence", "reference-dependent preferences", "reference point"],
        "synonym": ["reference-dependent", "reference point*"],
        "related": ["loss aversion", "prospect theory", "expectations-based reference point*", "framing"],
    },
    "prospect theory": {
        "aliases": ["prospect theory"],
        "narrower": ["cumulative prospect theory"],
        "related": ["loss aversion", "reference dependence", "probability weighting", "value function", "framing"],
    },
    "probability weighting": {
        "aliases": ["probability weighting", "probability weighting function", "decision weights"],
        "synonym": ["probability weighting function", "decision weight*", "weighting function"],
        "related": ["prospect theory", "cumulative prospect theory", "rank-dependent utility", "certainty effect"],
    },
    "default effect": {
        "aliases": ["default effect", "default effects", "defaults"],
        "synonym": ["default effect"],
        "narrower": ["automatic enrollment", "auto-enrollment", "opt-out"],
        "related": ["status quo bias", "inertia", "choice architecture", "nudge", "opt-in", "active choice"],
    },
    "status quo bias": {
        "aliases": ["status quo bias", "status-quo bias"],
        "synonym": ["status-quo bias"],
        "related": ["default effect", "inertia", "endowment effect", "loss aversion"],
    },
    "inertia": {
        "aliases": ["inertia"],
        "related": ["status quo bias", "default effect", "procrastination", "switching cost*", "passive choice"],
    },
    "endowment effect": {
        "aliases": ["endowment effect"],
        "related": ["loss aversion", "willingness to accept", "willingness to pay", "status quo bias"],
    },
    "nudge": {
        "aliases": ["nudge", "nudges", "nudging"],
        "synonym": ["nudging"],
        "related": ["choice architecture", "libertarian paternalism", "default effect", "behavioral intervention*"],
    },
    "choice architecture": {
        "aliases": ["choice architecture"],
        "related": ["nudge", "default effect", "framing", "libertarian paternalism"],
    },
    "framing effect": {
        "aliases": ["framing effect", "framing effects", "framing"],
        "synonym": ["framing"],
        "related": ["prospect theory", "loss aversion", "reference dependence"],
    },
    "anchoring": {
        "aliases": ["anchoring", "anchoring effect"],
        "synonym": ["anchoring effect"],
        "related": ["anchor*", "insufficient adjustment", "heuristics"],
    },
    "overconfidence": {
        "aliases": ["overconfidence", "overconfident"],
        "synonym": ["overconfident"],
        "narrower": ["overestimation", "overplacement", "overprecision"],
        "related": ["naivete", "naive", "optimism", "projection bias"],
    },
    "social preferences": {
        "aliases": ["social preferences", "other-regarding preferences"],
        "synonym": ["other-regarding preferences"],
        "narrower": ["altruism", "inequity aversion", "inequality aversion", "reciprocity", "warm glow", "fairness"],
        "related": ["dictator game", "ultimatum game", "public goods game", "trust game"],
    },
    "inequity aversion": {
        "aliases": ["inequity aversion", "inequality aversion"],
        "synonym": ["inequality aversion"],
        "related": ["fairness", "social preferences", "envy", "guilt", "reciprocity"],
        "broader": ["social preferences"],
    },
    "ambiguity aversion": {
        "aliases": ["ambiguity aversion", "ambiguity-averse"],
        "synonym": ["ambiguity-averse", "ambiguity averse"],
        "related": ["Ellsberg", "Knightian uncertainty", "uncertainty aversion", "maxmin expected utility"],
    },
    "limited attention": {
        "aliases": ["limited attention", "inattention"],
        "synonym": ["inattention", "inattentive"],
        "related": ["salience", "rational inattention", "shrouded attribute*"],
    },
}


# ================================================================ normalization
_UK_US = {"behaviour": "behavior", "behavioural": "behavioral", "labour": "labor", "favour": "favor",
          "organisation": "organization", "modelling": "modeling", "programme": "program", "analyse": "analyze"}


def norm_label(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("&", " and ")
    text = re.sub(r"[^\w]+", " ", text).replace("_", " ")
    return " ".join(_UK_US.get(w, w) for w in text.split())


def _stem(word: str) -> str:
    """'biased', 'biases' and 'bias' -> 'bias'; 'preferences' -> 'preference'."""
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and word[-2] not in "saiu":
        return word[:-1]
    return word


def _variants(key: str) -> list:
    out = [key]
    words = key.split()
    if words and len(words[-1]) > 4 and words[-1].endswith("s") and not words[-1].endswith("ss"):
        out.append(" ".join(words[:-1] + [words[-1][:-1]]))
    if words and not words[-1].endswith("s"):
        out.append(key + "s")
    return out


def _label_keys(label: str) -> list:
    """A label's lookup keys: in full, without a parenthetical part, and the parenthetical alone."""
    keys = [norm_label(label)]
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", label)
    if m:
        keys += [norm_label(m.group(1)), norm_label(m.group(2))]
    return [k for k in dict.fromkeys(keys) if k]


# ================================================================ N-Triples
_NT = re.compile(r'^(<[^>]*>|_:\S+)\s+<([^>]*)>\s+(<[^>]*>|_:\S+|"(?:[^"\\]|\\.)*"(?:@[A-Za-z0-9-]+|\^\^<[^>]*>)?)\s*\.\s*$')
_ESC = re.compile(r'\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|[tbnrf"\'\\])')
_SIMPLE = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def _unescape(s: str) -> str:
    def repl(m):
        e = m.group(1)
        return chr(int(e[1:], 16)) if e[0] in "uU" else _SIMPLE[e]
    return _ESC.sub(repl, s)


def _literal(obj: str) -> tuple:
    m = re.match(r'^"((?:[^"\\]|\\.)*)"(?:@([A-Za-z0-9-]+)|\^\^<[^>]*>)?$', obj)
    return (_unescape(m.group(1)), (m.group(2) or "").lower()) if m else (obj, "")


def parse_ntriples(lines) -> dict:
    """Concepts and scheme metadata from STW's N-Triples. Returns the index structure."""
    concepts: dict = {}
    meta: dict = {}
    prefix = SCHEME + "/"

    def cid(uri: str) -> str:
        uri = uri.strip("<>")
        return uri[len(prefix):] if uri.startswith(prefix) else uri

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _NT.match(line)
        if not m:
            continue
        subj, pred, obj = m.group(1), m.group(2), m.group(3)
        if subj == f"<{SCHEME}>":
            key = _SCHEME_PRED.get(pred)
            if key:
                value, lang = _literal(obj) if obj.startswith('"') else (obj.strip("<>"), "")
                if key in ("attribution_name", "title"):
                    if lang in ("en", ""):
                        meta[key] = value
                else:
                    meta[key] = value
            continue
        kind = _PRED.get(pred)
        if kind is None or not subj.startswith("<"):
            continue
        c = concepts.setdefault(cid(subj), {})
        if kind in ("pref", "note"):
            value, lang = _literal(obj)
            c.setdefault(kind, {})[lang or "und"] = value
        elif kind in ("alt", "hid", "altn", "altr"):
            value, lang = _literal(obj)
            c.setdefault(kind, {}).setdefault(lang or "und", []).append(value)
        elif kind in ("b", "n", "r", "rep"):
            if obj.startswith("<"):
                c.setdefault(kind, []).append(cid(obj))
        elif kind == "dep":
            c["dep"] = _literal(obj)[0].lower() == "true"
        elif kind == "type":
            t = obj.strip("<>")
            if t.endswith("/Thsys"):
                c["t"] = "c"
            elif t.endswith("/Descriptor"):
                c["t"] = "d"
    concepts = {k: v for k, v in concepts.items() if v.get("pref") or v.get("rep")}
    for k, v in concepts.items():
        v.setdefault("t", "c" if k.startswith("thsys/") else "d")
    return {"format": INDEX_FORMAT, "meta": meta, "concepts": concepts}


# ================================================================ download and cache
def _download(url: str, dest: Path, timeout: float = 120.0) -> None:
    request = urllib.request.Request(url, headers={
        "User-Agent": f"paper-check/{__version__} (+https://github.com/jiaxinlu1024/paper_check)",
        "Accept": "application/zip, */*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(60 * 1024 * 1024)
    if not data.startswith(b"PK"):
        raise ValueError("the download is not a zip file")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    part.write_bytes(data)
    part.replace(dest)


def _parse_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.endswith(".nt")]
        if not members:
            raise ValueError("no .nt file in the archive")
        with zf.open(members[0]) as fh:  # read in memory; nothing is extracted to disk
            return parse_ntriples(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))


def ensure_stw(cache_dir: Optional[Path] = None, offline: bool = False, source: Optional[Path] = None) -> tuple:
    """(index or None, note). Downloads STW once; later calls read the cache.

    `source` is a local .nt or .nt.zip file to use instead of the download (used by the tests)."""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    index_path, zip_path, meta_path = cache_dir / "stw_index.json", cache_dir / "stw.nt.zip", cache_dir / "stw_meta.json"
    if source is not None:
        source = Path(source)
        if source.suffix == ".zip":
            data = _parse_zip(source)
        else:
            with source.open(encoding="utf-8") as fh:
                data = parse_ntriples(fh)
        data["meta"].update({"source_url": str(source)})
        return data, f"STW read from {source.name}"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if data.get("format") == INDEX_FORMAT and data.get("concepts"):
                return data, "STW read from the cache"
        except ValueError:
            pass
    note = "STW parsed from the cached download"
    if not zip_path.exists():
        if offline:
            return None, "STW thesaurus unavailable: offline, and no cached copy in " + str(cache_dir)
        try:
            _download(STW_FILE, zip_path)
            note = "STW downloaded from ZBW and cached"
        except Exception as exc:
            return None, f"STW thesaurus unavailable: download failed ({type(exc).__name__}: {str(exc)[:120]})"
    try:
        data = _parse_zip(zip_path)
    except Exception as exc:
        return None, f"STW thesaurus unavailable: the cached file could not be read ({type(exc).__name__}: {exc})"
    if len(data["concepts"]) < MIN_CONCEPTS:
        return None, "STW thesaurus unavailable: the downloaded file holds too few concepts"
    data["meta"].update({"source_url": STW_FILE, "download_page": STW_PAGE,
                         "downloaded": dt.date.today().isoformat(),
                         "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()})
    try:
        index_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        meta_path.write_text(json.dumps(data["meta"], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return data, note


def attribution(meta: dict) -> str:
    license_url = meta.get("license") or ""
    name = LICENSE_NAMES.get(license_url, license_url or "the license stated by ZBW")
    version = f" v{meta['version']}" if meta.get("version") else ""
    issued = f" ({meta['issued']})" if meta.get("issued") else ""
    who = meta.get("attribution_name") or "ZBW - Leibniz Information Centre for Economics"
    return (f"Thesaurus terms from the STW Thesaurus for Economics{version}{issued} by {who}, "
            f"http://zbw.eu/stw, licensed under {name}" + (f" ({license_url})." if license_url else "."))


# ================================================================ thesaurus
class Thesaurus:
    def __init__(self, data: dict):
        self.meta = data.get("meta", {})
        self.concepts = data.get("concepts", {})
        self.index: dict = {}
        for cid, c in self.concepts.items():
            for kind in ("pref", "alt", "hid", "altn", "altr"):
                values = c.get(kind) or {}
                for lang, labels in values.items():
                    for label in ([labels] if isinstance(labels, str) else labels):
                        for key in _label_keys(label):
                            self.index.setdefault(key, []).append((cid, kind, lang, label))

    @classmethod
    def load(cls, cache_dir: Optional[Path] = None, offline: bool = False, source: Optional[Path] = None) -> tuple:
        data, note = ensure_stw(cache_dir, offline=offline, source=source)
        return (cls(data) if data else None), note

    def label(self, cid: str, lang: str = "en") -> Optional[str]:
        pref = (self.concepts.get(cid) or {}).get("pref") or {}
        return pref.get(lang) or pref.get("en") or next(iter(pref.values()), None)

    def uri(self, cid: str) -> str:
        return cid if cid.startswith("http") else f"{SCHEME}/{cid}"

    def lookup(self, term: str, lang: str = "en") -> list:
        """[(concept id, label kind, matched label, 'exact' or 'partial')]."""
        key = norm_label(term)
        if not key:
            return []
        for variant in _variants(key):
            hits = self.index.get(variant)
            if hits:
                seen, out = set(), []
                for cid, kind, _, label in hits:
                    if (cid, kind) not in seen:
                        seen.add((cid, kind))
                        out.append((cid, kind, label, "exact"))
                return out
        tokens = {_stem(w) for w in key.split()}
        if len(tokens) < 2:
            return []  # a single word matched partially is mostly noise ("default" in "credit default swap")
        partial = []
        for k, hits in self.index.items():
            label_tokens = {_stem(w) for w in k.split()}
            if tokens <= label_tokens:
                for cid, kind, hlang, label in hits:
                    if hlang in (lang, "und"):
                        partial.append((len(label_tokens) - len(tokens), len(k), cid, kind, label))
        partial.sort()
        out, seen = [], set()
        for _, _, cid, kind, label in partial:
            if cid not in seen:
                seen.add(cid)
                out.append((cid, kind, label, "partial"))
            if len(out) >= 6:
                break
        return out

    def expand(self, term: str, lang: str = "en") -> tuple:
        """(terms, matches, notes) from STW for one term."""
        terms, matches, notes = [], [], []

        def labels(cid, kind):
            values = ((self.concepts.get(cid) or {}).get(kind) or {}).get(lang) or []
            return [values] if isinstance(values, str) else list(values)

        def add(label, relation, cid, via, basis=None):
            if label:
                row = {"term": label, "relation": relation, "source": "STW", "concept": self.uri(cid),
                       "concept_label": self.label(cid, lang), "via": via}
                if basis:
                    row["basis"] = basis
                terms.append(row)

        for cid, kind, matched, how in self.lookup(term, lang):
            concept = self.concepts.get(cid) or {}
            if concept.get("dep") and concept.get("rep"):
                notes.append(f"STW concept {self.uri(cid)} is deprecated; its replacement is used.")
                targets = concept["rep"]
            else:
                targets = [cid]
            for target in targets:
                c = self.concepts.get(target) or {}
                matches.append({"concept": self.uri(target), "label": self.label(target, lang),
                                "matched_label": matched, "match": f"{how} ({kind})"})
                if how == "partial":
                    basis = f"partial label match: {matched!r}"
                    add(self.label(target, lang), "related", target, "prefLabel", basis)
                    for alt in labels(target, "alt"):
                        add(alt, "related", target, "altLabel", basis)
                    continue
                if kind in ("pref", "alt", "hid"):
                    own, alt_rel = "synonym", "synonym"
                    altn_rel, altr_rel, b_rel, n_rel = "narrower", "related", "broader", "narrower"
                elif kind == "altn":   # the term is a narrower entry term of this concept
                    own, alt_rel = "broader", "broader"
                    altn_rel, altr_rel, b_rel, n_rel = "related", "related", "broader", "related"
                else:                  # altr: the term is a related entry term of this concept
                    own, alt_rel = "related", "related"
                    altn_rel, altr_rel, b_rel, n_rel = "related", "related", "related", "related"
                add(self.label(target, lang), own, target, "prefLabel")
                for alt in labels(target, "alt"):
                    add(alt, alt_rel, target, "altLabel")
                for alt in labels(target, "altn"):
                    add(alt, altn_rel, target, "altLabelNarrower")
                for alt in labels(target, "altr"):
                    add(alt, altr_rel, target, "altLabelRelated")
                for other in c.get("b", []):
                    rel = "category" if (self.concepts.get(other) or {}).get("t") == "c" else b_rel
                    add(self.label(other, lang), rel, other, "broader")
                for other in c.get("n", []):
                    if (self.concepts.get(other) or {}).get("t") != "c":
                        add(self.label(other, lang), n_rel, other, "narrower")
                for other in c.get("r", []):
                    add(self.label(other, lang), "related", other, "related")
        return terms, matches, notes


# ================================================================ glossary
def glossary_lookup(term: str) -> list:
    key = norm_label(term)
    out = []
    for concept, entry in GLOSSARY.items():
        keys = {norm_label(a) for a in entry.get("aliases", [])} | {norm_label(concept)}
        if any(v in keys for v in _variants(key)):
            out.append((concept, entry))
    return out


def _glossary_terms(term: str) -> tuple:
    terms, matched = [], []
    for concept, entry in glossary_lookup(term):
        matched.append(concept)
        if norm_label(concept) != norm_label(term):
            terms.append({"term": concept, "relation": "synonym", "source": "paper-check glossary", "concept": concept})
        for relation in ("synonym", "model", "symbol", "narrower", "broader", "related"):
            for label in entry.get(relation, []):
                terms.append({"term": label, "relation": relation, "source": "paper-check glossary", "concept": concept})
    return terms, matched


# ================================================================ public API
_DEFAULT: dict = {}


def get_thesaurus(offline: bool = False, cache_dir: Optional[Path] = None) -> tuple:
    """The default STW thesaurus, loaded once per process: (Thesaurus or None, note)."""
    key = (str(cache_dir or CACHE_DIR), offline)
    if key not in _DEFAULT:
        _DEFAULT[key] = Thesaurus.load(cache_dir, offline=offline)
    return _DEFAULT[key]


def expand(term: str, lang: str = "en", offline: bool = False, thesaurus: Optional[Thesaurus] = None,
           cache_dir: Optional[Path] = None, use_glossary: bool = True) -> dict:
    """Synonyms, broader, narrower and related terms for `term`, each with its relation and source."""
    if thesaurus is None:
        thesaurus, stw_note = get_thesaurus(offline=offline, cache_dir=cache_dir)
    else:
        stw_note = "STW supplied by the caller"
    notes, rows, matches = [], [], []
    if thesaurus is not None:
        stw_terms, matches, stw_notes = thesaurus.expand(term, lang)
        rows += stw_terms
        notes += stw_notes
        if not matches:
            notes.append(f"No STW concept matches {term!r}.")
        elif all(m["match"].startswith("partial") for m in matches):
            notes.append(f"STW has no concept named {term!r}; the closest labels contain its words and are "
                         "listed as related terms only.")
    else:
        notes.append(stw_note + ". Expansion uses the glossary only; add synonyms by hand.")
    glossary_concepts = []
    if use_glossary:
        g_terms, glossary_concepts = _glossary_terms(term)
        rows += g_terms
    best: dict = {}
    for row in rows:
        k = norm_label(row["term"])
        if not k or k == norm_label(term):
            continue
        if k not in best or _RANK[row["relation"]] < _RANK[best[k]["relation"]]:
            best[k] = row
    ordered = sorted(best.values(), key=lambda r: (_RANK[r["relation"]], r["source"] != "STW", r["term"].lower()))
    meta = thesaurus.meta if thesaurus is not None else {}
    return {
        "term": term,
        "terms": ordered,
        "matches": matches,
        "glossary_concepts": glossary_concepts,
        "sources": {
            "stw": {"available": thesaurus is not None, "version": meta.get("version"), "issued": meta.get("issued"),
                    "license": meta.get("license"), "note": stw_note},
            "glossary": {"available": use_glossary, "note": "short glossary written for paper-check; extend it in the trajectory"},
        },
        "attribution": attribution(meta) if thesaurus is not None else None,
        "notes": notes,
        "relations": RELATIONS,
    }


def terms_command(terms: list, offline: bool = False, lang: str = "en") -> int:
    """Print the expansion of each term as JSON (for `pc.py terms`, once the CLI wires it)."""
    out = [expand(t, lang=lang, offline=offline) for t in terms]
    print(json.dumps(out if len(out) != 1 else out[0], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--offline"]
    sys.exit(terms_command(args, offline="--offline" in sys.argv[1:]))
