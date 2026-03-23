'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function HomePage() {
  const router = useRouter();
  useEffect(() => { router.replace('/v2/terminal'); }, [router]);
  return null;
}
