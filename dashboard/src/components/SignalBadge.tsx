interface Props {
  signal: string;
  size?: 'sm' | 'md' | 'lg';
}

const styles: Record<string, string> = {
  'STRONG BUY': 'badge-strong-buy',
  'BUY': 'badge-buy',
  'NEUTRAL': 'badge-neutral',
  'SELL': 'badge-sell',
  'STRONG SELL': 'badge-strong-sell',
};

const sizes = {
  sm: 'text-[9px] px-2 py-0.5',
  md: 'text-[10px] px-3 py-1',
  lg: 'text-xs px-4 py-1.5',
};

export default function SignalBadge({ signal, size = 'md' }: Props) {
  return (
    <span className={`inline-block font-mono font-bold tracking-wider rounded-lg ${styles[signal] || ''} ${sizes[size]}`}>
      {signal}
    </span>
  );
}
