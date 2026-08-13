'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import type { AnalyticsSummary, CallRecord } from '@/app/api/analytics/route';

const EMPTY: AnalyticsSummary = {
  total: 0,
  successful: 0,
  failed: 0,
  success_rate: 0,
  recent: [],
};

const FAILURE_LABELS: Record<string, string> = {
  incomplete_enquiry: 'Incomplete enquiry',
  no_engagement: 'No engagement',
  tool_error: 'Tool error',
};

const REASON_LABELS: Record<string, string> = {
  order_line: 'Order noted',
  catalogue: 'Product found',
  escalation: 'Human help',
};

function formatWhen(iso: string) {
  try {
    return new Intl.DateTimeFormat('en-IN', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'Asia/Kolkata',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function formatDuration(seconds: number) {
  const safe = Math.max(0, seconds || 0);
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function reasonLabel(row: CallRecord) {
  if (row.outcome === 'success') {
    const labels = (row.success_reasons || []).map((key) => REASON_LABELS[key] ?? key);
    return labels.length ? labels.join(' · ') : 'Successful enquiry';
  }
  return FAILURE_LABELS[row.failure_type] ?? row.failure_type || 'Failed';
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsSummary>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (isPoll = false) => {
    if (!isPoll) {
      setLoading(true);
    }
    setError('');
    try {
      const res = await fetch('/api/analytics', { cache: 'no-store' });
      if (!res.ok) {
        throw new Error('Could not load analytics');
      }
      const payload = (await res.json()) as AnalyticsSummary;
      setData({
        total: payload.total ?? 0,
        successful: payload.successful ?? 0,
        failed: payload.failed ?? 0,
        success_rate: payload.success_rate ?? 0,
        recent: payload.recent ?? [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(true), 5000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <main className="bg-dd-bg text-dd-ink h-svh overflow-y-auto overscroll-y-contain">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-10 pb-20 sm:px-8">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-dd-muted text-sm tracking-wide uppercase">Dukaan Dost</p>
            <h1 className="text-2xl font-semibold tracking-tight">Call analytics</h1>
            <p className="text-dd-muted mt-1 text-sm">
              A call is successful if an order line was noted, a catalogue product was found, or a
              human-help escalation was created. No names or transcripts are stored here.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="border-dd-border bg-dd-card text-dd-ink hover:border-dd-accent hover:text-dd-accent rounded-md border px-4 py-2 text-sm transition disabled:opacity-60"
            >
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
            <Link
              href="/escalations"
              className="text-dd-accent hover:text-dd-accent-hover text-sm underline-offset-4 hover:underline"
            >
              Escalations
            </Link>
            <Link
              href="/"
              className="text-dd-accent hover:text-dd-accent-hover text-sm underline-offset-4 hover:underline"
            >
              Back to voice
            </Link>
          </div>
        </header>

        {error ? (
          <p className="border-dd-border bg-dd-card rounded-md border px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <section className="grid gap-3 sm:grid-cols-3">
          <div className="border-dd-border bg-dd-card rounded-lg border px-5 py-4">
            <p className="text-dd-muted text-xs tracking-wide uppercase">Total calls</p>
            <p className="mt-1 text-3xl font-semibold">{data.total}</p>
          </div>
          <div className="border-dd-border bg-dd-card rounded-lg border px-5 py-4">
            <p className="text-dd-muted text-xs tracking-wide uppercase">Successful</p>
            <p className="mt-1 text-3xl font-semibold text-[#4c8c4a]">{data.successful}</p>
          </div>
          <div className="border-dd-border bg-dd-card rounded-lg border px-5 py-4">
            <p className="text-dd-muted text-xs tracking-wide uppercase">Failed</p>
            <p className="mt-1 text-3xl font-semibold">{data.failed}</p>
          </div>
        </section>

        <p className="text-dd-muted text-sm">
          Success rate: <span className="text-dd-ink font-medium">{data.success_rate}%</span>
        </p>

        {!loading && !error && data.recent.length === 0 ? (
          <div className="border-dd-border bg-dd-card rounded-lg border px-5 py-8 text-center">
            <p className="font-medium">No calls recorded yet</p>
            <p className="text-dd-muted mt-2 text-sm">
              Start a voice call, then hang up. Totals update from real browser sessions.
            </p>
          </div>
        ) : null}

        {data.recent.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {data.recent.map((row) => (
              <li
                key={row.call_id}
                className="border-dd-border bg-dd-card rounded-lg border px-5 py-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-mono text-sm font-semibold">{row.call_id}</p>
                    <p className="text-dd-muted mt-1 text-xs">{formatWhen(row.started_at)}</p>
                  </div>
                  <span className="border-dd-border rounded-full border px-2.5 py-0.5 text-xs capitalize">
                    {row.outcome}
                  </span>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-dd-muted">Duration</dt>
                    <dd>{formatDuration(row.duration_s)}</dd>
                  </div>
                  <div>
                    <dt className="text-dd-muted">Channel</dt>
                    <dd className="capitalize">{row.channel}</dd>
                  </div>
                  <div>
                    <dt className="text-dd-muted">Language</dt>
                    <dd>{row.language}</dd>
                  </div>
                  <div className="sm:col-span-3">
                    <dt className="text-dd-muted">Result</dt>
                    <dd>{reasonLabel(row)}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </main>
  );
}
