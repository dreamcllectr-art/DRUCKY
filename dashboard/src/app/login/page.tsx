'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (data.ok) {
        router.push(params.get('next') ?? '/');
        router.refresh();
      } else {
        setError('Incorrect password');
        setPassword('');
        inputRef.current?.focus();
      }
    } catch {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-10 w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-8">
          <span className="text-emerald-600 text-2xl">◈</span>
          <div>
            <div className="text-[13px] font-bold text-gray-900 tracking-widest">DAS</div>
            <div className="text-[9px] text-gray-400 tracking-widest uppercase">Druckenmiller Alpha System</div>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-[10px] text-gray-500 tracking-widest uppercase block mb-2">
              Access Password
            </label>
            <input
              ref={inputRef}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-[13px] text-gray-900 placeholder-gray-300 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 transition-all"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="text-[11px] text-red-500 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-[12px] font-semibold tracking-wider rounded-xl py-3 transition-all"
          >
            {loading ? 'Authenticating…' : 'Enter'}
          </button>
        </form>

        <div className="mt-6 pt-6 border-t border-gray-100 text-center text-[9px] text-gray-300 tracking-widest uppercase">
          Private Access Only
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
