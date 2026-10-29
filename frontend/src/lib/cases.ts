import type { ChatResult } from "@/lib/api"

export type Turn =
  | { role: "user"; text: string }
  | { role: "copilot"; result: ChatResult }

export type Case = { id: string; title: string; createdAt: string; turns: Turn[] }

const KEY = "copilot.cases.v1"

// shortcut: cases live in this browser only, because the API has no thread listing;
// the backend's in-memory checkpointer also forgets threads on restart. Move both server-side before real use.
export function loadCases(): Case[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]")
  } catch {
    return []
  }
}

export function saveCases(cases: Case[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(cases))
  } catch {
    // Storage full or blocked: the session still works, it just won't survive a reload.
  }
}

export const titleFrom = (text: string) => {
  const line = text.trim().split("\n")[0]
  return line.length > 48 ? `${line.slice(0, 47)}…` : line
}
