'use client';

import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

/**
 * JS-driven waveform (requestAnimationFrame).
 * Safari respects prefers-reduced-motion and can skip CSS/Motion animations;
 * rAF still runs so speaking/listening feedback stays visible.
 */
export function Waveform({
  active = false,
  bars = 28,
  className,
}: {
  active?: boolean;
  bars?: number;
  className?: string;
}) {
  const seeds = useMemo(
    () => Array.from({ length: bars }, (_, i) => 0.35 + ((i * 41) % 65) / 100),
    [bars]
  );
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let frame = 0;
    let raf = 0;
    let last = 0;

    const loop = (now: number) => {
      if (now - last > 48) {
        frame += 1;
        setTick(frame);
        last = now;
      }
      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      className={cn(
        'flex h-11 w-full max-w-[240px] items-center justify-center gap-[3px]',
        className
      )}
      aria-hidden
    >
      {seeds.map((seed, index) => {
        const wave = Math.sin(tick * 0.35 + index * 0.55) * 0.5 + 0.5;
        const idleH = 8 + seed * 8;
        const activeH = 10 + seed * 14 + wave * (18 + seed * 12);
        const height = active ? activeH : idleH;
        const opacity = active ? 0.45 + wave * 0.55 : 0.28;

        return (
          <span
            key={index}
            style={{
              display: 'inline-block',
              width: 3,
              height: `${Math.round(height)}px`,
              borderRadius: 999,
              backgroundColor: 'rgba(184, 116, 68, 0.85)',
              opacity,
              transformOrigin: 'center bottom',
            }}
          />
        );
      })}
    </div>
  );
}
