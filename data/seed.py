"""Build data/reference.db from the files fetched by data/fetch.sh.

Rebuilds from scratch into a temp file and swaps it in, so a failed run leaves the old DB.
Table and column comments live in the DDL below; read them with
`SELECT sql FROM sqlite_master WHERE type = 'table'`.
"""

import csv
import io
import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent
DB = DATA / "reference.db"

SCHEMA = """
-- Provenance per dataset (spec 6.6). Cite `release` alongside any code or claim taken from it.
CREATE TABLE source (
  name TEXT PRIMARY KEY,
  release TEXT NOT NULL,
  url TEXT NOT NULL,
  license TEXT NOT NULL,
  retrieved TEXT NOT NULL  -- date the files were downloaded
);

-- WHO ICD-11 MMS linearization, one row per chapter, block or category.
CREATE TABLE icd11 (
  linearization_uri TEXT PRIMARY KEY,  -- residual "other/unspecified" entities end in /other or /unspecified
  foundation_uri TEXT NOT NULL,
  code TEXT,                           -- e.g. 1A00; NULL for chapters and blocks
  block_id TEXT,                       -- set for blocks, e.g. BlockL1-1A0
  title TEXT NOT NULL,
  class_kind TEXT NOT NULL,            -- chapter | block | category
  depth INTEGER NOT NULL,              -- depth within class_kind
  chapter TEXT NOT NULL,
  is_leaf INTEGER NOT NULL,
  is_residual INTEGER NOT NULL,
  parent_uri TEXT,                     -- foundation_uri of the parent
  coding_note TEXT
);
CREATE INDEX icd11_code ON icd11(code);
CREATE INDEX icd11_foundation ON icd11(foundation_uri);

-- WHO crosswalks. icd10 here is WHO ICD-10 (dotted, e.g. A00.0), close to but not the same as ICD-10-CM.
CREATE TABLE icd11_to_icd10 (
  icd11_code TEXT, icd11_title TEXT NOT NULL, icd11_uri TEXT NOT NULL,
  icd10_code TEXT, icd10_title TEXT
);
CREATE INDEX icd11_to_icd10_code ON icd11_to_icd10(icd11_code);
CREATE TABLE icd10_to_icd11 (
  icd10_code TEXT, icd10_title TEXT NOT NULL,
  icd11_code TEXT, icd11_title TEXT, icd11_uri TEXT
);
CREATE INDEX icd10_to_icd11_code ON icd10_to_icd11(icd10_code);

-- US ICD-10-CM (CDC). Codes stored dotted (A00.0) to match clinical display and icd10_to_icd11.
CREATE TABLE icd10cm (
  code TEXT PRIMARY KEY,
  billable INTEGER NOT NULL,  -- 1 = valid for submission, 0 = header/category
  short_title TEXT NOT NULL,
  long_title TEXT NOT NULL
);

-- Human Phenotype Ontology terms (symptoms, signs, findings).
CREATE TABLE hpo_term (
  id TEXT PRIMARY KEY,  -- HP:0001945
  name TEXT NOT NULL,
  definition TEXT,
  obsolete INTEGER NOT NULL
);
CREATE TABLE hpo_synonym (id TEXT NOT NULL REFERENCES hpo_term(id), synonym TEXT NOT NULL);
CREATE INDEX hpo_synonym_id ON hpo_synonym(id);
CREATE TABLE hpo_is_a (child TEXT NOT NULL, parent TEXT NOT NULL);  -- walk with a recursive CTE
CREATE INDEX hpo_is_a_child ON hpo_is_a(child);
CREATE INDEX hpo_is_a_parent ON hpo_is_a(parent);

-- HPO disease annotations (phenotype.hpoa). Mostly rare/Mendelian disease (OMIM, ORPHA, DECIPHER).
CREATE TABLE hpo_annotation (
  disease_id TEXT NOT NULL,  -- OMIM:619340 | ORPHA:58 | DECIPHER:1
  disease_name TEXT NOT NULL,
  negated INTEGER NOT NULL,  -- 1 = feature explicitly NOT present in this disease
  hpo_id TEXT NOT NULL,
  reference TEXT,            -- PMID:..., OMIM:..., ORPHA:...; the citable source
  evidence TEXT,             -- IEA inferred from electronic annotation | PCS published clinical study | TAS traceable author statement
  onset TEXT,                -- HPO onset term
  frequency TEXT,            -- HPO frequency term, n/m count or percentage
  sex TEXT,
  modifier TEXT,
  aspect TEXT                -- P phenotype | I inheritance | C onset/course | M modifier
);
CREATE INDEX hpo_annotation_hpo ON hpo_annotation(hpo_id);
CREATE INDEX hpo_annotation_disease ON hpo_annotation(disease_id);

-- Orphanet rare disease nomenclature (product 1).
CREATE TABLE orphanet_disorder (
  orpha_code INTEGER PRIMARY KEY,  -- ORPHA:58 -> 58
  name TEXT NOT NULL,
  disorder_type TEXT,              -- Disease, Malformation syndrome, ...
  disorder_group TEXT,             -- Group of disorders | Disorder | Subtype of a disorder
  url TEXT
);
CREATE TABLE orphanet_synonym (orpha_code INTEGER NOT NULL, synonym TEXT NOT NULL);
CREATE INDEX orphanet_synonym_code ON orphanet_synonym(orpha_code);
CREATE TABLE orphanet_xref (
  orpha_code INTEGER NOT NULL,
  source TEXT NOT NULL,     -- ICD-10 | ICD-11 | OMIM | MONDO | UMLS | MeSH | MedDRA | GARD
  reference TEXT NOT NULL,  -- MONDO is the bare number (0011778), joinable to PrimeKG disease ids
  relation TEXT,            -- E exact | NTBT narrower | BTNT broader | ...
  validation TEXT
);
CREATE INDEX orphanet_xref_code ON orphanet_xref(orpha_code);
CREATE INDEX orphanet_xref_ref ON orphanet_xref(source, reference);

-- Orphanet disorder -> HPO phenotype with frequency (product 4).
CREATE TABLE orphanet_phenotype (
  orpha_code INTEGER NOT NULL,
  hpo_id TEXT NOT NULL,
  hpo_term TEXT NOT NULL,
  frequency TEXT,           -- Obligate (100%) | Very frequent (99-80%) | Frequent (79-30%) | Occasional (29-5%) | Very rare (<4-1%) | Excluded (0%)
  diagnostic_criterion TEXT
);
CREATE INDEX orphanet_phenotype_hpo ON orphanet_phenotype(hpo_id);
CREATE INDEX orphanet_phenotype_code ON orphanet_phenotype(orpha_code);

-- MED-RT drug knowledge (VA). Drugs are RxNorm ingredients (from_code = rxcui), diseases are MeSH.
-- rel: may_treat, may_prevent, may_diagnose, CI_with (drug-condition contraindication),
-- CI_MoA / CI_PE / CI_ChemClass, induces, has_MoA, has_PE, has_TC, has_SC, Parent Of, ...
CREATE TABLE medrt_association (
  rel TEXT NOT NULL,
  from_ns TEXT NOT NULL,  -- RxNorm | MED-RT | MeSH | SNOMED CT
  from_code TEXT NOT NULL,
  from_name TEXT NOT NULL,
  to_ns TEXT NOT NULL,
  to_code TEXT NOT NULL,
  to_name TEXT NOT NULL
);
CREATE INDEX medrt_from ON medrt_association(from_code, rel);
CREATE INDEX medrt_to ON medrt_association(to_name, rel);
CREATE TABLE medrt_concept (
  code TEXT PRIMARY KEY,  -- NUI, e.g. N0000000223
  name TEXT NOT NULL,
  kind TEXT               -- MoA mechanism | PE physiologic effect | EPC established pharmacologic class | ...
);

-- RxNorm prescribable subset: drug names and concepts (SAB=RXNORM rows only).
CREATE TABLE rxnorm_concept (
  rxcui TEXT NOT NULL,
  tty TEXT NOT NULL,  -- IN ingredient | PIN | MIN | BN brand | SCD/SBD clinical/branded drug | SCDC | DF | ...
  name TEXT NOT NULL,
  suppress TEXT       -- N = not suppressed
);
CREATE INDEX rxnorm_concept_rxcui ON rxnorm_concept(rxcui);
CREATE INDEX rxnorm_concept_name ON rxnorm_concept(name COLLATE NOCASE);
-- Concept-level RxNorm relations. Reads "rxcui2 <rela> rxcui1", e.g. rxcui2=SCD has_ingredient rxcui1=IN.
CREATE TABLE rxnorm_rel (rxcui1 TEXT NOT NULL, rela TEXT NOT NULL, rxcui2 TEXT NOT NULL);
CREATE INDEX rxnorm_rel_1 ON rxnorm_rel(rxcui1, rela);
CREATE INDEX rxnorm_rel_2 ON rxnorm_rel(rxcui2, rela);

-- PrimeKG drug -> disease edges (2023; edges derived from DrugCentral). Use to propose options, not as a citation.
CREATE TABLE primekg_drug_disease (
  relation TEXT NOT NULL,  -- indication | contraindication | off-label use
  drug_id TEXT NOT NULL,   -- DrugBank id, e.g. DB00331
  drug_name TEXT NOT NULL,
  disease_id TEXT NOT NULL, -- MONDO number(s) without prefix, grouped ones joined by "_"
  disease_name TEXT NOT NULL
);
CREATE INDEX primekg_drug ON primekg_drug_disease(drug_name COLLATE NOCASE);
CREATE INDEX primekg_disease ON primekg_drug_disease(disease_name COLLATE NOCASE);

-- Retraction Watch (Crossref). Check a cited DOI/PMID here before showing it (spec 6.5).
CREATE TABLE retraction (
  record_id INTEGER PRIMARY KEY,
  title TEXT,
  journal TEXT,
  article_type TEXT,
  nature TEXT,            -- Retraction | Correction | Expression of concern | Reinstatement
  reason TEXT,
  retraction_date TEXT,   -- ISO YYYY-MM-DD
  retraction_doi TEXT,
  retraction_pmid TEXT,
  original_date TEXT,
  original_doi TEXT,      -- lowercase
  original_pmid TEXT
);
CREATE INDEX retraction_doi ON retraction(original_doi);
CREATE INDEX retraction_pmid ON retraction(original_pmid);
"""


