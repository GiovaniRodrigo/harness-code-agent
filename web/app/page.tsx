'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import { Activity, Check, ChevronRight, CircleStop, Clock3, Code2, Cpu, LoaderCircle, Play, RefreshCw, Server, ShieldAlert, Terminal, X } from 'lucide-react'

type Provider = 'anthropic' | 'openai' | 'google'
type Status = 'running' | 'succeeded' | 'failed' | 'error'
type Event = { ts: number; step: number; kind: string; [key: string]: unknown }
type Run = { run_id: string; task: string; provider: Provider; model?: string; orchestrate: boolean; status: Status; summary: string; error: string | null }
type RunDetail = Run & { events: Event[] }

const API_BASE = process.env.NEXT_PUBLIC_HARNESS_API || 'http://127.0.0.1:8000'
const fetcher = (url: string) => fetch(url).then(async (response) => {
  if (!response.ok) throw new Error(`API error ${response.status}`)
  return response.json()
})

function statusStyles(status: Status) {
  return {
    running: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    succeeded: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    failed: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
    error: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  }[status]
}

function eventStyles(kind: string) {
  if (kind === 'tool_executed') return 'border-blue-500/35 bg-blue-500/10 text-blue-700 dark:text-blue-300'
  if (kind === 'evaluation_failed') return 'border-amber-500/35 bg-amber-500/10 text-amber-700 dark:text-amber-300'
  if (kind === 'task_completed' || kind === 'orchestration_done') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
  if (kind === 'tool_rejected' || kind === 'stopped_without_tools') return 'border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300'
  return 'border-border bg-muted text-muted-foreground'
}

function compactFields(event: Event) {
  const ignored = new Set(['ts', 'step', 'kind'])
  return Object.entries(event)
    .filter(([key, value]) => !ignored.has(key) && value !== null && value !== undefined)
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`)
    .join('  ·  ')
}

function StatusBadge({ status }: { status: Status }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${statusStyles(status)}`}><span className={status === 'running' ? 'h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500' : `h-1.5 w-1.5 rounded-full ${status === 'succeeded' ? 'bg-emerald-500' : 'bg-red-500'}`} />{status}</span>
}

