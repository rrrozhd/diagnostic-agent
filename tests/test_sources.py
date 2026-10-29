import json
import os
import sqlite3

import httpx
import pytest

from app import tools
from app.tools import drug_label, pubmed_abstract, pubmed_search

live = pytest.mark.skipif(
    os.environ.get("LIVE") != "1", reason="set LIVE=1 to hit real APIs"
)

ESEARCH = {"esearchresult": {"idlist": ["111", "222"]}}
ESUMMARY = {
    "result": {
        "uids": ["111", "222"],
        "111": {
            "title": "CAP guideline",
            "fulljournalname": "Am J Respir Crit Care Med",
            "pubdate": "2019 Oct 1",
            "pubtype": ["Journal Article", "Practice Guideline"],
        },
        "222": {
            "title": "A trial",
            "source": "Lancet",
            "pubdate": "2020",
            "pubtype": ["Randomized Controlled Trial"],
        },
    }
}
EFETCH = b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>111</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue><Title>Am J Respir Crit Care Med</Title></Journal>
  <ArticleTitle>Diagnosis and treatment of <i>CAP</i></ArticleTitle>
  <Abstract><AbstractText Label="BACKGROUND">Pneumonia is common.</AbstractText>
  <AbstractText Label="RESULTS">Use amoxicillin<sup>1</sup>.</AbstractText></Abstract>
</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
LABEL = {
    "results": [
        {
            "set_id": "abc-123",
            "openfda": {"generic_name": ["LEVOFLOXACIN"], "brand_name": ["Levaquin"]},
            "indications_and_usage": ["Pneumonia.", "Sinusitis."],
            "contraindications": ["Hypersensitivity."],
            "warnings": ["Tendon rupture."],
            "boxed_warning": ["x" * 5000],
        }
    ]
}


@pytest.fixture
def http(monkeypatch):
    """Route tool HTTP calls to a handler; returns the list of requests seen."""
    seen = []

    def use(handler):
        def record(request):
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(
            tools, "_http", httpx.Client(transport=httpx.MockTransport(record))
        )
        return seen

    monkeypatch.setattr(tools, "_EUTILS_MIN_INTERVAL_S", 0.0)
    return use


@pytest.fixture
def ref_db(tmp_path, monkeypatch):
    path = tmp_path / "ref.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE retraction (original_pmid TEXT, nature TEXT);
        INSERT INTO retraction VALUES ('111', 'Retraction'), ('333', 'Correction');
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(tools, "REFERENCE_DB", path)


def eutils_handler(request):
    if request.url.path.endswith("esearch.fcgi"):
        return httpx.Response(200, json=ESEARCH)
    if request.url.path.endswith("esummary.fcgi"):
        return httpx.Response(200, json=ESUMMARY)
    return httpx.Response(200, content=EFETCH)


def test_search_returns_articles(http):
    seen = http(eutils_handler)
    out = json.loads(pubmed_search.invoke({"query": 'pneumonia "guideline" & x=1'}))
    assert out[0] == {
        "pmid": "111",
        "title": "CAP guideline",
        "journal": "Am J Respir Crit Care Med",
        "year": "2019",
        "url": "https://pubmed.ncbi.nlm.nih.gov/111/",
        "pubtype": ["Journal Article", "Practice Guideline"],
    }
    assert out[1]["journal"] == "Lancet" and out[1]["year"] == "2020"
    assert seen[0].url.params["term"] == 'pneumonia "guideline" & x=1'
    assert seen[0].url.params["sort"] == "relevance"
    assert "api_key" not in seen[0].url.params


def test_search_empty_skips_summary(http):
    seen = http(lambda r: httpx.Response(200, json={"esearchresult": {"idlist": []}}))
    assert pubmed_search.invoke({"query": "nothing"}) == "[]"
    assert len(seen) == 1


def test_search_adds_api_key_when_set(http, monkeypatch):
    monkeypatch.setattr(tools, "NCBI_API_KEY", "secret")
    seen = http(eutils_handler)
    pubmed_search.invoke({"query": "x"})
    assert all(r.url.params["api_key"] == "secret" for r in seen)


def test_search_http_error_hides_url(http, monkeypatch):
    monkeypatch.setattr(tools, "NCBI_API_KEY", "secret")
    http(lambda r: httpx.Response(500))
    out = pubmed_search.invoke({"query": "x"})
    assert out.startswith("Source error:") and "500" in out and "secret" not in out


def test_search_bad_json_is_source_error(http):
    http(lambda r: httpx.Response(200, content=b"<html>"))
    assert pubmed_search.invoke({"query": "x"}).startswith("Source error:")


