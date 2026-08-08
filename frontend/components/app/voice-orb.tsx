'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

export type VoiceOrbMode = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';

/**
 * Voice orb with JS-driven pulse so Safari + Reduce Motion still show activity.
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
      return;
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const t = tick * 0.08;
  let scale = 1;
  let glow = 0.35;

  if (mode === 'speaking') {
    scale = 1 + Math.sin(t * 2.2) * 0.045 + Math.sin(t * 3.1) * 0.02;
    glow = 0.45 + (Math.sin(t * 2.2) * 0.5 + 0.5) * 0.35;
  } else if (mode === 'listening') {
    scale = 1 + Math.sin(t * 1.1) * 0.035;
    glow = 0.4 + (Math.sin(t * 1.1) * 0.5 + 0.5) * 0.3;
  } else if (mode === 'thinking' || mode === 'connecting') {
    scale = 1 + Math.sin(t * 0.7) * 0.02;
    glow = 0.32 + (Math.sin(t * 0.7) * 0.5 + 0.5) * 0.18;
  } else {
    scale = 1 + Math.sin(t * 0.45) * 0.012;
    glow = 0.28 + (Math.sin(t * 0.45) * 0.5 + 0.5) * 0.16;
  }

  const ringRotate =
    mode === 'thinking' || mode === 'connecting' ? (tick * 2.2) % 360 : 0;

  return (
    <button
      type="button"
      aria-label="Voice"
      disabled={!onClick}
      onClick={onClick}
      className={cn(
        'relative flex size-[196px] shrink-0 items-center justify-center overflow-hidden rounded-full border-0 bg-transparent p-0',
        onClick ? 'cursor-pointer' : 'cursor-default',
        className
      )}
    >
      <span
        className="pointer-events-none absolute inset-[-8%] rounded-full bg-[#B87444] blur-2xl"
        style={{ opacity: glow, transform: `scale(${0.95 + glow * 0.15})` }}
      />

      {(mode === 'idle' || mode === 'listening') && (
        <>
          <span
            className="pointer-events-none absolute inset-[8%] rounded-full border border-[#B87444]/30"
            style={{
              transform: `scale(${0.92 + (Math.sin(t) * 0.5 + 0.5) * 0.28})`,
              opacity: 0.35 - (Math.sin(t) * 0.5 + 0.5) * 0.3,
            }}
          />
          <span
            className="pointer-events-none absolute inset-[8%] rounded-full border border-[#B87444]/18"
            style={{
              transform: `scale(${0.92 + (Math.sin(t + 1.2) * 0.5 + 0.5) * 0.28})`,
              opacity: 0.28 - (Math.sin(t + 1.2) * 0.5 + 0.5) * 0.25,
            }}
          />
        </>
      )}

      {(mode === 'thinking' || mode === 'connecting') && (
        <span
          className="pointer-events-none absolute inset-[-4%] rounded-full"
          style={{
            transform: `rotate(${ringRotate}deg)`,
            background:
              'conic-gradient(from 0deg, transparent 0%, rgba(184,116,68,0.55) 28%, transparent 58%)',
            WebkitMask:
              'radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1px))',
            mask: 'radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1px))',
          }}
        />
      )}

      <div
        className="relative z-[1] size-[72%] rounded-full"
        style={{
          transform: `scale(${scale})`,
          background:
            'radial-gradient(circle at 30% 26%, #FFFFFF 0%, #F6F2EB 36%, #E8D5C0 64%, #B87444 100%)',
          boxShadow:
            '0 24px 50px -24px rgba(184,116,68,0.5), inset 0 1px 1px rgba(255,255,255,0.85)',
        }}
      >
        <div className="absolute inset-[14%] rounded-full bg-[radial-gradient(circle_at_38%_32%,rgba(255,255,255,0.95),transparent_70%)]" />
      </div>
    </button>
  );
}
