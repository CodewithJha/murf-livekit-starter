'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import type { EscalationRecord } from '@/app/api/escalations/route';

const REASON_LABELS: Record<string, string> = {
  payment_refund_dispute: 'Payment / refund dispute',
  order_dispute: 'Order dispute',
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

export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<EscalationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/escalations', { cache: 'no-store' });
      if (!res.ok) {
        throw new Error('Could not load escalations');
      }
      const data = (await res.json()) as { escalations: EscalationRecord[] };
      setEscalations(data.escalations ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="bg-dd-bg text-dd-ink min-h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-10 sm:px-8">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-dd-muted text-sm tracking-wide uppercase">Dukaan Dost</p>
            <h1 className="text-2xl font-semibold tracking-tight">Open help requests</h1>
            <p className="text-dd-muted mt-1 text-sm">
              Human-help escalations from voice calls — shopkeeper review queue.
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

        {!loading && !error && escalations.length === 0 ? (
          <div className="border-dd-border bg-dd-card rounded-lg border px-5 py-8 text-center">
            <p className="font-medium">No open requests</p>
            <p className="text-dd-muted mt-2 text-sm">
              When a caller escalates a payment or order dispute, it will appear here.
            </p>
          </div>
        ) : null}

        <ul className="flex flex-col gap-4">
          {escalations.map((item) => (
            <li
              key={item.reference_id}
              className="border-dd-border bg-dd-card rounded-lg border px-5 py-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-sm font-semibold">{item.reference_id}</p>
                  <p className="text-dd-muted mt-1 text-xs">{formatWhen(item.created_at)}</p>
                </div>
                <span className="border-dd-border rounded-full border px-2.5 py-0.5 text-xs capitalize">
                  {item.urgency} urgency
                </span>
              </div>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-dd-muted">Reason</dt>
                  <dd>{REASON_LABELS[item.reason] ?? item.reason}</dd>
                </div>
                <div>
                  <dt className="text-dd-muted">Caller</dt>
                  <dd>{item.caller_name}</dd>
                </div>
                <div>
                  <dt className="text-dd-muted">Language</dt>
                  <dd>{item.language}</dd>
                </div>
                <div>
                  <dt className="text-dd-muted">Preferred follow-up</dt>
                  <dd>{item.preferred_followup || 'Not specified'}</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-dd-muted">What happened</dt>
                  <dd className="mt-0.5">{item.what_happened}</dd>
                </div>
                {item.already_checked ? (
                  <div className="sm:col-span-2">
                    <dt className="text-dd-muted">Already checked</dt>
                    <dd className="mt-0.5">{item.already_checked}</dd>
                  </div>
                ) : null}
              </dl>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
