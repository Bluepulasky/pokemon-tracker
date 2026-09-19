import { NavLink, useLocation } from 'react-router';

import { cn } from '@/lib/cn';

import { GlobalSearch } from './GlobalSearch';

interface Tab {
  to: string;
  label: string;
  /** Other path prefixes that light this tab up. */
  alsoActiveOn?: string[];
  desktopOnly?: boolean;
}

const TABS: Tab[] = [
  { to: '/dashboard', label: 'Dash' },
  { to: '/sets', label: 'Sets', alsoActiveOn: ['/set/'] },
  { to: '/cartas', label: 'Cartas', alsoActiveOn: ['/collection'] },
  { to: '/missing', label: 'Faltantes' },
  // Long-running imports and price sweeps are not offered on a phone.
  { to: '/mantenimiento', label: 'Mantenimiento', desktopOnly: true },
];

export function Topbar() {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-40 flex flex-wrap items-center gap-2.5 border-b border-line bg-surface/90 px-3 pt-2.5 backdrop-blur-lg backdrop-saturate-150 md:h-16 md:flex-nowrap md:gap-4.5 md:px-4 md:pt-0">
      <NavLink to="/dashboard" className="flex items-center gap-2 font-bold tracking-tight">
        <img
          src={`${import.meta.env.BASE_URL}favicon_ios.png`}
          width={45}
          height={45}
          alt=""
          className="rounded-sm"
        />
        TomBot<span className="font-medium text-fg-dim max-md:hidden">Tracker</span>
      </NavLink>

      <nav className="flex gap-0.5 max-md:order-2 max-md:ml-auto max-md:overflow-x-auto">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) => {
              const active =
                isActive || tab.alsoActiveOn?.some((prefix) => pathname.startsWith(prefix));
              return cn(
                'rounded-full px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap transition md:px-3 md:text-sm',
                tab.desktopOnly && 'max-md:hidden',
                active
                  ? 'bg-accent font-semibold text-surface'
                  : 'text-fg-dim hover:bg-surface-2 hover:text-fg',
              );
            }}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <GlobalSearch />
    </header>
  );
}
