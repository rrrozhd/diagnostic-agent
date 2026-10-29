import json
import os
import re
import sqlite3

import httpx
import pytest

from evals.e2e_checks import (
    banned_hits,
    check_differential,
    check_refusal,
    check_treatment,
    load_patterns,
    make_resolver,
    resolve_source,
)

PATTERNS = load_patterns()
GOOD = {
    "kind": "pubmed",
    "id": "1",
    "title": "t",
    "url": "u",
    "excerpt": "e",
    "access": "abstract",
}
BAD = GOOD | {"id": "2"}
SET_ID = "003307c5-3f73-4a5d-a704-bfdea3c656e8"


def resolver(source):
    return source["id"] == "1"


def claim(text="consistent with", source=GOOD):
    return {"text": text, "sources": [source]}


def candidate(name, source=GOOD, tests=True):
    return {
        "name": name,
        "likelihood": "possible",
        "cant_miss": False,
        "findings_for": [claim(source=source)],
        "findings_against": [],
        "missing_findings": [],
        "discriminating_tests": [claim("chest X-ray would help distinguish", source)]
        if tests
        else [],
    }


def differential(*candidates):
    return {
        "kind": "differential",
        "message": "These are possibilities to consider.",
        "differential": {
            "candidates": list(candidates),
            "missing_inputs": [],
            "evidence_gaps": [],
        },
    }


def option(name, source=GOOD, warnings=()):
    return {
        "name": name,
        "line": "first-line",
        "evidence_level": "guideline",
        "rationale": [claim(source=source)],
        "warnings": list(warnings),
    }


def treatment(*options, diagnosis="Community-acquired pneumonia"):
    return {
        "kind": "treatment",
        "message": "Options to consider.",
        "treatment": {
            "diagnosis": diagnosis,
            "options": list(options),
            "evidence_gaps": [],
        },
    }


# --- differential ---


def test_differential_ok():
    assert (
        check_differential(
            differential(candidate("a"), candidate("b"), candidate("c")), resolver
        )
        == []
    )


@pytest.mark.parametrize(
    "resp, expected",
    [
        (None, "no response"),
        (treatment(), "expected 'differential'"),
        (differential(candidate("a"), candidate("b")), "2 candidates"),
        (
            differential(candidate("a"), candidate("b"), candidate("c", BAD)),
            "'c': no source resolves",
        ),
        (
            differential(candidate("a"), candidate("b"), candidate("c", tests=False)),
            "'c': no discriminating test",
        ),
    ],
)
def test_differential_problems(resp, expected):
    problems = check_differential(resp, resolver)
    assert len(problems) == 1 and expected in problems[0], problems


# --- treatment ---


def test_treatment_ok_with_allergen_warning():
    resp = treatment(
        option("Levofloxacin"),
        option(
            "Ceftriaxone plus azithromycin", warnings=[claim("cross-reactivity risk")]
        ),
    )
    assert (
        check_treatment(resp, "community-acquired pneumonia", ["ceftriaxone"], resolver)
        == []
    )


@pytest.mark.parametrize(
    "resp, expected",
    [
        (None, "no response"),
        (differential(), "expected 'treatment'"),
        (treatment(option("Levofloxacin")), "1 treatment options"),
        (
            treatment(option("Levofloxacin"), option("Doxycycline", BAD)),
            "'Doxycycline': no source resolves",
        ),
        (
            treatment(option("Levofloxacin"), option("AMOXICILLIN 1 g")),
            "allergen drug 'amoxicillin'",
        ),
        (
            treatment(option("a"), option("b"), diagnosis=""),
            "does not match selection",
        ),
        (
            treatment(option("a"), option("b"), diagnosis="Pulmonary embolism"),
            "does not match selection",
        ),
    ],
)
def test_treatment_problems(resp, expected):
    problems = check_treatment(
        resp, "community-acquired pneumonia", ["amoxicillin"], resolver
    )
    assert len(problems) == 1 and expected in problems[0], problems


