'use client';

import type { AppConfig } from '@/app-config';
import { VoiceWorkspace } from '@/components/app/voice-workspace';

interface ViewControllerProps {
  appConfig: AppConfig;
}

/** Single desktop workspace — WhatsApp-style two-panel app. */
export function ViewController({ appConfig }: ViewControllerProps) {
  return <VoiceWorkspace appConfig={appConfig} />;
}
