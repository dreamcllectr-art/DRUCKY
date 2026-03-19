'use client';

import React, { Component, type ReactNode } from 'react';

/* ------------------------------------------------------------------ */
/*  DataError — inline error card for API / data-fetch failures       */
/* ------------------------------------------------------------------ */

interface DataErrorProps {
  message?: string;
  onRetry?: () => void;
}

export function DataError({ message, onRetry }: DataErrorProps) {
  return (
    <div className="rounded-2xl bg-white border border-gray-200 shadow-sm p-6 flex flex-col items-center gap-3 text-center">
      {/* icon */}
      <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-50">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5 text-red-500"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M18 10c0 4.418-3.582 8-8 8s-8-3.582-8-8 3.582-8 8-8 8 3.582 8 8zm-8-4a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      </div>

      <p className="text-sm text-gray-600 max-w-xs">
        {message ?? 'Something went wrong while loading data.'}
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 px-4 py-1.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors"
        >
          Try Again
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ErrorBoundary — class component that catches render errors        */
/* ------------------------------------------------------------------ */

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex items-center justify-center min-h-[200px] p-4">
          <DataError
            message={this.state.error?.message ?? 'An unexpected error occurred.'}
            onRetry={this.handleRetry}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
