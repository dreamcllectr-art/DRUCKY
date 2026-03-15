import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import CommandPalette from '@/components/CommandPalette';

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
            <div className="p-6 max-w-[1600px] mx-auto">
              {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
