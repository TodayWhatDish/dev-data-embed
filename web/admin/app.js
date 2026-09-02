const TOKEN_KEY = "admin_token";

  const form = document.querySelector("#login-form");
  const errorEl = document.querySelector("#error");
  const submitBtn = form.querySelector("button");

  form.addEventListener("submit", async (e) => {
    // 이게 없으면 브라우저가 페이지를 새로고침해 버려 아래 fetch가 실행되지 않는다.
    e.preventDefault();

    errorEl.textContent = "";
    submitBtn.disabled = true;

    const password = document.querySelector("#password").value;

    try {
      const res = await fetch("/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (!res.ok) {
        // 서버는 실패 사유를 detail에 담아 보낸다 (admin_auth.py:19)
        const body = await res.json();
        errorEl.textContent = body.detail || "로그인에 실패했습니다.";
        return;
      }

      const { access_token } = await res.json();
      localStorage.setItem(TOKEN_KEY, access_token);
      window.location.href = "/static/admin/dashboard.html";
    } catch {
      // 서버가 아예 안 떠 있으면 fetch 자체가 터진다. 이때 화면이 조용하면 원인을 못 찾는다.
      errorEl.textContent = "서버에 연결할 수 없습니다.";
    } finally {
      submitBtn.disabled = false;
    }
  });