'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'COMMAND CENTER',
    items: [
      { label: 'Home', href: '/', icon: '◈' },
      { label: 'Discover', href: '/discover', icon: '◉' },
      { label: 'Screener', href: '/screener', icon: '⊞' },
      { label: 'Portfolio', href: '/portfolio', icon: '◧' },
      { label: 'Watchlist', href: '/watchlist', icon: '◉' },
    ],
  },
  {
    title: 'ALPHA SIGNALS',
    items: [
      { label: 'Trading Ideas', href: '/trading-ideas', icon: '▸' },
      { label: 'Fat Pitches', href: '/consensus-blindspots', icon: '★' },
      { label: 'Pairs / Runners', href: '/pairs', icon: '⇄' },
      { label: 'Displacement', href: '/displacement', icon: '⚡' },
      { label: 'M&A Targets', href: '/ma', icon: '◆' },
    ],
  },
  {
    title: 'DEEP ANALYSIS',
    items: [
      { label: 'Convergence', href: '/synthesis', icon: '⊕' },
      { label: 'Conflicts', href: '/signal-conflicts', icon: '⚠' },
      { label: 'Patterns', href: '/patterns', icon: '∿' },
      { label: 'Insider Activity', href: '/insider', icon: '◐' },
      { label: 'Est. Momentum', href: '/estimate-momentum', icon: '↗' },
      { label: 'Predictions', href: '/predictions', icon: '◎' },
      { label: 'Regulatory', href: '/regulatory', icon: '§' },
      { label: 'Energy Intel', href: '/energy', icon: '⚡' },
      { label: 'AI Exec', href: '/ai-exec', icon: '●' },
    ],
  },
  {
    title: 'MACRO CONTEXT',
    items: [
      { label: 'Macro Regime', href: '/macro', icon: '◐' },
      { label: 'Economic', href: '/economic', icon: '≡' },
      { label: 'Worldview', href: '/worldview', icon: '◎' },
      { label: 'Thesis Lab', href: '/thesis', icon: '◇' },
    ],
  },
  {
    title: 'TOOLS',
    items: [
      { label: 'Performance', href: '/performance', icon: '▣' },
      { label: 'Stress Test', href: '/stress-test', icon: '⊗' },
      { label: 'Paper Trader', href: '/paper-trader', icon: '◧' },
      { label: 'Hyperliquid', href: '/hyperliquid', icon: 'H' },
      { label: 'Reports', href: '/reports', icon: '⊡' },
      { label: 'Alt Data', href: '/alt-data', icon: '◫' },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  // Persist collapse state
  useEffect(() => {
    const saved = localStorage.getItem('sidebar-collapsed');
    if (saved) setCollapsed(JSON.parse(saved));
    const savedGroups = localStorage.getItem('sidebar-groups');
    if (savedGroups) setCollapsedGroups(JSON.parse(savedGroups));
  }, []);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('sidebar-collapsed', JSON.stringify(next));
  };

  const toggleGroup = (title: string) => {
    const next = { ...collapsedGroups, [title]: !collapsedGroups[title] };
    setCollapsedGroups(next);
    localStorage.setItem('sidebar-groups', JSON.stringify(next));
  };

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <aside
      className={`h-screen bg-terminal-bg border-r border-terminal-border flex flex-col shrink-0 transition-all duration-200 ${
        collapsed ? 'w-[48px]' : 'w-[220px]'
      }`}
    >
      {/* Header */}
      <div className="p-3 flex items-center justify-between border-b border-terminal-border">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="text-terminal-green text-lg glow-green font-bold">◈</span>
            <span className="text-[11px] font-display font-bold text-terminal-bright tracking-widest">
              DAS
            </span>
          </div>
        )}
        <button
          onClick={toggleCollapse}
          className="text-terminal-dim hover:text-terminal-green transition-colors text-[10px] p-1"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '▸' : '◂'}
        </button>
      </div>

      {/* Search trigger */}
      {!collapsed && (
        <button
          onClick={() => {
            // Dispatch Cmd+K event to open CommandPalette
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
          }}
          className="mx-3 mt-3 mb-1 flex items-center gap-2 px-2.5 py-1.5 rounded-sm border border-terminal-border
                     text-[10px] text-terminal-dim hover:border-terminal-green/30 hover:text-terminal-text transition-colors"
        >
          <span>⌘K</span>
          <span className="tracking-wider">Search...</span>
        </button>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_GROUPS.map(group => (
          <div key={group.title} className="mb-1">
            {/* Group header */}
            {!collapsed && (
              <button
                onClick={() => toggleGroup(group.title)}
                className="w-full flex items-center justify-between px-4 py-1.5 text-[8px] text-terminal-dim
                           tracking-[0.2em] uppercase hover:text-terminal-text transition-colors"
              >
                <span>{group.title}</span>
                <span className="text-[7px]">{collapsedGroups[group.title] ? '▸' : '▾'}</span>
              </button>
            )}

            {/* Items */}
            {!collapsedGroups[group.title] && (
              <div className={collapsed ? 'space-y-0.5 px-1' : ''}>
                {group.items.map(item => {
                  const active = isActive(item.href);
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      className={`flex items-center gap-2.5 transition-colors relative ${
                        collapsed
                          ? 'justify-center py-2 mx-0.5 rounded-sm'
                          : 'px-4 py-1.5'
                      } ${
                        active
                          ? 'text-terminal-green bg-terminal-green/[0.06]'
                          : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-green/[0.02]'
                      }`}
                      title={collapsed ? item.label : undefined}
                    >
                      {/* Active indicator */}
                      {active && !collapsed && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-terminal-green rounded-r shadow-[0_0_6px_rgba(0,255,65,0.4)]" />
                      )}
                      <span className={`text-[11px] ${collapsed ? '' : 'w-4 text-center'}`}>
                        {item.icon}
                      </span>
                      {!collapsed && (
                        <span className="text-[11px] tracking-wide">{item.label}</span>
                      )}
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Footer — freshness */}
      {!collapsed && (
        <div className="px-4 py-3 border-t border-terminal-border">
          <div className="text-[8px] text-terminal-dim tracking-widest uppercase">System</div>
          <div className="text-[10px] text-terminal-dim mt-1 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-terminal-green animate-pulse" />
            <span>Online</span>
          </div>
        </div>
      )}
    </aside>
  );
}
