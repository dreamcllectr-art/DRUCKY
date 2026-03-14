'use client';

import React, { useEffect, useState, useRef } from 'react';
import {
  api,
  type IntelligenceReport,
  type ReportListItem,
} from '@/lib/api';

const AVAILABLE_TOPICS = [
  { key: 'energy', label: 'Energy', icon: '⛽' },
  { key: 'utilities', label: 'Utilities', icon: '⚡' },
  { key: 'ai_compute', label: 'AI / Compute', icon: '🧠' },
  { key: 'semiconductors', label: 'Semiconductors', icon: '◧' },
  { key: 'financials', label: 'Financials', icon: '◈' },
  { key: 'biotech', label: 'Biotech', icon: '◬' },
  { key: 'defense', label: 'Defense', icon: '⊗' },
  { key: 'commodities', label: 'Commodities', icon: '⊙' },
  { key: 'AI power', label: 'AI Power (Theme)', icon: '⬡' },
  { key: 'nuclear renaissance', label: 'Nuclear (Theme)', icon: '☢' },
  { key: 'rate sensitivity', label: 'Rate Sensitive (Theme)', icon: '◐' },
  { key: 'data center', label: 'Data Centers (Theme)', icon: '⊞' },
];

const REGIME_COLORS: Record<string, string> = {
  strong_risk_on: '#00FF41',
  risk_on: '#69F0AE',
  neutral: '#FFB800',
  risk_off: '#FF6B35',
  strong_risk_off: '#FF073A',
};

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [activeReport, setActiveReport] = useState<IntelligenceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Load report list
  useEffect(() => {
    api.reportList()
      .then(data => {
        setReports(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Load a specific report
  const loadReport = (topic: string) => {
    setError(null);
    api.reportLatest(topic).then(data => {
      if (data && 'status' in data && (data as { status: string }).status === 'not_found') {
        setActiveReport(null);
        setError(`No report found for "${topic}". Generate one first.`);
      } else {
        setActiveReport(data as IntelligenceReport);
      }
    }).catch(() => {
      setError('Failed to load report.');
    });
  };

  // Generate a new report
  const generateReport = async (topic: string) => {
    setGenerating(topic);
    setError(null);
    try {
      const result = await api.reportGenerate(topic);
      if (result.status === 'error') {
        setError(result.error || 'Generation failed');
        setGenerating(null);
        return;
      }
      // Refresh list and load new report
      const list = await api.reportList();
      setReports(Array.isArray(list) ? list : []);
      loadReport(topic);
    } catch (e) {
      setError(`Generation failed: ${e}`);
    }
    setGenerating(null);
  };

  // Write HTML content to iframe
  useEffect(() => {
    if (activeReport?.report_html && iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(activeReport.report_html);
        doc.close();
      }
    }
  }, [activeReport]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">LOADING INTEL REPORTS...</div>
      </div>
    );
  }

  // Parse metadata for display
  const parseMeta = (meta: string) => {
    try { return JSON.parse(meta); } catch { return {}; }
  };

  // Group reports by topic (latest only)
  const latestByTopic = new Map<string, ReportListItem>();
  for (const r of reports) {
    if (!latestByTopic.has(r.topic)) {
      latestByTopic.set(r.topic, r);
    }
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          INTELLIGENCE REPORTS
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          INSTITUTIONAL-GRADE SECTOR & THEMATIC RESEARCH BRIEFS
        </p>
      </div>

      {/* Topic selector grid */}
      <div>
        <h2 className="text-[10px] text-terminal-dim tracking-widest mb-3 uppercase">
          Generate New Report
        </h2>
        <div className="grid grid-cols-4 gap-2">
          {AVAILABLE_TOPICS.map(({ key, label, icon }) => {
            const hasReport = latestByTopic.has(key);
            const isGenerating = generating === key;
            return (
              <button
                key={key}
                onClick={() => generateReport(key)}
                disabled={isGenerating || generating !== null}
                className={`
                  panel p-3 text-left transition-all duration-200 group
                  ${isGenerating
                    ? 'border border-terminal-green/30 bg-terminal-green/5'
                    : 'hover:border-terminal-green/20 hover:bg-terminal-green/5 cursor-pointer'}
                  ${generating !== null && !isGenerating ? 'opacity-40' : ''}
                `}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-base">{icon}</span>
                  {hasReport && (
                    <span className="text-[8px] text-terminal-green tracking-wider">CACHED</span>
                  )}
                </div>
                <div className="text-xs text-terminal-bright font-mono tracking-wide">
                  {isGenerating ? (
                    <span className="text-terminal-green animate-pulse">GENERATING...</span>
                  ) : label}
                </div>
                {hasReport && (
                  <div className="text-[9px] text-terminal-dim mt-1">
                    {new Date(latestByTopic.get(key)!.generated_at).toLocaleDateString()}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="panel p-3 border border-red-500/30 bg-red-500/5">
          <span className="text-xs text-red-400 font-mono">{error}</span>
        </div>
      )}

      {/* Report list */}
      {reports.length > 0 && (
        <div>
          <h2 className="text-[10px] text-terminal-dim tracking-widest mb-3 uppercase">
            Previous Reports ({reports.length})
          </h2>
          <div className="panel overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-terminal-border">
                  <th className="text-left p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Topic</th>
                  <th className="text-left p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Type</th>
                  <th className="text-left p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Regime</th>
                  <th className="text-left p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Symbols</th>
                  <th className="text-left p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Generated</th>
                  <th className="text-right p-3 text-[9px] text-terminal-dim tracking-widest uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r, i) => {
                  const meta = parseMeta(r.metadata || '{}');
                  const regimeColor = REGIME_COLORS[r.regime] || '#FFB800';
                  const symbols = (r.symbols_covered || '').split(',');
                  return (
                    <tr
                      key={`${r.id}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/5 transition-colors"
                    >
                      <td className="p-3 font-mono text-terminal-bright font-bold uppercase">
                        {r.topic}
                      </td>
                      <td className="p-3 text-terminal-dim">{r.topic_type}</td>
                      <td className="p-3">
                        <span
                          className="text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
                          style={{ backgroundColor: `${regimeColor}20`, color: regimeColor }}
                        >
                          {(r.regime || '').replace(/_/g, ' ').toUpperCase()}
                        </span>
                      </td>
                      <td className="p-3 text-terminal-dim">
                        {symbols.length} tickers
                        {meta.pairs_count > 0 && (
                          <span className="text-terminal-dim/50 ml-1">| {meta.pairs_count} pairs</span>
                        )}
                      </td>
                      <td className="p-3 text-terminal-dim font-mono text-[10px]">
                        {new Date(r.generated_at).toLocaleString()}
                      </td>
                      <td className="p-3 text-right">
                        <button
                          onClick={() => loadReport(r.topic)}
                          className="text-terminal-green hover:text-terminal-bright text-[10px] tracking-widest uppercase transition-colors"
                        >
                          VIEW
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Active report viewer */}
      {activeReport && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[10px] text-terminal-dim tracking-widest uppercase">
              Viewing: {activeReport.topic.toUpperCase()} — {new Date(activeReport.generated_at).toLocaleString()}
            </h2>
            <button
              onClick={() => setActiveReport(null)}
              className="text-[10px] text-terminal-dim hover:text-terminal-bright tracking-widest uppercase transition-colors"
            >
              CLOSE
            </button>
          </div>
          <div className="panel overflow-hidden rounded-lg" style={{ height: '80vh' }}>
            <iframe
              ref={iframeRef}
              title="Intelligence Report"
              className="w-full h-full border-0"
              sandbox="allow-same-origin"
            />
          </div>
        </div>
      )}

      {/* Empty state */}
      {reports.length === 0 && !activeReport && (
        <div className="panel p-12 text-center">
          <div className="text-4xl mb-4">📋</div>
          <h3 className="text-terminal-bright font-display text-lg mb-2">No Reports Generated Yet</h3>
          <p className="text-terminal-dim text-sm max-w-md mx-auto">
            Click any topic above to generate an institutional-grade intelligence report.
            Each report synthesizes all 14 convergence modules, EIA data, pairs analysis,
            prediction markets, and AI-powered narrative synthesis.
          </p>
        </div>
      )}
    </div>
  );
}
