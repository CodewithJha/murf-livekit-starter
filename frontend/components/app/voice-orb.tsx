'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

export type VoiceOrbMode = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';

/**
 * Compact voice control. Speaking/listening use a shuttle-line ring
 * (traveling arc) instead of a large pulsing glow.
 */
export function VoiceOrb({
  mode = 'idle',
  className,
  onClick,
}: {
  mode?: VoiceOrbMode;
  className?: string;
  onClick?: () => void;
}) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let raf = 0;
    let last = 0;
    let frame = 0;
    const loop = (now: number) => {
      if (now - last > 32) {
        frame += 1;
        setTick(frame);
        last = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const t = tick * 0.08;
  const speaking = mode === 'speaking';
  const listening = mode === 'listening';
  const thinking = mode === 'thinking' || mode === 'connecting';

  // Shuttle angle travels around the ring
  const shuttleAngle =
    speaking || listening ? (tick * (speaking ? 4.5 : 2.2)) % 360 : thinking ? (tick * 2.2) % 360 : 0;

  const coreScale = speaking
    ? 1 + Math.sin(t * 2) * 0.012
    : listening
      ? 1 + Math.sin(t * 1.1) * 0.01
      : 1 + Math.sin(t * 0.45) * 0.008;

  return (
    <button
      type="button"
      aria-label="Voice"
      disabled={!onClick}
      onClick={onClick}
      data-orb="shuttle-v3"
      className={cn(
        'relative flex shrink-0 items-center justify-center overflow-visible rounded-full border-0 bg-transparent p-0',
        onClick ? 'cursor-pointer' : 'cursor-default',
        className
      )}
      style={{ width: 128, height: 128 }}
    >
      {/* Shuttle line ring — primary speaking/listening effect */}
      {(speaking || listening || thinking) && (
        <span
          className="pointer-events-none absolute inset-0 rounded-full"
          style={{
            transform: `rotate(${shuttleAngle}deg)`,
            background: speaking
              ? 'conic-gradient(from 0deg, transparent 0%, transparent 62%, rgba(184,116,68,0.15) 72%, rgba(184,116,68,0.95) 86%, rgba(184,116,68,0.15) 94%, transparent 100%)'
              : listening
                ? 'conic-gradient(from 0deg, transparent 0%, transparent 70%, rgba(184,116,68,0.7) 85%, transparent 100%)'
                : 'conic-gradient(from 0deg, transparent 0%, rgba(184,116,68,0.5) 28%, transparent 58%)',
            WebkitMask:
              'radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 1.5px))',
            mask: 'radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 1.5px))',
          }}
        />
      )}

      {/* Quiet idle ring */}
      {mode === 'idle' && (
        <span
          className="pointer-events-none absolute inset-[6%] rounded-full border"
          style={{
            borderColor: 'rgba(184,116,68,0.28)',
            opacity: 0.55 + Math.sin(t * 0.5) * 0.15,
          }}
        />
      )}

      {/* Compact core — no big glow bloom */}
      <div
        className="relative z-[1] rounded-full"
        style={{
          width: '58%',
          height: '58%',
          transform: `scale(${coreScale})`,
          background:
            'radial-gradient(circle at 30% 26%, #FFFFFF 0%, #F6F2EB 40%, #E8D5C0 68%, #B87444 100%)',
          boxShadow: '0 10px 24px -14px rgba(184,116,68,0.45), inset 0 1px 1px rgba(255,255,255,0.85)',
        }}
      >
        <div
          className="absolute rounded-full"
          style={{
            inset: '16%',
            background:
              'radial-gradient(circle at 38% 32%, rgba(255,255,255,0.95), transparent 70%)',
          }}
        />
      </div>
    </button>
  );
}