export default function Page() {
  const { data: historyData, error: historyError, mutate: refreshHistory } = useSWR<{ runs: Run[] }>(`${API_BASE}/runs`, fetcher, { refreshInterval: 5000 })
  const [task, setTask] = useState('')
  const [provider, setProvider] = useState<Provider>('anthropic')
  const [model, setModel] = useState('')
  const [testCommand, setTestCommand] = useState('')
  const [orchestrate, setOrchestrate] = useState(false)
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [requestError, setRequestError] = useState('')
  const timelineRef = useRef<HTMLDivElement>(null)

  const history = historyData?.runs || []
  const isRunning = selectedRun?.status === 'running'

  useEffect(() => {
    if (!selectedRun?.run_id || selectedRun.status !== 'running') return
    let stopped = false
    const poll = async () => {
      try {
        const next = await fetcher(`${API_BASE}/events/${selectedRun.run_id}`) as RunDetail
        if (!stopped) setSelectedRun(next)
        if (!stopped && next.status === 'running') window.setTimeout(poll, 1000)
        else if (!stopped) refreshHistory()
      } catch (error) {
        if (!stopped) {
          setRequestError(error instanceof Error ? error.message : 'Não foi possível consultar os eventos.')
          window.setTimeout(poll, 2000)
        }
      }
    }
    void poll()
    return () => { stopped = true }
  }, [selectedRun?.run_id, selectedRun?.status, refreshHistory])

  useEffect(() => {
    timelineRef.current?.scrollTo({ top: timelineRef.current.scrollHeight, behavior: 'smooth' })
  }, [selectedRun?.events.length])

  const headerMeta = useMemo(() => selectedRun ? `${selectedRun.provider} · ${selectedRun.model || 'provider default'} · ${selectedRun.orchestrate ? 'multi-agent' : 'single-agent'}` : 'Nenhuma execução selecionada', [selectedRun])

  async function selectHistoryRun(run: Run) {
    setRequestError('')
    try {
      const detail = await fetcher(`${API_BASE}/events/${run.run_id}`) as RunDetail
      setSelectedRun(detail)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Não foi possível carregar a execução.')
      setSelectedRun({ ...run, events: [] })
    }
  }

  async function launchTask(event: React.FormEvent) {
    event.preventDefault()
    if (isStarting) return
    if (!task.trim()) {
      setRequestError('Descreva uma task antes de iniciar.')
      return
    }
    setIsStarting(true)
    setRequestError('')
    try {
      const response = await fetch(`${API_BASE}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task: task.trim(), provider, ...(model.trim() ? { model: model.trim() } : {}), orchestrate, ...(testCommand.trim() ? { test_command: testCommand.trim() } : {}) }) })
      if (!response.ok) throw new Error(`Não foi possível iniciar a execução (${response.status}).`)
      const { run_id } = await response.json()
      setSelectedRun({ run_id, task: task.trim(), provider, model: model.trim(), orchestrate, status: 'running', summary: '', error: null, events: [] })
      void refreshHistory()
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Não foi possível iniciar a execução.')
    } finally {
      setIsStarting(false)
    }
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-background text-foreground">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
          <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Code2 className="h-5 w-5" /></div><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Harness control</p><h1 className="text-xl font-semibold tracking-tight">Coding-agent runner</h1></div></div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><Server className="h-3.5 w-3.5" /><span className="max-w-[260px] truncate font-mono">{API_BASE}</span><span className="h-2 w-2 rounded-full bg-emerald-500" /></div>
        </header>

        {requestError && <div role="alert" className="mb-5 flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300"><ShieldAlert className="h-4 w-4 shrink-0" />{requestError}<button className="ml-auto" onClick={() => setRequestError('')} aria-label="Fechar erro"><X className="h-4 w-4" /></button></div>}

        <div className="grid gap-5 lg:grid-cols-[minmax(300px,0.82fr)_minmax(0,1.5fr)]">
          <section className="rounded-xl border border-border bg-card shadow-sm"><div className="border-b border-border px-5 py-4"><div className="flex items-center gap-2"><Terminal className="h-4 w-4 text-muted-foreground" /><h2 className="font-semibold">Launch a task</h2></div><p className="mt-1 text-sm text-muted-foreground">Configure uma nova execução do agente.</p></div>
            <form onSubmit={launchTask} className="space-y-5 p-5">
              <div><label htmlFor="task" className="mb-2 block text-sm font-medium">Task description <span className="text-red-500">*</span></label><textarea id="task" required value={task} onChange={(event) => setTask(event.target.value)} placeholder="Describe what the coding agent should build or investigate..." className="min-h-40 w-full resize-y rounded-lg border border-input bg-background px-3 py-3 text-sm leading-6 shadow-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20" /></div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2"><div><label htmlFor="provider" className="mb-2 block text-sm font-medium">Provider</label><select id="provider" value={provider} onChange={(event) => setProvider(event.target.value as Provider)} className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring/20"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option><option value="google">Google</option></select></div><div><label htmlFor="model" className="mb-2 block text-sm font-medium">Model</label><input id="model" value={model} onChange={(event) => setModel(event.target.value)} placeholder="provider default" className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20" /></div></div>
              <div><label htmlFor="test-command" className="mb-2 block text-sm font-medium">Test command <span className="font-normal text-muted-foreground">(optional)</span></label><input id="test-command" value={testCommand} onChange={(event) => setTestCommand(event.target.value)} placeholder="python3 -m pytest -q" className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20" /></div>
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-3 py-3"><span><span className="block text-sm font-medium">Orchestrate</span><span className="block text-xs text-muted-foreground">Multi-agent coordination</span></span><input type="checkbox" checked={orchestrate} onChange={(event) => setOrchestrate(event.target.checked)} className="peer sr-only" /><span aria-hidden="true" className={`relative h-6 w-11 rounded-full transition-colors ${orchestrate ? 'bg-primary' : 'bg-muted-foreground/30'}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-background shadow transition-transform ${orchestrate ? 'translate-x-6' : 'translate-x-1'}`} /></span></label>
              <button disabled={!task.trim() || isStarting} className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"><Play className="h-4 w-4 fill-current" />{isStarting ? 'Starting...' : 'Run task'}</button>
            </form>
          </section>

          <section className="flex min-h-[560px] flex-col rounded-xl border border-border bg-card shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4"><div><div className="flex items-center gap-2"><Activity className="h-4 w-4 text-muted-foreground" /><h2 className="font-semibold">Run</h2></div><p className="mt-1 max-w-[600px] truncate font-mono text-xs text-muted-foreground">{headerMeta}</p></div>{selectedRun && <StatusBadge status={selectedRun.status} />}</div>
            <div ref={timelineRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-5">{!selectedRun ? <div className="flex h-full min-h-[430px] flex-col items-center justify-center text-center"><div className="mb-4 rounded-full border border-dashed border-border p-4"><Clock3 className="h-6 w-6 text-muted-foreground" /></div><p className="font-medium">Pronto para executar</p><p className="mt-1 max-w-xs text-sm text-muted-foreground">Inicie uma task ou selecione uma execução no histórico.</p></div> : selectedRun.events.length === 0 && isRunning ? <div className="flex h-full min-h-[430px] flex-col items-center justify-center text-center"><LoaderCircle className="mb-3 h-6 w-6 animate-spin text-muted-foreground" /><p className="text-sm text-muted-foreground">Aguardando o primeiro evento...</p></div> : selectedRun.events.map((event, index) => <div key={`${event.ts}-${index}`} className="relative flex gap-3"><div className="relative flex w-7 shrink-0 justify-center"><div className={`z-10 mt-1 h-2.5 w-2.5 rounded-full border-2 bg-card ${eventStyles(event.kind).split(' ')[0].replace('border-', 'border-')}`} />{index < selectedRun.events.length - 1 && <div className="absolute top-3 h-full w-px bg-border" />}</div><div className={`min-w-0 flex-1 rounded-lg border px-3 py-2 ${eventStyles(event.kind)}`}><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs font-semibold">{event.kind}</span><span className="rounded bg-background/60 px-1.5 py-0.5 text-[10px] font-medium">step {event.step}</span><span className="ml-auto font-mono text-[10px] opacity-60">{new Date(event.ts * 1000).toLocaleTimeString()}</span></div>{compactFields(event) && <p className="mt-1 truncate font-mono text-[11px] opacity-75">{compactFields(event)}</p>}</div></div>)}
              {selectedRun && !isRunning && selectedRun.summary && <div className="mt-5 border-t border-border pt-5"><p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"><Check className="h-3.5 w-3.5" />Final summary</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 font-mono text-xs leading-5 text-foreground">{selectedRun.summary}</pre></div>}
              {selectedRun?.error && <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">{selectedRun.error}</div>}
            </div>
          </section>
        </div>

        <section className="mt-5 rounded-xl border border-border bg-card shadow-sm"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><div className="flex items-center gap-2"><RefreshCw className="h-4 w-4 text-muted-foreground" /><h2 className="font-semibold">History</h2></div><p className="mt-1 text-sm text-muted-foreground">Execuções recentes do harness.</p></div><span className="font-mono text-xs text-muted-foreground">{history.length} runs</span></div><div className="divide-y divide-border">{historyError ? <p className="px-5 py-6 text-sm text-muted-foreground">Histórico indisponível. Verifique a conexão com a API.</p> : history.length === 0 ? <p className="px-5 py-6 text-sm text-muted-foreground">Nenhuma execução encontrada.</p> : history.map((run) => <button key={run.run_id} onClick={() => void selectHistoryRun(run)} className={`flex w-full items-center gap-3 px-5 py-3 text-left transition hover:bg-muted/60 ${selectedRun?.run_id === run.run_id ? 'bg-muted/60' : ''}`}><StatusBadge status={run.status} /><span className="min-w-0 flex-1 truncate text-sm font-medium">{run.task}</span><span className="hidden shrink-0 items-center gap-1.5 text-xs text-muted-foreground sm:flex"><Cpu className="h-3.5 w-3.5" />{run.provider} · {run.model || 'default'}</span><ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" /></button>)}</div></section>
      </div>
    </main>
  )
}
