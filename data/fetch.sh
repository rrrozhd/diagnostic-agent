#!/usr/bin/env bash
# Re-fetch the reference datasets listed in data/README.md. Run from repo root: bash data/fetch.sh
set -euo pipefail
cd "$(dirname "$0")"

get() { # get <dir> <url> [name]
  mkdir -p "$1"
  curl -fsSL --retry 3 -o "$1/${3:-$(basename "${2%%\?*}")}" "$2"
}

ICD11=https://icdcdn.who.int/static/releasefiles/2026-01
get icd11 "$ICD11/SimpleTabulation-ICD-11-MMS-en.zip"
get icd11 "$ICD11/mapping.zip" icd11-icd10-mapping.zip

ICD10CM=https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD10CM/2027
get icd10cm "$ICD10CM/icd10cm-code-descriptions-2027.zip"
get icd10cm "$ICD10CM/icd10cm-table-and-index-2027.zip"

HPO=https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download
get hpo "$HPO/phenotype.hpoa"
get hpo "$HPO/hp.json"

get orphanet https://www.orphadata.com/data/xml/en_product1.xml
get orphanet https://www.orphadata.com/data/xml/en_product4.xml

get medrt https://evs.nci.nih.gov/ftp1/MED-RT/Core_MEDRT_XML.zip

get rxnorm https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_10052026.zip

get retractions https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv

# PrimeKG: keep only drug->disease indication / contraindication / off-label edges (full kg is ~1 GB).
DV=https://dataverse.harvard.edu/api/access/datafile
get primekg "$DV/6180617" nodes.tab
curl -fsSL --retry 3 "$DV/6180616" | python3 -I -c '
import csv, sys
nodes = {r["node_index"]: r for r in csv.DictReader(open(sys.argv[1], newline=""), delimiter="\t")}
keep = {"indication", "contraindication", "off-label use"}
out = csv.writer(open(sys.argv[2], "w", newline=""))
out.writerow(["relation", "drug_id", "drug_name", "disease_id", "disease_name"])
n = 0
for r in csv.DictReader(sys.stdin):
    if r["relation"] not in keep:
        continue
    x, y = nodes[r["x_index"]], nodes[r["y_index"]]
    if x["node_type"] != "drug":  # each edge is stored in both directions
        continue
    out.writerow([r["relation"], x["node_id"], x["node_name"], y["node_id"], y["node_name"]])
    n += 1
assert n > 0, "no drug-disease edges kept; check relation names"
print(f"primekg: {n} drug-disease edges", file=sys.stderr)
' primekg/nodes.tab primekg/drug_disease.csv
