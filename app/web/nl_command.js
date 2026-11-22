// 자연어 명령 창 — OpenStat Studio 화면에 덧붙이는 별도 스크립트(원본 index.html 은 고치지 않는다).
// 원본 시제품(demo/web/nl_command.js)에 Gemini API 키 입력란과 대시보드 연결을 더한 판.
// 질문을 /api/nl/run 으로 보내고, 돌아온 결과 카드를 기존 결과 시트에 그대로 추가한다(applyRunPayload).
// 키는 이 서버(127.0.0.1)의 메모리에만 전달·보관되며 브라우저 저장소에는 남기지 않는다.
(function () {
  "use strict";
  const HIDE = ["rb-sem", "rb-mixture", "rb-medmod", "rb-factor", "rb-linearmodels", "rb-timeseries", "rb-survival", "rb-text", "rb-network"]; // 쓰지 않는 메뉴
  const BAYES = ["bayesTTestIS", "bayesANOVA", "bayesCorr"];
  const STEPS = "질문 해석 → 코드 작성 → 실행 전 점검 → 격리 실행 → 출력 통제";

  function css() {
    const st = document.createElement("style");
    st.textContent = `
#nl-panel { flex: 0 0 auto; background: #F3F7FB; border-bottom: 1px solid #CBD5E1; padding: 10px 14px 9px; }
#nl-panel .nl-row { display: flex; align-items: center; gap: 8px; }
#nl-panel .nl-label { flex: 0 0 auto; font-weight: 700; font-size: 13px; color: #1E3A5F; white-space: nowrap; }
#nl-panel .nl-label small { display: block; font-weight: 500; font-size: 10.5px; color: #64748B; }
#nl-panel input[type=text], #nl-panel input[type=password] { min-width: 0; height: 36px; padding: 0 12px; font-size: 14px; border: 1.5px solid #1E3A5F; border-radius: 6px; outline: none; background: #FFFFFF; color: #1F2937; }
#nl-input { flex: 1 1 auto; }
#nl-panel input:focus { border-color: #0D9488; box-shadow: 0 0 0 3px rgba(13,148,136,.15); }
#nl-panel button.nl-main { flex: 0 0 auto; height: 36px; padding: 0 18px; font-size: 13.5px; font-weight: 700; color: #FFFFFF; background: #1E3A5F; border: 0; border-radius: 6px; cursor: pointer; }
#nl-panel button.nl-main:disabled { background: #94A3B8; cursor: default; }
#nl-panel .nl-sub { display: flex; align-items: center; gap: 6px; margin-top: 7px; flex-wrap: wrap; font-size: 11.5px; color: #475569; }
#nl-panel .nl-chip { padding: 3px 9px; border: 1px solid #94A3B8; border-radius: 999px; background: #FFFFFF; color: #1E3A5F; font-size: 11.5px; cursor: pointer; text-decoration: none; }
#nl-panel .nl-chip:hover { border-color: #0D9488; color: #0F766E; }
#nl-status { margin-left: auto; font-size: 11.5px; color: #0F766E; }
#nl-status.err { color: #B91C1C; }
#nl-keybox { display: none; margin-top: 8px; padding: 8px 10px; background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; }
#nl-keybox.open { display: block; }
#nl-keybox p { margin: 6px 0 0; font-size: 11px; color: #64748B; line-height: 1.5; }
#nl-key { flex: 1 1 auto; }
#nl-model { height: 32px; min-width: 260px; padding: 0 8px; font-size: 13px; border: 1.5px solid #1E3A5F; border-radius: 6px; background: #FFFFFF; color: #1F2937; }`;
    document.head.appendChild(st);
  }

  function trimMenus() {
    HIDE.forEach((id) => { const el = document.getElementById(id); if (el) el.style.display = "none"; });
    try {
      for (const lang of ["ko", "en"]) {
        const M = RIBBON_MENUS_I18N[lang];
        for (const k of Object.keys(M)) if (Array.isArray(M[k])) M[k] = M[k].filter((it) => !BAYES.includes(it.id));
      }
    } catch (e) { /* 메뉴 정의가 바뀐 판 */ }
  }

  async function api(url, method, body) {
    const r = await fetch(url, { method: method || "GET", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    return r.json();
  }

  function build(info) {
    const pane = document.getElementById("results-pane");
    const bar = pane && pane.querySelector(".right-pane-subbar");
    if (!bar || document.getElementById("nl-panel")) return;
    const el = document.createElement("div");
    el.id = "nl-panel";
    el.addEventListener("click", (e) => e.stopPropagation());
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    const chips = (info.examples || []).map((x, i) => `<button class="nl-chip" data-i="${i}" title="${esc(x.q)}">${esc(x.kind)}</button>`).join("");
    el.innerHTML = `
      <div class="nl-row">
        <div class="nl-label">자연어 명령<small>말로 요청 → 집계표·그림</small></div>
        <input id="nl-input" type="text" autocomplete="off" placeholder="예: 65세 이상 기초연금 수급률을 연령 구간별 표로 / 소득 분위별 에너지바우처 이용률 막대그래프">
        <button id="nl-run" class="nl-main">실행</button>
      </div>
      <div class="nl-sub"><span>예시</span>${chips}
        <button class="nl-chip" id="nl-key-toggle">API 키</button>
        <a class="nl-chip" href="/dashboard" target="_blank" rel="noopener">정책 대시보드</a>
        <span id="nl-status"></span></div>
      <div id="nl-keybox">
        <div class="nl-row">
          <input id="nl-key" type="password" autocomplete="off" placeholder="Gemini API 키">
          <button id="nl-key-save" class="nl-main">등록</button>
          <button id="nl-key-clear" class="nl-chip">키 지우기</button>
        </div>
        <div class="nl-row" style="margin-top:8px">
          <div class="nl-label" style="font-size:12px">모형</div>
          <select id="nl-model"></select>
          <span id="nl-model-note" style="font-size:11px;color:#64748B"></span>
        </div>
        <p>키는 이 컴퓨터에서 실행 중인 서버의 메모리에만 보관되며 서버를 끄면 사라진다. Google 로 전송되는 것은 질문, 변수 설명, 출력 통제를 거친 집계 결과이며 개인 단위 자료는 전송되지 않는다. 키 발급: aistudio.google.com/app/apikey</p>
      </div>`;
    bar.insertAdjacentElement("afterend", el);
    const $ = (s) => el.querySelector(s);
    const input = $("#nl-input"), btn = $("#nl-run"), status = $("#nl-status"), keybox = $("#nl-keybox"), keyIn = $("#nl-key");

    const modelSel = $("#nl-model"), modelNote = $("#nl-model-note");
    function showModels(st) {
      const list = st.models || [];
      modelSel.innerHTML = "";
      const auto = document.createElement("option");
      auto.value = ""; auto.textContent = "자동 선택(목록 순서대로, 한도 초과 시 다음 모형)";
      modelSel.appendChild(auto);
      list.forEach((m) => { const o = document.createElement("option"); o.value = m; o.textContent = m; modelSel.appendChild(o); });
      modelSel.value = st.selected || "";
      modelSel.disabled = !st.has_key;
      modelNote.textContent = st.has_key ? (list.length ? `이 키로 쓸 수 있는 모형 ${list.length}개` : "모형 목록을 받지 못함(자동 선택으로 동작)") : "키를 등록하면 목록이 나타남";
    }
    modelSel.addEventListener("change", async () => {
      try {
        const r = await api("/api/nl/model", "POST", { model: modelSel.value });
        if (r.status !== "success") throw new Error(r.message || "바꾸지 못함");
        showState(r);
      } catch (e) { status.className = "err"; status.textContent = "오류: " + e.message; }
    });

    function showState(st) {
      showModels(st);
      status.className = st.ready ? "" : "err";
      status.textContent = st.ready ? `Gemini API 연결(${st.model}) · 분석 함수의 출력 통제 적용` : "준비 안 됨: " + (st.missing || []).join(" / ");
      if (!st.has_key) keybox.classList.add("open");
    }
    showState(info);
    el.querySelectorAll(".nl-chip[data-i]").forEach((c) => c.addEventListener("click", () => { input.value = info.examples[+c.dataset.i].q; input.focus(); }));
    $("#nl-key-toggle").addEventListener("click", () => keybox.classList.toggle("open"));
    $("#nl-key-save").addEventListener("click", async () => {
      const k = keyIn.value.trim();
      if (!k) return;
      status.className = ""; status.textContent = "키 확인 중";
      try {
        const r = await api("/api/nl/key", "POST", { key: k });
        keyIn.value = "";
        if (r.status !== "success") throw new Error(r.message || "등록하지 못함");
        keybox.classList.remove("open"); showState(r);
      } catch (e) { status.className = "err"; status.textContent = "오류: " + e.message; }
    });
    $("#nl-key-clear").addEventListener("click", async () => { keyIn.value = ""; showState(await api("/api/nl/key", "DELETE")); });

    async function run() {
      const q = input.value.trim();
      if (!q || btn.disabled) return;
      btn.disabled = true; status.className = ""; status.textContent = "처리 중 — " + STEPS;
      try {
        const p = await api("/api/nl/run", "POST", { question: q });
        if (p.status !== "success") throw new Error(p.message || p.detail || "처리하지 못함");
        if (typeof switchRightView === "function") switchRightView("results");
        applyRunPayload(p);
        const n = p.nl || {};
        status.textContent = (n.executed ? "산출 완료" : "응답 완료(산출 없음)") + ` · 모형 호출 ${n.n_calls ?? "-"}회 · ${n.elapsed_sec ?? "-"}초 · Gemini API(${n.model || "-"})`;
        setTimeout(() => { const cards = document.querySelectorAll(".jmv-results-sheet"); if (cards.length) cards[cards.length - 1].scrollIntoView({ block: "start" }); }, 150);
      } catch (e) {
        status.className = "err"; status.textContent = "오류: " + e.message;
      } finally { btn.disabled = false; }
    }
    btn.addEventListener("click", run);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
    window.NL = { run, input };
  }

  async function init() {
    css(); trimMenus();
    let info = { ready: false, missing: ["서버 정보를 받지 못함"], examples: [] };
    try { info = await api("/api/nl/info"); } catch (e) { /* 정보 없이 진행 */ }
    build(info);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
