/**
 * Metric definitions — hover tooltips for every scored dimension across the system.
 * Used by Tooltip / InfoTip components throughout the dashboard.
 */

export const MACRO_DEFS: Record<string, string> = {
  overall:
    'Sum of all signed macro sub-scores. Above +30 = Risk-On (bullish conditions). +10 to +30 = Neutral. Below +10 = Risk-Off. Not a percentage — each component contributes its own positive or negative value.',
  fed_policy:
    'Federal Funds Rate direction. Positive when the Fed is cutting rates (stimulative). Negative when hiking (restrictive). Score reflects pace and magnitude of rate cycle relative to historical norms.',
  yield_curve:
    '10Y minus 2Y Treasury spread. Positive = normal upward slope (growth expected). Negative = inverted curve (recession warning historically). Wider positive spread = stronger bullish signal.',
  credit_spreads:
    'High-yield corporate bond spreads over Treasuries (HY OAS). Tight spreads = risk appetite is high, bullish. Widening spreads = credit stress, bearish. Max positive score when spreads compress below historical median.',
  dxy:
    'US Dollar Index 3-month trend. Falling dollar = bullish for risk assets, commodities, and multinationals. Rising dollar = headwind for earnings, EM, and commodities. Score is negative when USD is strengthening.',
  vix:
    'CBOE Volatility Index. Low VIX (below ~18) and in contango = bullish (fear is low, carry is positive). High VIX or backwardation = bearish. Score penalizes elevated or rising volatility.',
  m2:
    'M2 money supply year-over-year growth. Positive growth = more liquidity in the system, historically bullish. Negative or contracting M2 = liquidity tightening, headwind for asset prices.',
  real_rates:
    'Fed Funds Rate minus CPI — the "true" cost of money. Negative real rates = stimulative (money is cheap relative to inflation). Positive and rising real rates = restrictive (borrowing is expensive), historically bearish for growth assets.',
};

export const BREADTH_DEFS: Record<string, string> = {
  pct_above_200dma:
    'Percentage of S&P 500/400 stocks trading above their 200-day moving average. Above 70% = broad-based bull market. 40–70% = mixed. Below 40% = deteriorating internals even if index holds up.',
  advance_decline:
    'Advancing stocks divided by declining stocks on a given day. Above 1.5 = strong breadth. Below 0.7 = broad selling. Sustained divergence from index price = early warning signal.',
  new_highs:
    'Stocks making new 52-week highs. Rising highs with rising index = healthy trend. Falling highs while index rises = narrowing leadership, a yellow flag.',
  new_lows:
    'Stocks making new 52-week lows. Rising lows during a "rally" signals underlying deterioration. Ideally near zero in a healthy bull market.',
  breadth_score:
    'Composite breadth score (0–100) combining 200dma participation, A/D ratio, new highs/lows. Above 60 = healthy market internals. Below 40 = breadth deteriorating.',
};

export const GATE_DEFS: Record<number, { name: string; description: string }> = {
  1: {
    name: 'Macro Regime',
    description:
      'Is the macro environment supportive? Checks Fed policy direction, yield curve shape, credit spread levels, and dollar trend. A stock can only pass if the broad macro backdrop is neutral-to-bullish. Gate eliminates stocks during risk-off regimes.',
  },
  2: {
    name: 'Liquidity',
    description:
      'Is systemic liquidity adequate? Checks M2 growth, repo market conditions, financial conditions index, and reverse repo outstanding. Ensures the "plumbing" of markets is functioning. Tightening liquidity kills even good setups.',
  },
  3: {
    name: 'Forensic / Accounting Quality',
    description:
      'Does the company have clean books? Flags earnings manipulation risk using Beneish M-Score, accruals ratio, and cash flow vs. earnings divergence. High accruals or aggressive revenue recognition = eliminated here.',
  },
  4: {
    name: 'Sector Rotation',
    description:
      'Is capital flowing into this sector? Uses relative strength vs. SPX, institutional fund flows, and sector momentum. A great stock in a sector with outflows faces a structural headwind this gate eliminates.',
  },
  5: {
    name: 'Technical Trend',
    description:
      'Is the stock in a technical uptrend? Checks price vs. 50/200dma, RSI, MACD, and volume trend. Filters out fundamentally sound companies in technical downtrends — "don\'t fight the tape."',
  },
  6: {
    name: 'Fundamental Quality',
    description:
      'Is the business fundamentally sound? Scores revenue growth, margin trajectory, FCF generation, and return on capital. Eliminates deteriorating businesses even if they look cheap on price.',
  },
  7: {
    name: 'Smart Money',
    description:
      'Are institutions accumulating? Checks 13F filings for insider ownership changes, dark pool prints, and options unusual activity pointing to informed positioning. Tracks where sophisticated capital is actually moving.',
  },
  8: {
    name: 'Signal Convergence',
    description:
      'Do multiple independent signals agree? Requires 3+ modules (insider, patterns, alt data, options, supply chain, etc.) to be simultaneously bullish. Convergence dramatically reduces false positives — the most predictive filter.',
  },
  9: {
    name: 'Catalyst',
    description:
      'Is there a near-term event to unlock value? Looks for earnings beats, product launches, regulatory approval, M&A rumors, analyst upgrades, or macro tailwinds specific to the stock. Timing matters — catalyst gives conviction a trigger.',
  },
  10: {
    name: 'Fat Pitch',
    description:
      'Maximum conviction — all 10 gates clear simultaneously. Named after Warren Buffett\'s concept of waiting for the "fat pitch" — a setup so obvious and well-supported that you swing hard. These are the only positions sized aggressively.',
  },
};

