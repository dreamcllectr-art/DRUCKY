'use client';

import { useEffect, useRef } from 'react';

interface Props {
  prices: { date: string; close: number }[];
  width?: number;
  height?: number;
}

export default function Sparkline({ prices, width = 120, height = 40 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || prices.length < 2) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Retina support
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    const sorted = [...prices].sort((a, b) => a.date.localeCompare(b.date));
    const closes = sorted.map(p => p.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;

    const isUp = closes[closes.length - 1] >= closes[0];
    const color = isUp ? '#00FF41' : '#FF073A';

    ctx.clearRect(0, 0, width, height);

    // Draw line
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    const pad = 2;
    const drawW = width - pad * 2;
    const drawH = height - pad * 2;

    closes.forEach((close, i) => {
      const x = pad + (i / (closes.length - 1)) * drawW;
      const y = pad + drawH - ((close - min) / range) * drawH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Gradient fill below line
    ctx.lineTo(pad + drawW, pad + drawH);
    ctx.lineTo(pad, pad + drawH);
    ctx.closePath();

    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, isUp ? 'rgba(0,255,65,0.12)' : 'rgba(255,7,58,0.12)');
    gradient.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gradient;
    ctx.fill();

    // Current price dot at the end
    const lastX = pad + drawW;
    const lastY = pad + drawH - ((closes[closes.length - 1] - min) / range) * drawH;
    ctx.beginPath();
    ctx.arc(lastX, lastY, 2, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

  }, [prices, width, height]);

  if (prices.length < 2) return null;

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      className="block"
    />
  );
}
