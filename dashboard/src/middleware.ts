import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const COOKIE_NAME = 'das_auth';
const AUTH_PATH = '/login';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow login page and its API handler
  if (pathname === AUTH_PATH || pathname.startsWith('/api/')) {
    return NextResponse.next();
  }

  const password = process.env.DASHBOARD_PASSWORD;

  // If no password is configured, allow through (dev mode)
  if (!password) {
    return NextResponse.next();
  }

  const cookie = request.cookies.get(COOKIE_NAME);
  if (cookie?.value === password) {
    return NextResponse.next();
  }

  // Redirect to login, preserving the intended destination
  const loginUrl = new URL(AUTH_PATH, request.url);
  loginUrl.searchParams.set('next', pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