def test_treatment_selection_ignores_punctuation():
    resp = treatment(option("a"), option("b"), diagnosis="Graves' disease")
    assert check_treatment(resp, "Graves disease", [], resolver) == []


# --- banned phrases ---


@pytest.mark.parametrize(
    "text",
    [
        "The diagnosis is pneumonia.",
        "A clear chest X-ray rules out pneumonia.",
        "PE has been ruled out.",
        "This confirms Graves disease.",
        "Pneumonia was confirmed.",
        "This is definitively bacterial.",
        "A definitive diagnosis.",
        "The patient has pneumonia.",
        "You should prescribe amoxicillin.",
        "This is certainly thyrotoxicosis.",
        "Sensitivity is 100 %.",
    ],
)
def test_banned_phrase_hits(text):
    assert any(re.search(p, text, re.IGNORECASE) for p in PATTERNS), text


@pytest.mark.parametrize(
    "text",
    [
        "A CT would help rule out pulmonary embolism.",
        "Order a D-dimer to rule out PE.",
        "PE cannot be ruled out.",
        "PE is not ruled out.",
        "PE has not been ruled out yet.",
        "If confirmed, consider antithyroid drugs.",
        "Not confirmed by culture.",
        "The diagnosis is not established.",
        "The patient has a history of penicillin anaphylaxis.",
        "Findings are consistent with pneumonia; may be considered.",
    ],
)
def test_banned_phrase_spares_hedged_wording(text):
    assert not [p for p in PATTERNS if re.search(p, text, re.IGNORECASE)], text


def test_banned_hits_scans_app_text_but_not_sources():
    quote = GOOD | {
        "title": "Pneumonia confirmed",
        "excerpt": "Culture confirms the diagnosis",
        "url": "x/definitive",
    }
    resp = differential(
        candidate("a", quote), candidate("b", quote), candidate("c", quote)
    )
    assert banned_hits(resp, PATTERNS) == []
    resp["differential"]["candidates"][1]["missing_findings"] = [
        "a culture that confirms it"
    ]
    resp["differential"]["evidence_gaps"] = ["The patient has CAP"]
    assert banned_hits(resp, PATTERNS) == [
        "banned phrase 'confirms' at differential.candidates[1].missing_findings[0]",
        "banned phrase 'The patient has' at differential.evidence_gaps[0]",
    ]


# --- refusal ---

REFUSED = {
    "thread_id": "t",
    "refused": True,
    "refusal": "Please call emergency services.\n",
    "response": None,
    "cost_usd": 0.0,
    "model_calls": 0,
    "trace_id": None,
}


def test_refusal_ok_ignores_outer_whitespace():
    assert (
        check_refusal(
            REFUSED | {"refusal": "Please call emergency services."},
            "Please call emergency services.\n",
        )
        == []
    )


def test_refusal_problems():
    bad = REFUSED | {
        "refused": False,
        "refusal": "Something else",
        "model_calls": 2,
        "response": differential(),
    }
    assert check_refusal(bad, REFUSED["refusal"]) == [
        "not refused",
        "refusal text differs from refusal.md",
        "model_calls is 2, expected 0",
        "response is not null",
    ]


