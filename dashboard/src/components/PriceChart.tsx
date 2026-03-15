'use client';

import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi, ColorType, LineStyle } from 'lightweight-charts';
import type { PriceBar } from '@/lib/api';
import { cs } from '@/lib/styles';

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
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#9ca3af',
        fontFamily: "'JetBrains Mono', monospace",
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
      rightPriceScale: {
        borderColor: '#e5e7eb',
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    chartRef.current = chart;

    // Sort data oldest first
    const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#059669',
      downColor: '#e11d48',
      borderUpColor: '#059669',
      borderDownColor: '#e11d48',
      wickUpColor: '#05966980',
      wickDownColor: '#e11d4880',
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
      color: '#05966920',
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
        color: bar.close >= bar.open ? '#05966925' : '#e11d4825',
      })) as any
    );

    // Entry/Stop/Target lines
    if (entry) {
      candleSeries.createPriceLine({
        price: entry,
        color: '#2563eb',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'ENTRY',
      });
    }

    if (stop) {
      candleSeries.createPriceLine({
        price: stop,
        color: '#e11d48',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'STOP',
      });
    }

    if (target) {
      candleSeries.createPriceLine({
        price: target,
        color: '#059669',
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
        <p className="text-gray-500 text-[11px]">No price data for {symbol}</p>
      </div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div ref={containerRef} {...cs({ width: '100%', height: 360 })} />
    </div>
  );
}