export const SIGNAL_MODULE_DEFS: Record<string, string> = {
  insider:
    'Insider Activity: scores C-suite and director open-market purchases using SEC Form 4 filings. Cluster buys (multiple insiders buying within 14 days) and large-dollar purchases score highest. Insider sales are penalized less — executives sell for many reasons, but they only buy when they expect the stock to rise.',
  patterns:
    'Technical Patterns: identifies Wyckoff accumulation/distribution phases, chart patterns (cup-and-handle, bull flags, base breakouts), momentum compression (NR7, squeeze), and volume analysis. Hurst exponent measures trending vs. mean-reverting behavior.',
  options:
    'Options Intelligence: detects unusual call/put activity, sweep orders, and block trades that signal informed positioning. IV rank shows whether options are cheap or expensive. Put/call imbalance and skew direction indicate market sentiment.',
  alt_data:
    'Alternative Data: non-traditional signals including satellite imagery, credit card transaction trends, web traffic, job postings, and app download velocity. Tracks real-world business activity before it appears in financial statements.',
  supply_chain:
    'Supply Chain Intelligence: monitors rail freight volumes, shipping rates (Baltic Dry, container), and trucking capacity utilization. Supply chain stress or recovery often leads earnings by 1–2 quarters for industrials, materials, and consumer stocks.',
  ma:
    'M&A Intelligence: screens for acquisition targets using valuation screens, activist ownership, strategic fit analysis, and rumor credibility scoring. Expected premium estimates are based on comparable deal multiples. Deal stage ranges from rumor to definitive agreement.',
  pairs:
    'Pairs Trading: identifies statistically cointegrated stock pairs that have diverged beyond 2 standard deviations. The spread Z-score measures how far the pair has stretched from its historical relationship. Signals close when spread reverts to mean.',
  prediction_markets:
    'Prediction Markets: aggregates binary event probabilities from Polymarket and other prediction platforms for events affecting this stock — earnings beats, regulatory decisions, product approvals. Market prices reveal crowd wisdom on specific outcomes.',
  digital_exhaust:
    'Digital Footprint: tracks app store rankings (iOS top free/grossing), GitHub repository activity (commit velocity, contributors), and SaaS pricing changes. Leading indicator for tech/consumer companies — app traction and developer activity precede revenue.',
};

export const ENERGY_DEFS: Record<string, string> = {
  overall:
    'Composite energy sector score derived from EIA weekly inventory reports, JODI production data, demand proxies, trade flow data, and global supply/demand balance. Scores are category-level (all upstream E&P stocks share the same commodity environment).',
  inventory:
    'EIA weekly crude oil and product inventory levels vs. seasonal 5-year average. High inventories (supply surplus) = bearish for energy prices. Low inventories = bullish. Z-score measures standard deviations from seasonal norm.',
  production:
    'US crude oil production trend from EIA weekly reports plus OPEC+ quota compliance. Rising production with flat demand = bearish. Production cuts or discipline = bullish. Score reflects current production vs. expected trajectory.',
  demand:
    'Implied demand from product supplied (gasoline, distillates, jet fuel). Summer driving season and industrial activity drive demand. Score is highest when demand runs above seasonal average and is trending up.',
  trade_flows:
    'US crude and product export/import volumes. Rising exports = tighter domestic market = bullish. Falling exports or rising imports = looser supply = bearish. Also tracks tanker rates as a leading indicator.',
  global:
    'Global supply-demand balance from IEA/JODI data. Measures OECD commercial inventory days-of-supply vs. 5-year average. When global days-of-supply falls below 60 days, historically bullish for oil prices.',
};

export const CONVICTION_DEFS: Record<string, string> = {
  HIGH:
    'High Conviction: 3+ independent signal modules aligned bullishly with strong magnitude. Suitable for a full position (up to max sizing). Requires active monitoring for catalyst events.',
  NOTABLE:
    'Notable signal: 1–2 modules showing bullish evidence, or multiple modules with weak signals. Position sizing should be half or less of a High Conviction name. Worth tracking for upgrade.',
  WEAK:
    'Weak or emerging signal: signals present but not yet confirmed by multiple modules. Watch list only — do not size aggressively until conviction builds.',
};

export const CONVERGENCE_DEFS: Record<string, string> = {
  convergence_score:
    'Composite score (0–100) measuring how many independent signal sources agree on a bullish thesis. Calculated as a weighted average across all modules with valid signals. Above 65 = high convergence. Below 40 = low conviction.',
  composite_score:
    'Overall signal score combining convergence, fundamental quality, and macro regime adjustment. This is the primary ranking score used across the system. 0–100 scale.',
  module_count:
    'Number of independent signal modules producing a valid (non-neutral) signal for this stock today. Higher count = more evidence. A score of 70 from 6 modules is more reliable than 70 from 2.',
};