def zip_text(path, member):
    return io.TextIOWrapper(
        zipfile.ZipFile(path).open(member), encoding="utf-8-sig", newline=""
    )


def tsv(f):
    return csv.DictReader(f, delimiter="\t")


def none(s):
    return s.strip() or None if s is not None else None


def icd11_records(f):
    """Coding notes contain unquoted newlines; every real record starts with a foundation URI."""
    record = next(f)
    for line in f:
        if line.startswith("http://id.who.int/icd/entity/"):
            yield record
            record = line
        else:
            record = record.rstrip("\r\n") + " " + line
    yield record


def load_icd11(db):
    z = DATA / "icd11/SimpleTabulation-ICD-11-MMS-en.zip"
    db.executemany(
        "INSERT INTO icd11 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            (
                r["Linearization URI"],
                r["Foundation URI"],
                none(r["Code"]),
                none(r["BlockId"]),
                re.sub(r"^(- )+", "", r["Title"]),
                r["ClassKind"],
                int(r["DepthInKind"]),
                r["ChapterNo"],
                r["isLeaf"] == "True",
                r["IsResidual"] == "True",
                none(r["Parent"]),
                none(r["CodingNote"]),
            )
            for r in tsv(
                icd11_records(zip_text(z, "SimpleTabulation-ICD-11-MMS-en.txt"))
            )
        ),
    )
    m = DATA / "icd11/icd11-icd10-mapping.zip"
    db.executemany(
        "INSERT INTO icd11_to_icd10 VALUES (?,?,?,?,?)",
        (
            (
                none(r["icd11Code"]),
                r["icd11Title"],
                r["Linearization (release) URI"],
                none(r["icd10Code"]),
                none(r["icd10Title"]),
            )
            for r in tsv(zip_text(m, "11To10MapToOneCategory.txt"))
        ),
    )
    db.executemany(
        "INSERT INTO icd10_to_icd11 VALUES (?,?,?,?,?)",
        (
            (
                none(r["icd10Code"]),
                r["icd10Title"],
                none(r["icd11Code"]),
                none(r["icd11Title"]),
                none(r["Linearization (releaseURI)"]),
            )
            for r in tsv(zip_text(m, "10To11MapToOneCategory.txt"))
        ),
    )


