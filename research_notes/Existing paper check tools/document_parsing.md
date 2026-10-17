# Document ingestion and parsing tools for the paper-check skill (PDF, LaTeX, Word, references, tables)

> Evidence date: 2026-10-17. Method: PyPI JSON metadata (versions, release dates, licenses, wheel sizes, dependencies), README, docs and source files read from raw.githubusercontent.com, and blob-less shallow clones used only to read files and last-commit dates (nothing was installed, imported or run). Limits: the session's web-search budget was used up after the first batch, and arxiv.org, api.semanticscholar.org, docs.mathpix.com, manpages.debian.org and metacpan were unreachable. Comparison papers could therefore not be re-read; the one result quoted from memory is marked. Benchmarks published by a tool's own vendor are labelled "vendor-reported". "Last commit" dates come from shallow clones made on 2026-10-17.

## 1. PDF tools: accuracy on two-column academic PDFs, math, tables, footnotes and references; license; install size; GPU needs; speed

### Takeaway
No PDF tool is both light and structurally accurate on a CPU laptop. Text-layer libraries give exact characters with coordinates but no semantic structure. pdfplumber, pdfminer.six, pypdfium2 and pypdf are permissively licensed; PyMuPDF and pymupdf4llm are AGPL or commercial. ML pipelines (Docling, MinerU, Marker) add layout, tables and formulas, but they need PyTorch or ONNX models and are much slower. GROBID (Apache-2.0, Java or Docker) is the specialist for scholarly structure: references, citation contexts, footnotes and sentence coordinates. VLM tools (olmOCR, Nougat, Marker "balanced", MinerU VLM) and the commercial Mathpix API lead the benchmarks, but they need a GPU or send the draft to a cloud service.

### Cited Findings

#### Benchmarks
- **olmOCR-Bench** (AllenAI) has "over 7,000 test cases across 1,400 documents" ([olmOCR README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md)). Marker describes it as "1,403 PDFs with ~8,400 pass/fail unit tests covering math rendering, table structure, reading order, headers/footers, and old scans" ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)). The two READMEs give slightly different counts.
- olmOCR-Bench results in the olmOCR README, as Overall / ArXiv math / Tables / Multi column. Rows marked * in the source are marked * here; the README's meaning of the asterisk was not checked ([olmOCR README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md)):
  - Chandra OCR 0.1.0*: 83.1 / 82.2 / 88.0 / 81.2
  - Infinity-Parser 7B*: 82.5 / 84.4 / 85.0 / 84.2
  - olmOCR v0.4.0: 82.4 / 83.0 / 84.9 / 83.7
  - PaddleOCR-VL*: 80.0 / 85.7 / 84.1 / 79.9
  - Marker 1.10.1: 76.1 / 83.8 / 72.9 / 80.0
  - DeepSeek-OCR: 75.7 / 77.2 / 80.2 / 66.4
  - MinerU 2.5.4*: 75.2 / 76.6 / 84.9 / 78.2
  - Mistral OCR API: 72.0 / 77.2 / 60.6 / 71.3
- Marker's own olmOCR-Bench table (vendor-reported; throughput measured on one B200 GPU host), as overall / born-digital-only / throughput ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)):
  - Marker balanced (GPU): 76.0 / 83.5 / 2.9 pages/s
  - MinerU pipeline (GPU): 72.7 / 83.3 / 0.54 pages/s
  - Marker fast (GPU): 66.6 / 71.6 / 7.4 pages/s
  - docling (GPU): 50.3 / 64.0 / 2.1 pages/s
  - Marker fast with no OCR (CPU): 43.6 / 55.8 / 23.7 pages/s
  - Marker's no-OCR CPU mode by category: arXiv math 0.0, Tables 46.1, Multi column 67.0, Headers and footers 92.8, Baseline 85.9. Marker says its fast mode "reads equations from the PDF text layer rather than VLM-OCRing them, so LaTeX-level math tests (arXiv math) mostly miss" ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)).
- **OmniDocBench v1.6_full** end-to-end leaderboard. Overall = ((1 − text edit distance) × 100 + table TEDS + formula CDM) / 3 ([OmniDocBench README](https://raw.githubusercontent.com/opendatalab/OmniDocBench/HEAD/README.md)):
  - Specialized VLMs lead: TeleOCR 96.91, PaddleOCR-VL-1.6 96.34, MinerU2.5-Pro 95.75, MinerU-2.5 93.04, Gemini 3 Pro 92.91, olmOCR 85.74, Mistral OCR 85.66.
  - The only "Pipeline Tools" rows are MinerU-Pipeline at 86.47 (text edit 0.055, formula CDM 83.07, table TEDS 81.88, reading-order edit 0.153) and Marker at 78.44 (0.157, 85.24, 65.77, 0.243).
  - Docling, Unstructured, Nougat and Mathpix were evaluated in earlier versions, according to the update log and model list, but are not in the v1.6 table ([OmniDocBench README](https://raw.githubusercontent.com/opendatalab/OmniDocBench/HEAD/README.md)).
- **OpenDataLoader benchmark** (vendor-reported; "200 real-world PDFs including multi-column and scientific papers"), as overall / reading order / table / seconds per page ([OpenDataLoader README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md)):
  - opendataloader hybrid: 0.907 / 0.934 / 0.928 / 0.463
  - docling: 0.882 / 0.898 / 0.887 / 0.762
  - marker: 0.861 / 0.890 / 0.808 / 53.9
  - unstructured hi_res: 0.841 / 0.904 / 0.588 / 3.0
  - opendataloader local: 0.831 / 0.902 / 0.489 / 0.015
  - mineru: 0.831 / 0.857 / 0.873 / 5.96
  - pymupdf4llm: 0.732 / 0.885 / 0.401 / 0.091
  - unstructured (fast): 0.686 / 0.882 / 0.000 / 0.077
  - markitdown: 0.589 / 0.844 / 0.273 / 0.114
  - The same table lists marker as GPL-3.0 and mineru as AGPL-3.0. This contradicts the current licenses: Marker's code is Apache-2.0 ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)) and MinerU uses Apache-2.0 plus extra terms ([MinerU LICENSE](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/LICENSE.md)). The table is at least partly stale.
- The Docling score differs across vendor benchmarks: 50.3 on olmOCR-Bench in Marker's table ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)) versus 0.882 overall in OpenDataLoader's table ([OpenDataLoader README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md)). These use different metrics, so they are not directly comparable.
- GROBID's own end-to-end benchmarks are covered under GROBID below and in section 5 ([GROBID PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)).

#### Tool records (facts only; verdicts are in Inferences)

**GROBID** — https://github.com/kermitt2/grobid
- **Extracts**:
  - Header metadata, reference extraction and parsing, citation contexts linked to their references, and full-text structure: "paragraph, section titles, reference and footnote callouts, figures, tables, data availability statements". It uses 68 final labels ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
  - Version 0.9.0 added extraction of conflict-of-interest and author-contribution statements, of figures, tables and equations from back and annex sections, and of URLs from PDF annotations ([CHANGELOG](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)).
- **Anchors**:
  - A `@coords` attribute (page,x,y,w,h, several boxes joined by ";") can be requested with `teiCoordinates` for `ref`, `biblStruct`, `persName`, `figure` (figures and tables), `formula`, `head`, `s` (sentences, when `segmentSentences` is used), `p`, `note` (footnotes), `title` and `affiliation`.
  - Origin is the upper-left corner, units are PDF units, and the first page is 1. Page sizes are given in `<facsimile>` ([Coordinates doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Coordinates-in-PDF.md)).
  - `includeRawCitations=1` returns the raw reference strings, and `start`/`end` limit the page range ([service doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-service.md)).
- **Accuracy** (README):
  - References: about .87 F1 on 1,943 PubMed Central PDFs (90,125 references) and about .90 on 2,000 bioRxiv PDFs, with the deep-learning citation model.
  - Citation-context resolution: .76–.91 F1, depending on the collection.
  - References parsed in isolation: above .90 F1 at instance level and .95 F1 at field level ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
- **Accuracy** (v0.9.0 PMC benchmark, strict / soft-match F1) ([PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)):
  - section_title 70.0 / 75.21
  - table_title 57.3 / 79.79
  - figure_title 29.09 / 72.67
  - reference_citation 58.47 / 62.78
  - reference_table 86.14 / 86.31
  - The documentation warns that full-text scores against JATS "are thus not very meaningful in absolute term".
- **Model defaults**: CRF models only, "to accommodate 'out of the box' hardware". The docs say "Some GROBID Deep Learning models perform significantly better than default CRF, in particular for bibliographical reference parsing" ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)). The full image adds "2-4 points in terms of F1-score for bibliographical reference parsing and 2-5 points in term of citation context identifications" over the CRF-only image ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md)).
- **Speed**:
  - 1,943 PMC PDFs took 1,467 s (0.75 s per PDF) with deep-learning models on 16 CPUs plus a GTX 1080 Ti. With CRF-only models they took 470 s (0.24 s per PDF) on 4 CPUs with 8 threads ([PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)).
  - On bioRxiv: 0.85 s per PDF and 0.31 s per PDF respectively ([bioRxiv benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-biorxiv.md)).
  - 10.6 PDFs per second on one 16-CPU machine ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
- **License**: Apache-2.0 ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
- **Install**:
  - Docker "full" image of about 8 GB (deep learning plus CRF, "recommended to run it with a GPU") or "crf" image of about 500 MB. 4 GB of RAM is recommended for full-text processing. Docker GPU use works only on Linux ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md)).
  - Native builds need OpenJDK 21 and run on Linux 64-bit or macOS (Intel and ARM). The README says: "We cannot ensure currently support for Windows as we did before" ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
  - The ARM64 Docker documentation is inconsistent. The Docker doc says the images "are currently only for amd64" and run emulated on macOS/arm64, and also tells users to pass `--platform linux/amd64` ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md)). The 0.9.0 changelog lists "Multi-architecture Docker builds with ARM64 support" ([CHANGELOG](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)).
  - Version 0.9.1 fails fast at startup when the grobid-home path contains spaces and the Wapiti engine is configured ([CHANGELOG](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)).
