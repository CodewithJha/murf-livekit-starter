'use client';

import { Ear, Loader2, Mic, MicOff, Phone, PhoneOff, Volume2, Wifi } from 'lucide-react';
import { motion } from 'motion/react';
import { VoiceOrb, type VoiceOrbMode } from '@/components/app/voice-orb';
import { Waveform } from '@/components/app/waveform';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

export type WorkspaceStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'ended';

const STATUS_META: Record<
  WorkspaceStatus,
  { label: string; detail: string; tone: string; Icon: typeof Mic }
> = {
  idle: {
    label: 'Idle',
    detail: 'Ready when you are',
    tone: 'bg-[#F3EEE6] text-dd-ink',
    Icon: Mic,
  },
  connecting: {
    label: 'Connecting',
    detail: 'Joining the call…',
    tone: 'bg-[#F4E8DA] text-[#6B3F1F]',
    Icon: Loader2,
  },
  connected: {
    label: 'Connected',
    detail: 'On the call',
    tone: 'bg-[#E8F2E7] text-[#2F5D2E]',
    Icon: Wifi,
  },
  listening: {
    label: 'Listening',
    detail: 'Listening to you',
    tone: 'bg-[#E8F2E7] text-[#2F5D2E]',
    Icon: Ear,
  },
  thinking: {
    label: 'Thinking',
    detail: 'Preparing a reply…',
    tone: 'bg-[#F0EBE4] text-dd-ink',
    Icon: Loader2,
  },
  speaking: {
    label: 'Speaking',
    detail: 'Agent is speaking',
    tone: 'bg-[#F4E8DA] text-[#6B3F1F]',
    Icon: Volume2,
  },
  ended: {
    label: 'Call ended',
    detail: 'Start again anytime',
    tone: 'bg-[#EEEAE4] text-dd-muted',
    Icon: PhoneOff,
  },
};

const PROMPTS = ['Milk', 'Tomatoes', 'Medical Store', 'Fresh Fruits', 'Nearby Grocery'];

function orbMode(status: WorkspaceStatus): VoiceOrbMode {
  if (status === 'speaking') return 'speaking';
  if (status === 'listening') return 'listening';
  if (status === 'thinking') return 'thinking';
  if (status === 'connecting') return 'connecting';
  return 'idle';
}

function formatDuration(seconds: number) {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0');
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, '0');
  return `${m}:${s}`;
}

