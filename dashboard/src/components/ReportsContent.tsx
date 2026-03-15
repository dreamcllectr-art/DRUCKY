'use client';
import React, { useEffect, useState, useRef } from 'react';
import { api, type IntelligenceReport, type ReportListItem } from '@/lib/api';

const AVAILABLE_TOPICS = [
  { key: 'energy', label: 'Energy', icon: 'E' }, { key: 'utilities', label: 'Utilities', icon: 'U' },
  { key: 'ai_compute', label: 'AI / Compute', icon: 'AI' }, { key: 'semiconductors', label: 'Semis', icon: 'S' },
  { key: 'financials', label: 'Financials', icon: 'F' }, { key: 'biotech', label: 'Biotech', icon: 'B' },
  { key: 'defense', label: 'Defense', icon: 'D' }, { key: 'commodities', label: 'Commodities', icon: 'C' },
];

export default function ReportsContent() {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [activeReport, setActiveReport] = useState<IntelligenceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    api.reportList()
      .then(d => { setReports(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(e => { setError(e.message || 'Failed to load reports'); setLoading(false); });
  }, []);

  const loadReport = (topic: string) => {
    setError(null);
    api.reportLatest(topic).then(data => {
      if (data && 'status' in data && (data as { status?: string }).status === 'not_found') { setActiveReport(null); setError(`No report for "${topic}".`); }
      else setActiveReport(data as IntelligenceReport);
    }).catch(() => setError('Failed to load.'));
  };

  const generateReport = async (topic: string) => {
    setGenerating(topic); setError(null);
    try {
      const result = await api.reportGenerate(topic);
      if (result.status === 'error') { setError(result.error || 'Failed'); setGenerating(null); return; }
      const list = await api.reportList(); setReports(Array.isArray(list) ? list : []); loadReport(topic);
    } catch (e) { setError(`Failed: ${e}`); }
    setGenerating(null);
  };

  useEffect(() => {
    if (activeReport?.report_html && iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      if (doc) { doc.open(); doc.write(activeReport.report_html); doc.close(); }
    }
  }, [activeReport]);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading reports...</div>;

  const latestByTopic = new Map<string, ReportListItem>();
  for (const r of reports) { if (!latestByTopic.has(r.topic)) latestByTopic.set(r.topic, r); }

  return (
    <div className="space-y-5">
      <div><h2 className="text-[10px] text-gray-500 tracking-widest mb-3 uppercase">Generate New Report</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">{AVAILABLE_TOPICS.map(({ key, label, icon }) => {
          const has = latestByTopic.has(key);
          return (<button key={key} onClick={() => generateReport(key)} disabled={generating !== null} className={`panel p-3 text-left transition-all group ${generating === key ? 'border-emerald-600/30 bg-emerald-600/5' : 'hover:border-emerald-600/20 cursor-pointer'} ${generating !== null && generating !== key ? 'opacity-40' : ''}`}>
            <div className="flex items-center justify-between mb-1"><span className="text-base font-mono">{icon}</span>{has && <span className="text-[8px] text-emerald-600 tracking-wider">CACHED</span>}</div>
            <div className="text-xs text-gray-900 font-mono tracking-wide">{generating === key ? <span className="text-emerald-600 animate-pulse">GENERATING...</span> : label}</div>
          </button>);
        })}</div>
      </div>
      {error && <div className="panel p-3 border border-red-500/30 bg-red-500/5"><span className="text-xs text-red-400 font-mono">{error}</span></div>}
      {reports.length > 0 && (
        <div><h2 className="text-[10px] text-gray-500 tracking-widest mb-3 uppercase">Previous Reports ({reports.length})</h2>
          <div className="panel overflow-hidden"><table className="w-full text-xs"><thead><tr className="border-b border-gray-200"><th className="text-left p-3 text-[9px] text-gray-500 tracking-widest uppercase">Topic</th><th className="text-left p-3 text-[9px] text-gray-500 tracking-widest uppercase">Generated</th><th className="text-right p-3 text-[9px] text-gray-500 tracking-widest uppercase">Actions</th></tr></thead>
            <tbody>{reports.map((r, i) => (
              <tr key={`${r.id}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/5"><td className="p-3 font-mono text-gray-900 font-bold uppercase">{r.topic}</td><td className="p-3 text-gray-500 font-mono text-[10px]">{new Date(r.generated_at).toLocaleString()}</td><td className="p-3 text-right"><button onClick={() => loadReport(r.topic)} className="text-emerald-600 hover:text-gray-900 text-[10px] tracking-widest uppercase">VIEW</button></td></tr>
            ))}</tbody></table></div>
        </div>
      )}
      {activeReport && (
        <div><div className="flex items-center justify-between mb-3"><h2 className="text-[10px] text-gray-500 tracking-widest uppercase">{activeReport.topic.toUpperCase()}</h2><button onClick={() => setActiveReport(null)} className="text-[10px] text-gray-500 hover:text-gray-900 tracking-widest uppercase">CLOSE</button></div>
          <div className="panel overflow-hidden rounded-lg h-[80vh]"><iframe ref={iframeRef} title="Report" className="w-full h-full border-0" sandbox="allow-same-origin" /></div>
        </div>
      )}
    </div>
  );
}
