/**
 * Layout — shared chrome across all pages: header (logo + theme toggle)
 * and the tab navigation separating dashboard / narrative content pages.
 */
import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

/** Temporary logo mark — a simple geometric bolt, not an emoji. Swap for a
 * real designed logo later; this just needs to look intentional in the
 * meantime. */
function LogoMark() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
    </svg>
  )
}

const TAB_ICONS = {
  origine: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16.5" />
      <circle cx="12" cy="7.5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  ),
  pipeline: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="6" r="2.2" />
      <circle cx="5" cy="18" r="2.2" />
      <circle cx="19" cy="12" r="2.2" />
      <path d="M7 6.8 17 11.2M7 17.2 17 12.8" />
    </svg>
  ),
  dashboard: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="19" x2="5" y2="11" />
      <line x1="12" y1="19" x2="12" y2="5" />
      <line x1="19" y1="19" x2="19" y2="14" />
    </svg>
  ),
}

const TABS = [
  { to: '/origine',  label: 'À propos',           icon: 'origine' },
  { to: '/pipeline', label: 'Pipeline de données', icon: 'pipeline' },
  { to: '/',         label: 'Dashboard',           icon: 'dashboard', end: true },
]

export function Layout() {
  const [theme, setTheme] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return (
    <div className="app-layout" data-testid="app-layout">
      <a href="#main-content" className="skip-link">Passer au contenu principal</a>

      <header className="app-header">
        <span className="logo" aria-label="WATT WATCHER">
          <span className="logo-mark"><LogoMark /></span>
          WATT WATCHER
        </span>

        <div className="header-actions">
          <button
            className="btn btn-ghost"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            aria-label="Basculer le thème"
            data-testid="theme-toggle"
          >
            {theme === 'dark' ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4.5" />
                <path d="M12 2.5v2.5M12 19v2.5M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2.5 12H5M19 12h2.5M4.2 19.8 6 18M18 6l1.8-1.8" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z" />
              </svg>
            )}
          </button>
        </div>
      </header>

      <nav className="app-tabs" aria-label="Navigation principale">
        {TABS.map(({ to, label, end, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => 'app-tab' + (isActive ? ' app-tab--active' : '')}
          >
            {TAB_ICONS[icon]}
            {label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
