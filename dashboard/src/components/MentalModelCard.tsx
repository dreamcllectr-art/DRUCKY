import ScoreBar from './ScoreBar';

interface Props {
  category: string;
  name: string;
  one_liner: string;
  relevance: number;
  applies_to: string[];
  regime_note: string;
}

const CATEGORY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  Macro: {
    bg: 'bg-emerald-600/10',
    text: 'text-emerald-600',
    border: 'border-emerald-600/20',
  },
  Valuation: {
    bg: 'bg-amber-600/10',
    text: 'text-amber-600',
    border: 'border-amber-600/20',
  },
  Behavioral: {
    bg: 'bg-blue-600/10',
    text: 'text-blue-600',
    border: 'border-blue-600/20',
  },
  Risk: {
    bg: 'bg-rose-600/10',
    text: 'text-rose-600',
    border: 'border-rose-600/20',
  },
  Competitive: {
    bg: 'bg-gray-50',
    text: 'text-gray-500',
    border: 'border-gray-200',
  },
};

export default function MentalModelCard({
  category,
  name,
  one_liner,
  relevance,
  applies_to,
  regime_note,
}: Props) {
  const colors = CATEGORY_COLORS[category] || CATEGORY_COLORS.Competitive;

  return (
    <div className="panel p-3 animate-fade-in">
      {/* Category + Name */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-[8px] px-1.5 py-0.5 rounded-lg tracking-widest uppercase font-bold ${colors.bg} ${colors.text} border ${colors.border}`}>
          {category}
        </span>
      </div>
      <h4 className="text-[11px] font-bold text-gray-900 tracking-wider uppercase mb-1">
        {name}
      </h4>

      {/* One-liner */}
      <p className="text-[10px] text-gray-500 leading-relaxed mb-2">
        {one_liner}
      </p>

      {/* Relevance Score */}
      <ScoreBar value={relevance} max={100} label="Relevance" />

      {/* Regime Note */}
      <p className="text-[10px] text-gray-500/70 mt-2 italic">
        {regime_note}
      </p>

      {/* Applies To */}
      {applies_to.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {applies_to.map((sym) => (
            <span
              key={sym}
              className="text-[10px] px-1.5 py-0.5 rounded-lg bg-emerald-600/5 text-emerald-600/70 border border-emerald-600/10"
            >
              {sym}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
