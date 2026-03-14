import { useAppContext } from '../hooks/useAppContext';
import type { ModelNode as ModelNodeType, DiagnosisAnnotation } from '../types/electron';

// ── Status colour maps ────────────────────────────────────────────────────────

const DOT_CLASS: Record<string, string> = {
  pending:      'bg-white/20',
  'in-progress': 'bg-[rgba(255,212,168,0.85)] animate-pulse',
  positive:     'bg-[#ff857a]',
  negative:     'bg-[#8be0b3]',
};

const TEXT_CLASS: Record<string, string> = {
  pending:      'text-[rgba(244,246,248,0.35)]',
  'in-progress': 'text-[rgba(255,212,168,0.96)]',
  positive:     'text-[#ff857a]',
  negative:     'text-[#8be0b3]',
};

const CONFIDENCE_CLASS: Record<string, string> = {
  high:   'text-[#ff857a]',
  medium: 'text-[#ffd870]',
  low:    'text-[#8be0b3]',
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ModelNodeRow({ node, depth = 0 }: { node: ModelNodeType; depth?: number }) {
  return (
    <div>
      <div
        className="flex items-start gap-2.5 py-1.5"
        style={{ paddingLeft: `${depth * 18}px` }}
      >
        <div
          className={`mt-[5px] flex-shrink-0 w-2 h-2 rounded-full ${DOT_CLASS[node.status] ?? 'bg-white/20'}`}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className={`text-[13px] font-medium ${TEXT_CLASS[node.status] ?? 'text-[#f4f6f8]'}`}>
              {node.model.name}
            </span>
            <span className="text-[10px] text-[rgba(244,246,248,0.32)] uppercase tracking-[0.1em]">
              {node.model.provider}
            </span>
          </div>
          <p className="m-0 mt-0.5 text-[11.5px] text-[rgba(244,246,248,0.45)] leading-relaxed">
            {node.model.description}
          </p>
        </div>
      </div>
      {node.children.map((child, i) => (
        <ModelNodeRow key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

function AnnotationsCard({ annotations }: { annotations: DiagnosisAnnotation[] }) {
  return (
    <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
      <p className="mb-3 m-0 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
        Findings ({annotations.length})
      </p>
      <div className="flex flex-col">
        {annotations.map((ann) => (
          <div
            key={ann.number}
            className="flex items-start gap-2.5 py-2 border-b border-white/[0.05] last:border-0"
          >
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/[0.08] flex items-center justify-center text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
              {ann.number}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[13px] font-medium text-[#f4f6f8]">{ann.name}</span>
                <span className={`text-[10.5px] font-semibold uppercase tracking-[0.08em] ${CONFIDENCE_CLASS[ann.confidence] ?? 'text-[rgba(244,246,248,0.48)]'}`}>
                  {ann.confidence}
                </span>
              </div>
              <p className="m-0 mt-0.5 text-[12px] text-[rgba(244,246,248,0.62)] leading-relaxed">
                {ann.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function DiagnosisView() {
  const { state } = useAppContext();

  // Show the most recently updated diagnosis
  const diagnosis = state.diagnosisResults[state.diagnosisResults.length - 1] ?? null;

  if (!diagnosis) {
    return (
      <div className="flex flex-col gap-[22px] animate-view-fade-in">
        <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
          <p className="m-0 text-[13px] text-[rgba(244,246,248,0.48)]">
            No diagnosis in progress. Press the hotkey to scan.
          </p>
        </article>
      </div>
    );
  }

  const pct = Math.round(diagnosis.percent_completion * 100);
  const isComplete = diagnosis.percent_completion >= 1.0;

  return (
    <div className="flex flex-col gap-[22px] animate-view-fade-in">

      {/* Progress header */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <div className="flex items-center justify-between mb-2.5">
          <p className="m-0 uppercase tracking-[0.14em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
            AI Model Pipeline
          </p>
          <span className={[
            'inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-[0.06em] uppercase',
            isComplete
              ? 'text-[#8be0b3] bg-[rgba(139,224,179,0.08)] shadow-[inset_0_0_0_1px_rgba(139,224,179,0.16)]'
              : 'text-[rgba(255,212,168,0.96)] bg-[rgba(255,188,96,0.08)] shadow-[inset_0_0_0_1px_rgba(255,202,148,0.18)]',
          ].join(' ')}>
            {isComplete ? 'Complete' : `${pct}% · Running`}
          </span>
        </div>
        <div className="w-full h-1 rounded-full bg-white/[0.08] overflow-hidden">
          <div
            className="h-full rounded-full bg-[rgba(255,212,168,0.7)] transition-all duration-700 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      </article>

      {/* Model tree */}
      <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
        <p className="mb-3 m-0 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
          Model Tree
        </p>
        <ModelNodeRow node={diagnosis.progress_tree} />
      </article>

      {/* Findings */}
      {diagnosis.annotations.length > 0 && (
        <AnnotationsCard annotations={diagnosis.annotations} />
      )}

      {/* Overall assessment */}
      {diagnosis.overall_diagnosis_context && (
        <article className="p-4 rounded-[18px] bg-white/[0.045] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
          <p className="mb-2 m-0 uppercase tracking-[0.12em] text-[10px] font-semibold text-[rgba(244,246,248,0.48)]">
            Overall Assessment
          </p>
          <p className="m-0 text-[13px] text-[rgba(244,246,248,0.78)] leading-relaxed">
            {diagnosis.overall_diagnosis_context}
          </p>
        </article>
      )}

    </div>
  );
}
