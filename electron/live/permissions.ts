import type { SystemPreferences } from 'electron';
import log from 'electron-log/main';

export type MediaAccessStatus =
  | 'not-determined'
  | 'granted'
  | 'denied'
  | 'restricted'
  | 'unknown';

export interface MediaAccessInfo {
  mediaType: string;
  status: MediaAccessStatus;
  message: string;
}

const KNOWN_MEDIA_ACCESS_STATUSES = new Set<MediaAccessStatus>([
  'not-determined',
  'granted',
  'denied',
  'restricted',
  'unknown'
]);

export function normalizeMediaAccessStatus(status: unknown): MediaAccessStatus {
  const normalized = String(status || '').trim().toLowerCase() as MediaAccessStatus;
  if (KNOWN_MEDIA_ACCESS_STATUSES.has(normalized)) {
    return normalized;
  }
  return 'unknown';
}

function buildMicrophoneAccessMessage(status: MediaAccessStatus): string {
  switch (status) {
    case 'denied':
      return (
        'Microphone access is denied. Enable this app in System Settings > ' +
        'Privacy & Security > Microphone, then retry the mic.'
      );
    case 'restricted':
      return 'Microphone access is restricted by macOS. Update the system restriction, then retry.';
    case 'not-determined':
      return 'Microphone access has not been granted yet. Approve the macOS prompt to use the live mic.';
    default:
      return 'Microphone access is unavailable.';
  }
}

function buildScreenAccessMessage(status: MediaAccessStatus): string {
  switch (status) {
    case 'denied':
      return (
        'Screen recording access is denied. Enable this app in System Settings > ' +
        'Privacy & Security > Screen & System Audio Recording, then retry screen sharing.'
      );
    case 'restricted':
      return 'Screen recording access is restricted by macOS. Update the system restriction, then retry.';
    case 'not-determined':
      return 'Screen recording permission has not been granted yet. Approve the macOS prompt to share the screen.';
    default:
      return 'Screen recording access is unavailable.';
  }
}

export function buildMediaAccessInfo(mediaType: string, status: unknown): MediaAccessInfo {
  const normalizedStatus = normalizeMediaAccessStatus(status);
  const message =
    mediaType === 'microphone'
      ? buildMicrophoneAccessMessage(normalizedStatus)
      : buildScreenAccessMessage(normalizedStatus);
  return {
    mediaType,
    status: normalizedStatus,
    message
  };
}

export function getMediaAccessInfo(
  systemPreferences: Pick<SystemPreferences, 'getMediaAccessStatus'>,
  mediaType: string,
  platform: string = process.platform
): MediaAccessInfo {
  if (platform !== 'darwin') {
    return {
      mediaType,
      status: 'granted',
      message: ''
    };
  }

  return buildMediaAccessInfo(
    mediaType,
    systemPreferences.getMediaAccessStatus(mediaType as Parameters<SystemPreferences['getMediaAccessStatus']>[0])
  );
}

export async function ensureMicrophoneAccess(
  systemPreferences: Pick<SystemPreferences, 'getMediaAccessStatus' | 'askForMediaAccess'>,
  platform: string = process.platform
): Promise<MediaAccessInfo> {
  const access = getMediaAccessInfo(systemPreferences, 'microphone', platform);
  if (access.status === 'granted') {
    return access;
  }

  if (platform !== 'darwin') {
    return access;
  }

  // Dev Electron builds can surface stale or misleading microphone states.
  // Ask macOS directly whenever the app is not yet granted so TCC has a
  // chance to register the packaged app instead of only the parent shell.
  try {
    await systemPreferences.askForMediaAccess('microphone');
  } catch (error) {
    // Ignore — renderer getUserMedia will still provide the final result.
  }

  const refreshed = getMediaAccessInfo(systemPreferences, 'microphone', platform);
  log.warn(
    `[permissions] macOS mic status="${refreshed.status}" — deferring to renderer getUserMedia`
  );
  return refreshed;
}