def load_icd10cm(db):
    f = zip_text(
        DATA / "icd10cm/icd10cm-code-descriptions-2027.zip",
        "icd10cm-code-descriptions-2027/icd10cm-order-2027.txt",
    )
    # Fixed width: order(5) code(7) billable(1) short(60) long, single-space separated.
    rows = []
    for line in f:
        code = line[6:13].strip()
        rows.append(
            (
                code[:3] + "." + code[3:] if len(code) > 3 else code,
                int(line[14]),
                line[16:76].strip(),
                line[77:].strip(),
            )
        )
    db.executemany("INSERT INTO icd10cm VALUES (?,?,?,?)", rows)


def hp_id(uri):
    return uri.rsplit("/", 1)[-1].replace("_", ":")


def load_hpo(db):
    with open(DATA / "hpo/hp.json", encoding="utf-8") as f:
        g = json.load(f)["graphs"][0]
    terms = [n for n in g["nodes"] if n.get("type") == "CLASS" and "/HP_" in n["id"]]
    db.executemany(
        "INSERT INTO hpo_term VALUES (?,?,?,?)",
        (
            (
                hp_id(n["id"]),
                n.get("lbl", ""),
                n.get("meta", {}).get("definition", {}).get("val"),
                bool(n.get("meta", {}).get("deprecated")),
            )
            for n in terms
        ),
    )
    db.executemany(
        "INSERT INTO hpo_synonym VALUES (?,?)",
        (
            (hp_id(n["id"]), s["val"])
            for n in terms
            for s in n.get("meta", {}).get("synonyms", [])
        ),
    )
    db.executemany(
        "INSERT INTO hpo_is_a VALUES (?,?)",
        (
            (hp_id(e["sub"]), hp_id(e["obj"]))
            for e in g["edges"]
            if e["pred"] == "is_a" and "/HP_" in e["sub"] and "/HP_" in e["obj"]
        ),
    )
    with open(DATA / "hpo/phenotype.hpoa", encoding="utf-8", newline="") as f:
        lines = (line for line in f if not line.startswith("#"))
        db.executemany(
            "INSERT INTO hpo_annotation VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    r["database_id"],
                    r["disease_name"],
                    r["qualifier"] == "NOT",
                    r["hpo_id"],
                    none(r["reference"]),
                    none(r["evidence"]),
                    none(r["onset"]),
                    none(r["frequency"]),
                    none(r["sex"]),
                    none(r["modifier"]),
                    none(r["aspect"]),
                )
                for r in csv.DictReader(lines, delimiter="\t")
            ),
        )


