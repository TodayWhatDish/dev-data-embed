const API = window.location.origin;

// ==================================
//  로그인 (계정 없이 공용 비밀번호 하나로만 검증. 서버가 JWT 토큰을 발급해준다)
// ==================================
const loginGate = document.querySelector("#loginGate");
const adminArea = document.querySelector("#adminArea");
const adminPasswordInput = document.querySelector("#adminPasswordInput");
const loginBtn = document.querySelector("#loginBtn");
const loginError = document.querySelector("#loginError");
const logoutBtn = document.querySelector("#logoutBtn");
const whoami = document.querySelector("#whoami");

let adminToken = localStorage.getItem("adminToken") || "";

const authHeaders = () => ({
  Authorization: `Bearer ${adminToken}`,
});

const enterAdmin = () => {
  loginGate.hidden = true;
  adminArea.hidden = false;
  whoami.textContent = "관리자";
  loadCustomers();
};

const showLoginGate = () => {
  adminToken = "";
  localStorage.removeItem("adminToken");
  adminArea.hidden = true;
  loginGate.hidden = false;
  adminPasswordInput.value = "";
};

loginBtn.addEventListener("click", async () => {
  loginError.textContent = "";
  const password = adminPasswordInput.value;

  const res = await fetch(`${API}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  if (!res.ok) {
    const body = await res.json();
    loginError.textContent = body.detail || "로그인 실패";
    return;
  }

  const { access_token } = await res.json();
  adminToken = access_token;
  localStorage.setItem("adminToken", adminToken);
  enterAdmin();
});

logoutBtn.addEventListener("click", showLoginGate);

// ==================================
//  API 호출
// ==================================
const getCustomers = async () => {
  const res = await fetch(`${API}/api/customers`, { headers: authHeaders() });
  if (res.status === 401) { showLoginGate(); throw new Error("토큰 만료"); }
  if (!res.ok) throw new Error();
  return res.json();
};

const getCustomerInfo = async (id) => {
  const res = await fetch(`${API}/api/customers/${id}`, { headers: authHeaders() });
  if (res.status === 401) { showLoginGate(); throw new Error("토큰 만료"); }
  if (!res.ok) throw new Error();
  return res.json();
};

// ==================================
//  상태
// ==================================
let customers = [];
let selectedCustomer = null; // getCustomerInfo() 결과 (pets, purchases 포함)

// ==================================
//  고객 목록 (사이드바)
// ==================================
const customerListEl = document.querySelector("#customerList");
const searchInput = document.querySelector("#searchInput");

const loadCustomers = async () => {
  customers = await getCustomers();
  renderCustomerList(customers);
};

const renderCustomerList = (list) => {
  if (list.length === 0) {
    customerListEl.innerHTML = `<div class="no-result">검색 결과가 없습니다.</div>`;
    return;
  }
  customerListEl.innerHTML = list
    .map(
      (c) => `
      <div class="customer-item${selectedCustomer && selectedCustomer.user_id === c.user_id ? " active" : ""}" data-id="${c.user_id}">
        <div class="avatar">${(c.name || "?")[0]}</div>
        <div class="cust-meta">
          <div class="cust-name">${c.name}</div>
          <div class="cust-sub">${c.region ?? ""}</div>
        </div>
      </div>`
    )
    .join("");

  customerListEl.querySelectorAll(".customer-item").forEach((el) => {
    el.addEventListener("click", () => selectCustomer(Number(el.dataset.id)));
  });
};

const filterCustomers = (keyword) => {
  const kw = keyword.trim().toLowerCase();
  const filtered = kw ? customers.filter((c) => c.name.toLowerCase().includes(kw)) : customers;
  renderCustomerList(filtered);
};

// ==================================
//  고객 상세 (프로필 카드 + 구매이력)
// ==================================
const mainArea = document.querySelector("#mainArea");
const aiBtn = document.querySelector("#aiBtn");

const selectCustomer = async (userId) => {
  selectedCustomer = await getCustomerInfo(userId);
  renderCustomerList(searchInput.value ? customers.filter((c) => c.name.toLowerCase().includes(searchInput.value.trim().toLowerCase())) : customers);
  renderCustomerDetail(selectedCustomer);
  aiBtn.disabled = false;
};

const renderCustomerDetail = (c) => {
  const petTags = (c.pets || [])
    .map((p) => `<span class="tag">${p.animal_category} · ${p.name}</span>`)
    .join("") || `<span class="tag">등록된 반려동물 없음</span>`;

  const totalSpent = (c.purchases || []).reduce((sum, p) => sum + p.unit_price_krw * p.quantity, 0);

  const rows = (c.purchases || [])
    .map((p) => {
      const ratingBadge =
        p.rating != null
          ? `<span class="rating">별점 ${p.rating}</span>`
          : `<span class="rating none">리뷰 없음</span>`;
      const reviewText = p.review_body
        ? `<div class="review-text">${p.review_body}</div>`
        : "";
      return `
        <tr>
          <td>${(p.purchased_at || "").slice(0, 10)}</td>
          <td>${p.product_name}</td>
          <td>${p.quantity}개</td>
          <td>${(p.unit_price_krw * p.quantity).toLocaleString()}원</td>
          <td>${ratingBadge}${reviewText}</td>
        </tr>`;
    })
    .join("");

  mainArea.innerHTML = `
    <div class="profile-card">
      <div class="profile-left">
        <div class="avatar-lg">${(c.name || "?")[0]}</div>
        <div>
          <div class="profile-name">${c.name}</div>
          <div class="profile-tags">${petTags}</div>
        </div>
      </div>
      <div class="profile-right">
        <span>연락처</span><b>${c.phone ?? "-"}</b>
        <span>가입일</span><b>${(c.created_at || "").slice(0, 10)}</b>
        <span>구매 건수</span><b>${(c.purchases || []).length}건</b>
        <span>총 구매액</span><b>${totalSpent.toLocaleString()}원</b>
      </div>
    </div>

    <div class="section-title">구매 금액 추이</div>
    <div class="chart-card">
      <canvas id="purchaseChartCanvas" height="90"></canvas>
    </div>

    <div class="section-title">구매 이력</div>
    <table class="purchases">
      <thead>
        <tr><th>날짜</th><th>상품</th><th>수량</th><th>금액</th><th>후기</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="5">구매 이력이 없습니다.</td></tr>`}</tbody>
    </table>
  `;

  drawPurchaseChart(c.purchases || []);
};

// ==================================
//  구매 금액 선그래프 (Chart.js)
// ==================================
let purchaseChart = null;

const drawPurchaseChart = (purchases) => {
  const ctx = document.getElementById("purchaseChartCanvas");
  if (!ctx) return;

  if (purchaseChart) {
    purchaseChart.destroy();
  }

  const sorted = [...purchases].sort((a, b) => a.purchased_at.localeCompare(b.purchased_at));
  const labels = sorted.map((p) => (p.purchased_at || "").slice(0, 10));
  const amounts = sorted.map((p) => p.unit_price_krw * p.quantity);

  purchaseChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "구매 금액(원)",
        data: amounts,
        borderColor: "#2f6f5e",
        backgroundColor: "rgba(47,111,94,0.12)",
        tension: 0.25,
        fill: true,
        pointRadius: 3,
        pointBackgroundColor: "#2f6f5e",
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: (v) => v.toLocaleString() + "원" } },
      },
    },
  });
};

