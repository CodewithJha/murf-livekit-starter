'use client';

import { useEffect } from 'react';

/**
 * Boosts LiveKit room <audio> playback above the browser's 1.0 volume cap
 * via Web Audio GainNode.
 */
export function AgentAudioBoost({ gain = 2 }: { gain?: number }) {
  useEffect(() => {
    const boosted = new WeakSet<HTMLMediaElement>();
    const contexts: AudioContext[] = [];

    const boostElement = (el: HTMLMediaElement) => {
      if (boosted.has(el)) return;
      boosted.add(el);
      el.volume = 1;

      try {
        const Ctx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const ctx = new Ctx();
        contexts.push(ctx);
        const source = ctx.createMediaElementSource(el);
        const gainNode = ctx.createGain();
        gainNode.gain.value = gain;
        source.connect(gainNode);
        gainNode.connect(ctx.destination);
        if (ctx.state === 'suspended') {
          const resume = () => void ctx.resume();
          window.addEventListener('pointerdown', resume, { once: true });
          window.addEventListener('keydown', resume, { once: true });
        }
      } catch {
        // Element may already be connected; ignore.
      }
    };

    const scan = () => {
      document.querySelectorAll('audio').forEach((node) => {
        boostElement(node as HTMLMediaElement);
      });
    };

    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      for (const ctx of contexts) {
        void ctx.close();
      }
    };
  }, [gain]);

  return null;
}
