/**
 * RegisterPage — create account with email + password.
 * On success → shows confirmation pending message.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { register as apiRegister, resendConfirmation } from '../services/api.js'

export default function RegisterPage() {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [confirm,  setConfirm]  = useState('')
  const [error,    setError]    = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [done,     setDone]     = useState(false)
  const [resent,   setResent]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Les mots de passe ne correspondent pas.')
      return
    }
    if (password.length < 8) {
      setError('Le mot de passe doit faire au moins 8 caractères.')
      return
    }
    setLoading(true)
    try {
      await apiRegister(email, password)
      setDone(true)
    } catch (err) {
      setError(err.message || 'Erreur lors de l\'inscription')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    try {
      await resendConfirmation(email)
      setResent(true)
    } catch { /* ignore */ }
  }

  if (done) {
    return (
      <div className="auth-page">
        <div className="auth-card glass-card">
          <div className="auth-logo">⚡ WATT WATCHER</div>
          <h1 className="auth-title">Vérifiez votre email</h1>
          <p className="auth-hint">
            Un lien de confirmation a été envoyé à <strong>{email}</strong>.
            Cliquez dessus pour activer votre compte.
          </p>
          {resent ? (
            <p className="auth-hint auth-hint--success">Email renvoyé ✓</p>
          ) : (
            <button className="btn btn-ghost auth-resend" onClick={handleResend}>
              Renvoyer l'email de confirmation
            </button>
          )}
          <div className="auth-links">
            <Link to="/login" className="auth-link">Retour à la connexion</Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card glass-card">
        <div className="auth-logo">⚡ WATT WATCHER</div>
        <h1 className="auth-title">Créer un compte</h1>

        {error && (
          <div className="auth-error" role="alert">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          <div className="auth-field">
            <label htmlFor="reg-email" className="auth-label">Adresse email</label>
            <input
              id="reg-email"
              type="email"
              className="selector-input auth-input"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={loading}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="reg-password" className="auth-label">Mot de passe</label>
            <input
              id="reg-password"
              type="password"
              className="selector-input auth-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
              disabled={loading}
            />
            <span className="auth-hint">8 caractères minimum</span>
          </div>

          <div className="auth-field">
            <label htmlFor="reg-confirm" className="auth-label">Confirmer le mot de passe</label>
            <input
              id="reg-confirm"
              type="password"
              className="selector-input auth-input"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary auth-submit"
            disabled={loading || !email || !password || !confirm}
          >
            {loading ? 'Inscription…' : 'Créer mon compte'}
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login" className="auth-link">Déjà un compte ? Se connecter</Link>
        </div>
      </div>
    </div>
  )
}
