"""APA entries with a month and day after the year: the date is not the title."""

import pytest

from paper_check.ingest import pdf_reader
from paper_check.ingest.docx_reader import parse_reference as parse_docx

ENTRIES = [
    ("Roe, J. (2020, December 2). New rules for small loans take effect. Example Policy Center. "
     "https://policy.example.org/news/2020/12/02/x", "New rules for small loans take effect", "December 2"),
    ("Poe, D. (2019, Oct. 21). City adopts a new transit plan. Example Public Radio.",
     "City adopts a new transit plan", "Oct. 21"),
    ("Smith, J. (2018, Spring). Saving in the gig economy. Policy Brief.", "Saving in the gig economy", "Spring"),
]


@pytest.mark.parametrize("parse", [parse_docx, pdf_reader.parse_reference], ids=["docx", "pdf"])
@pytest.mark.parametrize("entry,title,date", ENTRIES)
def test_apa_month_and_day_belong_to_the_date(parse, entry, title, date):
    fields = parse(entry)
    assert fields["year"] in ("2018", "2019", "2020")
    assert fields["title"] == title and fields["date"] == date
