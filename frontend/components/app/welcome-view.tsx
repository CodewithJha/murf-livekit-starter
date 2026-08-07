'use client';

import { MicrophoneIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

interface WelcomeViewProps {
  companyName?: string;
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  companyName = 'Dukaan Dost',
  startButtonText,
  onStartCall,
  ref,
  className,
  ...props
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div
      ref={ref}
      className={cn('relative flex min-h-svh w-full flex-col', className)}
      {...props}
    >
      {/* Flipkart blue bar — hard hex so color always paints */}
      <header className="bg-[#2874F0] text-white">
        <div className="flex h-14 w-full items-center justify-between px-4 sm:px-6">
          <p className="text-[17px] font-bold tracking-tight">{companyName}</p>
          <span className="rounded bg-[#FFE500] px-2 py-0.5 text-[10px] font-extrabold tracking-wide text-[#212121] uppercase">
            Voice
          </span>
        </div>
      </header>

      <div className="flex flex-1 flex-col bg-[#F1F3F6]">
        <main className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center px-6 py-16 text-center">
          <p className="mb-3 text-[12px] font-semibold tracking-wide text-[#878787] uppercase">
            Local Commerce · #VoiceForBharat
          </p>

          <h1 className="max-w-[12ch] text-[2.35rem] leading-[1.1] font-bold tracking-tight text-[#212121] sm:text-5xl">
            Order groceries by voice
          </h1>

          <p className="mt-4 max-w-[32ch] text-[15px] leading-relaxed text-[#878787]">
            Speak your order. We confirm items — the seller sets the price.
          </p>

          <Button
            size="lg"
            onClick={onStartCall}
            className={cn(
              'mt-9 h-12 min-w-[220px] rounded-sm bg-[#2874F0] text-[14px] font-bold text-white shadow-sm',
              'hover:bg-[#1A5DC8] hover:text-white',
              'focus-visible:ring-[#FFE500]'
            )}
          >
            <MicrophoneIcon weight="fill" className="size-4" />
            {startButtonText}
          </Button>

          <div className="mt-5 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-sm bg-[#FFE500]" />
            <p className="text-[12px] text-[#878787]">Powered by Murf Falcon</p>
          </div>
        </main>
      </div>
    </div>
  );
};
