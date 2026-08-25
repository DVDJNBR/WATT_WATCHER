/**
 * Layout — shared chrome across all pages: header (logo + theme toggle)
 * and the tab navigation separating dashboard / narrative content pages.
 */
import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const TABS = [
  { to: '/origine', label: 'À propos' },
  { to: '/',        label: 'Dashboard', end: true },
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
          ⚡ WATT WATCHER
        </span>

        <div className="header-actions">
          <button
            className="btn btn-ghost"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            aria-label="Basculer le thème"
            data-testid="theme-toggle"
          >
            {theme === 'dark' ? '☀' : '⏾'}
          </button>
        </div>
      </header>

      <nav className="app-tabs" aria-label="Navigation principale">
        {TABS.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => 'app-tab' + (isActive ? ' app-tab--active' : '')}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
