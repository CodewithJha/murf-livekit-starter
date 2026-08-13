import { readFile } from 'fs/promises';
import path from 'path';
import { NextResponse } from 'next/server';

export type CallRecord = {
  call_id: string;
  started_at: string;
  ended_at: string;
  duration_s: number;
  channel: string;
  language: string;
  outcome: 'success' | 'failed' | string;
  failure_type: string;
  order_line_count: number;
  catalogue_found: boolean;
  escalation_created: boolean;
  success_reasons: string[];
};

export type AnalyticsSummary = {
  total: number;
  successful: number;
  failed: number;
  success_rate: number;
  recent: CallRecord[];
};

const JSONL_PATH = path.join(process.cwd(), '..', 'backend', 'data', 'calls.jsonl');

export const revalidate = 0;

function parseJsonl(raw: string): CallRecord[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as CallRecord);
}

function summarize(rows: CallRecord[]): AnalyticsSummary {
  const recent = [...rows].sort((a, b) => b.started_at.localeCompare(a.started_at));
  const total = rows.length;
  const successful = rows.filter((row) => row.outcome === 'success').length;
  const failed = rows.filter((row) => row.outcome === 'failed').length;
  const success_rate = total ? Math.round((1000 * successful) / total) / 10 : 0;
  return { total, successful, failed, success_rate, recent };
}

export async function GET() {
  try {
    const raw = await readFile(JSONL_PATH, 'utf-8');
    const calls = parseJsonl(raw);
    return NextResponse.json(summarize(calls), {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT') {
      return NextResponse.json(
        { total: 0, successful: 0, failed: 0, success_rate: 0, recent: [] },
        { headers: { 'Cache-Control': 'no-store' } }
      );
    }
    console.error('Failed to read calls.jsonl', error);
    return NextResponse.json({ error: 'Could not load analytics' }, { status: 500 });
  }
}
