"""Output contracts shared by the subagents, the main agent, the API and the e2e checks."""

from typing import Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    kind: Literal["pubmed", "reference_db", "drug_label"]
    id: str = Field(
        description="pubmed: the PMID digits. drug_label: the openFDA set_id. "
        "reference_db: '<table>.<column>=<value>' naming one row that exists, e.g. "
        "'hpo_annotation.disease_id=OMIM:154700'."
    )
    title: str
    url: str
    excerpt: str = Field(description="Short quote from the source that supports the claim.")
    access: Literal["abstract", "full_text", "database", "label"]


class Claim(BaseModel):
    text: str
    sources: list[Source] = Field(min_length=1)


class Candidate(BaseModel):
    name: str
    likelihood: Literal["more likely", "possible", "less likely but important to exclude"]
    cant_miss: bool
    findings_for: list[Claim]
    findings_against: list[Claim]
    missing_findings: list[str] = Field(description="Findings not given that would change the likelihood.")
    discriminating_tests: list[Claim] = Field(min_length=1)


class Differential(BaseModel):
    candidates: list[Candidate]
    missing_inputs: list[str]
    evidence_gaps: list[str]


class TreatmentOption(BaseModel):
    name: str
    line: str = Field(description="e.g. 'first-line', 'alternative', 'adjunct'.")
    evidence_level: Literal["guideline", "systematic review", "RCT", "observational", "case report", "label", "reference database"]
    rationale: list[Claim] = Field(min_length=1)
    warnings: list[Claim] = Field(description="Patient-specific: allergy, interaction, dosing, pregnancy, comorbidity.")


class TreatmentPlan(BaseModel):
    diagnosis: str
    options: list[TreatmentOption]
    evidence_gaps: list[str]


class CopilotResponse(BaseModel):
    """The main agent's final structured output for one turn."""

    kind: Literal["differential", "treatment", "clarification"]
    message: str = Field(description="Short hedged summary for the physician; never a final diagnosis or a prescription.")
    differential: Differential | None = None
    treatment: TreatmentPlan | None = None
