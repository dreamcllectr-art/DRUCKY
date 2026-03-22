'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';

interface NavItem { label: string; href: string; icon: React.ReactNode; }
interface NavGroup { title: string; items: NavItem[]; }

// ─── SVG Icons ────────────────────────────────────────────────────────────────
const Icons = {
  terminal: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="2" width="12" height="10" rx="1.5"/>
      <path d="M3.5 5.5L5.5 7L3.5 8.5"/>
      <path d="M7 8.5h3"/>
    </svg>
  ),
  gates: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1.5 4h11M1.5 7h8M1.5 10h5"/>
    </svg>
  ),
  portfolio: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 10.5L5 7l2.5 2L9.5 6l2.5 2"/>
      <rect x="1" y="1.5" width="12" height="11" rx="1.5"/>
    </svg>
  ),
  alpha: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11L7 3l4 8"/>
      <path d="M4.5 8.5h5"/>
    </svg>
  ),
  risk: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 1.5L12.5 11H1.5L7 1.5z"/>
      <path d="M7 5.5v3M7 9.5v.5"/>
    </svg>
  ),
  journal: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="1.5" width="9" height="11" rx="1.5"/>
      <path d="M5 5h4M5 7.5h4M5 10h2.5"/>
    </svg>
  ),
  chevronDown: (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 3.5L5 6l2.5-2.5"/>
    </svg>
  ),
  chevronRight: (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3.5 2.5L6 5l-2.5 2.5"/>
    </svg>
  ),
  sidebarCollapse: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3L5 7l4 4"/>
    </svg>
  ),
  sidebarExpand: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 3l4 4-4 4"/>
    </svg>
  ),
  search: (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5.5" cy="5.5" r="3.5"/>
      <path d="M8.5 8.5l2 2"/>
    </svg>
  ),
  logo: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5L14.5 8L8 14.5L1.5 8L8 1.5z" stroke="#059669" strokeWidth="1.75" fill="rgba(5,150,105,0.08)"/>
      <path d="M8 5L11 8L8 11L5 8L8 5z" fill="#059669"/>
    </svg>
  ),
};

const V2_NAV_GROUPS: NavGroup[] = [
  {
    title: 'MARKET',
    items: [
      { label: 'Terminal',       href: '/v2/terminal',  icon: Icons.terminal  },
    ],
  },
  {
    title: 'OUR PROCESS',
    items: [
      { label: 'Gates (Cascade)', href: '/v2/gates',     icon: Icons.gates     },
      { label: 'Portfolio',       href: '/v2/conviction', icon: Icons.portfolio },
      { label: 'Alpha Stack',     href: '/v2/alpha',     icon: Icons.alpha     },
    ],
  },
  {
    title: 'TOOLS',
    items: [
      { label: 'Risk',    href: '/v2/risk',    icon: Icons.risk    },
      { label: 'Journal', href: '/v2/journal', icon: Icons.journal },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [dateStr, setDateStr] = useState('');

  useEffect(() => {
    const saved = localStorage.getItem('sidebar-collapsed');
    if (saved) setCollapsed(JSON.parse(saved));
    const savedGroups = localStorage.getItem('sidebar-groups');
    if (savedGroups) setCollapsedGroups(JSON.parse(savedGroups));
    setDateStr(new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }));
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
    if (href === '/v2/terminal') return pathname === '/v2/terminal' || pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <aside
      className={`h-screen bg-white border-r border-slate-200/80 flex flex-col shrink-0 transition-all duration-200 ${
        collapsed ? 'w-[52px]' : 'w-[224px]'
      }`}
    >
      {/* Logo + Collapse */}
      <div className="h-12 px-3 flex items-center justify-between border-b border-slate-100 shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            {Icons.logo}
            <span className="text-[11px] font-bold text-slate-900 tracking-[0.12em] uppercase">DAS</span>
          </div>
        )}
        {collapsed && (
          <div className="mx-auto">{Icons.logo}</div>
        )}
        {!collapsed && (
          <button
            onClick={toggleCollapse}
            className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            title="Collapse"
          >
            {Icons.sidebarCollapse}
          </button>
        )}
      </div>

      {/* Expand button when collapsed */}
      {collapsed && (
        <button
          onClick={toggleCollapse}
          className="mx-auto mt-2 p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
          title="Expand"
        >
          {Icons.sidebarExpand}
        </button>
      )}

      {/* Search */}
      {!collapsed && (
        <button
          onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
          className="mx-3 mt-2.5 mb-1 flex items-center gap-2 px-2.5 py-2 rounded-lg border border-slate-200 text-[11px] text-slate-400 hover:border-slate-300 hover:text-slate-600 hover:bg-slate-50 transition-all group"
        >
          <span className="text-slate-300 group-hover:text-slate-400 transition-colors">{Icons.search}</span>
          <span className="flex-1 text-left tracking-wide">Search...</span>
          <kbd className="text-[9px] font-mono bg-slate-100 text-slate-400 px-1 py-0.5 rounded">⌘K</kbd>
        </button>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 space-y-0.5">
        {V2_NAV_GROUPS.map(group => (
          <div key={group.title} className="mb-1">
            {!collapsed && (
              <button
                onClick={() => toggleGroup(group.title)}
                className="w-full flex items-center justify-between px-3.5 py-1.5 text-[9px] font-semibold text-slate-400 tracking-[0.1em] uppercase hover:text-slate-600 transition-colors"
              >
                <span>{group.title}</span>
                <span className="text-slate-300">
                  {collapsedGroups[group.title] ? Icons.chevronRight : Icons.chevronDown}
                </span>
              </button>
            )}
            {!collapsedGroups[group.title] && (
              <div className={collapsed ? 'px-2 space-y-0.5' : 'space-y-0.5'}>
                {group.items.map(item => {
                  const active = isActive(item.href);
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      className={`flex items-center transition-all relative ${
                        collapsed
                          ? 'justify-center p-2 mx-1 rounded-lg'
                          : 'gap-2.5 px-3.5 py-2 mx-1 rounded-lg'
                      } ${
                        active
                          ? 'text-emerald-700 bg-emerald-50 font-medium'
                          : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
                      }`}
                      title={collapsed ? item.label : undefined}
                    >
                      {active && !collapsed && (
                        <div className="absolute left-0 inset-y-1.5 w-[2.5px] bg-emerald-600 rounded-r-full" />
                      )}
                      <span className={`shrink-0 ${active ? 'text-emerald-600' : ''}`}>
                        {item.icon}
                      </span>
                      {!collapsed && (
                        <span className="text-[12px] tracking-tight">{item.label}</span>
                      )}
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* System Status */}
      {!collapsed && (
        <div className="px-4 py-3.5 border-t border-slate-100 shrink-0">
          <div className="text-[9px] font-semibold text-slate-400 tracking-[0.1em] uppercase mb-1.5">System</div>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
            <span className="text-[11px] text-slate-600 font-medium">Pipeline Active</span>
          </div>
          <div className="text-[10px] text-slate-400 mt-1">{dateStr}</div>
        </div>
      )}
      {collapsed && (
        <div className="pb-3 flex justify-center shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        </div>
      )}
    </aside>
  );
}