# --- resolve_source (no network) ---


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "ref.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE hpo_annotation (disease_id TEXT, hpo_id TEXT);
        INSERT INTO hpo_annotation VALUES ('OMIM:154700', 'HP:0001166');
        CREATE TABLE rxnorm_concept (rxcui INTEGER, name TEXT);
        INSERT INTO rxnorm_concept VALUES (18631, 'azithromycin');
    """)
    con.commit()
    con.close()
    return path


def fake_api(request: httpx.Request) -> httpx.Response:
    if "esummary" in request.url.path:
        uid = request.url.params["id"]
        doc = (
            {"uid": uid}
            if uid == "31573350"
            else {"uid": uid, "error": "cannot get document summary"}
        )
        return httpx.Response(200, json={"result": {"uids": [uid], uid: doc}})
    if SET_ID in request.url.params["search"]:
        return httpx.Response(
            200, json={"meta": {"results": {"total": 1}}, "results": [{}]}
        )
    return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})


@pytest.fixture
def http():
    with httpx.Client(transport=httpx.MockTransport(fake_api)) as client:
        yield client


@pytest.mark.parametrize(
    "kind, sid, expected",
    [
        ("pubmed", "31573350", True),
        ("pubmed", "99999999", False),
        ("pubmed", "31573350,1", False),
        ("drug_label", SET_ID, True),
        ("drug_label", "00000000-0000-0000-0000-000000000000", False),
        ("drug_label", '" OR *', False),
        ("reference_db", "hpo_annotation.disease_id=OMIM:154700", True),
        ("reference_db", "rxnorm_concept.rxcui=18631", True),
        ("reference_db", "hpo_annotation.disease_id=OMIM:000000", False),
        ("reference_db", "hpo_annotation.nope=OMIM:154700", False),
        ("reference_db", "sqlite_master.name=hpo_annotation", False),
        ("reference_db", 'hpo_annotation" --.disease_id=x', False),
        ("reference_db", "hpo_annotation.disease_id", False),
        ("other", "1", False),
    ],
)
def test_resolve_source(http, db, kind, sid, expected):
    assert resolve_source({"kind": kind, "id": sid}, http, db) is expected


def test_resolver_caches_successful_lookups(db):
    calls = []

    def api(request):
        calls.append(request)
        return fake_api(request)

    with httpx.Client(transport=httpx.MockTransport(api)) as client:
        resolve, errors = make_resolver(client, db)
        src = {"kind": "drug_label", "id": SET_ID}
        assert resolve(src) is True and resolve(dict(src)) is True
    assert len(calls) == 1 and errors == []


def test_resolver_reports_api_errors_without_caching_them(db):
    calls = []

    def down(request):
        calls.append(request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(down)) as client:
        resolve, errors = make_resolver(client, db)
        src = {"kind": "drug_label", "id": SET_ID}
        assert resolve(src) is False and resolve(src) is False
    assert len(calls) == 4  # one retry on 5xx each time; failures are not cached
    assert len(errors) == 2 and "not checked" in errors[0]


def test_e2e_cases_parse():
    from app.config import ROOT

    cases = [
        json.loads(line)
        for line in (ROOT / "evals" / "e2e_cases.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert {c["id"] for c in cases if c.get("expect_refusal")} == {"refusal-patient"}
    assert all(
        "selection" in c and "allergen_drugs" in c
        for c in cases
        if not c.get("expect_refusal")
    )


# --- live (LIVE=1) ---


@pytest.mark.skipif(
    os.environ.get("LIVE") != "1", reason="set LIVE=1 to hit PubMed and openFDA"
)
def test_live_resolve_source():
    from app.config import REFERENCE_DB

    with httpx.Client(timeout=20) as client:
        resolve, errors = make_resolver(client)
        assert resolve({"kind": "pubmed", "id": "31573350"}) is True
        assert resolve({"kind": "pubmed", "id": "99999999"}) is False
        assert resolve({"kind": "drug_label", "id": SET_ID}) is True
        assert (
            resolve(
                {"kind": "drug_label", "id": "00000000-0000-0000-0000-000000000000"}
            )
            is False
        )
        if REFERENCE_DB.exists():
            assert (
                resolve(
                    {
                        "kind": "reference_db",
                        "id": "hpo_annotation.disease_id=OMIM:154700",
                    }
                )
                is True
            )
            assert (
                resolve(
                    {
                        "kind": "reference_db",
                        "id": "hpo_annotation.disease_id=OMIM:000000",
                    }
                )
                is False
            )
        assert errors == []
