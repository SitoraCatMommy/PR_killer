import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
    isActive && 'bg-secondary text-foreground',
  );

export function RootLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="sticky top-0 z-10 border-b border-border/80 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3 md:px-6">
          <NavLink
            to="/"
            className={({ isActive }) =>
              cn(
                'font-semibold tracking-tight text-foreground transition-opacity hover:opacity-80',
                isActive && 'opacity-100',
              )
            }
            end
          >
            {ru.brand}
          </NavLink>
          <nav className="flex flex-wrap items-center gap-1" aria-label="Основная навигация">
            <NavLink to="/" end className={navLinkClass}>
              {ru.nav.home}
            </NavLink>
            <NavLink to="/projects" className={navLinkClass}>
              {ru.nav.projects}
            </NavLink>
            <NavLink to="/materials" className={navLinkClass}>
              {ru.nav.materials}
            </NavLink>
            <NavLink to="/analytics" className={navLinkClass}>
              {ru.nav.analytics}
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-6">
        <Outlet />
      </main>
    </div>
  );
}
