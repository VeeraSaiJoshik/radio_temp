import { useAppContext } from '../hooks/useAppContext';
import { InsightsView } from './InsightsView';
import { MeasureView } from './MeasureView';
import { CompareView } from './CompareView';
import { QAView } from './QAView';
import { TranscriptView } from './TranscriptView';

interface ContentPanelProps {
  onCapture: () => void;
}

export function ContentPanel({ onCapture }: ContentPanelProps) {
  const { state } = useAppContext();

  return (
    <section
      className={[
        'flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-[22px] py-[18px] pb-5',
        'bg-gradient-to-b from-white/[0.02] to-black/[0.08]',
        'transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]',
      ].join(' ')}
    >
      {/* Status line */}
      <div className="flex items-center gap-1.5 pb-3.5 mb-1.5 border-b border-white/[0.07] text-[11.5px] text-[rgba(244,246,248,0.48)]">
        <span>{state.confirmationMessage || state.statusMessage || 'Ready'}</span>
        <span className="opacity-30">·</span>
        <span>{state.live.phase || state.live.message}</span>
      </div>

      {/* Warning banner */}
      {state.permissionWarning && (
        <section className="mb-3 px-3 py-2.5 rounded-[14px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[rgba(255,212,168,0.96)] text-[12.5px]">
          {state.permissionWarning}
        </section>
      )}

      {/* Views */}
      {state.activeView === 'Insights' && <InsightsView onCapture={onCapture} />}
      {state.activeView === 'Measure' && <MeasureView />}
      {state.activeView === 'Compare' && <CompareView />}
      {state.activeView === 'QA' && <QAView />}
      {state.activeView === 'Transcript' && <TranscriptView />}
    </section>
  );
}
