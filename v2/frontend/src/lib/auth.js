const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID
const DEV_MODE = import.meta.env.VITE_DEV_MODE === 'true'

let _token = null
let _onSignIn = null
let _onSignOut = null

export function initAuth({ onSignIn, onSignOut }) {
  _onSignIn = onSignIn
  _onSignOut = onSignOut

  if (DEV_MODE) {
    _token = 'dev-token'
    onSignIn({ email: 'dev@localhost', name: 'Dev User', picture: null })
    return
  }

  if (!CLIENT_ID) {
    console.warn('VITE_GOOGLE_CLIENT_ID not set — auth disabled')
    return
  }

  window.google?.accounts.id.initialize({
    client_id: CLIENT_ID,
    callback: (response) => {
      _token = response.credential
      const payload = _parseJwt(response.credential)
      onSignIn({ email: payload.email, name: payload.name, picture: payload.picture })
    },
    auto_select: true,
  })
}

export function renderSignInButton(element) {
  if (DEV_MODE || !CLIENT_ID) return
  window.google?.accounts.id.renderButton(element, {
    theme: 'filled_black',
    size: 'medium',
    shape: 'rectangular',
    text: 'signin_with',
  })
  window.google?.accounts.id.prompt()
}

export function signOut() {
  _token = null
  window.google?.accounts.id.disableAutoSelect()
  _onSignOut?.()
}

export function getToken() {
  return _token
}

function _parseJwt(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return {}
  }
}
