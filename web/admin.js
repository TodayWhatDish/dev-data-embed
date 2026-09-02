const API = window.location.origin;

// 개/고양이 두 종만 있는 데이터셋 - 종 이름으로 이모지 매핑 (아바타/태그에 사용)
const petEmoji = (species) => (species === "개" ? "🐶" : species === "고양이" ? "🐱" : "🐾");
// DB 값은 "개"지만 화면엔 "강아지"로 표기
const speciesLabel = (species) => (species === "개" ? "강아지" : species);
// list_users()가 준 species(콤마로 합친 문자열)로 강아지/고양이/모두 카테고리를 가른다
const petCategory = (speciesCsv) => {
  const has = (s) => (speciesCsv || "").includes(s);
  if (has("개") && has("고양이")) return "모두";
  if (has("개")) return "강아지";
  if (has("고양이")) return "고양이";
  return "미등록";
};
const genderLabel = (g) => (g === "M" ? "♂" : g === "F" ? "♀" : "-");
// 반려동물 생년월일로 나이 계산 (사람 나이가 아니다 - user 테이블엔 생년월일이 없다)
const ageLabel = (birthDate) => {
  if (!birthDate) return "-";
  const b = new Date(birthDate);
  const now = new Date();
  let months = (now.getFullYear() - b.getFullYear()) * 12 + (now.getMonth() - b.getMonth());
  if (now.getDate() < b.getDate()) months -= 1;
  if (months < 0) return "-";
  return months < 12 ? `${months}개월` : `${Math.floor(months / 12)}살`;
};

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
  checkSystemStatus();
  setInterval(checkSystemStatus, 30000);
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
let askGen = 0; // askQuestion()이 겹쳐 호출돼도 오래된 스트림이 화면에 못 쓰게 막는 세대 번호
// 사료/간식 표 각각의 정렬 상태 - 헤더 클릭 때마다 갱신되고 renderCustomerDetail() 재호출로 반영된다
let purchaseSort = { 사료: { key: "purchased_at", dir: "desc" }, 간식: { key: "purchased_at", dir: "desc" } };

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
          <div class="cust-name">${c.name} <span class="cust-id">펫 ${genderLabel(c.gender)} ${ageLabel(c.birth_date)}</span></div>
          <div class="cust-sub">${c.region ?? ""} · ${petCategory(c.species)}</div>
        </div>
      </div>`
    )
    .join("");

  customerListEl.querySelectorAll(".customer-item").forEach((el) => {
    el.addEventListener("click", () => selectCustomer(Number(el.dataset.id)));
  });
};

// 이름 또는 고객 id(부분 일치)로 검색 - id는 화면엔 안 보이지만 검색은 되게 한다
const matchesSearch = (c, kw) => c.name.toLowerCase().includes(kw) || String(c.user_id).includes(kw);

const filterCustomers = (keyword) => {
  const kw = keyword.trim().toLowerCase();
  const filtered = kw ? customers.filter((c) => matchesSearch(c, kw)) : customers;
  renderCustomerList(filtered);
};

// ==================================
//  고객 상세 (프로필 카드 + 구매이력)
// ==================================
const mainArea = document.querySelector("#mainArea");
const aiBtn = document.querySelector("#aiBtn");

const selectCustomer = async (userId) => {
  selectedCustomer = await getCustomerInfo(userId);
  const kw = searchInput.value.trim().toLowerCase();
  renderCustomerList(kw ? customers.filter((c) => matchesSearch(c, kw)) : customers);
  renderCustomerDetail(selectedCustomer);
  aiBtn.disabled = false;
};

const renderCustomerDetail = (c) => {
  const petTags = (c.pets || [])
    .map((p) => `<span class="tag">${speciesLabel(p.animal_category)} · ${p.name}</span>`)
    .join("") || `<span class="tag">등록된 반려동물 없음</span>`;

  const totalSpent = (c.purchases || []).reduce((sum, p) => sum + p.unit_price_krw * p.quantity, 0);

  // 사료/간식 구분 - product_type은 백엔드가 product_category 트리를 최상위(사료/간식)로 접어서 준다
  const purchaseRow = (p) => {
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
          <td>${p.amount.toLocaleString()}원</td>
          <td>${ratingBadge}${reviewText}</td>
        </tr>`;
  };
  // 헤더 클릭으로 날짜/금액/별점 정렬 (오름/내림 토글) - purchaseSort에 상태 저장, 클릭 시 상세 화면 전체를 다시 그린다
  const sortArrow = (type, key) =>
    purchaseSort[type].key === key ? (purchaseSort[type].dir === "desc" ? " ▼" : " ▲") : "";
  const purchaseTable = (type) => {
    const sort = purchaseSort[type];
    const rows = (c.purchases || [])
      .filter((p) => p.product_type === type)
      .map((p) => ({ ...p, amount: p.unit_price_krw * p.quantity }))
      .sort((a, b) => {
        const av = a[sort.key] ?? -Infinity;
        const bv = b[sort.key] ?? -Infinity;
        const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
        return sort.dir === "desc" ? -cmp : cmp;
      })
      .map(purchaseRow)
      .join("");
    return `
    <table class="purchases">
      <thead>
        <tr><th colspan="5">${type}</th></tr>
        <tr>
          <th class="sortable" onclick="sortPurchases('${type}','purchased_at')">날짜${sortArrow(type, "purchased_at")}</th>
          <th>상품</th>
          <th>수량</th>
          <th class="sortable" onclick="sortPurchases('${type}','amount')">금액${sortArrow(type, "amount")}</th>
          <th class="sortable" onclick="sortPurchases('${type}','rating')">별점${sortArrow(type, "rating")}</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="5">구매 이력이 없습니다.</td></tr>`}</tbody>
    </table>`;
  };

  mainArea.innerHTML = `
    <div class="profile-card">
      <div class="profile-left">
        <div class="avatar-lg">${petEmoji((c.pets || [])[0]?.animal_category)}</div>
        <div>
          <div class="profile-name">${c.name}</div>
          <div class="profile-tags">${petTags}</div>
        </div>
      </div>
      <div class="profile-right">
        <span>이메일</span><b>${c.email ?? "-"}</b>
        <span>연락처</span><b>${c.phone ?? "-"}</b>
        <span>반려동물 나이</span><b>${ageLabel((c.pets || [])[0]?.birth_date)}</b>
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
    ${purchaseTable("사료")}
    <div style="height:16px;"></div>
    ${purchaseTable("간식")}
  `;

  drawPurchaseChart(c.purchases || []);
};

// 같은 컬럼을 다시 누르면 방향만 뒤집고, 다른 컬럼이면 내림차순부터 시작
const sortPurchases = (type, key) => {
  const cur = purchaseSort[type];
  cur.dir = cur.key === key ? (cur.dir === "desc" ? "asc" : "desc") : "desc";
  cur.key = key;
  renderCustomerDetail(selectedCustomer);
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

// ==================================
//  회원 / 검증 / 시스템 화면 전환 - sidebar+main(회원)과 두 full-view 섹션 중 하나만 보여준다.
// ==================================
const sidebarEl = document.querySelector(".sidebar");
const verifyView = document.querySelector("#verifyView");
const systemView = document.querySelector("#systemView");

const switchView = (view) => {
  document.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  sidebarEl.hidden = view !== "members";
  mainArea.hidden = view !== "members";
  verifyView.hidden = view !== "verify";
  systemView.hidden = view !== "system";
  if (view === "system") checkSystemStatus();
};

document.querySelectorAll(".view-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

// ==================================
//  DB / API 연결 상태 (시스템 화면) - /ready 를 주기적으로 폴링
// ==================================
const checkSystemStatus = async () => {
  const dbDot = document.querySelector("#dbDot");
  const apiDot = document.querySelector("#apiDot");
  try {
    const res = await fetch(`${API}/ready`);
    const data = await res.json();
    dbDot.style.background = data.db ? "#2e9e5b" : "#c0392b";
    apiDot.style.background = data.llm ? "#2e9e5b" : "#c0392b";
  } catch {
    dbDot.style.background = "#c0392b";
    apiDot.style.background = "#c0392b";
  }
};

// 추천/전략/질문을 탭으로 나눠 한 화면에 다 쌓이지 않게 한다 - 패널이 좁아 셋을 동시에 보여주면 스크롤이 너무 길어진다.
const renderAskForm = () => {
  aiPanelBody.innerHTML = `
    <div class="ai-tabs">
      <button class="ai-tab active" data-tab="recs">추천</button>
      <button class="ai-tab" data-tab="strategy">전략</button>
      <button class="ai-tab" data-tab="ask">질문</button>
    </div>

    <div class="ai-tab-panel" data-panel="recs">
      <div id="historyRecs"><div class="ai-loading" style="height:auto;padding:10px 0;"><div class="spinner"></div>구매 이력 확인 중...</div></div>
    </div>

    <div class="ai-tab-panel" data-panel="strategy" hidden>
      <div class="section-title" style="font-size:13px;">판매전략 / CS 응대안</div>
      <button id="strategyBtn" class="ai-btn" style="width:100%;justify-content:center;">생성하기</button>
      <div id="strategyResult" style="margin-top:14px;"></div>
    </div>

    <div class="ai-tab-panel" data-panel="ask" hidden>
      <form id="askForm">
        <input id="askInput" type="text" placeholder="예) 이 고객에게 어떤 사료가 맞을까요?"
               style="width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font-size:13.5px;outline:none;">
        <button type="submit" class="ai-btn" style="margin-top:10px;width:100%;justify-content:center;">묻기</button>
      </form>
      <div id="askError" style="color:#c0392b;font-size:13px;margin-top:10px;"></div>
      <div id="askAnswer" class="answer-text" style="margin-top:14px;white-space:pre-wrap;"></div>
      <div id="askVerify" style="color:#c0392b;font-size:13px;margin-top:10px;line-height:1.7;white-space:pre-wrap;"></div>

      <div class="scroll-block" id="askFacts"></div>
      <div class="scroll-block" id="askSources"></div>
    </div>
  `;
  document.querySelectorAll(".ai-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".ai-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".ai-tab-panel").forEach((p) => {
        p.hidden = p.dataset.panel !== btn.dataset.tab;
      });
    });
  });
  document.querySelector("#askForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = document.querySelector("#askInput").value.trim();
    if (!text) return;
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await askQuestion(text);
    } finally {
      btn.disabled = false;
    }
  });
  document.querySelector("#strategyBtn").addEventListener("click", loadStrategy);
};

// 판매전략/CS 응대안 생성. LLM 호출 비용이 있어 패널을 열 때 자동 실행하지 않고 버튼으로 트리거한다.
// citations의 verified는 서버가 SQL로 대조한 결과 - 실제 이 고객 구매가 아니면 false.
const loadStrategy = async () => {
  const btn = document.querySelector("#strategyBtn");
  const resultEl = document.querySelector("#strategyResult");
  btn.disabled = true;
  resultEl.innerHTML = `<div class="ai-loading" style="height:auto;padding:10px 0;"><div class="spinner"></div>생성 중...</div>`;

  const res = await fetch(`${API}/api/customers/${selectedCustomer.user_id}/strategy`, {
    method: "POST",
    headers: authHeaders(),
  });
  btn.disabled = false;
  if (res.status === 401) { showLoginGate(); return; }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    resultEl.innerHTML = `<p style="font-size:13px;color:#c0392b;">${err.detail ?? "생성 실패"}</p>`;
    return;
  }

  const data = await res.json();
  resultEl.innerHTML =
    `<div class="answer-text" style="white-space:pre-wrap;">${data.strategy}</div>` +
    `<div class="section-title" style="font-size:12px;margin-top:12px;">근거</div>` +
    data.citations.map((c) => `
      <div class="ai-block">
        <h3><span class="dot" style="background:${c.verified ? "#2e9e5b" : "#c0392b"};"></span>
          구매#${c.purchase_id} · ${c.verified ? "확인됨" : "확인 불가"}</h3>
        <div class="review-text">${c.quote}</div>
      </div>`).join("");
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
    data.found.slice(0, 3).map((s) => `
      <div class="ai-block">
        <h3><span class="dot"></span>${s.name} (${s.brand}) · 유사도 ${s.score.toFixed(3)}</h3>
        <div class="review-text">${s.review}</div>
      </div>`).join("");
};

// 선택된 고객의 첫 번째 펫 프로필로 /ask 를 스트리밍 호출.
// NDJSON 을 줄 단위로 읽는다 - 네트워크 조각이 줄 한가운데를 자를 수 있어 buffer 가 꼭 필요
const askQuestion = async (question) => {
  // 이 호출만의 세대 번호. 도중에 새 askQuestion()이 또 호출되면 askGen이 바뀌어
  // 이 호출의 타이머/쓰기는 전부 스스로 멈춘다 - 같은 #askAnswer에 두 스트림이 동시에 안 써진다.
  const myGen = ++askGen;
  const answerEl = document.querySelector("#askAnswer");
  const sourcesEl = document.querySelector("#askSources");
  const errorEl = document.querySelector("#askError");
  answerEl.textContent = "";
  sourcesEl.innerHTML = "";
  errorEl.textContent = "";
  document.querySelector("#askFacts").innerHTML = "";
  document.querySelector("#askVerify").textContent = "";

  // 델타가 네트워크 조각 단위(단어/문장)로 오더라도 화면엔 한 글자씩 흘러나오게 큐에 쌓아 타이핑한다
  let typeQueue = "";
  const typeTimer = setInterval(() => {
    if (myGen !== askGen) { clearInterval(typeTimer); return; }
    if (!typeQueue) return;
    answerEl.textContent += typeQueue[0];
    typeQueue = typeQueue.slice(1);
  }, 20);

  const petId = (selectedCustomer.pets || [])[0]?.pet_id ?? null;

  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ user_query: question, pet_id: petId, user_id: selectedCustomer.user_id }),
  });
  if (res.status === 401) { showLoginGate(); return; }
  if (!res.body) { errorEl.textContent = "응답을 받지 못했습니다."; return; }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    if (myGen !== askGen) { reader.cancel(); return; } // 그 사이 새 질문이 시작됐으면 이 스트림은 그만 읽는다
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const chunk = JSON.parse(line);
        if (chunk.type === "customer_facts") {
          document.querySelector("#askFacts").innerHTML =
            `<div class="section-title" style="font-size:12px;margin-top:12px;">실제 구매 이력 (답변 검증 기준)</div>` +
            `<div class="review-text" style="white-space:pre-wrap;">${chunk.text}</div>`;
        }
        else if (chunk.type === "verification") {
          const pct = Math.round(chunk.accuracy * 100);
          document.querySelector("#askVerify").innerHTML =
            `반증 결과 · 정확도 ${pct}% — ${chunk.note}`;
        }
        else if (chunk.type === "sources") renderSources(chunk.sources);
        else if (chunk.type === "delta") typeQueue += chunk.text;
        else if (chunk.type === "error") errorEl.textContent = chunk.message;
      } catch { /* 깨진 줄 하나 때문에 전체를 멈추지 않는다 */ }
    }
  }

  // 큐에 남은 글자를 마저 흘려보낸 뒤 타이머를 정리한다
  const drain = setInterval(() => {
    if (myGen !== askGen || !typeQueue) {
      clearInterval(typeTimer);
      clearInterval(drain);
    }
  }, 20);
};

// 질문 기준 임베딩 검색 결과 (candidates() 가 찾은, 이 고객 프로필 조건에 맞는 유사 리뷰)
const renderSources = (sources) => {
  const sourcesEl = document.querySelector("#askSources");
  if (!sources.length) return;
  sourcesEl.innerHTML = `<div class="section-title" style="font-size:13px;margin-top:16px;">질문 기준 임베딩 검색 결과</div>` +
    sources.slice(0, 3).map((s) => `
      <div class="ai-block">
        <h3><span class="dot"></span>${s.name} (${s.brand}) · 유사도 ${s.score.toFixed(3)}</h3>
        <div class="review-text">${s.review}</div>
      </div>`).join("");
};

// 새로고침해도 로그인 상태 유지 (모든 함수 선언이 끝난 뒤에 실행해야 함)
// 토큰이 만료됐으면 getCustomers()가 401을 받아 자동으로 로그인 화면으로 돌려보낸다
if (adminToken) enterAdmin();
