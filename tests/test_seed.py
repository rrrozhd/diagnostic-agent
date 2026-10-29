import io

from data.seed import icd11_records, pmid, us_date


def test_icd11_records_joins_unquoted_newlines():
    f = io.StringIO(
        "Foundation URI\tTitle\tCodingNote\n"
        "http://id.who.int/icd/entity/1\tA\tline one\n"
        "line two\n"
        "http://id.who.int/icd/entity/2\tB\t\n"
    )
    assert list(icd11_records(f)) == [
        "Foundation URI\tTitle\tCodingNote\n",
        "http://id.who.int/icd/entity/1\tA\tline one line two\n",
        "http://id.who.int/icd/entity/2\tB\t\n",
    ]


def test_retraction_field_normalisation():
    assert us_date("3/15/2012 0:00") == "2012-03-15"
    assert us_date("") is None
    assert pmid("0") is None
    assert pmid("18636547") == "18636547"
