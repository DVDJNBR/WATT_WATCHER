/**
 * Azure AD MSAL.js authentication service — Story 5.1, Task 3.2
 *
 * AC #4: MSAL.js v2 for seamless SSO token acquisition.
 * Reads config from environment variables injected at build time.
 */
import { PublicClientApplication, InteractionRequiredAuthError } from '@azure/msal-browser'

const msalConfig = {
  auth: {
    clientId:    import.meta.env.VITE_AZURE_AD_CLIENT_ID  || '',
    authority:   `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_AD_TENANT_ID || ''}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
  },
  cache: {
    cacheLocation:          'sessionStorage',
    storeAuthStateInCookie: false,
  },
}

const loginRequest = {
  scopes: [`api://${import.meta.env.VITE_AZURE_AD_CLIENT_ID || ''}/.default`],
}

let _msalInstance = null
let _initialized = false

/**
 * Return (or create) the singleton MSAL PublicClientApplication.
 * Calls initialize() exactly once — subsequent calls are no-ops.
 */
export async function getMsalInstance() {
  if (!_msalInstance) {
    _msalInstance = new PublicClientApplication(msalConfig)
  }
  if (!_initialized) {
    await _msalInstance.initialize()
    _initialized = true
  }
  return _msalInstance
}

/** Reset MSAL instance (used in tests). */
export function _resetMsalInstance() {
  _msalInstance = null
  _initialized = false
}

/**
 * Acquire a Bearer token silently; fall back to interaction if needed.
 * AC #4: Seamless SSO — silent acquisition first.
 *
 * Set VITE_SKIP_AUTH=true in .env.local to bypass MSAL for local dev.
 *
 * @returns {Promise<string>} Access token, or '' if redirect was triggered
 */
export async function acquireToken() {
  if (import.meta.env.VITE_SKIP_AUTH === 'true') return ''

  const msal = await getMsalInstance()

  const accounts = msal.getAllAccounts()
  if (!accounts.length) {
    await msal.loginRedirect(loginRequest)
    return ''
  }

  const silentRequest = { ...loginRequest, account: accounts[0] }

  try {
    const response = await msal.acquireTokenSilent(silentRequest)
    return response.accessToken
  } catch (err) {
    if (err instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect(silentRequest)
      return ''
    }
    throw err
  }
}

/**
 * Return the currently signed-in account, or null.
 */
export async function getCurrentAccount() {
  const msal = await getMsalInstance()
  const accounts = msal.getAllAccounts()
  return accounts[0] ?? null
}

/**
 * Sign out the current user.
 */
export async function signOut() {
  const msal = await getMsalInstance()
  const account = await getCurrentAccount()
  await msal.logoutRedirect({ account })
}
