/* 공유 인증 가드 — 모든 페이지에서 로드 */
(function () {
  const API = 'http://127.0.0.1:8000';
  const LOGIN_PAGE = '/login.html';

  if (location.pathname === LOGIN_PAGE || location.pathname.endsWith('/login.html')) return;

  const token = localStorage.getItem('authToken');
  if (!token) { location.replace(LOGIN_PAGE); return; }

  // split 역할이 접근 가능한 페이지 목록
  const SPLIT_ALLOWED = ['/split.html', '/account.html'];
  const isSplitAllowed = SPLIT_ALLOWED.some(p => location.pathname.endsWith(p.replace('/', '')));

  fetch(`${API}/api/auth/check?token=${encodeURIComponent(token)}`)
    .then(r => {
      if (!r.ok) throw new Error();
      return r.json();
    })
    .then(data => {
      const role = data.role || 'split';
      localStorage.setItem('authRole', role);
      // split 역할이면 허용 페이지 외 접근 차단
      if (role === 'split' && !isSplitAllowed) {
        location.replace('/split.html');
      }
    })
    .catch(() => {
      localStorage.removeItem('authToken');
      localStorage.removeItem('authRole');
      location.replace(LOGIN_PAGE);
    });
})();

/* 로그아웃 */
function authLogout() {
  const token = localStorage.getItem('authToken');
  if (token) {
    fetch('http://127.0.0.1:8000/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }).catch(() => {});
  }
  localStorage.removeItem('authToken');
  localStorage.removeItem('authRole');
  location.replace('/login.html');
}

/* 현재 역할 반환 */
function getAuthRole() {
  return localStorage.getItem('authRole') || 'split';
}