export function LeftVoicePanel({
  companyName,
  status,
  connected,
  micEnabled,
  micButtonProps,
  language,
  onLanguageChange,
  durationSec,
  micError,
  onStart,
  onEnd,
  startLabel = 'Start call',
}: {
  companyName: string;
  status: WorkspaceStatus;
  connected: boolean;
  micEnabled: boolean;
  micButtonProps: React.ButtonHTMLAttributes<HTMLButtonElement>;
  language: string;
  onLanguageChange: (value: string) => void;
  durationSec: number;
  micError: string | null;
  onStart: () => void;
  onEnd: () => void;
  startLabel?: string;
}) {
  const meta = STATUS_META[status];
  const StatusIcon = meta.Icon;
  const spin = status === 'connecting' || status === 'thinking';
  const callActive = connected || status === 'connecting';

  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-white px-6 pb-7"
      style={{ paddingTop: 18 }}
    >
      <div className="flex shrink-0 items-center gap-3">
        <span className="bg-dd-accent flex size-10 shrink-0 items-center justify-center rounded-[14px] text-[13px] font-semibold text-white">
          DD
        </span>
        <div className="min-w-0 flex-1 overflow-hidden">
          <p className="text-dd-ink truncate text-[15px] font-semibold tracking-tight">
            {companyName}
          </p>
          <p className="text-dd-muted truncate text-[12px]">Voice-first Local Commerce</p>
        </div>
      </div>

      <motion.div
        key={status}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          'mt-7 flex shrink-0 items-center gap-3 overflow-hidden rounded-[20px] px-4 py-3.5',
          meta.tone
        )}
      >
        <StatusIcon className={cn('size-4 shrink-0', spin && 'animate-spin')} strokeWidth={2} />
        <div className="min-w-0 overflow-hidden">
          <p className="truncate text-[13px] font-semibold">{meta.label}</p>
          <p className="mt-0.5 truncate text-[12px] opacity-80">{meta.detail}</p>
        </div>
      </motion.div>

      {micError ? (
        <div
          role="alert"
          className="mt-4 shrink-0 overflow-hidden rounded-[20px] border border-red-200 bg-[#FFF8F6] px-4 py-3 text-[12px] leading-relaxed text-red-800"
        >
          <p className="font-semibold">Microphone blocked</p>
          <p className="mt-1 opacity-90">{micError}</p>
          <p className="mt-1 opacity-80">Allow mic in site settings, then start again.</p>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-5 overflow-hidden py-6">
        <VoiceOrb mode={orbMode(status)} onClick={callActive ? undefined : onStart} />
        <Waveform
          active={status === 'listening' || status === 'speaking'}
          className="max-w-[240px]"
        />
      </div>

      <div className="flex shrink-0 flex-col gap-3 overflow-hidden">
        {/* Idle / ended → Start; active call → End call (subtle red) */}
        {!callActive && status !== 'ended' ? (
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              size="lg"
              onClick={onStart}
              className="bg-dd-accent hover:bg-dd-accent-hover h-12 w-full rounded-[18px] text-[14px] font-semibold text-white shadow-[0_12px_28px_-16px_rgba(184,116,68,0.65)]"
            >
              <Phone className="size-4" strokeWidth={2} />
              {startLabel}
            </Button>
          </motion.div>
        ) : null}

        {callActive && status !== 'ended' ? (
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              size="lg"
              onClick={onEnd}
              disabled={status === 'connecting'}
              className="h-12 w-full rounded-[18px] border border-[#E2B4AA] bg-[#F6EDEA] text-[14px] font-semibold text-[#9A4F42] shadow-[0_8px_20px_-14px_rgba(154,79,66,0.35)] hover:bg-[#F0E0DB] disabled:opacity-50"
            >
              <PhoneOff className="size-4" strokeWidth={2} />
              End call
            </Button>
          </motion.div>
        ) : null}

        {status === 'ended' ? (
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              size="lg"
              onClick={onStart}
              className="bg-dd-accent hover:bg-dd-accent-hover h-12 w-full rounded-[18px] text-[14px] font-semibold text-white"
            >
              <Phone className="size-4" strokeWidth={2} />
              Start again
            </Button>
          </motion.div>
        ) : null}

        <div className="grid grid-cols-2 gap-3">
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              type="button"
              variant="outline"
              size="lg"
              aria-pressed={!micEnabled}
              className={cn(
                'border-dd-border h-11 w-full rounded-[18px] bg-white text-[12px] font-semibold',
                !micEnabled && 'border-red-200 bg-[#FFF8F6] text-red-700'
              )}
              {...micButtonProps}
              disabled={!connected}
            >
              {micEnabled ? <Mic className="size-3.5" /> : <MicOff className="size-3.5" />}
              {micEnabled ? 'Mute' : 'Unmute'}
            </Button>
          </motion.div>

          <label className="border-dd-border relative flex h-11 min-w-0 items-center overflow-hidden rounded-[18px] border bg-white px-3 text-[12px] font-semibold transition-shadow hover:shadow-[0_6px_16px_-12px_rgba(42,36,31,0.35)]">
            <span className="sr-only">Language</span>
            <select
              value={language}
              onChange={(e) => onLanguageChange(e.target.value)}
              className="text-dd-ink w-full min-w-0 appearance-none truncate bg-transparent outline-none"
            >
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="auto">Auto</option>
            </select>
          </label>
        </div>

      </div>

      <div className="mt-5 shrink-0 overflow-hidden">
        <p className="text-dd-muted mb-3 text-[12px]">Quick prompts</p>
        <div className="flex flex-wrap gap-2">
          {PROMPTS.map((item) => (
            <motion.button
              key={item}
              type="button"
              whileHover={{ y: -2, backgroundColor: '#F3EEE6' }}
              whileTap={{ scale: 0.97 }}
              onClick={onStart}
              className="border-dd-border text-dd-ink max-w-full truncate rounded-full border bg-[#FAF7F2] px-3 py-1.5 text-[12px] font-medium"
            >
              {item}
            </motion.button>
          ))}
        </div>
      </div>

      <div className="border-dd-border text-dd-muted mt-6 grid shrink-0 grid-cols-2 gap-x-4 gap-y-2.5 overflow-hidden border-t pt-5 text-[12px]">
        <span>Duration</span>
        <span className="text-dd-ink text-right font-medium tabular-nums">
          {formatDuration(durationSec)}
        </span>
        <span>Microphone</span>
        <span className="text-dd-ink text-right font-medium">
          {!connected ? 'Off' : micEnabled ? 'On' : 'Muted'}
        </span>
        <span>Language</span>
        <span className="text-dd-ink truncate text-right font-medium uppercase">{language}</span>
        <span>Connection</span>
        <span className="text-dd-ink text-right font-medium">
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
    </aside>
  );
}
