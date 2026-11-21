/* 공유 인증 가드 — 모든 페이지에서 로드 */
(function () {
  const API = 'http://127.0.0.1:8000';
  const LOGIN_PAGE = '/login.html';

  // 로그인 페이지 자체는 체크 불필요
  if (location.pathname === LOGIN_PAGE || location.pathname === '/login.html') return;

  const token = localStorage.getItem('authToken');
  if (!token) {
    location.replace(LOGIN_PAGE);
    return;
  }

  // 서버에서 토큰 유효성 확인
  fetch(`${API}/api/auth/check?token=${encodeURIComponent(token)}`)
    .then(r => { if (!r.ok) throw new Error(); })
    .catch(() => {
      localStorage.removeItem('authToken');
      location.replace(LOGIN_PAGE);
    });
})();

/* 로그아웃 함수 — 모든 페이지에서 사용 가능 */
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
  location.replace('/login.html');
}