def test_abstract_flags_retraction(http, ref_db):
    http(eutils_handler)
    out = json.loads(pubmed_abstract.invoke({"pmid": "111"}))
    assert out["title"] == "Diagnosis and treatment of CAP"
    assert out["journal"] == "Am J Respir Crit Care Med" and out["year"] == "2019"
    assert (
        out["abstract"]
        == "BACKGROUND: Pneumonia is common.\nRESULTS: Use amoxicillin1."
    )
    assert out["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert out["retracted"] is True


@pytest.mark.parametrize("pmid", ["222", "333"])  # 333 has only a Correction
def test_abstract_not_retracted(http, ref_db, pmid):
    http(eutils_handler)
    assert json.loads(pubmed_abstract.invoke({"pmid": pmid}))["retracted"] is False


def test_abstract_truncated(http, ref_db, monkeypatch):
    monkeypatch.setattr(tools, "ABSTRACT_MAX_CHARS", 10)
    http(eutils_handler)
    assert (
        json.loads(pubmed_abstract.invoke({"pmid": "111"}))["abstract"]
        == "BACKGROUND [truncated]"
    )


def test_abstract_missing_db_gives_null(http, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "REFERENCE_DB", tmp_path / "absent.db")
    http(eutils_handler)
    assert json.loads(pubmed_abstract.invoke({"pmid": "111"}))["retracted"] is None


def test_abstract_not_found(http):
    http(
        lambda r: httpx.Response(200, content=b"<PubmedArticleSet></PubmedArticleSet>")
    )
    assert pubmed_abstract.invoke({"pmid": "999"}).startswith("Source error:")


@pytest.mark.parametrize("pmid", ["12a", "1 OR 1=1", ""])
def test_abstract_rejects_non_digit_pmid(http, pmid):
    seen = http(eutils_handler)
    assert pubmed_abstract.invoke({"pmid": pmid}).startswith("Source error:")
    assert seen == []


def test_abstract_http_error(http):
    http(lambda r: httpx.Response(429))
    assert pubmed_abstract.invoke({"pmid": "111"}).startswith("Source error: HTTP 429")


def test_label_returns_fields(http):
    seen = http(lambda r: httpx.Response(200, json=LABEL))
    [out] = json.loads(drug_label.invoke({"drug_name": "levofloxacin"}))
    assert out["set_id"] == "abc-123"
    assert out["generic_name"] == "LEVOFLOXACIN" and out["brand_name"] == "Levaquin"
    assert (
        out["url"] == "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=abc-123"
    )
    assert out["indications_and_usage"] == "Pneumonia. Sinusitis."
    assert out["warnings_and_cautions"] == "Tendon rupture."  # falls back to warnings
    assert (
        out["boxed_warning"].endswith("[truncated]")
        and len(out["boxed_warning"]) < 1600
    )
    assert seen[0].url.params["limit"] == "3"


def test_label_sanitizes_search_syntax(http):
    seen = http(lambda r: httpx.Response(200, json=LABEL))
    drug_label.invoke({"drug_name": 'x" OR openfda.route:*'})
    assert (
        seen[0].url.params["search"]
        == 'openfda.generic_name:"x OR openfda route" openfda.brand_name:"x OR openfda route"'
    )


def test_label_empty(http):
    http(lambda r: httpx.Response(404, json={"error": {"code": "NOT_FOUND"}}))
    assert drug_label.invoke({"drug_name": "notadrug"}) == "[]"


def test_label_http_error(http):
    http(lambda r: httpx.Response(503))
    assert drug_label.invoke({"drug_name": "levofloxacin"}).startswith(
        "Source error: HTTP 503"
    )


def test_label_network_error(http):
    def fail(request):
        raise httpx.ConnectError("boom", request=request)

    http(fail)
    assert (
        drug_label.invoke({"drug_name": "levofloxacin"}) == "Source error: ConnectError"
    )


@live
def test_live_pubmed_search_and_abstract():
    hits = json.loads(
        pubmed_search.invoke({"query": "community acquired pneumonia guideline"})
    )
    assert hits and all(h["pmid"].isdigit() for h in hits)
    out = json.loads(pubmed_abstract.invoke({"pmid": hits[0]["pmid"]}))
    assert out["title"] and out["abstract"] and isinstance(out["retracted"], bool)
    print(hits[0], out["title"], out["retracted"])


@live
def test_live_drug_label():
    out = json.loads(drug_label.invoke({"drug_name": "levofloxacin"}))
    assert out and out[0]["set_id"] and "LEVOFLOXACIN" in out[0]["generic_name"].upper()
    assert out[0]["indications_and_usage"]
    print(out[0]["set_id"], out[0]["brand_name"], out[0]["boxed_warning"][:80])


@live
def test_live_known_retraction_is_flagged():
    pmid = (
        sqlite3.connect(f"file:{tools.REFERENCE_DB}?mode=ro", uri=True)
        .execute(
            "SELECT original_pmid FROM retraction WHERE nature = 'Retraction' AND original_pmid IS NOT NULL LIMIT 1"
        )
        .fetchone()[0]
    )
    assert json.loads(pubmed_abstract.invoke({"pmid": pmid}))["retracted"] is True


def test_abstract_handles_book_records(http, ref_db):
    book = b"""<PubmedArticleSet><PubmedBookArticle><BookDocument><PMID>444</PMID>
      <Book><BookTitle>StatPearls</BookTitle><PubDate><Year>2024</Year></PubDate></Book>
      <ArticleTitle>Pneumonia</ArticleTitle><Abstract><AbstractText>Overview.</AbstractText></Abstract>
    </BookDocument></PubmedBookArticle></PubmedArticleSet>"""
    http(lambda r: httpx.Response(200, content=book))
    out = json.loads(pubmed_abstract.invoke({"pmid": "444"}))
    assert (out["title"], out["journal"], out["year"], out["abstract"]) == (
        "Pneumonia",
        "StatPearls",
        "2024",
        "Overview.",
    )


def test_label_malformed_payload_is_source_error(http):
    http(lambda r: httpx.Response(200, json={"results": ["not a dict"]}))
    assert drug_label.invoke({"drug_name": "x"}).startswith("Source error:")
