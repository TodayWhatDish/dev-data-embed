const TOKEN_KEY = "admin_token";

const loginForm = document.querySelector("#login-form");
const whoamiEl = document.querySelector("#whoami");

// login.html에만 있는 폼으로 로그인 화면을 처리한다.
if (loginForm) {
  const errorEl = document.querySelector("#error");

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.textContent = "";

    const password = document.querySelector("#password").value;

    const res = await fetch("/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });

    if (!res.ok) {
      const body = await res.json();
      errorEl.textContent = body.detail || "로그인 실패";
      return;
    }

    const { access_token } = await res.json();
    localStorage.setItem(TOKEN_KEY, access_token);
    window.location.href = "/static/admin/dashboard.html";
  });
}

// dashboard.html에만 있는 표시 영역 — 있으면 대시보드 화면이다.
if (whoamiEl) {
  const token = localStorage.getItem(TOKEN_KEY);

  if (!token) {
    window.location.href = "/static/admin/login.html";
  } else {
    fetch("/admin/me", {
      headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
      if (!res.ok) {
        localStorage.removeItem(TOKEN_KEY);
        window.location.href = "/static/admin/login.html";
        return;
      }
      whoamiEl.textContent = "관리자로 로그인됨";
    });
  }
}
