'use client';

import { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import type { IndicatorHistoryPoint } from '@/lib/api';

interface Props {
  data: IndicatorHistoryPoint[];
  name: string;
  unit?: string;
  thresholdLines?: { value: number; color: string; label?: string }[];
  height?: number;
}

export default function EconomicChart({ data, name, unit, thresholdLines, height = 250 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#111111' },
        textColor: '#555',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#1A1A1A' },
        horzLines: { color: '#1A1A1A' },
      },
      crosshair: {
        vertLine: { color: '#00FF4140', labelBackgroundColor: '#111' },
        horzLine: { color: '#00FF4140', labelBackgroundColor: '#111' },
      },
      timeScale: {
        borderColor: '#1A1A1A',
        timeVisible: false,
      },
      rightPriceScale: {
        borderColor: '#1A1A1A',
      },
    });

    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));

    const mainSeries = chart.addLineSeries({
      color: '#00E5FF',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    mainSeries.setData(
      sorted.map(d => ({ time: d.date, value: d.value }))
    );

    // Add threshold lines
    if (thresholdLines) {
      for (const tl of thresholdLines) {
        const threshSeries = chart.addLineSeries({
          color: tl.color,
          lineWidth: 1,
          lineStyle: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        threshSeries.setData(
          sorted.map(d => ({ time: d.date, value: tl.value }))
        );
      }
    }

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
  }, [data, name, thresholdLines, height]);

  return (
    <div className="panel">
      <div className="px-4 py-2 border-b border-terminal-border flex items-center justify-between">
        <span className="text-[10px] text-terminal-dim tracking-widest uppercase">
          {name}
        </span>
        {unit && (
          <span className="text-[9px] text-terminal-dim">{unit}</span>
        )}
      </div>
      <div ref={containerRef} />
    </div>
  );
}