def disorders(path):
    for _, el in ET.iterparse(path):
        if (
            el.tag == "Disorder"
            and el.find("OrphaCode") is not None
            and el.find("Name") is not None
        ):
            yield int(el.findtext("OrphaCode", "")), el
            el.clear()


def load_orphanet(db):
    for code, d in disorders(DATA / "orphanet/en_product1.xml"):
        db.execute(
            "INSERT INTO orphanet_disorder VALUES (?,?,?,?,?)",
            (
                code,
                d.findtext("Name"),
                d.findtext("DisorderType/Name"),
                d.findtext("DisorderGroup/Name"),
                d.findtext("ExpertLink"),
            ),
        )
        db.executemany(
            "INSERT INTO orphanet_synonym VALUES (?,?)",
            ((code, s.text) for s in d.iterfind("SynonymList/Synonym")),
        )
        db.executemany(
            "INSERT INTO orphanet_xref VALUES (?,?,?,?,?)",
            (
                (
                    code,
                    x.findtext("Source"),
                    x.findtext("Reference"),
                    none(x.findtext("DisorderMappingRelation/Name")),
                    none(x.findtext("DisorderMappingValidationStatus/Name")),
                )
                for x in d.iterfind("ExternalReferenceList/ExternalReference")
            ),
        )
    for code, d in disorders(DATA / "orphanet/en_product4.xml"):
        db.executemany(
            "INSERT INTO orphanet_phenotype VALUES (?,?,?,?,?)",
            (
                (
                    code,
                    a.findtext("HPO/HPOId"),
                    a.findtext("HPO/HPOTerm"),
                    none(a.findtext("HPOFrequency/Name")),
                    none(a.findtext("DiagnosticCriteria/Name")),
                )
                for a in d.iterfind("HPODisorderAssociationList/HPODisorderAssociation")
            ),
        )


