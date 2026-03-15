'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';

interface NavItem { label: string; href: string; icon: string; }
interface NavGroup { title: string; items: NavItem[]; }

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'COMMAND CENTER',
    items: [
      { label: 'Home', href: '/', icon: '\u25C8' },
      { label: 'Discover', href: '/discover', icon: '\u25C9' },
      { label: 'Portfolio', href: '/portfolio', icon: '\u25A7' },
    ],
  },
  {
    title: 'SIGNALS',
    items: [
      { label: 'Signal Intel', href: '/signals', icon: '\u25B8' },
      { label: 'Patterns', href: '/patterns', icon: '\u223F' },
      { label: 'Energy Intel', href: '/energy', icon: '\u26A1' },
    ],
  },
  {
    title: 'ALPHA',
    items: [
      { label: 'Alpha Intelligence', href: '/alpha', icon: '\u03B1' },
    ],
  },
  {
    title: 'ANALYSIS',
    items: [
      { label: 'Synthesis', href: '/synthesis', icon: '\u2295' },
      { label: 'Risk & Thesis', href: '/risk', icon: '\u26A0' },
      { label: 'Intelligence', href: '/intelligence', icon: '\u00A7' },
    ],
  },
  {
    title: 'MACRO',
    items: [
      { label: 'Macro', href: '/macro', icon: '\u25D0' },
    ],
  },
  {
    title: 'TOOLS',
    items: [
      { label: 'Performance', href: '/performance', icon: '\u25A3' },
      { label: 'Reports', href: '/reports', icon: '\u2521' },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

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
      className={`h-screen bg-white border-r border-gray-200 flex flex-col shrink-0 transition-all duration-200 ${
        collapsed ? 'w-[48px]' : 'w-[220px]'
      }`}
    >
      <div className="p-3 flex items-center justify-between border-b border-gray-200">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="text-emerald-600 text-lg font-bold">{'\u25C8'}</span>
            <span className="text-[11px] font-semibold text-gray-900 tracking-widest">DAS</span>
          </div>
        )}
        <button onClick={toggleCollapse} className="text-gray-400 hover:text-gray-700 transition-colors text-[10px] p-1" title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? '\u25B8' : '\u25C2'}
        </button>
      </div>

      {!collapsed && (
        <button
          onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
          className="mx-3 mt-3 mb-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-gray-200 text-[10px] text-gray-400 hover:border-gray-300 hover:text-gray-600 transition-colors"
        >
          <span>{'\u2318'}K</span><span className="tracking-wider">Search...</span>
        </button>
      )}

      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_GROUPS.map(group => (
          <div key={group.title} className="mb-1">
            {!collapsed && (
              <button onClick={() => toggleGroup(group.title)} className="w-full flex items-center justify-between px-4 py-1.5 text-[8px] text-gray-400 tracking-widest uppercase hover:text-gray-600 transition-colors">
                <span>{group.title}</span>
                <span className="text-[7px]">{collapsedGroups[group.title] ? '\u25B8' : '\u25BE'}</span>
              </button>
            )}
            {!collapsedGroups[group.title] && (
              <div className={collapsed ? 'space-y-0.5 px-1' : ''}>
                {group.items.map(item => {
                  const active = isActive(item.href);
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      className={`flex items-center gap-2.5 transition-colors relative ${
                        collapsed ? 'justify-center py-2 mx-0.5 rounded-lg' : 'px-4 py-1.5'
                      } ${
                        active
                          ? 'text-emerald-600 bg-emerald-50'
                          : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                      }`}
                      title={collapsed ? item.label : undefined}
                    >
                      {active && !collapsed && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-emerald-600 rounded-r" />}
                      <span className={`text-[11px] ${collapsed ? '' : 'w-4 text-center'}`}>{item.icon}</span>
                      {!collapsed && <span className="text-[11px] tracking-wide">{item.label}</span>}
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </nav>

      {!collapsed && (
        <div className="px-4 py-3 border-t border-gray-200">
          <div className="text-[8px] text-gray-400 tracking-widest uppercase">System</div>
          <div className="text-[10px] text-gray-500 mt-1 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>Online</span>
          </div>
        </div>
      )}
    </aside>
  );
}
