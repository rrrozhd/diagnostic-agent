import { useEffect, useState } from "react"
import { FileText, ListTree, Loader2, Pill, Plus, Send } from "lucide-react"

import { DifferentialView, SourceView, TreatmentView } from "@/components/artifact-panel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { chat, treatmentRequest, type ChatResult, type Claim, type Source } from "@/lib/api"
import { loadCases, saveCases, titleFrom, type Case } from "@/lib/cases"
import { cn } from "@/lib/utils"

// null follows the newest artifact; a number pins one copilot turn.
type View = null | number | { source: Source; claim: Claim; back: number | null }

const hasArtifact = (r: ChatResult) => !!(r.response?.differential || r.response?.treatment)

function caseStatus(c: Case): { text: string; warn?: boolean } {
  const last = [...c.turns].reverse().find((t) => t.role === "copilot")
  if (!last || last.role !== "copilot") return { text: "No research yet" }
  if (last.result.refused) return { text: "Declined" }
  const d = last.result.response?.differential
  const open = d?.candidates.filter((x) => x.cant_miss).length ?? 0
  if (open) return { text: `${open} can't-miss to exclude`, warn: true }
  if (last.result.response?.treatment) return { text: `Treatment · ${last.result.response.treatment.diagnosis}` }
  return { text: "Awaiting your reply" }
}