def load_medrt(db):
    z = zipfile.ZipFile(DATA / "medrt/Core_MEDRT_XML.zip")
    member = next(n for n in z.namelist() if n.endswith("_XML.xml"))
    version = None
    for _, el in ET.iterparse(z.open(member)):
        if el.tag == "association":
            db.execute(
                "INSERT INTO medrt_association VALUES (?,?,?,?,?,?,?)",
                tuple(
                    el.findtext(t)
                    for t in (
                        "name",
                        "from_namespace",
                        "from_code",
                        "from_name",
                        "to_namespace",
                        "to_code",
                        "to_name",
                    )
                ),
            )
            el.clear()
        elif el.tag == "concept":
            kind = next(
                (
                    p.findtext("value")
                    for p in el.iterfind("property")
                    if p.findtext("name") == "CTY"
                ),
                None,
            )
            db.execute(
                "INSERT INTO medrt_concept VALUES (?,?,?)",
                (el.findtext("code"), el.findtext("name"), kind),
            )
            el.clear()
        elif el.tag == "namespace" and version is None:
            version = el.findtext("version")
    return version


def load_rxnorm(db):
    z = DATA / "rxnorm/RxNorm_full_prescribe_10052026.zip"
    rows = (line.split("|") for line in zip_text(z, "rrf/RXNCONSO.RRF"))
    db.executemany(
        "INSERT INTO rxnorm_concept VALUES (?,?,?,?)",
        ((r[0], r[12], r[14], r[16]) for r in rows if r[11] == "RXNORM"),
    )
    rows = (line.split("|") for line in zip_text(z, "rrf/RXNREL.RRF"))
    db.executemany(
        "INSERT INTO rxnorm_rel VALUES (?,?,?)",
        (
            (r[0], r[7], r[4])
            for r in rows
            if r[2] == "CUI" and r[10] == "RXNORM" and r[7]
        ),
    )


def load_primekg(db):
    with open(DATA / "primekg/drug_disease.csv", encoding="utf-8", newline="") as f:
        db.executemany(
            "INSERT INTO primekg_drug_disease VALUES (?,?,?,?,?)",
            list(csv.reader(f))[1:],
        )


def us_date(s):  # "3/15/2012 0:00" -> "2012-03-15"
    return (
        datetime.strptime(s.split()[0], "%m/%d/%Y").date().isoformat()
        if s.strip()
        else None
    )


def pmid(s):  # the file uses 0 for "no PMID"
    return None if s.strip() in ("", "0") else s.strip()


def load_retractions(db):
    with open(
        DATA / "retractions/retraction_watch.csv", encoding="utf-8", newline=""
    ) as f:
        db.executemany(
            "INSERT INTO retraction VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    int(r["Record ID"]),
                    r["Title"],
                    r["Journal"],
                    none(r["ArticleType"]),
                    none(r["RetractionNature"]),
                    none(r["Reason"]),
                    us_date(r["RetractionDate"]),
                    none(r["RetractionDOI"]),
                    pmid(r["RetractionPubMedID"]),
                    us_date(r["OriginalPaperDate"]),
                    none(r["OriginalPaperDOI"].lower()),
                    pmid(r["OriginalPaperPubMedID"]),
                )
                for r in csv.DictReader(f)
            ),
        )


