import { useAppContext } from '../hooks/useAppContext';
import type { ViewName } from '../store/appState';

const NAV_VIEWS: { label: string; view: ViewName; shortcut: string }[] = [
  { label: 'Insights', view: 'Insights', shortcut: '⌘⌥A' },
  { label: 'Measure', view: 'Measure', shortcut: '⌘⌥M' },
  { label: 'Compare', view: 'Compare', shortcut: '⌘⌥C' },
  { label: 'QA', view: 'QA', shortcut: '⌘⌥Q' },
];

interface TopBarProps {
  onMicClick: () => void;
  onAskClick: () => void;
  onSimulateClick: () => void;
}

export function TopBar({ onMicClick, onAskClick, onSimulateClick }: TopBarProps) {
  const { state, actions } = useAppContext();

  return (
    <nav
      className={[
        'relative flex items-center min-h-[50px] px-3 gap-1.5 app-drag',
        'border-b bg-white/[0.03]',
        state.analysis || state.captureInFlight
          ? 'border-white/[0.07]'
          : 'border-transparent',
      ].join(' ')}
    >
      {/* Mini-orb collapse button */}
      <button
        type="button"
        title="Collapse to orb"
        onClick={() => actions.setActiveView('Insights')}
        className={[
          'app-no-drag flex-shrink-0 mr-0.5 w-7 h-7 rounded-full cursor-pointer',
          'mini-orb-gradient',
          'shadow-[inset_0_1px_0_rgba(255,255,255,0.38),inset_0_-10px_18px_rgba(255,255,255,0.03),0_8px_20px_rgba(0,0,0,0.12)]',
          'transition-transform duration-150 ease-out',
          'hover:scale-[1.04] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.42),inset_0_-10px_18px_rgba(255,255,255,0.04),0_10px_22px_rgba(0,0,0,0.15)]',
        ].join(' ')}
      />

      {/* Nav pills */}
      <div className="app-no-drag flex gap-1 flex-1 relative z-10">
        {NAV_VIEWS.map(({ label, view, shortcut }) => (
          <button
            key={view}
            type="button"
            onClick={() => actions.setActiveView(view)}
            className={[
              'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full',
              'text-[12.5px] font-medium tracking-[0.01em] cursor-pointer whitespace-nowrap',
              'transition-all duration-[120ms] ease-out select-none border-0',
              state.activeView === view
                ? 'bg-transparent shadow-[inset_0_0_0_1px_rgba(255,202,148,0.16)] text-[rgba(255,212,168,0.96)]'
                : 'bg-transparent text-[rgba(244,246,248,0.78)] shadow-[inset_0_0_0_1px_transparent]',
              state.activeView !== view &&
                'hover:bg-white/[0.03] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)] hover:text-[#f4f6f8]',
              'active:scale-[0.98]',
            ].join(' ')}
          >
            {label}
            <span className="text-[10px] opacity-50 font-normal">{shortcut}</span>
          </button>
        ))}
      </div>

      {/* Centered title */}
      <div className="absolute left-1/2 -translate-x-1/2 text-xs font-semibold tracking-[0.02em] text-[rgba(244,246,248,0.48)] pointer-events-none whitespace-nowrap">
        Radiology Copilot
      </div>

      {/* Right-side actions */}
      <div className="app-no-drag flex gap-1 ml-auto relative z-10">
        {state.demoMode && (
          <button
            type="button"
            onClick={onSimulateClick}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12.5px] font-medium tracking-[0.01em] cursor-pointer whitespace-nowrap transition-all duration-[120ms] ease-out select-none border-0 bg-transparent text-[rgba(244,246,248,0.78)] hover:bg-white/[0.03] hover:text-[#f4f6f8] active:scale-[0.98]"
          >
            Simulate
          </button>
        )}
        <button
          type="button"
          onClick={onMicClick}
          disabled={!state.live.connected}
          className={[
            'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full',
            'text-[12.5px] font-medium tracking-[0.01em] cursor-pointer whitespace-nowrap',
            'transition-all duration-[120ms] ease-out select-none border-0',
            state.live.micActive
              ? 'bg-transparent shadow-[inset_0_0_0_1px_rgba(255,202,148,0.16)] text-[rgba(255,212,168,0.96)]'
              : 'bg-transparent text-[rgba(244,246,248,0.78)] hover:bg-white/[0.03] hover:text-[#f4f6f8]',
            'disabled:opacity-35 disabled:cursor-default',
          ].join(' ')}
        >
          {state.live.micActive ? 'Stop Mic' : 'Mic'}
        </button>
        <button
          type="button"
          onClick={onAskClick}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12.5px] font-medium tracking-[0.01em] cursor-pointer whitespace-nowrap transition-all duration-[120ms] ease-out select-none border-0 bg-transparent text-[rgba(244,246,248,0.78)] hover:bg-white/[0.03] hover:text-[#f4f6f8] active:scale-[0.98]"
        >
          Ask ^
        </button>
      </div>
    </nav>
  );
}
