'use client';

import { useEffect, useMemo } from 'react';
import { Room, TokenSource } from 'livekit-client';
import { useSession } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { AgentAudioBoost } from '@/components/app/agent-audio-boost';
import { ViewController } from '@/components/app/view-controller';
import { Toaster } from '@/components/ui/sonner';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { getSandboxTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();

  // Safari/Next overlay: LiveKit can throw unhandled NegotiationError during ICE.
  useEffect(() => {
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const name = reason?.name ? String(reason.name) : '';
      const message = reason?.message ? String(reason.message) : String(reason ?? '');
      if (
        name === 'NegotiationError' ||
        message.toLowerCase().includes('negotiation timed out') ||
        message.toLowerCase().includes('negotiation')
      ) {
        event.preventDefault();
      }
    };
    window.addEventListener('unhandledrejection', onRejection);
    return () => window.removeEventListener('unhandledrejection', onRejection);
  }, []);

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const tokenSource = useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);

  // Stable Room — connect timeouts are set in start({ roomConnectOptions }).
  const room = useMemo(
    () =>
      new Room({
        adaptiveStream: true,
        dynacast: true,
        disconnectOnPageLeave: true,
      }),
    []
  );

  const session = useSession(tokenSource, {
    room,
    ...(appConfig.agentName ? { agentName: appConfig.agentName } : {}),
    // Agent can take >10s on cold start / slow LiveKit connect; default is too tight.
    agentConnectTimeoutMilliseconds: 60_000,
  });

  return (
    <AgentSessionProvider session={session} volume={1}>
      <AppSetup />
      <AgentAudioBoost gain={2} />
      <main className="relative h-svh overflow-hidden">
        <ViewController appConfig={appConfig} />
      </main>
      <StartAudioButton label="Start Audio" />
      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
