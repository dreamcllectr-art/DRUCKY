'use client';

import React from 'react';

interface Props { children: React.ReactNode; }
interface State { error: Error | null; }

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center h-[60vh]">
          <div className="panel p-8 text-center max-w-md">
            <div className="text-rose-600 text-sm font-bold mb-2">Something went wrong</div>
            <p className="text-[11px] text-gray-500 mb-4">{this.state.error.message}</p>
            <button onClick={() => this.setState({ error: null })} className="px-4 py-2 text-[10px] tracking-widest text-emerald-600 border border-emerald-600/30 rounded-lg hover:bg-emerald-600/5">
              TRY AGAIN
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
