import { useEffect, useRef } from 'react';
import { useAppContext } from '../hooks/useAppContext';

export function TranscriptView() {
  const { state } = useAppContext();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [state.transcriptEntries]);

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="m-0 text-[14px] font-semibold">Conversation</h3>
        </div>
        <div
          ref={logRef}
          className="flex flex-col gap-2 max-h-[280px] overflow-y-auto"
        >
          {state.transcriptEntries.length === 0 ? (
            <div className="px-3 py-2.5 rounded-[14px] bg-white/[0.045] shadow-[inset_2px_0_0_rgba(255,216,112,0.7),inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[12.5px] leading-relaxed text-[rgba(244,246,248,0.48)]">
              Gemini Live messages will appear here once the session is connected.
            </div>
          ) : (
            state.transcriptEntries.map((entry, i) => (
              <div
                key={i}
                className={[
                  'px-3 py-2.5 rounded-[14px] bg-white/[0.045] text-[12.5px] leading-relaxed',
                  entry.role === 'user'
                    ? 'shadow-[inset_2px_0_0_rgba(255,202,148,0.7),inset_0_0_0_1px_rgba(255,255,255,0.08)]'
                    : entry.role === 'assistant'
                    ? 'shadow-[inset_2px_0_0_rgba(139,224,179,0.7),inset_0_0_0_1px_rgba(255,255,255,0.08)]'
                    : 'shadow-[inset_2px_0_0_rgba(255,216,112,0.7),inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[rgba(244,246,248,0.48)]',
                ].join(' ')}
              >
                {`${entry.role === 'assistant' ? 'Gemini' : entry.role === 'system' ? 'System' : 'You'}: ${entry.text}`}
              </div>
            ))
          )}
        </div>
      </article>
    </div>
  );
}
