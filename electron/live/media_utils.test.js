const test = require('node:test');
const assert = require('node:assert/strict');

const {
  downsampleFloat32ToPcm16,
  float32ToPcm16,
  hashBytes
} = require('./media_utils');

test('hashBytes matches the truncated sha256 used by screenshot hashing', async () => {
  const digest = await hashBytes(Buffer.from('hello', 'utf8'));
  assert.equal(digest, '2cf24dba5fb0a30e');
});

test('float32ToPcm16 converts normalized samples into signed pcm16', () => {
  const pcm = float32ToPcm16(new Float32Array([-1, 0, 1]));
  assert.deepEqual(Array.from(pcm), [-32768, 0, 32767]);
});

test('downsampleFloat32ToPcm16 reduces sample count to the target sample rate', () => {
  const input = new Float32Array(480);
  input.fill(0.5);

  const output = downsampleFloat32ToPcm16(input, 48000, 16000);
  assert.equal(output.length, 160);
  assert.ok(output.every((sample) => sample > 0));
});