- **Maintenance**:
  - 0.9.1 (2026-08-04) and 0.9.0 (2026-04-07). Version 0.9.1 made pdfalto output deterministic; before that, "the same PDF could yield different `<TextLine>`" grouping ([CHANGELOG](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)).
  - The Python client grobid-client-python 0.2.1 was released 2026-10-16 ([PyPI](https://pypi.org/project/grobid-client-python/)).
  - Public demo servers run on Hugging Face ("runs however on CPU only") ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).

**PyMuPDF** — https://github.com/pymupdf/PyMuPDF
- **Version, license, size**: 1.28.2 (2026-08-06), "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License". Wheels are 18–24 MB with no Python dependencies ([PyPI](https://pypi.org/project/PyMuPDF/)).
- **Extracts and anchors**: `page.get_text()` options text, blocks, words, dict, rawdict, json, xml and html, each with an optional `clip` rectangle. `page.find_tables()` extracts tables ([page.rst](https://raw.githubusercontent.com/pymupdf/PyMuPDF/HEAD/docs/page.rst)).
- **Speed**: pdfplumber's README says PyMuPDF "is substantially faster than pdfminer.six (and thus also pdfplumber)" ([pdfplumber README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md)).
- **Upcoming change**: the pymupdf4llm GitHub README is now a placeholder stating that "the pymupdf-2.x package now contains the 4llm code" ([pymupdf4llm GitHub README](https://raw.githubusercontent.com/pymupdf/pymupdf4llm/HEAD/README.md)). PyPI's latest PyMuPDF on 2026-10-17 was still 1.28.2 ([PyPI](https://pypi.org/project/PyMuPDF/)).

**pymupdf4llm** — https://github.com/pymupdf/pymupdf4llm
- **Version, license, dependencies**: 1.28.2 (2026-08-06), AGPL-3.0 or commercial. It depends on `pymupdf` and `pymupdf_layout` ([PyPI](https://pypi.org/project/pymupdf4llm/)).
- **Layout model**: PyMuPDF Layout (42.9 MB wheel, onnxruntime, AGPL or commercial) "trains Graph Neural Networks directly on PDF internals", runs CPU-only ([PyPI pymupdf-layout](https://pypi.org/project/pymupdf-layout/)).
- **Outputs and anchors**: Markdown, JSON and text. `to_json()` "Returns bounding box info, layout data, and text per element". `page_chunks=True` returns `metadata`, `toc_items`, `page_boxes` and `text` ([PyPI](https://pypi.org/project/pymupdf4llm/)).
- **Features**: multi-column reading order, table detection (Markdown or `table_output="html"`), header and footer detection, and "hybrid OCR" through Tesseract only where needed ([PyPI](https://pypi.org/project/pymupdf4llm/)).
- **Accuracy**: OpenDataLoader's vendor-reported scores are in the Benchmarks list above.

**pdfplumber** — https://github.com/jsvine/pdfplumber
- **Version, license, dependencies**: 0.11.10 (2026-06-15), MIT. It depends on pdfminer.six, pypdfium2 and Pillow ([PyPI](https://pypi.org/project/pdfplumber/)).
- **Anchors**: every character object has `x0`, `x1`, `top`, `bottom` and `doctop`.
- **Extraction**: `extract_words`, `extract_text(layout=...)`, and the experimental `extract_text_lines` and `search()`, which return matching characters.
- **Cropping and images**: `crop()` and `within_bbox()`; `to_image(resolution=...)` "works as expected with `Page.crop(...)`"; visual debugging with `debug_tablefinder`.
- **Tables**: table finder with `lines`, `lines_strict`, `text` and `explicit` strategies.
- **Limits**: "Works best on machine-generated, rather than scanned, PDFs"; no OCR ([README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md)).
- **Maintenance**: last commit 2026-06-14 ([repo](https://github.com/jsvine/pdfplumber)).

**pdfminer.six** — https://github.com/pdfminer/pdfminer.six
- 20260107 (2026-01-07), MIT ([PyPI](https://pypi.org/project/pdfminer.six/)).
- It can "get the exact location, font or color of the text" and does automatic layout analysis. It is "community-maintained with limited maintainer availability" ([README](https://raw.githubusercontent.com/pdfminer/pdfminer.six/HEAD/README.md)).

**pypdf** — https://github.com/py-pdf/pypdf
- 6.21.1 (2026-10-17), BSD-3-Clause, pure Python ([PyPI](https://pypi.org/project/pypdf/)).
- `extract_text(extraction_mode="layout")`. Visitor callbacks receive the text with its current transformation matrix (cm), text matrix (tm), font dictionary and font size.
- The docs warn: "In complicated documents, the calculated positions may be difficult to determine". There is no OCR ([extract-text docs](https://raw.githubusercontent.com/py-pdf/pypdf/HEAD/docs/user/extract-text.md)).

**pypdfium2** — https://github.com/pypdfium2-team/pypdfium2
- 5.14.0 (2026-10-04), BSD-3-Clause and Apache-2.0 (PDFium), prebuilt wheels of about 3 MB ([PyPI](https://pypi.org/project/pypdfium2/)). It has no mandatory runtime dependencies apart from Python and PDFium, which is bundled.
- Text can be read by rectangle (`get_text_bounded`) or by character range, and searched; search returns (char_index, char_count). Pages can be rendered ([README](https://raw.githubusercontent.com/pypdfium2-team/pypdfium2/HEAD/README.md)).

**pdftotext / poppler**
- The PyPI `pdftotext` package (4.0.0, MIT) is only a binding. It needs poppler C++ development libraries, for example `apt install libpoppler-cpp-dev` or `brew install poppler` ([binding README](https://raw.githubusercontent.com/jalan/pdftotext/HEAD/README.md); [PyPI](https://pypi.org/project/pdftotext/)).
- The poppler CLI manuals for `-bbox-layout`, `pdftoppm` and `pdffonts` could not be fetched this session (see Gaps).

**pdfalto** (GROBID's PDF layer) — https://github.com/kermitt2/pdfalto
- GPL-2.0, Xpdf-based. Converts PDF to ALTO XML, with options for image coordinates, per-group vector boxes, outlines and annotations ([README](https://raw.githubusercontent.com/kermitt2/pdfalto/HEAD/Readme.md)).
- New Python bindings 0.6.3 (2026-09-09), with 18.5–19 MB wheels ([PyPI](https://pypi.org/project/pdfalto/)).

**Marker** — https://github.com/datalab-to/marker
- **Version and license**: 2.0.0 (2026-07-20) ([PyPI](https://pypi.org/project/marker-pdf/)). Code is Apache-2.0. Model weights use "a modified AI Pubs Open Rail-M license (free for research, personal use, and startups under $5M funding/revenue)".
- **Inputs and outputs**: PDF, images, PPTX, DOCX, XLSX, HTML and EPUB. Output is Markdown, JSON (a block tree where each block has a 4-corner `polygon`), HTML or chunks.
- **Hardware**: runs on GPU, CPU or MPS. Layout, OCR and tables go through a surya VLM served by vllm (NVIDIA) or llama.cpp `llama-server` (CPU or Apple Silicon). `--mode fast` is the CPU default. `--disable_ocr` gives "pure text-layer extraction; equations and scanned pages are skipped".
- **Privacy**: `--use_llm` defaults to a Google Gemini service ([README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)).
- **Surya**: same split, Apache-2.0 code and OpenRAIL-M weights ([Surya README](https://raw.githubusercontent.com/datalab-to/surya/HEAD/README.md)).

**MinerU** — https://github.com/opendatalab/MinerU
- **Version**: `mineru` 4.0.12 (2026-10-11) ([PyPI](https://pypi.org/project/mineru/)).
- **License**: "MinerU Open Source License", which is Apache-2.0 plus extra terms. A commercial license is required above 100 million monthly active users or USD 20 million monthly revenue, online services must give attribution, and rights terminate automatically on breach ([LICENSE](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/LICENSE.md)). The old `magic-pdf` package is AGPL-3.0, last released 1.3.12 on 2025-05-24 ([PyPI magic-pdf](https://pypi.org/project/magic-pdf/)).
- **Tiers**: Flash, Basic, Standard and Advanced. Office, EPUB, HTML and CSV files use local "Flash" native parsing.
- **Hardware needs** ([README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md)):
  - By default, small models run on ONNX CPU and the VLM runs on llama.cpp (Vulkan).
  - The `basic` tier on ONNX needs about 0.8 GB of models and 2 GB of RAM: "None (CPU works)".
  - `standard`/`advanced` on ONNX plus llama.cpp need about 2 GB of models and 8 GB of RAM: "CPU works, Vulkan recommended".
  - Intel Macs map to `basic`.
- **Anchors**: stable locators of the form `doc:{short_id}/tier:{tier}/page:{page_no}/block:{block_no}`, and blocks can be exported as images ([README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md)).
- **Privacy**: documents are "not automatically uploaded". MinerU "may collect anonymous ... telemetry", which can be disabled ([README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md)).
- **Agent skill**: MinerU ships its own agent skill, installed with `npx skills add opendatalab/MinerU --skill mineru`. Its text tells agents to "Use another tool only when the user explicitly requests it, the format is unsupported, the MinerU CLI is unavailable, or all user-approved MinerU recovery paths have failed" ([README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md)).

**Docling** (IBM, now docling-project) — https://github.com/docling-project/docling
- **Version and license**: 2.140.0 (2026-10-16) ([PyPI](https://pypi.org/project/docling/)). Code is MIT; "For individual model usage, please refer to the model licenses" ([README](https://raw.githubusercontent.com/docling-project/docling/HEAD/README.md)).
- **Formats**: PDF, DOCX, PPTX, XLSX, HTML, LaTeX, JATS and more ([supported formats](https://raw.githubusercontent.com/docling-project/docling/HEAD/docs/usage/supported_formats.md)).
- **Features**: "page layout, reading order, table structure, code, formulas"; lossless JSON export; optional GraniteDocling (258M) VLM pipeline ([README](https://raw.githubusercontent.com/docling-project/docling/HEAD/README.md)).
- **Tables**: TableFormer "recognizes the structure of a table and the bounding boxes of the table content". The datasets it lists include PubTabNet and FinTabNet ([PyPI docling-ibm-models](https://pypi.org/project/docling-ibm-models/)).
- **Anchors**: items carry provenance entries (`ProvenanceItem`) with `page_no` and `bbox`; the code also handles a `charspan` ([docling-core document.py](https://raw.githubusercontent.com/docling-project/docling-core/HEAD/docling_core/types/doc/document.py)).
- **Install**:
  - `pip install docling` installs `docling-slim[standard]`, which pulls `torch`, `torchvision` and `docling-ibm-models`. The `docling-slim` extras allow format-only installs, for example `format-docx` (python-docx) or `format-latex` (pylatexenc) ([pyproject](https://raw.githubusercontent.com/docling-project/docling/HEAD/pyproject.toml)).
  - Works on macOS, Linux and Windows, x86_64 and arm64 ([installation](https://raw.githubusercontent.com/docling-project/docling/HEAD/docs/getting_started/installation.md)). On macOS x86_64, PyTorch stopped after 2.2.2, so users "must" run NumPy 1.x. Fully offline runs work via `artifacts_path` ([FAQ](https://raw.githubusercontent.com/docling-project/docling/HEAD/docs/faq/index.md)).
- **Speed**: the standard pipeline without OCR runs CPU-only at 1.5 pages/s (Linux, Ryzen 7 9800, 16 PyTorch threads) and 1.2 pages/s (Windows 11, same CPU), against 3.1–7.9 pages/s on GPUs ([gpu.md](https://raw.githubusercontent.com/docling-project/docling/HEAD/docs/usage/gpu.md)).

**Unstructured** — https://github.com/Unstructured-IO/unstructured
- 0.27.28 (2026-10-16), Apache-2.0, "Beta", Python >=3.11 and <3.14 ([PyPI](https://pypi.org/project/unstructured/)).
- PDF strategies are `auto`, `hi_res`, `fast` and `ocr_only` ([pdf.py](https://github.com/Unstructured-IO/unstructured/blob/HEAD/unstructured/partition/pdf.py)). Elements carry `page_number` and `CoordinatesMetadata` ([elements.py](https://github.com/Unstructured-IO/unstructured/blob/HEAD/unstructured/documents/elements.py)).
- Extras are installed per format, system packages such as `libmagic-dev` are needed, and multi-platform Docker images exist ([README](https://raw.githubusercontent.com/Unstructured-IO/unstructured/HEAD/README.md)).

**Nougat** (Meta) — https://github.com/facebookresearch/nougat
- Last PyPI release 0.1.17 (2023-10-04) ([PyPI](https://pypi.org/project/nougat-ocr/)); last commit 2025-02-21 ([repo](https://github.com/facebookresearch/nougat)).
- Code is MIT and "model weights are licensed under CC-BY-NC".
- It was trained on arXiv and PMC. Its `[MISSING_PAGE]` failure detection gives false positives "when computing on CPU or older GPUs" ([README](https://raw.githubusercontent.com/facebookresearch/nougat/HEAD/README.md)).

**olmOCR** (AllenAI) — https://github.com/allenai/olmocr
- 0.4.27 (2026-03-12), Apache-2.0 ([PyPI](https://pypi.org/project/olmocr/)).
- It is a 7B VLM that "requires a GPU": at least 12 GB of GPU RAM and 30 GB of disk. The Docker image is about 30 GB. Hosted API providers are also listed, at about $0.07–0.10 per million input tokens ([README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md)).

**Mathpix** (commercial cloud API) — https://mathpix.com
- The official client `mpxpy` 0.0.23 (2026-09-22) is MIT-licensed ([PyPI](https://pypi.org/project/mpxpy/)).
- It returns DOCX, Markdown, Mathpix Markdown (MMD) and a `lines.json` output via `to_lines_json_file` ([mpxpy README](https://raw.githubusercontent.com/Mathpix/mpxpy/HEAD/README.md)).
- The Mathpix documentation site was unreachable (see Gaps).

**science-parse** (AllenAI) — https://github.com/allenai/science-parse
- Extracts title, authors, abstract, sections, bibliography and "Mentions" (citation locations). The README points to "New version: SPv2" ([README](https://raw.githubusercontent.com/allenai/science-parse/HEAD/README.md)).
- Last commit 2019-10-07 ([repo](https://github.com/allenai/science-parse)).

**CERMINE** — https://github.com/CeON/CERMINE
- A Java library and web service that extracts metadata, full text and parsed references, and parses reference strings. Output formats include BibTeX. License: AGPL-3.0 ([README](https://raw.githubusercontent.com/CeON/CERMINE/HEAD/README.md)).
- Last commit 2018-02-04 ([repo](https://github.com/CeON/CERMINE)).

**papermage** (AllenAI) — https://github.com/allenai/papermage
- 0.20.0 (2024-04-05), Apache-2.0, built on pdfplumber ([PyPI](https://pypi.org/project/papermage/)).
- The README says: "research prototype for EMNLP 2023 ... unlikely to be addressing issues / maintaining this on a regular cadence" ([README](https://raw.githubusercontent.com/allenai/papermage/HEAD/README.md)).
- Last commit 2024-11-07 ([repo](https://github.com/allenai/papermage)).

**S2ORC doc2json** — https://github.com/allenai/s2orc-doc2json
- Converts GROBID's TEI output to JSON. The GROBID setup script is "hard-coded as version 0.7.3". LaTeX input needs `latexpand` and `tralics`.
- The README says the pipeline "will miss text or make errors on most PDFs" ([README](https://raw.githubusercontent.com/allenai/s2orc-doc2json/HEAD/README.md)).
- Last commit 2023-08-22 ([repo](https://github.com/allenai/s2orc-doc2json)). The PyPI package named `doc2json` is an unrelated project ([PyPI](https://pypi.org/project/doc2json/)).

**OpenDataLoader PDF** (newer entrant) — https://github.com/opendataloader-project/opendataloader-pdf
- Apache-2.0. Requires Java 11 or newer. Outputs JSON "with bounding boxes for every element" and uses XY-Cut++ reading order. Its hybrid mode routes pages to a docling-based backend ([README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md)).
- 2.5.13 (2026-10-13), with a 22.6 MB wheel ([PyPI](https://pypi.org/project/opendataloader-pdf/)).

### Inferences
- **Economics drafts.** Behavioral economics drafts are usually single-column working-paper PDFs with author-year citations, many footnotes and regression tables, and they carry less math than CS or physics papers. The hard PDF problems for this skill are therefore footnotes, the reference list, regression tables, and two-column journal reprints, more than formula OCR.
- **Quote from the text layer.** Verbatim quotes should come from the PDF text layer (pdfplumber, pypdfium2 or PyMuPDF). ML and VLM outputs re-type or normalize text and can break the design's verbatim-quote rule (section 8.1). Use ML tools for structure only, and map their blocks back to text-layer characters by bounding-box overlap.
- **Domain shift.** GROBID's numbers come from biomedical collections (PMC, bioRxiv). Accuracy on economics papers with author-year citations is untested, so the team should measure it on its own drafts.
- **Verdict per tool:**

| Tool | Role for a CPU laptop skill | Main reason |
|---|---|---|
| pdfplumber (+pdfminer.six, pypdfium2) | **Primary PDF reader** | MIT, pip-only, character boxes, crop-and-render, tables, visual debugging |
| pypdfium2 | Rendering and fast-text fallback | Permissive, small wheel, already a pdfplumber dependency |
| pypdf | Metadata, page sizes, fallback text | Pure Python, BSD; weak positions |
| PyMuPDF / pymupdf4llm | Optional fast path if AGPL is acceptable | Fastest, rich positions, multi-column layout; AGPL or commercial license |
| GROBID (Docker crf image) | **Optional enhancer** for references, citation contexts, sentence and footnote coordinates | Best evidence for scholarly structure; needs Docker, and Windows is not supported natively |
| Docling | Optional heavy fallback for hard layouts and tables | MIT with provenance, but PyTorch install and about 1.2–1.5 pages/s on a 16-thread CPU |
| MinerU 4 (basic tier) | Optional fallback for scanned or complex PDFs | CPU works with ONNX; custom license terms, telemetry (can be disabled), its own agent skill competes for control |
| Marker 2 | Not the default | Weights restricted for larger companies; CPU mode is weak without the VLM server |
| Unstructured | Not needed | Heavier than pdfplumber for the same text-layer result; hi_res needs extra models |
| olmOCR, Nougat, Marker balanced, MinerU VLM | Avoid on laptops | GPU-bound; Nougat weights are non-commercial and the project is stale |
| Mathpix, hosted GROBID demo | Only with explicit user consent | The unpublished draft leaves the laptop |
| science-parse, CERMINE, papermage, doc2json | Avoid | Unmaintained since 2018–2024; CERMINE is AGPL |
| OpenDataLoader | Watch | Promising bounding-box JSON, but needs Java and its claims are vendor-only |

- **AGPL.** For PyMuPDF, AGPL duties mainly apply when the software is conveyed to others or offered over a network. A skill shared inside one team that lists PyMuPDF in `requirements.txt` is a lower-risk case than publishing it. This is not legal advice; the team should check with counsel or choose the permissive default.

### Gaps
- Independent comparison papers could not be re-read: arxiv.org was blocked and the search budget was exhausted. These include Adhikari & Agarwal 2024 (arXiv 2410.09871), which compares PyMuPDF, pypdf, pdfplumber, Nougat, GROBID and others on DocLayNet categories, and Meuschke et al. 2023 (arXiv 2303.09957), which benchmarks GROBID, CERMINE and others on academic documents. Their findings are not used here.
- No benchmark seen this session measures reading order on two-column papers for the plain text-layer libraries (pdfplumber, pypdf, pdftotext, pypdfium2). No benchmark uses economics papers.
- No laptop CPU timings were found. Docling's CPU numbers are from a 16-thread desktop CPU.
- Mathpix pricing, data retention and the `lines.json` schema were not verified: docs.mathpix.com did not resolve.
- The poppler manuals (`pdftotext -bbox-layout`, `pdftoppm` cropping, `pdffonts`) could not be fetched.
- The science-parse license was not checked.
- The meaning of the asterisks in the olmOCR-Bench table was not checked.

## 2. Positions and anchors: page, line and bounding boxes for tracing quotes and cropping figures

### Takeaway
Character-level boxes are the most reliable base for "page N, line M" anchors and for checking quotes verbatim. pdfplumber (MIT) and PyMuPDF (AGPL) provide them. GROBID adds coordinates for semantic units (sentences, paragraphs, references, citation callouts, footnotes, figures, formulas). Docling, Marker, MinerU, pymupdf4llm and Unstructured give block-level boxes.

For LaTeX, `file:line` anchors come from parsers that keep source offsets (tree-sitter-latex, pylatexenc, TexSoup) and from flachtex's origin mapping after flattening. Word files have no page geometry, so anchors must be paragraph-based. Page images need a renderer such as LibreOffice.

### Cited Findings
| Tool | Position output | Granularity | Source |
|---|---|---|---|
| pdfplumber | `x0, x1, top, bottom, doctop` for every character, line, rect, curve and image; `extract_words`, `extract_text_lines` (experimental), `search()` returning characters; `crop()` and `to_image(resolution=)` | character, word, line | [README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md) |
| PyMuPDF | `get_text("words" / "dict" / "rawdict" / "json")` with a `clip` rectangle | character (rawdict), span, line, block, word | [page.rst](https://raw.githubusercontent.com/pymupdf/PyMuPDF/HEAD/docs/page.rst) |
| pymupdf4llm | `to_json()` with bbox per element; `page_chunks=True` gives `page_boxes` | layout element | [PyPI](https://pypi.org/project/pymupdf4llm/) |
| pdfminer.six | "exact location, font or color of the text"; layout analysis | character, line, box | [README](https://raw.githubusercontent.com/pdfminer/pdfminer.six/HEAD/README.md) |
| pypdfium2 | text by rectangle, by character range, search returning character index and count; rendering | character index, rectangle | [README](https://raw.githubusercontent.com/pypdfium2-team/pypdfium2/HEAD/README.md) |
| pypdf | visitor callbacks with the cm and tm matrices; "positions may be difficult to determine" | text chunk (matrix only) | [docs](https://raw.githubusercontent.com/py-pdf/pypdf/HEAD/docs/user/extract-text.md) |
| GROBID | `@coords` "page,x,y,w,h" on ref, biblStruct, persName, figure (and table), formula, head, s, p, note, title, affiliation; page sizes in `<facsimile>`; origin top-left, first page is 1 | semantic unit | [Coordinates doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Coordinates-in-PDF.md) |
| pdfalto | ALTO XML (the layer under GROBID), plus image and vector-box coordinates, outlines, annotations | text line, string | [README](https://raw.githubusercontent.com/kermitt2/pdfalto/HEAD/Readme.md) |
| Docling | provenance entries (`ProvenanceItem`) with `page_no` and `bbox`, plus `charspan` | layout item | [docling-core](https://raw.githubusercontent.com/docling-project/docling-core/HEAD/docling_core/types/doc/document.py) |
| Marker | JSON block tree with a 4-corner `polygon`; top-left first, clockwise | block | [README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md) |
| MinerU 4 | locators `doc:{id}/tier:{tier}/page:{n}/block:{m}`; `mineru read ... --format image` exports a block image | block | [README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md) |
| Unstructured | `page_number` and `CoordinatesMetadata` per element | element | [elements.py](https://github.com/Unstructured-IO/unstructured/blob/HEAD/unstructured/documents/elements.py) |
| OpenDataLoader | "Bounding boxes for every element" | element | [README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md) |
| Mathpix | `lines.json` output exists; schema not verified | line (claimed) | [mpxpy README](https://raw.githubusercontent.com/Mathpix/mpxpy/HEAD/README.md) |
| tree-sitter (LaTeX grammar) | every node has `start_point` and `end_point` as (row, column) | syntax node | [py-tree-sitter README](https://raw.githubusercontent.com/tree-sitter/py-tree-sitter/HEAD/README.md) |
| pylatexenc | nodes carry `pos` and `len`; `pos_to_lineno_colno()` | node | [_walker.py](https://raw.githubusercontent.com/phfaist/pylatexenc/HEAD/pylatexenc/latexwalker/_walker.py) |
| TexSoup | `position` ("NOT updated as the parsed tree is modified") and `char_pos_to_line()` | node | [data.py](https://raw.githubusercontent.com/alvinwan/TexSoup/HEAD/TexSoup/data.py) |
| flachtex | `get_origin_of_line(line, col)` and `get_origin(pos)` return the origin file and position; "Any character in the output can be traced back to its origin" | character | [README](https://raw.githubusercontent.com/d-krupke/flachtex/HEAD/README.md) |
| YaLafi | "mapping of character positions between LaTeX and plain text"; LanguageTool messages mapped back to lines and columns | character | [README](https://raw.githubusercontent.com/matze-dd/YaLafi/HEAD/README.md) |
| SyncTeX | "Synchronization for TeX" between the text editor and the PDF viewer (stable branch 2026.1) | source line ↔ PDF position | [README](https://raw.githubusercontent.com/jlaurens/synctex/HEAD/README.md) |
| docx2python | each `Par` keeps "a pointer to the xml element from which the paragraph was extracted", plus its Word style | paragraph | [README](https://raw.githubusercontent.com/ShayHill/docx2python/HEAD/README.md) |
| pandoc | `sourcepos` exists only for `commonmark` and `djot` input, so the LaTeX and docx readers give no positions | none | [MANUAL](https://raw.githubusercontent.com/jgm/pandoc/HEAD/MANUAL.txt) |

- Coordinate systems differ between tools. GROBID says: "match the page dimensions reported by GROBID ... with those from your tool, then scale accordingly" ([Coordinates doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Coordinates-in-PDF.md)). pdfplumber reports both `top` (from the top of the page) and `y0`/`y1` (from the bottom) ([README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md)).
- GROBID expands typographic ligatures (fi, fl, ff) when cleaning text ([CHANGELOG 0.9.1](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)). Its text can therefore differ from the raw text layer at the character level.

### Inferences
- **PDF anchor design.**
  - Build lines from pdfplumber words: split each page into columns by clustering x positions, then group words by `top` within a tolerance.
  - Number the lines per page in reading order. Store, per line, the page, column, line number, bounding box, character offsets in a page string, and the raw and normalized text.
  - Record "page N, line M" plus the bounding box, so a reviewer can highlight the quote.
  - When GROBID is available, attach its sentence and paragraph boxes and match them to text-layer lines by box intersection. This gives "sentence 4 of paragraph 2" anchors without trusting GROBID's normalized text.
- **Quote verification (`verify_quotes.py`).** Normalize before matching: NFKC, ligature expansion, removal of hyphens at line breaks, Unicode minus and dashes, curly quotes, and collapsed whitespace. Keep a map from normalized offsets back to raw character boxes, so a matched quote still points to exact coordinates.
- **Figure crops.**
  - Use GROBID `figure` coordinates if available.
  - Otherwise use pdfplumber image and curve objects, or the region above a "Figure N" caption line, then `page.crop(bbox).to_image(resolution=150–200)`.
  - This needs no poppler install, because pdfplumber renders through pypdfium2. Rendering behaviour is from the [pdfplumber README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md); the dependency is from [PyPI](https://pypi.org/project/pdfplumber/).
- **LaTeX plus PDF.** When both are supplied, a compile with `-synctex=1` (or a supplied `.synctex.gz`) could map PDF page and line findings back to `file:line`. Without SyncTeX, fuzzy-match PDF lines to flattened source text and use flachtex origins.
- **Word.** Anchors are "paragraph N under heading path" from body order, plus the XML element. Page numbers exist only after rendering, for example a LibreOffice PDF export, and may differ from Word's own pagination.

### Gaps
- No Python SyncTeX parser was verified. The `synctex` command-line `view` and `edit` interface was not checked this session.
- Docling's bounding-box origin (top-left or bottom-left) was not checked in its code.
- The Mathpix `lines.json` fields were not verified.
- Handling PDFs that print their own line numbers (LaTeX `lineno`, Word line numbering) was not researched.
- It was not verified whether Word's `w14:paraId` paragraph IDs can serve as stable paragraph anchors.

## 3. LaTeX: pylatexenc, TexSoup, plasTeX, LaTeXML, pandoc, arXiv source tools; `\input`/`\include`, user macros, mapping to source lines, BibTeX and BibLaTeX

### Takeaway
A pure-Python combination covers the design's needs without a TeX install:
- **Flattening**: flachtex (MIT) follows `\input`, `\include` and `\subimport` with character-level origin tracing, substitutes `\newcommand` macros, and strips comments and `\todo`.
- **Structure**: tree-sitter-latex (MIT, via tree-sitter-language-pack) or pylatexenc (MIT) gives labels, references, citations, sections and captions with line and column positions.
- **Bibliography**: bibtexparser v2, now stable, gives `.bib` entries with start lines and flags duplicates.

pandoc is a strong optional semantic converter (macros, `\input`, bibliographies to CSL JSON), but it has no source positions. LaTeXML and plasTeX emulate TeX fully but are heavy, and no line mapping was found for either.

### Cited Findings
- **pylatexenc** — https://github.com/phfaist/pylatexenc
  - 2.11 (2026-07-25), MIT, "Production/Stable" ([PyPI](https://pypi.org/project/pylatexenc/)); last commit 2026-08-20 ([repo](https://github.com/phfaist/pylatexenc)).
  - `latexwalker` parses into nodes and `latex2text` converts to text ([README](https://raw.githubusercontent.com/phfaist/pylatexenc/HEAD/README.rst)). Nodes carry `pos`, and `pos_to_lineno_colno()` maps an offset to a line and column ([_walker.py](https://raw.githubusercontent.com/phfaist/pylatexenc/HEAD/pylatexenc/latexwalker/_walker.py)).
  - `set_tex_input_directory()` makes `latex2text` follow `\input` and `\include` ([latex2text](https://raw.githubusercontent.com/phfaist/pylatexenc/HEAD/pylatexenc/latex2text/__init__.py)).
  - Docling's LaTeX backend is built on pylatexenc ([Docling pyproject](https://raw.githubusercontent.com/docling-project/docling/HEAD/pyproject.toml)).
- **TexSoup** — https://github.com/alvinwan/TexSoup
  - 0.3.3 (2026-04-05), BSD ([PyPI](https://pypi.org/project/TexSoup/)); last commit 2026-04-09 ([repo](https://github.com/alvinwan/TexSoup)).
  - "Fault-tolerant" search, navigation and modification of LaTeX ([README](https://raw.githubusercontent.com/alvinwan/TexSoup/HEAD/README.md)). `position` and `char_pos_to_line()` are provided ([data.py](https://raw.githubusercontent.com/alvinwan/TexSoup/HEAD/TexSoup/data.py)).
- **plasTeX** — https://github.com/plastex/plastex
  - "a LaTeX compiler written in Python" ([README](https://raw.githubusercontent.com/plastex/plastex/HEAD/README.md)).
  - 3.1 (2024-01-30), MIT ([PyPI](https://pypi.org/project/plasTeX/)); last commit 2026-01-07 ([repo](https://github.com/plastex/plastex)).
- **LaTeXML** (NIST) — https://github.com/brucemiller/LaTeXML
  - Converts TeX and LaTeX to XML, HTML, MathML, ePub and JATS. The README links a CC0 license badge ([README.pod](https://raw.githubusercontent.com/brucemiller/LaTeXML/HEAD/README.pod)).
  - The latest git tag is v0.8.8 (Changes entry dated 2024-02-29). The top Changes entry reads "0.8.9 2024-Winter" ([Changes](https://raw.githubusercontent.com/brucemiller/LaTeXML/HEAD/Changes)). Development is active: last commit 2026-09-20 ([repo](https://github.com/brucemiller/LaTeXML)).
- **pandoc** — https://github.com/jgm/pandoc
  - 3.12.1 (2026-10-07) ([changelog](https://raw.githubusercontent.com/jgm/pandoc/HEAD/changelog.md)).
  - The LaTeX reader handles `\input`, `\include` and `\subfile` ([LaTeX.hs](https://raw.githubusercontent.com/jgm/pandoc/HEAD/src/Text/Pandoc/Readers/LaTeX.hs)).
  - The `latex_macros` extension "will parse LaTeX macro definitions and apply the resulting macros to all LaTeX math and raw LaTeX".
  - `sourcepos` is limited to commonmark and djot.
  - It reads `bibtex`, `biblatex`, `csljson` and `endnotexml` bibliographies ([MANUAL](https://raw.githubusercontent.com/jgm/pandoc/HEAD/MANUAL.txt)).
  - `pypandoc-binary` 1.17 bundles the pandoc binary in 25–41 MB wheels ([PyPI](https://pypi.org/project/pypandoc-binary/)).
- **flachtex** — https://github.com/d-krupke/flachtex
  - 1.0.0 (2025-11-17), MIT, Beta, no dependencies ([PyPI](https://pypi.org/project/flachtex/)).
  - Flattens `\include`, `\input`, `\subimport` and explicit import comments. "Any character in the output can be traced back to its origin" via `get_origin_of_line()`.
  - Removes comments, `\todo{...}` and `changes`-package highlights; substitutes `\newcommand` macros; has a diff-friendly formatter ([README](https://raw.githubusercontent.com/d-krupke/flachtex/HEAD/README.md)).
- **YaLafi** — https://github.com/torik42/YaLafi
  - 1.5.0 (2024-03-26), GPL-3 ([PyPI](https://pypi.org/project/yalafi/)); maintainer changed to torik42; last commit 2024-03-26 ([repo](https://github.com/torik42/YaLafi)).
  - Plain-text extraction with position mapping for LanguageTool. "The library of LaTeX macros ... is still rather restricted" ([README](https://raw.githubusercontent.com/matze-dd/YaLafi/HEAD/README.md)).
- **tree-sitter-language-pack** — https://github.com/kreuzberg-dev/tree-sitter-language-pack
  - 1.22.1 (2026-10-12), MIT, 2.2–2.4 MB wheels ([PyPI](https://pypi.org/project/tree-sitter-language-pack/)).
  - Includes LaTeX and BibTeX grammars from latex-lsp. "Parsers are fetched on first use and cached locally"; `ts-pack download` pre-fetches them ([README](https://raw.githubusercontent.com/kreuzberg-dev/tree-sitter-language-pack/HEAD/README.md)).
  - No standalone `tree-sitter-latex` package exists on PyPI (404 on 2026-10-17).
- **tree-sitter-latex grammar** — https://github.com/latex-lsp/tree-sitter-latex
  - MIT ([LICENSE](https://raw.githubusercontent.com/latex-lsp/tree-sitter-latex/HEAD/LICENSE)); last commit 2026-08-01 ([repo](https://github.com/latex-lsp/tree-sitter-latex)).
  - Defines node types `citation`, `label_definition`, `label_reference`, `label_reference_range`, `latex_include`, `import_include`, `bibtex_include`, `biblatex_include`, `graphics_include`, `caption`, `new_command_definition`, `environment_definition`, `acronym_definition`, `acronym_reference` and `glossary_entry_definition` ([grammar.js](https://raw.githubusercontent.com/latex-lsp/tree-sitter-latex/HEAD/grammar.js)).
- **arXiv source tools**
  - `arxiv-to-prompt` 0.14.1 (2026-08-24, MIT) ([PyPI](https://pypi.org/project/arxiv-to-prompt/)) builds one LaTeX source from an arXiv ID or a local folder. It has `--no-comments` and `--no-appendix`, can expand `\newcommand` definitions inline, and lists figure paths ([README](https://raw.githubusercontent.com/takashiishida/arxiv-to-prompt/HEAD/README.md)).
  - `arxiv-latex-cleaner` 1.0.11 (2026-03-27, Apache-2.0) "Cleans the LaTeX code of your paper to submit to arXiv" ([PyPI](https://pypi.org/project/arxiv-latex-cleaner/)).
  - doc2json's `tex2json` needs `latexpand` and `tralics` ([README](https://raw.githubusercontent.com/allenai/s2orc-doc2json/HEAD/README.md)).
- **Docling LaTeX backend**: resolves relative `\input`, `\include` and `\includegraphics` paths. No provenance (line or offset) handling was found in its code ([backend.py](https://github.com/docling-project/docling/blob/HEAD/docling/backend/latex/backend.py)).
- **bibtexparser v2** — https://github.com/sciunto-org/python-bibtexparser
  - 2.1.0 (2026-10-02), MIT, "Production/Stable", Python >=3.10 ([PyPI](https://pypi.org/project/bibtexparser/)); last commit 2026-10-05 ([repo](https://github.com/sciunto-org/python-bibtexparser)).
  - Every block (`Entry`, `String`, `Preamble`, comments) carries `start_line` and `raw`.
  - Error blocks include `DuplicateBlockKeyBlock`, `DuplicateFieldKeyBlock`, `ParsingFailedBlock` and `MiddlewareErrorBlock` ([model.py](https://raw.githubusercontent.com/sciunto-org/python-bibtexparser/HEAD/bibtexparser/model.py)).
- **pybtex**: 0.26.1 (2026-04-03), MIT, Beta, "A BibTeX-compatible bibliography processor in Python" ([PyPI](https://pypi.org/project/pybtex/)).

### Inferences
- **Recommended LaTeX pipeline.**
  1. Find the main file (it contains `\documentclass`).
  2. Flatten with flachtex, keeping the origin map.
  3. Parse the flattened text with tree-sitter-latex, or pylatexenc if the grammar download is blocked, to collect sections, labels, `\ref`/`\eqref`/`\autoref`, `\cite*` keys (natbib `\citet`/`\citep`, biblatex `\textcite`/`\parencite`), captions, tables, `\newcommand` definitions and comments.
  4. Map each node's position back to `file:line` through flachtex.
  5. Parse `.bib` files with bibtexparser v2.
  6. If the user supplies `.aux`, `.bbl` or `.log` files, also read rendered reference text (`.bbl`), label numbers (`.aux`) and undefined citations or references (`.log`).
- **User macros.** Econ papers often define short macros (for example `\E`, `\Var` or treatment names). Substitute them for prose checks, and keep the raw source for quotes, because the design quotes the original. flachtex or pandoc can expand simple `\newcommand` macros, but complex `\def` or `xparse` macros will not expand reliably. Leave them raw and flag them.
- **Quote checks.** Run them against the flattened source, after collapsing whitespace and LaTeX line breaks, to match the design's `file:line` anchor rule.
- **Not recommended for the core.** LaTeXML (Perl install, Windows friction) and plasTeX (full TeX emulation, no verified line mapping) are too heavy. Pandoc is useful optionally, for example to convert `.bib` to CSL JSON or to get a semantic AST for READ checks, but its output cannot be anchored.
- **Draft leftovers.** arxiv-latex-cleaner and arxiv-to-prompt are useful references for FMT-11 (comments that would ship in an arXiv upload), but neither keeps line mapping.

### Gaps
- It was not verified whether plasTeX or LaTeXML can record source line numbers in their output.
- bibtexparser v2's handling of BibLaTeX-specific fields (`date`, `journaltitle`, `@online`) beyond generic parsing was not checked.
- Robustness of tree-sitter-latex on heavy macro packages is not benchmarked.
- The tree-sitter-language-pack grammar download host was not identified, so behaviour behind corporate proxies is unknown.

## 4. Word (.docx): python-docx, docx2python, pandoc docx reader, mammoth; comments, tracked changes, hidden text, reference-manager field codes

### Takeaway
python-docx (MIT) plus direct reading of the `.docx` XML (zipfile and lxml) is the lightest complete option. Since version 1.2, python-docx reads comments (author, initials, timestamp) and the hidden-text flag. Tracked changes and field codes still need raw XML.

pandoc with `--track-changes=all` is the only off-the-shelf converter that keeps insertions, deletions and comments with author and time. Its default `citations` extension also turns Zotero, Mendeley and EndNote field codes into native citations. docx2python is convenient for comments, footnotes and document properties, but it does not read deleted text or field instructions. mammoth accepts insertions, drops deletions and ignores comments by default.

### Cited Findings
- **python-docx** — https://github.com/python-openxml/python-docx
  - 1.2.0 (2025-06-16) "Add support for comments" ([HISTORY](https://raw.githubusercontent.com/python-openxml/python-docx/HEAD/HISTORY.rst)). No newer release as of 2026-10-17. MIT; depends on lxml ([PyPI](https://pypi.org/project/python-docx/)).
  - The `Comment` object exposes `author`, `initials`, `timestamp` and `text`, and `add_comment()` exists ([comments.py](https://raw.githubusercontent.com/python-openxml/python-docx/HEAD/src/docx/comments.py)).
  - `Font.hidden` is a "Read/write tri-state value" that "causes the text in the run to be hidden from display" ([font.py](https://raw.githubusercontent.com/python-openxml/python-docx/HEAD/src/docx/text/font.py)).
- **docx2python** — https://github.com/ShayHill/docx2python
  - 3.7.1 (2026-08-06), MIT, depends on lxml ([PyPI](https://pypi.org/project/docx2python/)); last commit 2026-08-05 ([repo](https://github.com/ShayHill/docx2python)).
  - Extracts headers, footers, text, footnotes, endnotes, document properties ("creator, lastModifiedBy"), images and paragraph styles ([README](https://raw.githubusercontent.com/ShayHill/docx2python/HEAD/README.md)).
  - Comments come as `(reference_text, author, date, comment_text)` ([README](https://raw.githubusercontent.com/ShayHill/docx2python/HEAD/README.md)).
  - Its registered XML tags include `w:t`, `m:t`, comment ranges, footnote and endnote references, hyperlinks, content controls (`w:sdt`), form fields and tables. They do not include `w:delText`, `w:instrText` or `w:vanish` ([attribute_register.py](https://github.com/ShayHill/docx2python/blob/HEAD/src/docx2python/attribute_register.py)).
- **pandoc docx reader**
  - `--track-changes=accept|reject|all`: "`all` includes all insertions, deletions, and comments, wrapped in spans with `insertion`, `deletion`, `comment-start`, and `comment-end` classes ... The author and time of change are included". Paragraph-level changes get `paragraph-insertion` and `paragraph-deletion` ([MANUAL](https://raw.githubusercontent.com/jgm/pandoc/HEAD/MANUAL.txt)).
  - `citations` extension (docx): "citations inserted by Zotero or Mendeley or EndNote plugins will be parsed as native pandoc citations" ([MANUAL](https://raw.githubusercontent.com/jgm/pandoc/HEAD/MANUAL.txt)).
  - The field parser accepts these field codes ([Fields.hs](https://raw.githubusercontent.com/jgm/pandoc/HEAD/src/Text/Pandoc/Readers/Docx/Fields.hs)):
    - `ADDIN [ZOTERO_ITEM] CSL_CITATION <json>`; the `ZOTERO_ITEM` prefix is optional, which also covers Mendeley's plain `CSL_CITATION`.
    - Bibliographies: `ADDIN ZOTERO_BIBL` and `ADDIN Mendeley Bibliography CSL_BIBLIOGRAPHY`.
    - EndNote: `ADDIN EN.CITE <xml>` and `ADDIN EN.REFLIST`.
  - EndNote citations are decoded with `readEndNoteXMLCitation`, and generated bibliographies are omitted. "Footnotes and Endnotes are silently combined" ([Docx.hs](https://raw.githubusercontent.com/jgm/pandoc/HEAD/src/Text/Pandoc/Readers/Docx.hs)).
  - Comments are read from `word/comments.xml`. The parser source contains no `vanish` (hidden text) handling ([Parse.hs](https://raw.githubusercontent.com/jgm/pandoc/HEAD/src/Text/Pandoc/Readers/Docx/Parse.hs)).
- **Zotero's** own integration code writes field codes of the form `ITEM CSL_CITATION ${code}` ([integration.js](https://raw.githubusercontent.com/zotero/zotero/HEAD/chrome/content/zotero/xpcom/integration.js)).
- **mammoth** — https://github.com/mwilliamson/python-mammoth
  - 1.13.0 (2026-09-26), BSD-2-Clause, no dependencies ([PyPI](https://pypi.org/project/mammoth/)).
  - "By default, comments are ignored". With the style map `comment-reference => sup`, "Comments will be appended to the end of the document". Footnotes and endnotes are supported, and warnings are returned as `messages` ([README](https://raw.githubusercontent.com/mwilliamson/python-mammoth/HEAD/README.md)).
  - Its ignored-element list contains `w:del` and `w:moveFrom`, while `w:ins` and `w:moveTo` are read as normal content. It reads `w:fldChar` and `w:instrText` and has no `vanish` handling ([body_xml.py](https://raw.githubusercontent.com/mwilliamson/python-mammoth/HEAD/mammoth/docx/body_xml.py)).
- **Docling's** Word backend builds a "comment_id -> comment object" map and links comments to paragraphs ([msword_backend.py](https://github.com/docling-project/docling/blob/HEAD/docling/backend/msword_backend.py)).

### Inferences
- **Recommended Word reader (`ingest.py` for .docx).**
  - Use python-docx for paragraphs, styles (heading path), tables and comments.
  - Add one pass over `word/document.xml`, `footnotes.xml`, `endnotes.xml`, `comments.xml`, `docProps/core.xml` and `docProps/custom.xml` with lxml for what python-docx does not expose:
    - insertions and deletions with author and date: `w:ins`, `w:del`, `w:delText`, `w:moveFrom`, `w:moveTo`;
    - hidden runs: `w:vanish`;
    - complex fields (`w:fldChar` begin/separate/end with `w:instrText`) and simple fields (`w:fldSimple`), covering Zotero, Mendeley and EndNote citations, table-of-contents and `REF` cross-reference fields, and stale field results for FMT-14.
- **Citation metadata.** Zotero and Mendeley field codes embed CSL JSON for every cited item. That gives exact reference metadata (title, authors, DOI where stored) for CIT-02 and CIT-03 without parsing reference strings. It also maps each in-text citation to its items, which is the CIT-01 cross-check. EndNote fields embed EndNote XML records that pandoc can decode.
- **pandoc as fallback.** Use pandoc through `pypandoc-binary` (no separate install) with `--track-changes=all` as a cross-check, or when the custom XML pass fails. Its output has no paragraph anchors, so match it back by text.
- **docx2python and mammoth.** Use docx2python only as a quick reader for comments and properties. It reads `w:t` only, so deleted text is dropped and inserted text appears unmarked. Do not rely on mammoth for hygiene checks: it accepts insertions and drops deletions.
- **Hidden text.** None of docx2python, mammoth or pandoc handles `w:vanish` in the code read. Hidden text would probably appear as ordinary text, which would hide an FMT-14 problem. Detect it explicitly with python-docx `Font.hidden` or the raw XML, and test this on a sample file.

### Gaps
- The storage format of the newer Mendeley Cite add-in (as opposed to the Mendeley Desktop plugin's `CSL_CITATION` fields) was not verified.
- Zotero's "store citations as bookmarks" mode was not verified.
- Whether EndNote sometimes keeps its record XML in binary field data (`EN.CITE.DATA`), which pandoc's parser may not read, was not verified.
- Citavi, Papers and ReadCube field codes were not verified.
- Behaviour on real tracked-change and hidden-text files was not tested. The statements above come from reading code, not from running it.

## 5. Reference-string and in-text citation parsing: AnyStyle, GROBID, CERMINE, Neural ParsCit and others, with reported accuracy

### Takeaway
Use exact metadata whenever the input has it: LaTeX `.bib` entries, and Zotero, Mendeley or EndNote field codes in Word. Parse strings only for PDFs and plain-text Word reference lists.

For string parsing, GROBID is the best-documented open parser. Its own benchmarks report about .87–.90 end-to-end F1 on biomedical PDFs, .95 field-level F1 for isolated strings with the deep-learning model, and citation-context resolution of .76–.91 F1. AnyStyle (Ruby, BSD-2) is a lighter trainable alternative, but no recent independent accuracy figures were found. CERMINE is unmaintained since 2018 and AGPL. Neural ParsCit's repository could not be reached. After parsing, match each reference to a DOI with Crossref's `query.bibliographic`.

### Cited Findings
- **GROBID reference accuracy.**
  - About .87 F1 (PMC, 90,125 references) and .90 (bioRxiv) end to end with the deep-learning citation model. Above .90 instance-level and .95 field-level F1 "in isolation". DOI/PMID resolution after consolidation is above 0.95 F1 ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
  - v0.9.0 PMC, all fields micro-average F1: strict 83.13, soft 86.35, Levenshtein 87.63. Instance-level (whole reference correct) F1: strict 44.03, Levenshtein 63.2 ([PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)).
  - bioRxiv: strict 87.4, soft 90.13, Levenshtein 91.41 ([bioRxiv benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-biorxiv.md)).
  - Citation contexts (in-text citations linked to their reference) on PMC: precision 84.55, recall 69.53, F1 76.31. GROBID predicted 59.19 contexts per article against 71.97 expected ([PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)).
  - The CRF-only image scores 2–4 F1 points lower on reference parsing and 2–5 points lower on citation contexts than the full image ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md)).
  - Citation endpoints accept `consolidateCitations` (Crossref or biblio-glutton) and `includeRawCitations` ([service doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-service.md); [README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
- **Third-party evaluations listed by GROBID**: Tkaczyk, Collins, Sheridan & Beel 2018, "Evaluation and Comparison of Open Source Bibliographic Reference Parsers: A Business Use Case" (arXiv 1802.01168); Grennan & Beel 2020 on synthetic versus real reference strings and the need for retraining and out-of-sample evaluation (arXiv 2004.10410); and the ParsCit CRF paper (LREC 2008) ([GROBID References.md](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/References.md)).
- **Tkaczyk et al. 2018 (from memory).** These numbers are recalled from the paper's abstract; arXiv was blocked this session, so they could not be re-checked. The study compared ten parsers, including Anystyle-Parser, CERMINE, GROBID, ParsCit and Science Parse. Out of the box, GROBID scored best (F1 about 0.89), then CERMINE (about 0.83) and ParsCit (about 0.75). Retraining on in-domain data improved all three, with GROBID at about 0.92 ([arXiv 1802.01168](https://arxiv.org/abs/1802.01168)). Re-verify before quoting.
- **AnyStyle** — https://github.com/inukshuk/anystyle
  - Gem 1.6.0 (2025-05-11) and anystyle-cli 1.5.0, BSD-2-Clause ([rubygems anystyle](https://rubygems.org/gems/anystyle); [rubygems anystyle-cli](https://rubygems.org/gems/anystyle-cli)). Last commit 2025-05-11 ([repo](https://github.com/inukshuk/anystyle)).
  - "A fast and smart parser of bibliographic references", with a `Parser` and a `Finder` (finds references in full documents) and custom model training. `anystyle check` "prints sequence and token error rates". The default parser model uses the "core" data set. There is a web app at anystyle.io ([README](https://raw.githubusercontent.com/inukshuk/anystyle/HEAD/README.md)).
- **CERMINE** can extract metadata from reference strings and output BibTeX. AGPL-3.0, Java; last commit 2018-02-04 ([README](https://raw.githubusercontent.com/CeON/CERMINE/HEAD/README.md); [repo](https://github.com/CeON/CERMINE)).
- **Neural ParsCit**: GROBID's docs list https://github.com/WING-NUS/Neural-ParsCit ([References.md](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/References.md)). A clone attempt on 2026-10-17 failed with an authentication prompt, which GitHub returns for missing or private repositories.
- **refextract** (CERN/INSPIRE): 1.1.7 (2026-10-01), GPL-2.0-or-later ([PyPI](https://pypi.org/project/refextract/)). Its README says that "this library cannot be locally installed on a mac" because of its `mmap` resize use ([PyPI description](https://pypi.org/project/refextract/)).
- **Science Parse** extracted the bibliography and "Mentions", meaning places where references are cited ([README](https://raw.githubusercontent.com/allenai/science-parse/HEAD/README.md)). Unmaintained since 2019 (section 1).
- **Crossref matching**: `query.bibliographic` is for "citation look up. Includes titles, authors, ISSNs and publication years". It replaced the deprecated `query.title` ([Crossref REST API doc](https://raw.githubusercontent.com/CrossRef/rest-api-doc/HEAD/README.md)).
- **pandoc** reads `bibtex`, `biblatex`, `csljson` and `endnotexml` bibliographies, which helps normalize Word and LaTeX sources to CSL JSON ([MANUAL](https://raw.githubusercontent.com/jgm/pandoc/HEAD/MANUAL.txt)).

### Inferences
- **Reference strategy by input:**
  - **LaTeX**: `.bib` via bibtexparser v2 for exact metadata; `\cite` keys from the tree-sitter `citation` node; the `.bbl` file, when present, for the rendered entries.
  - **Word with a reference manager**: CSL JSON or EndNote XML from field codes.
  - **Word or PDF with plain text references**:
    1. Split the reference section into entries. In PDFs, use hanging indents and line starts from pdfplumber coordinates.
    2. Parse each entry with GROBID's citation endpoint if it is running locally, otherwise with AnyStyle if `anystyle` is on PATH, otherwise with Claude into CSL-JSON fields.
    3. Look up and confirm every parse with Crossref `query.bibliographic` or OpenAlex before calling a reference wrong or missing (design guardrail 3).
- **In-text citations in PDF or plain Word** (economics uses author-year): use GROBID citation contexts if available. Otherwise use regular expressions for parenthetical and narrative author-year forms, such as "(Kahneman and Tversky, 1979)", "Thaler (1980)", "(e.g., Smith et al., 2019a; Lee, 2020)", "Thaler's (1980)". Then link them to references by surname and year, with a/b suffixes. Even GROBID's citation-context recall is 69.5% on PMC, so a regex fallback plus manual review is a reasonable baseline. How the two compare on economics author-year styles is untested.
- **Exact strings.** The reference text itself should always be quoted from the text layer. Parsed fields serve only for lookups.

### Gaps
- No independent, recent accuracy figures were found for AnyStyle, CERMINE or Neural ParsCit: search was exhausted, and arXiv and Semantic Scholar were blocked.
- No accuracy data was found for LLM-based reference parsing.
- No evaluation on economics reference styles (AEA, Chicago author-date) was found.

## 6. Table extraction from PDFs for checking regression tables: Camelot, tabula, pdfplumber tables, Docling, GROBID

### Takeaway
For regression tables, PDF extraction is the weakest link. Read tables from LaTeX `tabular` source or Word table XML whenever possible.

For PDFs, the pip-only options are pdfplumber's table finder, which is the lightest and has visual debugging, and Camelot 2.0. Camelot (MIT) no longer needs Ghostscript, offers lattice, stream, network and hybrid parsers plus an optional Table Transformer `ml` parser, and reports per-table accuracy and whitespace metrics. Docling's TableFormer gives the best structure among open pipelines in vendor benchmarks, but it needs PyTorch. GROBID locates tables and their captions but is not a table-structure tool. tabula needs Java.

### Cited Findings
- **Camelot** 2.0.0 (2026-06-04), MIT. Dependencies are numpy, opencv-python-headless, pandas, pillow and pypdfium2 ([PyPI](https://pypi.org/project/camelot-py/)); last commit 2026-10-14 ([repo](https://github.com/camelot-dev/camelot)).
  - "Five parsers": `lattice` for ruled tables, `stream` and `network` for whitespace-separated tables, `hybrid`, and an optional neural `ml` parser (Table Transformer). For borderless tables, `ml` "on FinTabNet ... roughly doubles borderless TEDS vs network/hybrid" (vendor claim). There is also `flavor="auto"`.
  - Each table gets "accuracy, whitespace, and a confidence score".
  - "the default pdfium backend is bundled, with no system dependencies". The built-in parsers need a text-based PDF ([README](https://raw.githubusercontent.com/camelot-dev/camelot/HEAD/README.md)).
- **tabula-py** 2.10.0 (2024-10-17), MIT. A wrapper around tabula-java that requires Java 8 or newer ([README](https://raw.githubusercontent.com/chezou/tabula-py/HEAD/README.md); [PyPI](https://pypi.org/project/tabula-py/)).
- **pdfplumber tables**: `find_tables()` and `extract_tables()` with strategies `lines`, `lines_strict`, `text` and `explicit`, explicit line lists, and `debug_tablefinder()`. It is not strong on OCR'd documents ([README](https://raw.githubusercontent.com/jsvine/pdfplumber/HEAD/README.md)).
- **PyMuPDF** has `page.find_tables()` with `vertical_strategy` and `horizontal_strategy` ([page.rst](https://raw.githubusercontent.com/pymupdf/PyMuPDF/HEAD/docs/page.rst)). pymupdf4llm can emit HTML tables ([PyPI](https://pypi.org/project/pymupdf4llm/)).
- **Docling TableFormer** recognizes table structure and cell bounding boxes, the datasets it lists include PubTabNet and FinTabNet ([PyPI docling-ibm-models](https://pypi.org/project/docling-ibm-models/)).
- **GROBID** benchmarks table captions only: table_title F1 57.3 strict and 79.79 soft on PMC ([PMC benchmark](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/benchmarks/Benchmarking-pmc.md)). It returns `figure` coordinates for figures and tables ([Coordinates doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Coordinates-in-PDF.md)).
- **Table scores in benchmarks**:
  - olmOCR-Bench Tables: Marker 1.10.1 72.9, MinerU 2.5.4 84.9, olmOCR 84.9, Chandra 88.0 ([olmOCR README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md)); Marker's CPU no-OCR mode 46.1 (vendor) ([Marker README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)).
  - OmniDocBench v1.6 table TEDS: MinerU-Pipeline 81.88, Marker 65.77 ([OmniDocBench README](https://raw.githubusercontent.com/opendatalab/OmniDocBench/HEAD/README.md)).
  - OpenDataLoader (vendor-reported) table scores: docling 0.887, mineru 0.873, marker 0.808, unstructured hi_res 0.588, opendataloader local 0.489, pymupdf4llm 0.401 ([OpenDataLoader README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md)).
- **Other light ML table tools**: `gmft` 0.4.4 (MIT, Table Transformer on PyTorch) ([PyPI](https://pypi.org/project/gmft/)); `img2table` 2.0.0 (MIT, OpenCV and pypdfium2) ([PyPI](https://pypi.org/project/img2table/)).

### Inferences
- **Typical layout.** Economics regression tables are usually typeset with booktabs: horizontal rules only, coefficients with standard errors in parentheses on the next row, significance stars, and N and R² rows. Ruled-grid methods (pdfplumber `lines`, Camelot `lattice`) will miss column boundaries.
- **Recommended PDF table settings.**
  - Start with pdfplumber `vertical_strategy="text"`, with `horizontal_strategy="lines"` or `"text"`.
  - Fall back to Camelot `network`, `hybrid` or `stream`, and use Camelot's accuracy and whitespace scores to reject bad tables.
  - Use Docling only when installed.
- **Post-processing.** Pair each coefficient row with the parenthesized SE or t row below it. Strip stars into a separate field. Keep the original cell text and bounding box for quoting.
- **Visual cross-check.** For important tables, crop the table region (pdfplumber `crop().to_image()`) and have Claude read the image. Compare its transcription with the extracted cells; a disagreement downgrades confidence. This is cheap on CPU and catches column misalignment. It is not benchmarked here.
- **Arithmetic checks (NUM-03).** Recompute t ≈ coef/SE and implied p-values against the stars, with a rounding tolerance. Parsing errors usually show up as impossible ratios, which also works as a sanity check on the extraction itself.

### Gaps
- No benchmark specific to regression or booktabs tables was found.
- Camelot's `network` and `hybrid` accuracy on borderless academic tables is not documented beyond the vendor FinTabNet claim.
- GROBID's table-content output, as opposed to captions, was not evaluated in any source read.

## 7. Recommended stack for a laptop skill (macOS or Windows, CPU only), fallbacks per format, and behaviour when a tool is missing

### Takeaway
Use a permissive, pip-only core that needs no system binaries and installs in a few tens of MB (wheel sizes are listed below; lxml and Pillow were not measured):
- **PDF**: pdfplumber (with pdfminer.six and pypdfium2) for text, positions, rendering and tables; pypdf for metadata.
- **Word**: python-docx plus lxml raw-XML passes.
- **LaTeX**: flachtex plus tree-sitter-language-pack or pylatexenc.
- **BibTeX**: bibtexparser v2.

Optional accelerators, used when present and listed as "enhanced" in the coverage table:
- GROBID's Docker CRF image, for references, citation contexts and sentence boxes;
- pandoc through `pypandoc-binary`, for tracked changes, citations and LaTeX semantics;
- Camelot, for tables;
- Docling or MinerU basic, for difficult PDFs;
- PyMuPDF, only if the AGPL license is acceptable.

GPU tools, unmaintained tools and cloud tools are excluded by default.

### Cited Findings
- **Install footprint** (wheel sizes from PyPI, 2026-10-17):
  - pdfplumber 0.1 MB, with pdfminer.six 6.6–8.5 MB and pypdfium2 about 2.7–3.4 MB ([pdfplumber](https://pypi.org/project/pdfplumber/); [pdfminer.six](https://pypi.org/project/pdfminer.six/); [pypdfium2](https://pypi.org/project/pypdfium2/))
  - pypdf about 0.4 MB ([PyPI](https://pypi.org/project/pypdf/))
  - python-docx 0.3 MB ([PyPI](https://pypi.org/project/python-docx/))
  - bibtexparser 0.1 MB ([PyPI](https://pypi.org/project/bibtexparser/))
  - flachtex under 0.1 MB ([PyPI](https://pypi.org/project/flachtex/))
  - pylatexenc 0.1–0.2 MB ([PyPI](https://pypi.org/project/pylatexenc/))
  - tree-sitter-language-pack 2.2–2.4 MB, plus a grammar download on first use ([PyPI](https://pypi.org/project/tree-sitter-language-pack/); [README](https://raw.githubusercontent.com/kreuzberg-dev/tree-sitter-language-pack/HEAD/README.md))
  - pypandoc-binary 25–41 MB ([PyPI](https://pypi.org/project/pypandoc-binary/))
  - PyMuPDF 18–24 MB ([PyPI](https://pypi.org/project/PyMuPDF/))
  - torch 2.14.1 (needed by Docling's standard install): 127 MB on macOS arm64, 124 MB on Windows amd64, 555 MB on Linux x86_64, for cp312 wheels ([PyPI torch](https://pypi.org/project/torch/))
  - onnxruntime 1.31.0: 15–24 MB ([PyPI onnxruntime](https://pypi.org/project/onnxruntime/))
  - MinerU basic tier: about 0.8 GB of models and 2 GB of RAM ([MinerU README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md))
  - GROBID Docker: about 500 MB (crf) or about 8 GB (full) ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md))
  - olmOCR Docker: about 30 GB ([olmOCR README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md))
- **Python version floors**:
  - bibtexparser, docling and mineru need Python 3.10 or newer; mineru supports up to below 3.15 ([bibtexparser](https://pypi.org/project/bibtexparser/); [docling](https://pypi.org/project/docling/); [mineru](https://pypi.org/project/mineru/)).
  - unstructured needs at least 3.11 and below 3.14 ([unstructured](https://pypi.org/project/unstructured/)).
  - pypdf needs 3.9 or newer, and pdfplumber 3.8 or newer ([pypdf](https://pypi.org/project/pypdf/); [pdfplumber](https://pypi.org/project/pdfplumber/)).
- **Platform frictions**:
  - GROBID: Windows support is not ensured ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)); Docker GPU works only on Linux ([Docker doc](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/doc/Grobid-docker.md)).
  - refextract cannot be installed on a Mac ([PyPI](https://pypi.org/project/refextract/)).
  - tabula needs Java 8 or newer ([README](https://raw.githubusercontent.com/chezou/tabula-py/HEAD/README.md)); OpenDataLoader needs Java 11 or newer ([README](https://raw.githubusercontent.com/opendataloader-project/opendataloader-pdf/HEAD/README.md)).
  - The Python `pdftotext` binding needs poppler development libraries ([README](https://raw.githubusercontent.com/jalan/pdftotext/HEAD/README.md)).
  - Docling on Intel Macs is pinned to an old PyTorch with NumPy 1.x ([FAQ](https://raw.githubusercontent.com/docling-project/docling/HEAD/docs/faq/index.md)).
  - Camelot no longer needs Ghostscript ([README](https://raw.githubusercontent.com/camelot-dev/camelot/HEAD/README.md)).
- **Privacy-relevant defaults**:
  - GROBID's public demo runs on Hugging Face ([README](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/Readme.md)).
  - Marker's `--use_llm` defaults to Gemini ([README](https://raw.githubusercontent.com/datalab-to/marker/HEAD/README.md)).
  - MinerU may send anonymous telemetry unless it is disabled ([README](https://raw.githubusercontent.com/opendatalab/MinerU/HEAD/README.md)).
  - olmOCR offers hosted inference providers ([README](https://raw.githubusercontent.com/allenai/olmocr/HEAD/README.md)).

### Inferences
- **Stack per format** (primary, then fallbacks in order):

| Need | Primary | Fallback 1 | Fallback 2 | If all are missing |
|---|---|---|---|---|
| PDF text with page/line anchors | pdfplumber | PyMuPDF (if installed and the license is accepted) | pypdfium2 text API; pypdf text gives page-level anchors only | Ask for LaTeX or Word source; report text checks as skipped |
| PDF page and figure images | pdfplumber `crop().to_image()` (pypdfium2) | pypdfium2 render | `pdftoppm` if on PATH | VISUAL checks skipped |
| PDF structure: sections, footnotes, references, citation contexts | GROBID at `localhost:8070` (crf image), sentence coordinates on | Heuristics on pdfplumber output (font size and bold for headings, small font at the page bottom for footnotes, "References" heading for the bibliography) | Docling or MinerU basic, if installed | Mark structure as heuristic |
| PDF tables | pdfplumber table finder (text strategy) | Camelot `network`/`stream` | Docling TableFormer; or crop the image and have Claude read it | Table checks downgraded to READ |
| PDF metadata, fonts, page size (FMT-02, FMT-15) | pypdf | pdfplumber character `fontname` | `pdffonts` if on PATH | — |
| LaTeX | flachtex + tree-sitter-latex | flachtex + pylatexenc | Built-in regex scanner with its own `\input` resolver | — (pure Python is always available) |
| BibTeX / BibLaTeX | bibtexparser v2 | pybtex | pandoc `bibtex`/`biblatex` reader to CSL JSON | Regex entry splitter |
| Word | python-docx + lxml XML pass | docx2python | pandoc `--track-changes=all` | Stdlib zipfile + xml.etree pass |
| Word citations | Field-code CSL JSON or EndNote XML from the XML pass | pandoc `citations` extension | Treat the reference list as plain text (section 5) | — |
| Reference strings | GROBID citation endpoint | AnyStyle CLI if on PATH | Claude parse, then Crossref `query.bibliographic` or OpenAlex match | References "unverified", with queries listed |

- **Detect, degrade, report.**
  - At the start, `ingest.py` should probe for optional tools:
    - Python packages via `importlib.util.find_spec`;
    - binaries via `shutil.which` (`docker`, `java`, `pandoc`, `pdftoppm`, `anystyle`, `soffice`);
    - a GROBID service via a short HTTP GET to `/api/isalive`. The endpoint name is not verified in the docs read here; check the GROBID service documentation.
  - Write the result to `paper-check-work/environment.json`.
  - Each check then declares what it needs. When a need is missing, the check runs a fallback with lower confidence, or it is marked "skipped (tool X missing)" in the coverage table. This matches design guardrail 4.
  - Never install anything silently. Print the one-line install command (for example `pip install camelot-py` or `docker run --rm -p 8070:8070 grobid/grobid:0.9.1-crf`) in the report's coverage section.
- **requirements.txt.**
  - Core: `pdfplumber`, `pypdf`, `python-docx`, `lxml`, `bibtexparser>=2`, `flachtex`, `pylatexenc`, and optionally `tree-sitter-language-pack`.
  - Optional extras file: `pypandoc-binary`, `camelot-py`, `grobid-client-python`, `docling`, `pymupdf`.
  - Recommend Python 3.11 or 3.12 to satisfy every package listed above.
- **Paths with spaces.** Windows and macOS users often keep drafts under paths with spaces, such as OneDrive folders; this notes folder also has spaces. Quote all paths. Prefer the GROBID Docker image over a native GROBID install, because 0.9.1 refuses grobid-home paths with spaces when Wapiti is configured ([CHANGELOG](https://raw.githubusercontent.com/kermitt2/grobid/HEAD/CHANGELOG.md)).
- **Inputs to request.** The skill should ask for LaTeX source plus the compiled PDF, or for the .docx, whenever the user provides only a PDF. Every format-specific weakness above (two-column order, math, tables, footnotes, reference parsing) disappears or shrinks with source files. This matches design section 9.
- **Third-party skills.** Do not let a third-party skill take over ingestion. MinerU's bundled skill tells agents to prefer MinerU for all parsing, which would conflict with the paper-check ingestion policy if both were installed.

### Gaps
- No laptop measurements (for example an M-series MacBook Air or a mid-range Windows laptop) were available for pdfplumber, GROBID crf or Docling on a 30–60 page draft. The team should time these on real drafts.
- GROBID's health-check endpoint name and the behaviour of the crf Docker image on Apple Silicon are unverified, because the docs conflict.
- Whether Docker Desktop is acceptable on coworkers' laptops (company policy, licensing for larger firms) is an organizational question not researched here.
- The download host used by tree-sitter-language-pack, and whether corporate proxies block it, is unknown.
