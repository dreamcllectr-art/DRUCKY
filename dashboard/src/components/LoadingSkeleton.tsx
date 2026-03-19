'use client';

import React from 'react';

export function CardSkeleton() {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-3 w-20 bg-gray-200 rounded-full" />
        <div className="h-5 w-5 bg-gray-100 rounded-md" />
      </div>
      <div className="h-7 w-28 bg-gray-200 rounded-lg mb-2" />
      <div className="h-3 w-16 bg-gray-100 rounded-full" />
    </div>
  );
}

export function CardRowSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden animate-pulse">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-3">
        <div className="h-4 w-32 bg-gray-200 rounded-full" />
        <div className="ml-auto h-3 w-20 bg-gray-100 rounded-full" />
      </div>

      {/* Column headers */}
      <div className="px-5 py-3 border-b border-gray-50 flex items-center gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <div
            key={i}
            className="h-3 bg-gray-100 rounded-full"
            style={{ width: i === 0 ? '20%' : `${60 / (cols - 1)}%` }}
          />
        ))}
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={rowIdx}
          className="px-5 py-3 border-b border-gray-50 last:border-b-0 flex items-center gap-4"
        >
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div
              key={colIdx}
              className="h-3 bg-gray-100 rounded-full"
              style={{
                width: colIdx === 0 ? '20%' : `${60 / (cols - 1)}%`,
                opacity: 0.6 + Math.random() * 0.4,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 animate-pulse">
      {/* Title */}
      <div className="flex items-center justify-between mb-6">
        <div className="h-4 w-36 bg-gray-200 rounded-full" />
        <div className="flex gap-2">
          <div className="h-6 w-12 bg-gray-100 rounded-md" />
          <div className="h-6 w-12 bg-gray-100 rounded-md" />
          <div className="h-6 w-12 bg-gray-100 rounded-md" />
        </div>
      </div>

      {/* Chart area */}
      <div
        className="relative w-full bg-gray-50 rounded-xl overflow-hidden"
        style={{ height }}
      >
        {/* Simulated axis lines */}
        <div className="absolute inset-0 flex flex-col justify-between py-4 px-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="w-full border-b border-gray-100" />
          ))}
        </div>

        {/* Simulated bar/line shapes */}
        <div className="absolute bottom-0 left-0 right-0 flex items-end justify-around px-6 pb-4 gap-2">
          {[40, 65, 50, 80, 55, 70, 45, 75, 60, 85, 50, 68].map((h, i) => (
            <div
              key={i}
              className="flex-1 bg-gray-200 rounded-t-md"
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="animate-pulse flex items-center justify-between">
        <div>
          <div className="h-6 w-48 bg-gray-200 rounded-lg mb-2" />
          <div className="h-3 w-64 bg-gray-100 rounded-full" />
        </div>
        <div className="h-8 w-24 bg-gray-100 rounded-lg" />
      </div>

      {/* Stat cards row */}
      <CardRowSkeleton count={4} />

      {/* Chart */}
      <ChartSkeleton />

      {/* Table */}
      <TableSkeleton rows={6} />
    </div>
  );
}
