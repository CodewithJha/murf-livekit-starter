'use client';

import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

/**
 * Flat shuttle-line indicator — short ticks on a thin track (not tall bars).
 * JS rAF so Safari always animates.
 */
export function Waveform({
  active = false,
  bars = 20,
  className,
}: {
  active?: boolean;
  bars?: number;
  className?: string;
}) {
  const seeds = useMemo(
    () => Array.from({ length: bars }, (_, i) => 0.4 + ((i * 37) % 60) / 100),
    [bars]
  );
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let frame = 0;
    let raf = 0;
    let last = 0;

    const loop = (now: number) => {
      if (now - last > 40) {
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
      className={cn('flex w-full items-center justify-center', className)}
      style={{
        height: 14,
        maxWidth: 168,
        gap: 3,
      }}
      aria-hidden
      data-waveform="shuttle-v2"
    >
      {seeds.map((seed, index) => {
        // Traveling shuttle: a soft peak moves across the line
        const phase = (tick * 0.28 + index * 0.45) % (Math.PI * 2);
        const wave = Math.sin(phase) * 0.5 + 0.5;
        const idleH = 3;
        const activeH = 3 + wave * (7 + seed * 3);
        const height = active ? activeH : idleH;
        const opacity = active ? 0.35 + wave * 0.65 : 0.3;

        return (
          <span
            key={index}
            style={{
              display: 'block',
              width: 2,
              height: `${Math.round(height)}px`,
              borderRadius: 999,
              backgroundColor: '#B87444',
              opacity,
              flexShrink: 0,
            }}
          />
        );
      })}
    </div>
  );
}
