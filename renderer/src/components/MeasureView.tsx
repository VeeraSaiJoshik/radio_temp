import { useAppContext } from '../hooks/useAppContext';

export function MeasureView() {
  const { state } = useAppContext();
  const summary = state.analysis
    ? state.analysis.recommendation || state.analysis.finding
    : 'Once a read is captured, the latest finding and recommendation will be staged here for structured measurements.';

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <p className="m-0 uppercase tracking-[0.14em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
          Measure
        </p>
        <h2 className="mt-1.5 mb-0 text-[18px] font-semibold leading-[1.28] text-[#f4f6f8]">
          Quick extraction
        </h2>
        <p className="mt-2 mb-0 text-[13px] text-[rgba(244,246,248,0.78)] leading-relaxed">
          {summary}
        </p>
      </article>
    </div>
  );
}
