import { useState, useCallback } from 'react';
import { useAppContext } from '../hooks/useAppContext';

interface InsightsViewProps {
  onCapture: () => void;
}

export function InsightsView({ onCapture }: InsightsViewProps) {
  const { state, actions } = useAppContext();
  const [localDoctorDraft, setLocalDoctorDraft] = useState(state.doctorDraft);

  const handleDoctorInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setLocalDoctorDraft(e.target.value);
    actions.setDoctorDraft(e.target.value);
  }, [actions]);

  const handleReveal = useCallback(() => {
    if (!state.doctorDraft.trim()) {
      actions.setStatus('Write your read before revealing the AI analysis.');
      return;
    }
    actions.setAiRevealed(true);
    actions.setFlagMode(false);
  }, [state.doctorDraft, actions]);

  const handleAgree = useCallback(async () => {
    if (state.analysis && state.aiRevealed) {
      try {
        await window.copilotDesktop.dismiss();
      } catch (error: unknown) {
        actions.setStatus((error as Error).message);
        return;
      }
    }
    await window.copilotDesktop.hideWindow();
  }, [state.analysis, state.aiRevealed, actions]);

  const handleDisagree = useCallback(() => {
    actions.setFlagMode(!state.flagMode);
  }, [state.flagMode, actions]);

  const handleSubmitFlag = useCallback(async () => {
    const overrideNote = state.flagDraft.trim() || state.doctorDraft.trim();
    try {
      await window.copilotDesktop.flag(overrideNote);
    } catch (error: unknown) {
      actions.setStatus((error as Error).message);
    }
  }, [state.flagDraft, state.doctorDraft, actions]);

  const { analysis } = state;

  function heroTitle(): string {
    if (!analysis) return 'Capture a screen to start the next read.';
    if (state.aiRevealed) return 'AI analysis revealed.';
    return 'Your read is staged. Reveal the model when ready.';
  }

  function heroBody(): string {
    if (state.permissionWarning) return state.permissionWarning;
    if (!analysis) return 'The overlay stays quiet until you capture the workstation and write your interpretation.';
    if (!state.aiRevealed) return 'Write your interpretation first, then reveal the model output to avoid anchoring bias.';
    return analysis.recommendation || 'No recommended action was returned for this read.';
  }

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">

      {/* Hero card */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] grid grid-cols-[minmax(0,1fr)_auto] gap-5 items-start">
        <div>
          <p className="m-0 uppercase tracking-[0.14em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
            Diagnosis-first workflow
          </p>
          <h2 className="mt-1.5 mb-0 text-[18px] font-semibold leading-[1.28] text-[#f4f6f8]">
            {heroTitle()}
          </h2>
          <p className="mt-2 mb-0 text-[13px] text-[rgba(244,246,248,0.78)] leading-relaxed">
            {heroBody()}
          </p>
        </div>
        <div className="flex flex-col gap-2 items-end">
          {analysis && (
            <span className={[
              'inline-flex items-center justify-center px-3 py-1.5 rounded-full',
              'bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.07)]',
              'text-[11px] font-semibold tracking-[0.06em] uppercase',
              analysis.confidence === 'high' ? 'text-[#ff857a]'
                : analysis.confidence === 'medium' ? 'text-[#ffd870]'
                : 'text-[#8be0b3]',
            ].join(' ')}>
              {analysis.confidence.toUpperCase()}
            </span>
          )}
          <span className="m-0 text-[rgba(244,246,248,0.48)] text-[11.5px]">
            {analysis ? analysis.image_hash : 'hash pending'}
          </span>
        </div>
      </article>

      {/* Doctor read card */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <label
          className="block mb-2 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]"
          htmlFor="doctor-input"
        >
          Your read
        </label>
        <textarea
          id="doctor-input"
          rows={3}
          placeholder="Type your interpretation before revealing the AI analysis."
          value={localDoctorDraft}
          onChange={handleDoctorInput}
          className="app-no-drag w-full px-[15px] py-[13px] border-0 rounded-[16px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[#f4f6f8] resize-y transition-all duration-[120ms] placeholder:text-[rgba(244,246,248,0.48)]"
        />
        <div className="flex gap-2 items-center mt-2.5">
          <button
            type="button"
            disabled={!analysis}
            onClick={handleReveal}
            className={[
              'app-no-drag inline-flex items-center justify-center px-4 py-2.5 rounded-[16px]',
              'text-[12.5px] font-medium cursor-pointer transition-all duration-[120ms] ease-out border-0',
              'bg-[rgba(255,188,96,0.12)] shadow-[inset_0_0_0_1px_rgba(255,202,148,0.18)] text-[rgba(255,212,168,0.96)]',
              'hover:bg-[rgba(255,188,96,0.16)] hover:shadow-[inset_0_0_0_1px_rgba(255,202,148,0.24)]',
              'hover:-translate-y-px active:scale-[0.98]',
              'disabled:opacity-35 disabled:cursor-default disabled:transform-none',
            ].join(' ')}
          >
            Reveal AI
          </button>
          <button
            type="button"
            disabled={state.captureInFlight}
            onClick={onCapture}
            className={[
              'app-no-drag inline-flex items-center justify-center px-4 py-2.5 rounded-[16px]',
              'text-[12.5px] font-medium cursor-pointer transition-all duration-[120ms] ease-out border-0',
              'bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[#f4f6f8]',
              'hover:bg-white/[0.08] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)] hover:-translate-y-px',
              'active:scale-[0.98] disabled:opacity-35 disabled:cursor-default disabled:transform-none',
            ].join(' ')}
          >
            Capture Again
          </button>
        </div>
      </article>

      {/* AI Analysis card */}
      {analysis && (
        <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="m-0 text-[14px] font-semibold">AI finding</h3>
            <span className={[
              'inline-flex items-center px-2.5 py-1 rounded-full',
              'bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]',
              'text-[11px] font-medium tracking-[0.06em] uppercase text-[rgba(244,246,248,0.48)]',
            ].join(' ')}>
              {state.aiRevealed ? 'Revealed' : 'Hidden'}
            </span>
          </div>

          <p className="mt-0 mb-0 text-[13px] text-[rgba(244,246,248,0.78)] leading-relaxed">
            {state.aiRevealed
              ? analysis.finding
              : 'AI analysis is hidden until you commit your own interpretation.'}
          </p>

          <div className="grid grid-cols-2 gap-4 my-4">
            <section>
              <p className="mb-2 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
                Recommended action
              </p>
              <p className="m-0 text-[rgba(244,246,248,0.78)]">
                {state.aiRevealed
                  ? analysis.recommendation || 'No recommended action returned.'
                  : 'Reveal the analysis to inspect the recommendation.'}
              </p>
            </section>
            <section>
              <p className="mb-2 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
                Specialist flags
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(analysis.specialist_flags || []).length === 0 ? (
                  <span className="text-[rgba(244,246,248,0.48)] text-[11.5px]">No specialist flags</span>
                ) : (
                  analysis.specialist_flags.map((flag) => (
                    <span
                      key={flag}
                      className="px-2.5 py-1 rounded-full bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[rgba(244,246,248,0.78)] text-[12px]"
                    >
                      {flag}
                    </span>
                  ))
                )}
              </div>
            </section>
          </div>

          <div className="flex gap-2 items-center">
            <button
              type="button"
              disabled={!state.aiRevealed}
              onClick={handleAgree}
              className={[
                'app-no-drag inline-flex items-center justify-center px-4 py-2.5 rounded-[16px]',
                'text-[12.5px] font-medium cursor-pointer transition-all duration-[120ms] ease-out border-0',
                'bg-[rgba(255,188,96,0.12)] shadow-[inset_0_0_0_1px_rgba(255,202,148,0.18)] text-[rgba(255,212,168,0.96)]',
                'hover:bg-[rgba(255,188,96,0.16)] hover:shadow-[inset_0_0_0_1px_rgba(255,202,148,0.24)] hover:-translate-y-px',
                'active:scale-[0.98] disabled:opacity-35 disabled:cursor-default disabled:transform-none',
              ].join(' ')}
            >
              Agree / Dismiss
            </button>
            <button
              type="button"
              disabled={!state.aiRevealed}
              onClick={handleDisagree}
              className={[
                'app-no-drag inline-flex items-center justify-center px-4 py-2.5 rounded-[16px]',
                'text-[12.5px] font-medium cursor-pointer transition-all duration-[120ms] ease-out border-0',
                'bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[#f4f6f8]',
                'hover:bg-white/[0.08] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)] hover:-translate-y-px',
                'active:scale-[0.98] disabled:opacity-35 disabled:cursor-default disabled:transform-none',
              ].join(' ')}
            >
              Disagree
            </button>
          </div>

          {/* Flag form */}
          {state.flagMode && state.aiRevealed && (
            <div className="mt-3.5">
              <label
                className="block mb-2 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]"
                htmlFor="flag-input"
              >
                Why do you disagree?
              </label>
              <textarea
                id="flag-input"
                rows={2}
                placeholder="Override note for QA log."
                value={state.flagDraft}
                onChange={(e) => actions.setFlagDraft(e.target.value)}
                className="app-no-drag w-full px-[15px] py-[13px] border-0 rounded-[16px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[#f4f6f8] resize-y placeholder:text-[rgba(244,246,248,0.48)]"
              />
              <button
                type="button"
                onClick={handleSubmitFlag}
                className={[
                  'app-no-drag mt-2 inline-flex items-center justify-center px-4 py-2.5 rounded-[16px]',
                  'text-[12.5px] font-medium cursor-pointer transition-all duration-[120ms] ease-out border-0',
                  'bg-[rgba(255,188,96,0.12)] shadow-[inset_0_0_0_1px_rgba(255,202,148,0.18)] text-[rgba(255,212,168,0.96)]',
                  'hover:bg-[rgba(255,188,96,0.16)] hover:shadow-[inset_0_0_0_1px_rgba(255,202,148,0.24)] hover:-translate-y-px',
                  'active:scale-[0.98]',
                ].join(' ')}
              >
                Submit Flag
              </button>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
