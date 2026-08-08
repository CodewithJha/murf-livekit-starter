'use client';

import { useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import { cn } from '@/lib/shadcn/utils';

export interface ConversationMessage {
  id: string;
  text: string;
  from: 'user' | 'assistant';
  timestamp?: number;
  streaming?: boolean;
}

function formatTime(ts?: number) {
  const d = new Date(ts ?? Date.now());
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function RightConversationPanel({
  statusLabel,
  messages,
  emptyHint,
}: {
  statusLabel: string;
  messages: ConversationMessage[];
  emptyHint?: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  return (
    <section className="bg-dd-bg flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <header className="border-dd-border flex shrink-0 items-center gap-3 overflow-hidden border-b bg-white/95 px-6 py-4 backdrop-blur-sm xl:px-12">
        <span className="bg-dd-accent flex size-10 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold text-white">
          DD
        </span>
        <div className="min-w-0 flex-1 overflow-hidden">
          <p className="text-dd-ink truncate text-[15px] font-semibold">Dukaan Dost</p>
          <p className="text-dd-muted truncate text-[12px]">{statusLabel}</p>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain px-6 py-8 xl:px-12">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4">
            <p className="text-dd-muted max-w-[36ch] text-center text-[15px] leading-relaxed">
              {emptyHint ??
                'Start a call on the left. Your conversation will appear here — scroll anytime.'}
            </p>
          </div>
        ) : (
          <ul className="mx-auto flex w-full max-w-[640px] flex-col gap-7 pb-8">
            {messages.map((message, index) => {
              const isUser = message.from === 'user';

              return (
                <motion.li
                  key={message.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    duration: 0.35,
                    delay: Math.min(index * 0.02, 0.12),
                    ease: [0.22, 1, 0.36, 1],
                  }}
                  className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}
                >
                  <div
                    className={cn(
                      'flex max-w-full gap-3',
                      isUser ? 'flex-row-reverse' : 'flex-row'
                    )}
                  >
                    {!isUser ? (
                      <span className="bg-dd-accent mt-1 flex size-8 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white">
                        DD
                      </span>
                    ) : null}

                    <div className="min-w-0 max-w-[min(100%,560px)]">
                      {!isUser ? (
                        <div className="text-dd-muted mb-2 flex items-center gap-2 px-1 text-[12px]">
                          <span className="text-dd-ink font-medium">Dukaan Dost</span>
                          <span>{formatTime(message.timestamp)}</span>
                        </div>
                      ) : (
                        <div className="text-dd-muted mb-2 flex justify-end gap-2 px-1 text-[12px]">
                          <span>You</span>
                          <span>{formatTime(message.timestamp)}</span>
                        </div>
                      )}

                      <div
                        className={cn(
                          'break-words rounded-[22px] px-4 py-3.5 text-[15px] leading-relaxed',
                          isUser
                            ? 'text-dd-ink rounded-br-lg bg-[#DFC9B0] shadow-[0_8px_22px_-16px_rgba(42,36,31,0.4)]'
                            : 'border-dd-border text-dd-ink rounded-bl-lg border bg-white shadow-[0_10px_28px_-18px_rgba(42,36,31,0.32)]'
                        )}
                      >
                        {message.streaming ? (
                          <span className="inline">
                            {message.text}
                            <span className="bg-dd-accent ml-0.5 inline-block h-3.5 w-[2px] animate-pulse align-middle" />
                          </span>
                        ) : (
                          message.text
                        )}
                      </div>
                    </div>
                  </div>
                </motion.li>
              );
            })}
            <div ref={bottomRef} />
          </ul>
        )}
      </div>

    </section>
  );
}
