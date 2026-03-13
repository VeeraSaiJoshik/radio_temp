import { useAppContext } from '../hooks/useAppContext';
import { LiveWaveform } from './LiveWaveform';

export function InputBar() {
  const { state, actions } = useAppContext();
  console.log(actions)

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
