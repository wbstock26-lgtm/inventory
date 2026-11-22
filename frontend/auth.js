/* 공유 인증 가드 — 모든 페이지에서 로드 */
(function () {
  const API = '';
  const LOGIN_PAGE = '/login.html';

  if (location.pathname.endsWith('/login.html')) return;

  const token = localStorage.getItem('authToken');
  if (!token) { location.replace(LOGIN_PAGE); return; }

  const isSplitPage   = location.pathname.endsWith('split.html');
  const isAccountPage = location.pathname.endsWith('account.html');

  fetch(`${API}/api/auth/check?token=${encodeURIComponent(token)}`)
    .then(r => {
      if (!r.ok) throw new Error();
      return r.json();
    })
    .then(data => {
      const role = data.role || 'split';
      localStorage.setItem('authRole', role);

      if (role !== 'split') return;

      // split 역할: 모든 페이지 접근 가능하지만 split.html 외에는 읽기 전용
      document.body.dataset.role = 'split';

      if (!isSplitPage && !isAccountPage) {
        // 읽기 전용 배너
        const bar = document.createElement('div');
        bar.id = 'readonly-bar';
        bar.style.cssText = [
          'position:fixed;top:0;left:0;right:0;z-index:9999',
          'background:#1d4ed8;color:#fff',
          'display:flex;align-items:center;justify-content:space-between',
          'padding:6px 16px;font-size:13px;font-weight:600;gap:12px',
        ].join(';');
        bar.innerHTML = `
          <span>🔒 읽기 전용 — 수정은 Split 페이지에서만 가능합니다</span>
          <a href="/split.html" style="color:#fff;text-decoration:underline;white-space:nowrap;font-weight:700">Split 페이지로 →</a>
        `;
        document.body.prepend(bar);
        // 배너 높이만큼 body 상단 여백 추가
        document.body.style.marginTop = '36px';
      }

      // 수정 버튼/입력 비활성화 CSS 주입
      const style = document.createElement('style');
      style.textContent = `
        /* inventory: 액션 버튼, 삭제 버튼 숨기기 */
        body[data-role="split"] .action-btn.primary { display:none!important; }
        body[data-role="split"] .del-btn { display:none!important; }
        body[data-role="split"] #ocrApplyBtn { display:none!important; }
        /* inventory: 인라인 편집 비활성화 */
        body[data-role="split"] .editable-cell { pointer-events:none!important; cursor:default!important; }
        body[data-role="split"] .dept-badge   { pointer-events:none!important; cursor:default!important; }
        body[data-role="split"] .split-btn    { pointer-events:none!important; opacity:.45!important; }
        /* prices: 저장/삭제/추가 버튼 숨기기 */
        body[data-role="split"] .btn-save-all   { display:none!important; }
        body[data-role="split"] .btn-row        { display:none!important; }
        body[data-role="split"] .btn-delete-row { display:none!important; }
        body[data-role="split"] .btn-add-product{ display:none!important; }
        body[data-role="split"] .btn-delete-dup { display:none!important; }
        body[data-role="split"] .register-actions { display:none!important; }
        body[data-role="split"] .price-input  { pointer-events:none!important; background:transparent!important; }
        body[data-role="split"] .unit-input   { pointer-events:none!important; background:transparent!important; }
        /* sales / import / manual_receive: 제출 버튼 숨기기 */
        body[data-role="split"] .btn-primary  { display:none!important; }
        body[data-role="split"] button[type="submit"] { display:none!important; }
        /* 공통: 삭제 확인 버튼 */
        body[data-role="split"] .del-confirm-yes { display:none!important; }
      `;
      document.head.appendChild(style);
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
    fetch('/api/auth/logout', {
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
