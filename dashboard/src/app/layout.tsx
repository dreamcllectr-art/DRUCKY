import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import CommandPalette from '@/components/CommandPalette';
import ErrorBoundary from '@/components/ErrorBoundary';

export const metadata: Metadata = {
  title: 'Druckenmiller Alpha System',
  description: 'Technical first. Fundamentals second. Macro always.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-700 antialiased">
        <CommandPalette />
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto bg-gray-50">
            <div className="p-4 md:p-6 max-w-[1600px] mx-auto">
              <ErrorBoundary>{children}</ErrorBoundary>
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
