// 자연어 명령 창 — OpenStat Studio 화면에 덧붙이는 별도 스크립트(원본 index.html 은 고치지 않는다).
// 질문을 /api/nl/run 으로 보내고, 돌아온 결과 카드를 기존 결과 시트에 그대로 추가한다(applyRunPayload).
(function () {
  "use strict";
  const HIDE = ["rb-sem", "rb-mixture", "rb-medmod", "rb-factor", "rb-linearmodels", "rb-timeseries", "rb-survival", "rb-text", "rb-network"]; // 이 시제품에서 쓰지 않는 메뉴
  const BAYES = ["bayesTTestIS", "bayesANOVA", "bayesCorr"];

  function css() {
    const st = document.createElement("style");
    st.textContent = `
#nl-panel { flex: 0 0 auto; background: #F3F7FB; border-bottom: 1px solid #CBD5E1; padding: 10px 14px 9px; }
#nl-panel .nl-row { display: flex; align-items: center; gap: 8px; }
#nl-panel .nl-label { flex: 0 0 auto; font-weight: 700; font-size: 13px; color: #1E3A5F; white-space: nowrap; }
#nl-panel .nl-label small { display: block; font-weight: 500; font-size: 10.5px; color: #64748B; }
#nl-input { flex: 1 1 auto; min-width: 0; height: 36px; padding: 0 12px; font-size: 14px; border: 1.5px solid #1E3A5F; border-radius: 6px; outline: none; background: #FFFFFF; color: #1F2937; }
#nl-input:focus { border-color: #0D9488; box-shadow: 0 0 0 3px rgba(13,148,136,.15); }
#nl-run { flex: 0 0 auto; height: 36px; padding: 0 18px; font-size: 13.5px; font-weight: 700; color: #FFFFFF; background: #1E3A5F; border: 0; border-radius: 6px; cursor: pointer; }
#nl-run:disabled { background: #94A3B8; cursor: default; }
#nl-panel .nl-sub { display: flex; align-items: center; gap: 6px; margin-top: 7px; flex-wrap: wrap; font-size: 11.5px; color: #475569; }
#nl-panel .nl-chip { padding: 3px 9px; border: 1px solid #94A3B8; border-radius: 999px; background: #FFFFFF; color: #1E3A5F; font-size: 11.5px; cursor: pointer; }
#nl-panel .nl-chip:hover { border-color: #0D9488; color: #0F766E; }
#nl-status { margin-left: auto; font-size: 11.5px; color: #0F766E; white-space: nowrap; }
#nl-status.err { color: #B91C1C; }`;
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

  function build(info) {
    const pane = document.getElementById("results-pane");
    const bar = pane && pane.querySelector(".right-pane-subbar");
    if (!bar || document.getElementById("nl-panel")) return;
    const el = document.createElement("div");
    el.id = "nl-panel";
    el.addEventListener("click", (e) => e.stopPropagation());
    const chips = (info.examples || []).map((x, i) => `<button class="nl-chip" data-i="${i}" title="${x.q.replace(/"/g, "&quot;")}">${x.kind}</button>`).join("");
    el.innerHTML = `
      <div class="nl-row">
        <div class="nl-label">자연어 명령<small>말로 요청 → 집계표·그림</small></div>
        <input id="nl-input" type="text" autocomplete="off" placeholder="예: 65세 이상 기초연금 수급률을 연령 구간별 표로 / 소득 분위별 에너지바우처 이용률 막대그래프">
        <button id="nl-run">실행</button>
      </div>
      <div class="nl-sub"><span>예시</span>${chips}<span id="nl-status"></span></div>`;
    bar.insertAdjacentElement("afterend", el);
    const input = el.querySelector("#nl-input"), btn = el.querySelector("#nl-run"), status = el.querySelector("#nl-status");
    const base = (info.mode === "live" ? "언어모형 서버 연결" : "언어모형 응답: 평가 기록 재생") + " · 분석 함수의 출력 통제 적용";
    status.textContent = base;
    el.querySelectorAll(".nl-chip").forEach((c) => c.addEventListener("click", () => { input.value = info.examples[+c.dataset.i].q; input.focus(); }));
    async function run() {
      const q = input.value.trim();
      if (!q || btn.disabled) return;
      btn.disabled = true; status.className = ""; status.textContent = "처리 중 — 질문 해석 → 코드 작성 → 실행 전 점검 → 격리 실행 → 출력 통제";
      try {
        const r = await fetch("/api/nl/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
        const p = await r.json();
        if (p.status !== "success") throw new Error(p.message || p.detail || "처리하지 못함");
        if (typeof switchRightView === "function") switchRightView("results");
        applyRunPayload(p);
        status.textContent = (p.nl && p.nl.executed ? "산출 완료" : "응답 완료(산출 없음)") + ` · 모형 호출 ${p.nl ? p.nl.n_calls : "-"}회 · ${p.nl ? p.nl.elapsed_sec : "-"}초 · ` + base;
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
    let info = { mode: "replay", examples: [] };
    try { info = await (await fetch("/api/nl/info")).json(); } catch (e) { /* 정보 없이 진행 */ }
    build(info);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
