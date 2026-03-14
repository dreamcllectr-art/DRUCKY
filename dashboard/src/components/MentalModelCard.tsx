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
    bg: 'bg-terminal-green/10',
    text: 'text-terminal-green',
    border: 'border-terminal-green/20',
  },
  Valuation: {
    bg: 'bg-terminal-amber/10',
    text: 'text-terminal-amber',
    border: 'border-terminal-amber/20',
  },
  Behavioral: {
    bg: 'bg-terminal-cyan/10',
    text: 'text-terminal-cyan',
    border: 'border-terminal-cyan/20',
  },
  Risk: {
    bg: 'bg-terminal-red/10',
    text: 'text-terminal-red',
    border: 'border-terminal-red/20',
  },
  Competitive: {
    bg: 'bg-white/5',
    text: 'text-terminal-dim',
    border: 'border-terminal-border',
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
        <span className={`text-[8px] px-1.5 py-0.5 rounded-sm tracking-widest uppercase font-bold ${colors.bg} ${colors.text} border ${colors.border}`}>
          {category}
        </span>
      </div>
      <h4 className="text-[11px] font-bold text-terminal-bright tracking-wider uppercase mb-1">
        {name}
      </h4>

      {/* One-liner */}
      <p className="text-[10px] text-terminal-dim leading-relaxed mb-2">
        {one_liner}
      </p>

      {/* Relevance Score */}
      <ScoreBar value={relevance} max={100} label="Relevance" />

      {/* Regime Note */}
      <p className="text-[9px] text-terminal-dim/70 mt-2 italic">
        {regime_note}
      </p>

      {/* Applies To */}
      {applies_to.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {applies_to.map((sym) => (
            <span
              key={sym}
              className="text-[9px] px-1.5 py-0.5 rounded-sm bg-terminal-green/5 text-terminal-green/70 border border-terminal-green/10"
            >
              {sym}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
