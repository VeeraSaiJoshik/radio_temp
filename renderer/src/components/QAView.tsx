import { useAppContext } from '../hooks/useAppContext';

export function QAView() {
  const { state } = useAppContext();
  const latest = state.screenshotHistory[0];

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">
      {/* Latest screenshot */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="m-0 text-[14px] font-semibold">Latest screenshot event</h3>
          <span className="m-0 text-[rgba(244,246,248,0.48)] text-[11.5px]">
            {latest
              ? `${latest.reason || 'Gemini requested a screenshot'} · ${latest.image_hash || 'hash pending'}`
              : 'No screenshot captured yet.'}
          </span>
        </div>
        {latest?.image_b64 ? (
          <img
            src={`data:image/jpeg;base64,${latest.image_b64}`}
            alt="Latest screenshot"
            className="w-full max-h-[240px] rounded-[14px] object-contain bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
          />
        ) : (
          <p className="m-0 text-[rgba(244,246,248,0.78)]">
            Gemini screenshot tool activity will appear here.
          </p>
        )}
      </article>

      {/* History list */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="m-0 text-[14px] font-semibold">Recent tool calls</h3>
        </div>
        <div className="flex flex-col gap-2">
          {state.screenshotHistory.length === 0 ? (
            <div className="px-3 py-2.5 rounded-[14px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[12px] text-[rgba(244,246,248,0.78)]">
              No screenshot tool activity yet.
            </div>
          ) : (
            state.screenshotHistory.map((entry, i) => (
              <div
                key={entry.request_id || i}
                className="px-3 py-2.5 rounded-[14px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] text-[12px] text-[rgba(244,246,248,0.78)]"
              >
                {`${entry.reason || 'Screenshot event'} · ${entry.backend_status || entry.status || 'pending'} · ${entry.image_hash || 'hash pending'}`}
              </div>
            ))
          )}
        </div>
      </article>
    </div>
  );
}
