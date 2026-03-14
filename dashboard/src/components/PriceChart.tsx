'use client';

import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi, ColorType, LineStyle } from 'lightweight-charts';
import type { PriceBar } from '@/lib/api';

interface Props {
  data: PriceBar[];
  symbol: string;
  entry?: number;
  stop?: number;
  target?: number;
}

export default function PriceChart({ data, symbol, entry, stop, target }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111111' },
        textColor: '#555555',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#1A1A1A' },
        horzLines: { color: '#1A1A1A' },
      },
      crosshair: {
        vertLine: { color: '#00FF4140', labelBackgroundColor: '#111111' },
        horzLine: { color: '#00FF4140', labelBackgroundColor: '#111111' },
      },
      rightPriceScale: {
        borderColor: '#1A1A1A',
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderColor: '#1A1A1A',
        timeVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    chartRef.current = chart;

    // Sort data oldest first
    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#00FF41',
      downColor: '#FF073A',
      borderUpColor: '#00FF41',
      borderDownColor: '#FF073A',
      wickUpColor: '#00FF4180',
      wickDownColor: '#FF073A80',
    });

    candleSeries.setData(
      sorted.map(bar => ({
        time: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })) as any
    );

    // Volume series
    const volumeSeries = chart.addHistogramSeries({
      color: '#00FF4120',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    volumeSeries.setData(
      sorted.map(bar => ({
        time: bar.date,
        value: bar.volume,
        color: bar.close >= bar.open ? '#00FF4125' : '#FF073A25',
      })) as any
    );

    // Entry/Stop/Target lines
    if (entry) {
      candleSeries.createPriceLine({
        price: entry,
        color: '#00E5FF',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'ENTRY',
      });
    }

    if (stop) {
      candleSeries.createPriceLine({
        price: stop,
        color: '#FF073A',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'STOP',
      });
    }

    if (target) {
      candleSeries.createPriceLine({
        price: target,
        color: '#00FF41',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'TARGET',
      });
    }

    chart.timeScale().fitContent();

    // Resize observer
    const resizeObserver = new ResizeObserver(entries => {
      for (const e of entries) {
        chart.applyOptions({
          width: e.contentRect.width,
          height: e.contentRect.height,
        });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, entry, stop, target]);

  if (data.length === 0) {
    return (
      <div className="panel p-8 text-center">
        <p className="text-terminal-dim text-[11px]">No price data for {symbol}</p>
      </div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div ref={containerRef} style={{ width: '100%', height: 360 }} />
    </div>
  );
}
