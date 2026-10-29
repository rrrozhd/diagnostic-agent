import { ArrowLeft, ExternalLink, TriangleAlert } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  safeUrl,
  type Candidate,
  type Claim,
  type Differential,
  type Likelihood,
  type Source,
  type TreatmentPlan,
} from "@/lib/api"

const TIERS: Likelihood[] = ["more likely", "possible", "less likely but important to exclude"]

const ACCESS: Record<Source["access"], string> = {
  abstract: "Abstract only",
  full_text: "Full text",
  database: "Database entry",
  label: "Drug label",
}

const sourceLabel = (s: Source) =>
  s.kind === "pubmed" ? `PMID ${s.id}` : s.kind === "drug_label" ? "Label" : "Ref DB"

export function TierBadge({ tier }: { tier: Likelihood }) {
  const style = {
    "more likely": "bg-primary text-primary-foreground",
    possible: "bg-primary/15 text-primary",
    "less likely but important to exclude": "border border-dashed border-foreground/60 bg-transparent text-foreground",
  }[tier]
  return <Badge className={style}>{tier[0].toUpperCase() + tier.slice(1)}</Badge>
}

function CantMiss() {
  return <Badge className="bg-warn text-white dark:text-black">Can&apos;t miss</Badge>
}

function ClaimLine({ claim, onSource }: { claim: Claim; onSource: (s: Source, c: Claim) => void }) {
  return (
    <li>
      {claim.text}
      {claim.sources.map((s, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSource(s, claim)}
          className="ml-1 rounded border border-primary/30 px-1.5 font-mono text-[11px] text-primary hover:bg-primary/10"
        >
          {sourceLabel(s)}
        </button>
      ))}
    </li>
  )
}

function Claims({ title, claims, onSource }: { title: string; claims: Claim[]; onSource: (s: Source, c: Claim) => void }) {
  return (
    <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
      <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</span>
      {claims.length ? (
        <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
          {claims.map((c, i) => (
            <ClaimLine key={i} claim={c} onSource={onSource} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">None found. A gap, not support.</p>
      )}
    </div>
  )
}

type Actions = {
  onSource: (s: Source, c: Claim) => void
  onSelect: (diagnosis: string) => void
  selected: string[]
  busy: boolean
}

function CandidateCard({ c, a }: { c: Candidate; a: Actions }) {
  const chosen = a.selected.includes(c.name)
  return (
    <article className={cn("flex flex-col gap-3 rounded-xl border bg-card p-4", chosen && "border-primary border-2")}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{c.name}</h3>
        <TierBadge tier={c.likelihood} />
        {c.cant_miss && <CantMiss />}
        {chosen && <Badge variant="secondary">Working diagnosis</Badge>}
      </div>
      <div className="flex flex-wrap gap-4">
        <Claims title="Findings for" claims={c.findings_for} onSource={a.onSource} />
        <Claims title="Findings against" claims={c.findings_against} onSource={a.onSource} />
        <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
          <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Missing, would matter</span>
          <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
            {c.missing_findings.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="flex">
        <Claims title="Tests that would most change the likelihood" claims={c.discriminating_tests} onSource={a.onSource} />
      </div>
      {!chosen && (
        <Button variant="outline" className="h-11 self-start" disabled={a.busy} onClick={() => a.onSelect(c.name)}>
          Mark as working diagnosis and research treatment
        </Button>
      )}
    </article>
  )
}

function Gaps({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <section className="flex flex-col gap-1 rounded-xl border bg-card p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="flex list-disc flex-col gap-1 pl-4 text-sm text-muted-foreground">
        {items.map((g, i) => (
          <li key={i}>{g}</li>
        ))}
      </ul>
    </section>
  )
}

export function DifferentialView({ d, a }: { d: Differential; a: Actions }) {
  const cantMiss = d.candidates.filter((c) => c.cant_miss)
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">Grouped by likelihood tier, not ranked. Can&apos;t-miss conditions come first.</p>
      {cantMiss.length > 0 && (
        <section className="flex flex-col gap-3 rounded-2xl border border-warn/40 bg-warn-soft p-4">
          <h2 className="flex items-center gap-2 text-sm font-bold text-warn">
            <TriangleAlert className="size-4" aria-hidden="true" />
            Can&apos;t miss — exclude before you close the case
          </h2>
          {cantMiss.map((c) => (
            <CandidateCard key={c.name} c={c} a={a} />
          ))}
        </section>
      )}
      {TIERS.map((tier) => {
        const rest = d.candidates.filter((c) => c.likelihood === tier && !c.cant_miss)
        if (!rest.length) return null
        return (
          <section key={tier} className="flex flex-col gap-3">
            <h2>
              <TierBadge tier={tier} />
            </h2>
            {rest.map((c) => (
              <CandidateCard key={c.name} c={c} a={a} />
            ))}
          </section>
        )
      })}
      <Gaps title="Missing inputs that limit this" items={d.missing_inputs} />
      <Gaps title="No evidence found for" items={d.evidence_gaps} />
    </div>
  )
}

export function TreatmentView({ t, onSource }: { t: TreatmentPlan; onSource: (s: Source, c: Claim) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Options for <strong className="text-foreground">{t.diagnosis}</strong> only. The choice and the prescription are yours.
      </p>
      {t.options.map((o) => (
        <article key={o.name} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{o.name}</h3>
            <Badge variant="secondary" className="capitalize">{o.evidence_level}</Badge>
            <Badge variant="outline">{o.line}</Badge>
          </div>
          {o.warnings.length > 0 && (
            <div className="flex flex-col gap-1 rounded-lg bg-warn p-3 text-sm text-white dark:text-black">
              <strong className="flex items-center gap-2">
                <TriangleAlert className="size-4" aria-hidden="true" />
                Patient-specific warning
              </strong>
              <ul className="flex list-disc flex-col gap-1 pl-5 [&_button]:border-current [&_button]:text-current">
                {o.warnings.map((w, i) => (
                  <ClaimLine key={i} claim={w} onSource={onSource} />
                ))}
              </ul>
            </div>
          )}
          <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
            {o.rationale.map((r, i) => (
              <ClaimLine key={i} claim={r} onSource={onSource} />
            ))}
          </ul>
        </article>
      ))}
      <Gaps title="No evidence found for" items={t.evidence_gaps} />
    </div>
  )
}

export function SourceView({ source, claim, onBack }: { source: Source; claim: Claim; onBack: () => void }) {
  const href = safeUrl(source.url)
  return (
    <div className="flex flex-col gap-4">
      <Button variant="ghost" className="h-11 self-start text-primary" onClick={onBack}>
        <ArrowLeft aria-hidden="true" /> Back
      </Button>
      <div className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Claim</span>
        <p className="font-medium">{claim.text}</p>
        <blockquote className="rounded-lg bg-muted p-3 text-sm italic">“{source.excerpt}”</blockquote>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Source</dt>
          <dd>{source.title}</dd>
          <dt className="text-muted-foreground">Identifier</dt>
          <dd className="font-mono break-all">{source.kind === "pubmed" ? `PMID ${source.id}` : source.id}</dd>
          <dt className="text-muted-foreground">Read</dt>
          <dd>{ACCESS[source.access]}</dd>
        </dl>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex h-11 items-center gap-2 self-start text-sm font-medium text-primary underline-offset-4 hover:underline">
            Open original <ExternalLink className="size-4" aria-hidden="true" />
          </a>
        ) : (
          <p className="text-sm text-muted-foreground">No valid link was returned for this source.</p>
        )}
      </div>
    </div>
  )
}
