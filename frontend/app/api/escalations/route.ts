import { readFile } from 'fs/promises';
import path from 'path';
import { NextResponse } from 'next/server';

export type EscalationRecord = {
  reference_id: string;
  created_at: string;
  status: string;
  reason: string;
  urgency: string;
  caller_name: string;
  language: string;
  preferred_followup: string;
  what_happened: string;
  already_checked: string;
  caller_consented: boolean;
};

const JSONL_PATH = path.join(process.cwd(), '..', 'backend', 'data', 'escalations.jsonl');

export const revalidate = 0;

function parseJsonl(raw: string): EscalationRecord[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as EscalationRecord);
}

export async function GET() {
  try {
    const raw = await readFile(JSONL_PATH, 'utf-8');
    const escalations = parseJsonl(raw)
      .filter((row) => row.status === 'open')
      .sort((a, b) => b.created_at.localeCompare(a.created_at));

    return NextResponse.json(
      { escalations },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT') {
      return NextResponse.json(
        { escalations: [] },
        { headers: { 'Cache-Control': 'no-store' } }
      );
    }
    console.error('Failed to read escalations.jsonl', error);
    return NextResponse.json({ error: 'Could not load escalations' }, { status: 500 });
  }
}
