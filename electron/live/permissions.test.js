const test = require('node:test');
const assert = require('node:assert/strict');

const {
  ensureMicrophoneAccess,
  getMediaAccessInfo,
  normalizeMediaAccessStatus
} = require('./permissions');

test('normalizeMediaAccessStatus keeps known statuses and rejects unknown values', () => {
  assert.equal(normalizeMediaAccessStatus('granted'), 'granted');
  assert.equal(normalizeMediaAccessStatus('DENIED'), 'denied');
  assert.equal(normalizeMediaAccessStatus('weird-status'), 'unknown');
});

test('getMediaAccessInfo returns macOS guidance for denied microphone access', () => {
  const info = getMediaAccessInfo(
    {
      getMediaAccessStatus() {
        return 'denied';
      }
    },
    'microphone',
    'darwin'
  );

  assert.equal(info.status, 'denied');
  assert.match(info.message, /System Settings > Privacy & Security > Microphone/u);
  assert.match(info.message, /Enable this app/u);
});

test('ensureMicrophoneAccess preserves denied state without prompting again', async () => {
  const fakeSystemPreferences = {
    getMediaAccessStatus() {
      return 'denied';
    },
    async askForMediaAccess() {
      throw new Error('should not prompt once denied');
    }
  };

  const access = await ensureMicrophoneAccess(fakeSystemPreferences, 'darwin');
  assert.equal(access.status, 'denied');
  assert.match(access.message, /System Settings > Privacy & Security > Microphone/u);
});

test('ensureMicrophoneAccess prompts when the status is not-determined', async () => {
  let prompted = false;
  const fakeSystemPreferences = {
    getMediaAccessStatus() {
      return prompted ? 'granted' : 'not-determined';
    },
    async askForMediaAccess() {
      prompted = true;
      return true;
    }
  };

  const access = await ensureMicrophoneAccess(fakeSystemPreferences, 'darwin');
  assert.equal(access.status, 'granted');
});
