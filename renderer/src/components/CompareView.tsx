import { useAppContext } from '../hooks/useAppContext';

export function CompareView() {
  const { state } = useAppContext();
  const doctorText = state.doctorDraft || 'No read drafted yet.';
  const aiText = state.analysis
    ? state.aiRevealed
      ? state.analysis.finding
      : 'Still hidden behind the diagnosis-first gate.'
    : 'No AI analysis loaded.';

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <div className="grid grid-cols-2 gap-4">
          <section>
            <p className="m-0 mb-1 uppercase tracking-[0.14em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
              Doctor
            </p>
            <p className="m-0 text-[rgba(244,246,248,0.78)]">{doctorText}</p>
          </section>
          <section>
            <p className="m-0 mb-1 uppercase tracking-[0.14em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
              AI
            </p>
            <p className="m-0 text-[rgba(244,246,248,0.78)]">{aiText}</p>
          </section>
        </div>
      </article>
    </div>
  );
}
