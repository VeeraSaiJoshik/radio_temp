import { useState, useCallback, useRef } from 'react';
import { useAppContext } from '../hooks/useAppContext';
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
      <input
        ref={inputRef}
        id="ask-text-input"
        type="text"
        placeholder="Ask what you have in mind..."
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="app-no-drag flex-1 py-2 border-0 bg-transparent shadow-none text-[#f4f6f8] text-[13px] focus:outline-none focus:shadow-none placeholder:text-[rgba(244,246,248,0.48)]"
      />

      {/* Listening indicator */}
      {state.live.micActive && (
        <span className="app-no-drag flex items-center gap-1.5 text-[11.5px] text-[rgba(255,212,168,0.96)] whitespace-nowrap">
          <span className="w-[7px] h-[7px] rounded-full bg-[#ffca94] animate-pulse-dot" />
          Listening for audio
        </span>
      )}

      {/* Input mode toggles */}
      <div className="app-no-drag flex gap-0.5 ml-1">
        {(['notes', 'transcript'] as InputMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => handleModeChange(mode)}
            className={[
              'px-[11px] py-[5px] rounded-full text-[11.5px] font-medium cursor-pointer border-0',
              'transition-all duration-[120ms] ease-out',
              state.inputMode === mode
                ? 'bg-white/[0.08] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.1)] text-[#f4f6f8]'
                : 'bg-transparent text-[rgba(244,246,248,0.48)] hover:bg-white/[0.045] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.07)] hover:text-[rgba(244,246,248,0.78)]',
            ].join(' ')}
          >
            {mode === 'notes' ? 'Notes' : 'Transcription'}
          </button>
        ))}
      </div>

      {/* Send button */}
      <button
        type="button"
        aria-label="Send"
        onClick={handleSend}
        className={[
          'app-no-drag w-[34px] h-[34px] rounded-full flex-shrink-0 border-0',
          'bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[#f4f6f8] text-[16px]',
          'flex items-center justify-center cursor-pointer',
          'transition-all duration-150 ease-out',
          hasText
            ? 'opacity-100 scale-100 pointer-events-auto hover:bg-white/[0.08] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.14)]'
            : 'opacity-0 scale-[0.8] pointer-events-none',
        ].join(' ')}
      >
        ↑
      </button>
    </div>
  );
}
