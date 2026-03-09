const test = require('node:test');
const assert = require('node:assert/strict');

const {
  BOOTSTRAP_PROMPT,
  SYSTEM_PROMPT,
  TAKE_SCREENSHOT_DECLARATION,
  buildLiveConnectConfig
} = require('./config');

test('buildLiveConnectConfig preserves the current live session shape', () => {
  const runtimeConfig = {
    micMode: 'continuous',
    voiceName: 'Kore',
    systemPrompt: SYSTEM_PROMPT,
    bootstrapPrompt: BOOTSTRAP_PROMPT,
    contextTriggerTokens: 24576,
    contextTargetTokens: 16384
  };

  const config = buildLiveConnectConfig(runtimeConfig, 'resume-handle');

  assert.deepEqual(config.responseModalities, ['AUDIO']);
  assert.deepEqual(config.inputAudioTranscription, {});
  assert.deepEqual(config.outputAudioTranscription, {});
  assert.equal(config.realtimeInputConfig.automaticActivityDetection.disabled, false);
  assert.equal(
    config.realtimeInputConfig.automaticActivityDetection.startOfSpeechSensitivity,
    'START_SENSITIVITY_HIGH'
  );
  assert.equal(
    config.realtimeInputConfig.automaticActivityDetection.endOfSpeechSensitivity,
    'END_SENSITIVITY_LOW'
  );
  assert.equal(config.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName, 'Kore');
  assert.match(config.systemInstruction, /Session bootstrap:/u);
  assert.match(
    config.systemInstruction,
    /Until at least one preview frame or screenshot has been received/u
  );
  assert.match(BOOTSTRAP_PROMPT, /Until a preview frame arrives/u);
  assert.equal(config.tools[0].functionDeclarations[0].name, TAKE_SCREENSHOT_DECLARATION.name);
  assert.equal(config.contextWindowCompression.triggerTokens, '24576');
  assert.equal(config.contextWindowCompression.slidingWindow.targetTokens, '16384');
  assert.equal(config.sessionResumption.handle, 'resume-handle');
  assert.equal('transparent' in config.sessionResumption, false);
  assert.equal('explicitVadSignal' in config, false);
});