// ==================================
//  AI 분석 패널 (슬라이드오버)
//  위쪽: 이 고객의 최근 리뷰를 근거로 한 구매 이력 기반 추천 (패널 열면 바로 조회)
//  아래쪽: admin이 직접 친 질문에 대한 실시간 LLM 답변 + 그 질문 기준 임베딩 검색 결과
// ==================================
const overlay = document.querySelector("#overlay");
const aiPanel = document.querySelector("#aiPanel");
const aiPanelName = document.querySelector("#aiPanelName");
const aiPanelBody = document.querySelector("#aiPanelBody");

const openAiPanel = () => {
  if (!selectedCustomer) return;
  aiPanelName.textContent = `${selectedCustomer.name} 고객 AI 분석`;
  overlay.classList.add("open");
  aiPanel.classList.add("open");
  renderAskForm();
  loadHistoryBasedRecs(selectedCustomer.user_id);
};

const closeAllPanels = () => {
  overlay.classList.remove("open");
  aiPanel.classList.remove("open");
};

const renderAskForm = () => {
  aiPanelBody.innerHTML = `
    <div id="historyRecs"><div class="ai-loading" style="height:auto;padding:10px 0;"><div class="spinner"></div>구매 이력 확인 중...</div></div>

    <div class="section-title" style="font-size:13px;margin-top:22px;">직접 질문하기</div>
    <form id="askForm">
      <input id="askInput" type="text" placeholder="예) 이 고객에게 어떤 사료가 맞을까요?"
             style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font-size:13.5px;outline:none;">
      <button type="submit" class="ai-btn" style="margin-top:10px;width:100%;justify-content:center;">묻기</button>
    </form>
    <div id="askError" style="color:#c0392b;font-size:13px;margin-top:10px;"></div>
    <div id="askAnswer" class="review-text" style="margin-top:16px;white-space:pre-wrap;"></div>
    <div id="askSources"></div>
  `;
  document.querySelector("#askForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = document.querySelector("#askInput").value.trim();
    if (text) askQuestion(text);
  });
};

