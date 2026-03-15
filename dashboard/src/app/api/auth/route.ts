import { NextRequest, NextResponse } from 'next/server';

const COOKIE_NAME = 'das_auth';

export async function POST(request: NextRequest) {
  const { password } = await request.json();
  const expected = process.env.DASHBOARD_PASSWORD;

  if (!expected) {
    // No password set — allow through
    return NextResponse.json({ ok: true });
  }

  if (password !== expected) {
    return NextResponse.json({ ok: false, error: 'Invalid password' }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE_NAME, password, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete('das_auth');
  return response;
}
