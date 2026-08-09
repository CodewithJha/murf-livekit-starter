'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ConnectionState, Track } from 'livekit-client';
import { motion } from 'motion/react';
import {
  useSessionContext,
  useSessionMessages,
  useTrackToggle,
  useVoiceAssistant,
} from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { LeftVoicePanel, type WorkspaceStatus } from '@/components/app/left-voice-panel';
import {
  type ConversationMessage,
  RightConversationPanel,
} from '@/components/app/right-conversation-panel';
import { cn } from '@/lib/shadcn/utils';

function micErrorMessage(error: unknown): string {
  const name =
    error && typeof error === 'object' && 'name' in error
      ? String((error as { name?: string }).name)
      : '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return 'Microphone access was blocked.';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No microphone was found on this device.';
  }
  return 'Could not start the call. Check mic and network.';
}

function statusFromSession(opts: {
  callEnded: boolean;
  starting: boolean;
  isConnected: boolean;
  connectionState: ConnectionState;
  agentState?: string;
}): WorkspaceStatus {
  if (opts.callEnded) return 'ended';
  if (
    opts.starting ||
    opts.connectionState === ConnectionState.Connecting ||
    opts.connectionState === ConnectionState.Reconnecting
  ) {
    return 'connecting';
  }
  if (!opts.isConnected) return 'idle';

  switch (opts.agentState) {
    case 'speaking':
      return 'speaking';
    case 'listening':
      return 'listening';
    case 'thinking':
      return 'thinking';
    case 'connecting':
    case 'pre-connect-buffering':
    case 'initializing':
      return 'connecting';
    case 'idle':
      return 'connected';
    default:
      return 'connected';
  }
}

function statusLabel(status: WorkspaceStatus): string {
  switch (status) {
    case 'listening':
      return 'Listening to you';
    case 'speaking':
      return 'Agent is speaking';
    case 'thinking':
      return 'Thinking…';
    case 'connecting':
      return 'Connecting…';
    case 'connected':
      return 'Connected';
    case 'ended':
      return 'Call ended';
    default:
      return 'Idle — start a call to begin';
  }
}

interface VoiceWorkspaceProps {
  appConfig: AppConfig;
}

