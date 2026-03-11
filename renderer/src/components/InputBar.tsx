import { useState, useCallback, useRef } from 'react';
import { useAppContext } from '../hooks/useAppContext';
import { LiveWaveform } from './LiveWaveform';
import type { InputMode } from '../store/appState';

interface InputBarProps {
  onSend: (text: string, mode: InputMode) => void;
}

export function InputBar({ onSend }: InputBarProps) {
  const { state, actions } = useAppContext();
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const hasText = inputValue.trim().length > 0;

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;
    onSend(text, state.inputMode);
    setInputValue('');
  }, [inputValue, state.inputMode, onSend]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleModeChange = useCallback((mode: InputMode) => {
    actions.setInputMode(mode);
    if (inputRef.current) {
      inputRef.current.placeholder = mode === 'transcript'
        ? 'Ask what changed on screen or request a screenshot...'
        : 'Ask what you have in mind...';
    }
  }, [actions]);

  return (
    <div className="app-drag flex items-center min-h-[54px] px-3 pl-[22px] gap-2 border-t border-white/[0.07] mt-auto bg-white/[0.035] transition-all duration-[180ms] ease-out">
      {/* Live waveform indicator */}
      {state.live.connected && (
        state.aiSpeaking ? <LiveWaveform mode="ai" /> :
        state.aiThinking ? <LiveWaveform mode="thinking" /> :
        state.live.micActive ? <LiveWaveform mode="user" /> :
        null
      )}
    </div>
  );
}