def file_version(path, pattern):
    with open(path, encoding="utf-8") as f:
        m = re.search(pattern, f.read(2000))
    assert m, f"no version in {path}"
    return m.group(1)


def build(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    loaders = [
        load_icd11,
        load_icd10cm,
        load_hpo,
        load_orphanet,
        load_rxnorm,
        load_primekg,
        load_retractions,
    ]
    for load in loaders:
        load(db)
        print(f"{load.__name__}: done", file=sys.stderr)
    medrt_version = load_medrt(db)
    retrieved = date.fromtimestamp((DATA / "SHA256SUMS").stat().st_mtime).isoformat()
    db.executemany(
        "INSERT INTO source VALUES (?,?,?,?,?)",
        [
            (
                "ICD-11 MMS",
                "2026-01",
                "https://icdcdn.who.int/static/releasefiles/2026-01/",
                "CC BY-ND 3.0 IGO",
                retrieved,
            ),
            (
                "ICD-10-CM",
                "FY2027",
                "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD10CM/2027/",
                "Public domain",
                retrieved,
            ),
            (
                "HPO",
                file_version(DATA / "hpo/phenotype.hpoa", r"#version: (\S+)"),
                "https://github.com/obophenotype/human-phenotype-ontology/releases",
                "HPO license",
                retrieved,
            ),
            (
                "Orphanet",
                file_version(DATA / "orphanet/en_product1.xml", r'date="([\d-]+)'),
                "https://www.orphadata.com/data/xml/",
                "CC BY 4.0",
                retrieved,
            ),
            (
                "MED-RT",
                medrt_version,
                "https://evs.nci.nih.gov/ftp1/MED-RT/",
                "Public domain",
                retrieved,
            ),
            (
                "RxNorm prescribable",
                "2026-10-05",
                "https://download.nlm.nih.gov/rxnorm/",
                "Public domain (NLM)",
                retrieved,
            ),
            (
                "PrimeKG",
                "v2 (2023)",
                "https://doi.org/10.7910/DVN/IXA7BM",
                "CC0; edges CC BY-SA 4.0",
                retrieved,
            ),
            (
                "Retraction Watch",
                retrieved,
                "https://gitlab.com/crossref/retraction-watch-data",
                "Crossref terms",
                retrieved,
            ),
        ],
    )
    db.commit()
    return db


def check(db):
    """Fail loud if a source changed format: every table populated, known entries present."""
    tables = [
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    ]
    for t in tables:
        n = db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n}", file=sys.stderr)
        assert n > 0, f"{t} is empty"
    one = lambda sql: db.execute(sql).fetchone()
    assert one("SELECT title FROM icd11 WHERE code = '1A00'") == ("Cholera",)
    assert one("SELECT short_title FROM icd10cm WHERE code = 'A00.0'")[0].startswith(
        "Cholera"
    )
    assert one("SELECT name FROM hpo_term WHERE id = 'HP:0001945'") == ("Fever",)
    assert one("SELECT name FROM orphanet_disorder WHERE orpha_code = 58") == (
        "Alexander disease",
    )
    assert one("SELECT 1 FROM rxnorm_concept WHERE name = 'metformin' AND tty = 'IN'")
    assert one("""SELECT 1 FROM medrt_association m JOIN rxnorm_concept r ON r.rxcui = m.from_code
                  WHERE r.name = 'metformin' AND m.rel = 'may_treat' AND m.to_name LIKE '%Diabetes%'""")
    # Direction of rxnorm_rel as documented in the schema.
    assert one("""SELECT 1 FROM rxnorm_rel x JOIN rxnorm_concept a ON a.rxcui = x.rxcui1 AND a.tty = 'IN'
                  JOIN rxnorm_concept b ON b.rxcui = x.rxcui2 AND b.tty = 'SCDC'
                  WHERE x.rela = 'has_ingredient' LIMIT 1""")


if __name__ == "__main__":
    tmp = DB.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    db = build(tmp)
    check(db)
    db.execute("VACUUM")
    db.close()
    tmp.replace(DB)
    print(f"wrote {DB}", file=sys.stderr)
