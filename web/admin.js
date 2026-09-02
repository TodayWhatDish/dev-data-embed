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
      return `
        <tr>
          <td>${(p.purchased_at || "").slice(0, 10)}</td>
          <td>${p.product_name}</td>
          <td>${p.quantity}개</td>
          <td>${p.unit_price_krw.toLocaleString()}원</td>
          <td>${ratingBadge}</td>
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

    <div class="section-title">구매 이력</div>
    <table class="purchases">
      <thead>
        <tr><th>날짜</th><th>상품</th><th>수량</th><th>금액</th><th>후기</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="5">구매 이력이 없습니다.</td></tr>`}</tbody>
    </table>
  `;
};

// ==================================
//  AI 분석 패널 (슬라이드오버)
//  ※ 지금은 실제 LLM 호출 없이 구매이력 기반으로 로컬에서 만든 임시 문구.
//    나중에 이 buildAiContent() 자리를 백엔드 LLM 호출로 교체하면 됨.
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
  aiPanelBody.innerHTML = `<div class="ai-loading"><div class="spinner"></div>분석 중...</div>`;

  setTimeout(() => {
    aiPanelBody.innerHTML = buildAiContent(selectedCustomer);
  }, 700);
};

const closeAiPanel = () => {
  overlay.classList.remove("open");
  aiPanel.classList.remove("open");
};

const buildAiContent = (c) => {
  const purchases = c.purchases || [];
  const rated = purchases.filter((p) => p.rating != null);
  const avgRating = rated.length
    ? (rated.reduce((s, p) => s + p.rating, 0) / rated.length).toFixed(1)
    : null;
  const hasFood = purchases.some((p) => p.product_name.includes("사료"));
  const hasSnack = purchases.some((p) => p.product_name.includes("간식") || p.product_name.includes("트릿"));
  const noReviewCount = purchases.length - rated.length;

  const sales = [];
  if (hasSnack && !hasFood) sales.push("간식 위주 구매 고객 - 사료 카테고리 교차 판매를 제안해볼 것");
  if (hasFood && !hasSnack) sales.push("사료만 구매 중 - 간식/영양제 추가 구매 유도 가능성 있음");
  if (purchases.length >= 3) sales.push("구매 빈도가 높은 편 - 정기구독(구독형 배송) 전환 제안 고려");
  if (sales.length === 0) sales.push("구매 이력이 적어 아직 뚜렷한 패턴 없음 - 첫 구매 후속 안내 필요");

  const marketing = [];
  marketing.push(`${(c.pets || [])[0]?.name ?? "반려동물"} 이름을 넣은 맞춤 안내 메시지 발송`);
  if (avgRating && avgRating >= 4) marketing.push("만족도가 높은 고객 - 리뷰 작성 리워드/추천인 이벤트 안내 적합");
  if (!avgRating) marketing.push("아직 남긴 후기가 없음 - 후기 작성 유도 쿠폰 제안");

  const cs = [];
  if (avgRating && avgRating < 3) cs.push("평균 별점이 낮음 - CS 우선 대응 및 만족도 확인 연락 권장");
  if (noReviewCount > 0) cs.push(`후기 미작성 구매 ${noReviewCount}건 - 배송/제품 이슈 여부 확인 필요`);
  if (cs.length === 0) cs.push("특별한 CS 이슈 신호 없음 - 정기 안부 메시지 정도로 충분");

  const block = (title, items) => `
    <div class="ai-block">
      <h3><span class="dot"></span>${title}</h3>
      <ul>${items.map((t) => `<li>${t}</li>`).join("")}</ul>
    </div>`;

  return (
    block("판매 전략", sales) +
    block("마케팅 아이디어", marketing) +
    block("CS 응대 전략", cs)
  );
};

// 새로고침해도 로그인 상태 유지 (모든 함수 선언이 끝난 뒤에 실행해야 함)
// 토큰이 만료됐으면 getCustomers()가 401을 받아 자동으로 로그인 화면으로 돌려보낸다
if (adminToken) enterAdmin();