// 이 고객이 실제로 남긴 최근 리뷰를 근거로 한 추천. 질문 없이도 패널을 열면 항상 뜬다
const loadHistoryBasedRecs = async (userId) => {
  const el = document.querySelector("#historyRecs");
  const res = await fetch(`${API}/api/customers/${userId}/similar-reviews`, { headers: authHeaders() });
  if (res.status === 401) { showLoginGate(); return; }
  const data = await res.json();

  if (!data.found.length) {
    el.innerHTML = `<p style="font-size:13px;color:var(--muted);">참고할 구매 후기가 없어 이력 기반 추천을 만들 수 없습니다.</p>`;
    return;
  }
  el.innerHTML =
    `<div class="section-title" style="font-size:13px;">구매 이력 기반 추천 <span style="font-weight:400;color:var(--muted);">(근거: "${data.product_name}" 후기)</span></div>` +
    data.found.map((s) => `
      <div class="ai-block">
        <h3><span class="dot"></span>${s.name} (${s.brand}) · 유사도 ${s.score.toFixed(3)}</h3>
        <div class="review-text">${s.review}</div>
      </div>`).join("");
};

// 선택된 고객의 첫 번째 펫 프로필로 /ask 를 스트리밍 호출.
// NDJSON 을 줄 단위로 읽는다 - 네트워크 조각이 줄 한가운데를 자를 수 있어 buffer 가 꼭 필요
const askQuestion = async (question) => {
  const answerEl = document.querySelector("#askAnswer");
  const sourcesEl = document.querySelector("#askSources");
  const errorEl = document.querySelector("#askError");
  answerEl.textContent = "";
  sourcesEl.innerHTML = "";
  errorEl.textContent = "";

  // 델타가 네트워크 조각 단위(단어/문장)로 오더라도 화면엔 한 글자씩 흘러나오게 큐에 쌓아 타이핑한다
  let typeQueue = "";
  const typeTimer = setInterval(() => {
    if (!typeQueue) return;
    answerEl.textContent += typeQueue[0];
    typeQueue = typeQueue.slice(1);
  }, 20);

  const petId = (selectedCustomer.pets || [])[0]?.pet_id ?? null;

  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ user_query: question, pet_id: petId }),
  });
  if (res.status === 401) { showLoginGate(); return; }
  if (!res.body) { errorEl.textContent = "응답을 받지 못했습니다."; return; }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const chunk = JSON.parse(line);
        if (chunk.type === "sources") renderSources(chunk.sources);
        else if (chunk.type === "delta") typeQueue += chunk.text;
        else if (chunk.type === "error") errorEl.textContent = chunk.message;
      } catch { /* 깨진 줄 하나 때문에 전체를 멈추지 않는다 */ }
    }
  }

  // 큐에 남은 글자를 마저 흘려보낸 뒤 타이머를 정리한다
  const drain = setInterval(() => {
    if (typeQueue) return;
    clearInterval(typeTimer);
    clearInterval(drain);
  }, 20);
};

// 질문 기준 임베딩 검색 결과 (candidates() 가 찾은, 이 고객 프로필 조건에 맞는 유사 리뷰)
const renderSources = (sources) => {
  const sourcesEl = document.querySelector("#askSources");
  if (!sources.length) return;
  sourcesEl.innerHTML = `<div class="section-title" style="font-size:13px;margin-top:16px;">질문 기준 임베딩 검색 결과</div>` +
    sources.map((s) => `
      <div class="ai-block">
        <h3><span class="dot"></span>${s.name} (${s.brand}) · 유사도 ${s.score.toFixed(3)}</h3>
        <div class="review-text">${s.review}</div>
      </div>`).join("");
};

// 새로고침해도 로그인 상태 유지 (모든 함수 선언이 끝난 뒤에 실행해야 함)
// 토큰이 만료됐으면 getCustomers()가 401을 받아 자동으로 로그인 화면으로 돌려보낸다
if (adminToken) enterAdmin();
