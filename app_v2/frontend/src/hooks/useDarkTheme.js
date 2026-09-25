import { useState, useEffect } from 'react'

/**
 * Whether the app is currently rendering dark.
 *
 * Three states, not two: an explicit choice stamps data-theme="dark"/"light"
 * on the root element, while the default "system" setting stamps nothing and
 * leaves prefers-color-scheme to decide. Components that pick colours in JS
 * (canvas, chart series) need the resolved answer, and they need it to update
 * when the user flips the toggle — hence the MutationObserver on the stamp.
 */
export function useDarkTheme() {
  const resolve = () => {
    const t = document.documentElement.getAttribute('data-theme')
    if (t === 'dark') return true
    if (t === 'light') return false
    return window.matchMedia('(prefers-color-scheme:dark)').matches
  }
  const [dark, setDark] = useState(resolve)
  useEffect(() => {
    const mo = new MutationObserver(() => setDark(resolve()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return dark
}