export function App() {
  const [cases, setCases] = useState<Case[]>(loadCases)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>(null)

  useEffect(() => saveCases(cases), [cases])

  const active = cases.find((c) => c.id === activeId) ?? null
  const artifactTurns = active
    ? active.turns.flatMap((t, i) => (t.role === "copilot" && hasArtifact(t.result) ? [i] : []))
    : []
  const shownTurn =
    view === null ? artifactTurns.at(-1) : typeof view === "number" ? view : undefined
  const userTexts = active?.turns.flatMap((t) => (t.role === "user" ? [t.text] : [])) ?? []

  function patch(id: string, fn: (c: Case) => Case) {
    setCases((all) => all.map((c) => (c.id === id ? fn(c) : c)))
  }

  // Called only from event handlers: a paid model run must never start from an effect.
  async function send(text: string) {
    const body = text.trim()
    if (!body || pending) return
    const id = active?.id ?? crypto.randomUUID()
    if (!active) {
      setCases((all) => [{ id, title: titleFrom(body), createdAt: new Date().toISOString(), turns: [] }, ...all])
      setActiveId(id)
    }
    patch(id, (c) => ({ ...c, turns: [...c.turns, { role: "user", text: body }] }))
    setDraft("")
    setError(null)
    setPending(id)
    try {
      const result = await chat(id, body)
      patch(id, (c) => ({ ...c, turns: [...c.turns, { role: "copilot", result }] }))
      setView(null)
    } catch (e) {
      // Take the unanswered message back so it can be retried as-is.
      setCases((all) =>
        all.flatMap((c) => (c.id !== id ? [c] : c.turns.length > 1 ? [{ ...c, turns: c.turns.slice(0, -1) }] : []))
      )
      setDraft(body)
      setError(e instanceof Error ? e.message : "The request failed.")
    } finally {
      setPending(null)
    }
  }

  const openSource = (source: Source, claim: Claim) =>
    setView({ source, claim, back: typeof view === "number" ? view : null })

  const shown = shownTurn !== undefined ? active?.turns[shownTurn] : undefined
  const shownResult = shown?.role === "copilot" ? shown.result.response : null
  const busy = pending !== null

  return (
    <div className="flex min-h-svh flex-col bg-muted/40 md:h-svh md:flex-row md:overflow-hidden">
      <nav aria-label="Cases" className="flex flex-col gap-3 border-b bg-background p-3 md:w-72 md:shrink-0 md:overflow-y-auto md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-1 font-semibold">
          <span className="grid size-7 place-items-center rounded-lg border-2 border-primary text-primary">+</span>
          Copilot
        </div>
        <Button className="h-11 justify-start" onClick={() => { setActiveId(null); setView(null); setError(null) }}>
          <Plus aria-hidden="true" /> New case
        </Button>
        <ul className="flex gap-2 overflow-x-auto md:flex-col md:gap-1 md:overflow-visible">
          {cases.map((c) => {
            const s = caseStatus(c)
            return (
              <li key={c.id} className="shrink-0 md:shrink">
                <button
                  type="button"
                  onClick={() => { setActiveId(c.id); setView(null); setError(null) }}
                  aria-current={c.id === activeId ? "page" : undefined}
                  className={cn(
                    "flex min-h-11 w-52 flex-col rounded-lg px-3 py-2 text-left hover:bg-muted md:w-full",
                    c.id === activeId && "bg-muted ring-1 ring-border"
                  )}
                >
                  <span className="truncate text-sm font-medium">{c.title}</span>
                  <span className={cn("text-xs text-muted-foreground", s.warn && "font-semibold text-warn")}>{s.text}</span>
                </button>
              </li>
            )
          })}
        </ul>
        <p className="mt-auto hidden px-1 text-xs text-muted-foreground md:block">Decision support · not a diagnosis</p>
      </nav>

      <section aria-label="Case conversation" className="flex min-w-0 flex-col bg-background md:h-svh md:flex-1 md:border-r">
        <header className="border-b px-6 py-3">
          <h1 className="truncate font-semibold">{active?.title ?? "New case"}</h1>
        </header>
        <div className="flex flex-1 flex-col gap-5 px-6 py-5 md:min-h-0 md:overflow-y-auto">
          {!active && (
            <div className="m-auto flex max-w-md flex-col gap-2 text-center">
              <h2 className="text-xl font-semibold">Start a case</h2>
              <p className="text-sm text-muted-foreground">
                Paste a synthetic, de-identified note: age, sex, symptoms, history, allergies with reaction, current
                medications. Anything left out is treated as not recorded, never as none.
              </p>
            </div>
          )}
          {active?.turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="flex flex-col items-end gap-1">
                <span className="text-xs text-muted-foreground">You</span>
                <p className="max-w-xl rounded-2xl rounded-br-sm bg-muted px-4 py-3 text-sm whitespace-pre-wrap">{t.text}</p>
              </div>
            ) : (
              <div key={i} className="flex flex-col gap-2">
                <span className="text-xs text-muted-foreground">Copilot</span>
                {t.result.refused ? (
                  <p className="max-w-xl rounded-lg border bg-muted/50 p-3 text-sm whitespace-pre-wrap">{t.result.refusal}</p>
                ) : (
                  <>
                    <p className="max-w-[60ch] text-[15px]">{t.result.response?.message}</p>
                    {t.result.response && hasArtifact(t.result) && (
                      <button
                        type="button"
                        onClick={() => setView(i)}
                        className={cn(
                          "flex min-h-14 max-w-md items-center gap-3 rounded-xl border bg-card px-4 py-3 text-left hover:border-primary",
                          shownTurn === i && "border-primary"
                        )}
                      >
                        {t.result.response.differential ? (
                          <ListTree className="size-5 text-primary" aria-hidden="true" />
                        ) : (
                          <Pill className="size-5 text-primary" aria-hidden="true" />
                        )}
                        <span className="flex flex-1 flex-col">
                          <span className="text-sm font-semibold">
                            {t.result.response.differential ? "Differential" : `Treatment · ${t.result.response.treatment?.diagnosis}`}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {t.result.response.differential
                              ? `${t.result.response.differential.candidates.length} candidates`
                              : `${t.result.response.treatment?.options.length} options`}
                          </span>
                        </span>
                        {(t.result.response.differential?.candidates.some((c) => c.cant_miss) ||
                          t.result.response.treatment?.options.some((o) => o.warnings.length)) && (
                          <Badge className="bg-warn text-white dark:text-black">
                            {t.result.response.differential ? "Can't miss" : "Warnings"}
                          </Badge>
                        )}
                      </button>
                    )}
                  </>
                )}
                <span className="text-xs text-muted-foreground">
                  ${t.result.cost_usd.toFixed(2)} · {t.result.model_calls} model calls
                </span>
              </div>
            )
          )}
          {pending && pending === activeId && (
            <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Researching. This can take a few minutes.
            </p>
          )}
        </div>
        <form
          className="flex flex-col gap-2 border-t px-6 pt-3 pb-4"
          onSubmit={(e) => { e.preventDefault(); void send(draft) }}
        >
          {error && <p role="alert" className="text-sm text-destructive">{error} Your message is back in the box; send it again to retry.</p>}
          {busy && pending !== activeId && <p className="text-sm text-muted-foreground">Another case is still running. One request at a time.</p>}
          <div className="flex items-end gap-2 rounded-xl border p-2 pl-3">
            <label htmlFor="ask" className="sr-only">Case note or question</label>
            <Textarea
              id="ask"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void send(draft) } }}
              placeholder={active ? "Ask about this case, or add a finding" : "Paste the case note"}
              rows={active ? 2 : 5}
              className="min-h-0 resize-none border-0 shadow-none focus-visible:ring-0"
            />
            <Button type="submit" size="icon-lg" aria-label="Send" disabled={busy || !draft.trim()}>
              <Send aria-hidden="true" />
            </Button>
          </div>
          <span className="text-xs text-muted-foreground">Ctrl/⌘ + Enter to send · synthetic, de-identified cases only</span>
        </form>
      </section>

      <aside aria-label="Research" className="flex min-w-0 flex-col md:h-svh md:flex-1 md:overflow-y-auto">
        {artifactTurns.length > 0 && (
          <div className="flex flex-wrap gap-1 border-b bg-background px-4">
            {artifactTurns.map((i) => {
              const t = active!.turns[i]
              const r = t.role === "copilot" ? t.result.response : null
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setView(i)}
                  aria-pressed={shownTurn === i}
                  className={cn(
                    "min-h-11 border-b-2 border-transparent px-3 text-sm text-muted-foreground hover:text-foreground",
                    shownTurn === i && "border-primary font-semibold text-foreground"
                  )}
                >
                  {r?.differential ? "Differential" : `Treatment · ${r?.treatment?.diagnosis}`}
                </button>
              )
            })}
          </div>
        )}
        <div className="p-5">
          {view !== null && typeof view === "object" ? (
            <SourceView source={view.source} claim={view.claim} onBack={() => setView(view.back)} />
          ) : shownResult?.differential ? (
            <DifferentialView
              d={shownResult.differential}
              a={{
                onSource: openSource,
                onSelect: (name) => void send(treatmentRequest(name)),
                selected: shownResult.differential.candidates.map((c) => c.name).filter((n) => userTexts.includes(treatmentRequest(n))),
                busy,
              }}
            />
          ) : shownResult?.treatment ? (
            <TreatmentView t={shownResult.treatment} onSource={openSource} />
          ) : (
            <div className="flex flex-col gap-3 text-sm text-muted-foreground">
              <FileText className="size-6" aria-hidden="true" />
              <p>Research appears here: the differential first, then treatment for the working diagnosis you mark.</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

export default App
