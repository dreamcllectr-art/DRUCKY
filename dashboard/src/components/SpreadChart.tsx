'use client';

import { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import type { PairSpread } from '@/lib/api';

interface Props {
  data: PairSpread[];
  symbolA: string;
  symbolB: string;
  height?: number;
}

export default function SpreadChart({ data, symbolA, symbolB, height = 300 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#9ca3af',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#e5e7eb' },
        horzLines: { color: '#e5e7eb' },
      },
      crosshair: {
        vertLine: { color: '#05966940', labelBackgroundColor: '#ffffff' },
        horzLine: { color: '#05966940', labelBackgroundColor: '#ffffff' },
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: false,
      },
      rightPriceScale: {
        borderColor: '#e5e7eb',
      },
    });

    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));

    // Main z-score line
    const zSeries = chart.addLineSeries({
      color: '#2563eb',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    zSeries.setData(
      sorted.map(d => ({ time: d.date, value: d.spread_zscore }))
    );

    // Zero line (mean)
    const zeroLine = chart.addLineSeries({
      color: '#05966940',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    zeroLine.setData(
      sorted.map(d => ({ time: d.date, value: 0 }))
    );

    // +2σ threshold (mean-reversion trigger)
    const plus2 = chart.addLineSeries({
      color: '#e11d4860',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    plus2.setData(sorted.map(d => ({ time: d.date, value: 2 })));

    // -2σ threshold
    const minus2 = chart.addLineSeries({
      color: '#e11d4860',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    minus2.setData(sorted.map(d => ({ time: d.date, value: -2 })));

    // ±1.5σ thresholds (runner detection)
    const plus15 = chart.addLineSeries({
      color: '#d9770640',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    plus15.setData(sorted.map(d => ({ time: d.date, value: 1.5 })));

    const minus15 = chart.addLineSeries({
      color: '#d9770640',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    minus15.setData(sorted.map(d => ({ time: d.date, value: -1.5 })));

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, symbolA, symbolB, height]);

  return (
    <div className="panel">
      <div className="px-4 py-2 border-b border-gray-200 flex items-center justify-between">
        <span className="text-[10px] text-gray-500 tracking-widest uppercase">
          {symbolA} / {symbolB} — SPREAD Z-SCORE
        </span>
        <div className="flex gap-3 text-[9px] text-gray-500">
          <span><span className="inline-block w-3 h-px bg-[#e11d48] mr-1 align-middle" />&plusmn;2&sigma;</span>
          <span><span className="inline-block w-3 h-px bg-[#d97706] mr-1 align-middle" />&plusmn;1.5&sigma;</span>
          <span><span className="inline-block w-3 h-px bg-[#2563eb] mr-1 align-middle" />Z-Score</span>
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