export function VoiceWorkspace({ appConfig }: VoiceWorkspaceProps) {
  const { isConnected, connectionState, start, end } = useSessionContext();
  const { state: agentState, audioTrack } = useVoiceAssistant();
  const { messages } = useSessionMessages();
  const { buttonProps: micButtonProps, enabled: micEnabled } = useTrackToggle({
    source: Track.Source.Microphone,
  });

  const [callEnded, setCallEnded] = useState(false);
  const [starting, setStarting] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [language, setLanguage] = useState('auto');
  const [durationSec, setDurationSec] = useState(0);
  const [agentIsSpeaking, setAgentIsSpeaking] = useState(false);
  const callStartedAt = useRef<number | null>(null);
  const wasConnected = useRef(false);

  // Safari-safe speaking detection: agent state OR remote participant speaking flag
  useEffect(() => {
    const sync = () => {
      const fromState = agentState === 'speaking';
      const fromParticipant = audioTrack?.participant?.isSpeaking === true;
      setAgentIsSpeaking(fromState || fromParticipant);
    };
    sync();

    const participant = audioTrack?.participant;
    if (!participant) return;

    participant.on('isSpeakingChanged', sync);
    return () => {
      participant.off('isSpeakingChanged', sync);
    };
  }, [agentState, audioTrack]);

  const status = statusFromSession({
    callEnded,
    starting,
    isConnected,
    connectionState,
    agentState: agentIsSpeaking ? 'speaking' : agentState,
  });

  const conversation: ConversationMessage[] = useMemo(() => {
    return messages.map((message, index) => {
      const isUser = message.from?.isLocal === true;
      const isLast = index === messages.length - 1;
      return {
        id: message.id,
        text: message.message,
        from: isUser ? 'user' : 'assistant',
        timestamp: message.timestamp,
        streaming: !isUser && isLast && status === 'thinking',
      };
    });
  }, [messages, status]);

  useEffect(() => {
    if (isConnected) {
      if (!callStartedAt.current) callStartedAt.current = Date.now();
      const id = window.setInterval(() => {
        if (callStartedAt.current) {
          setDurationSec(Math.floor((Date.now() - callStartedAt.current) / 1000));
        }
      }, 1000);
      return () => window.clearInterval(id);
    }
    callStartedAt.current = null;
    if (!callEnded) setDurationSec(0);
  }, [isConnected, callEnded]);

  useEffect(() => {
    if (isConnected) {
      wasConnected.current = true;
      setCallEnded(false);
      return;
    }
    if (wasConnected.current) {
      wasConnected.current = false;
      setCallEnded(true);
    }
  }, [isConnected]);

  const startCall = useCallback(async () => {
    if (starting || isConnected) return;
    setMicError(null);
    setCallEnded(false);
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      await start({
        roomConnectOptions: {
          // Default 15s is tight on Safari / flaky networks → NegotiationError.
          peerConnectionTimeout: 60_000,
          websocketTimeout: 30_000,
          maxRetries: 3,
        },
      });
    } catch (error) {
      const message =
        error && typeof error === 'object' && 'message' in error
          ? String((error as { message?: string }).message)
          : '';
      if (message.toLowerCase().includes('negotiation')) {
        setMicError('Connection timed out. Check Wi‑Fi/VPN, then try Start again.');
      } else {
        setMicError(micErrorMessage(error));
      }
      setCallEnded(false);
    } finally {
      setStarting(false);
    }
  }, [isConnected, start, starting]);

  const endCall = useCallback(async () => {
    setCallEnded(true);
    try {
      await end();
    } catch {
      // keep ended UI
    }
  }, [end]);

  return (
    <div className="bg-dd-bg flex h-svh w-full items-center justify-center overflow-hidden">
      <motion.div
        initial={{ opacity: 0, scale: 0.985 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          'border-dd-border flex overflow-hidden rounded-[28px] border bg-white',
          'shadow-[0_24px_64px_-20px_rgba(42,36,31,0.28)]'
        )}
        style={{
          width: 'min(95vw, 1440px)',
          height: 'calc(100vh - 32px)',
          margin: '16px auto',
        }}
      >
        {/* Always two columns — WhatsApp Desktop style. No tabs. */}
        <div className="flex h-full w-full min-w-0">
          <div
            className="h-full w-[340px] shrink-0 overflow-hidden min-[1440px]:w-[380px] xl:w-[360px]"
            style={{ borderRight: '1px solid #E9DFD3' }}
          >
            <LeftVoicePanel
              companyName={appConfig.companyName}
              status={status}
              connected={isConnected}
              micEnabled={micEnabled}
              micButtonProps={micButtonProps}
              language={language}
              onLanguageChange={setLanguage}
              durationSec={durationSec}
              micError={micError}
              onStart={startCall}
              onEnd={endCall}
              startLabel={appConfig.startButtonText || 'Start call'}
            />
          </div>
          {/* Visible separator — inline styles so Safari always paints it */}
          <div
            aria-hidden
            style={{
              width: 2,
              minWidth: 2,
              alignSelf: 'stretch',
              flexShrink: 0,
              backgroundColor: '#C4B5A3',
            }}
          />
          <div className="h-full min-w-0 flex-1 overflow-hidden">
            <RightConversationPanel
              statusLabel={statusLabel(status)}
              messages={conversation}
              emptyHint={
                status === 'ended'
                  ? 'Call ended. Start again from the left panel.'
                  : 'The left side is where you talk. This side is your conversation.'
              }
            />
          </div>
        </div>
      </motion.div>
    </div>
  );
}
