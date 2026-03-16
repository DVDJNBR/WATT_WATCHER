/**
 * LoginPage — email + password login form.
 * On success → JWT stored in AuthContext → redirect to dashboard.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { login as apiLogin } from '../services/api.js'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate   = useNavigate()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState(null)
  const [loading,  setLoading]  = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { token, user } = await apiLogin(email, password)
      login(token, user)
      navigate('/')
    } catch (err) {
      setError(err.message || 'Identifiants incorrects')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card glass-card">
        <div className="auth-logo">⚡ WATT WATCHER</div>
        <h1 className="auth-title">Connexion</h1>

        {error && (
          <div className="auth-error" role="alert">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          <div className="auth-field">
            <label htmlFor="login-email" className="auth-label">Adresse email</label>
            <input
              id="login-email"
              type="email"
              className="selector-input auth-input"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={loading}
              aria-describedby={error ? 'login-error' : undefined}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="login-password" className="auth-label">Mot de passe</label>
            <input
              id="login-password"
              type="password"
              className="selector-input auth-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary auth-submit"
            disabled={loading || !email || !password}
          >
            {loading ? 'Connexion…' : 'Se connecter'}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/register" className="auth-link">Créer un compte</Link>
          <span className="auth-links__sep">·</span>
          <Link to="/reset-password" className="auth-link">Mot de passe oublié ?</Link>
        </div>
      </div>
    </div>
  )
}
