# -*- coding: utf-8 -*-
"""B28 아동수당·양육수당·장애아동양육·농어촌양육·영아수당  (A4 / order 5, 20변수)

소스 (등급순)
  S1 R05 2023 보건복지통계연보(2022 실적)  [1차확인 2026-09-02]
     <표 5-2-3> 아동수당 지급 현황(시도)      2022 수급자 2,767,534명 / 지급실적 3,206,925백만원
     <표 4-3-11> 가정양육수당 수급 아동(월령대·성·시도)  280,267명
     <표 4-3-12> 영아수당 수급 아동(성·시도)             219,524명
     <표 4-3-10> 영유아 보육료 수급 아동(반연령·성·시도) 1,071,789명  → 배타 배분 분모
  S4 법정단가 params/raw/S4_2022_사업별_법정단가_welfare.csv  [1차확인]
     아동수당 100,000 / 영아수당(현금) 300,000 /
     가정양육수당 200,000·150,000·100,000 / 농어촌 200,000~100,000 / 장애아동 200,000·100,000
     원문: 2022년 아동수당 사업안내 PDF p.29, 2022년 영아수당 사업안내 PDF p.16,
           2022년 보육사업안내 본문 인쇄 p.374
  S0 R01 <표 2-19> 정부통계와 사회보장행정데이터의 양육수당 수급률 비교 (2020) [1차확인 p.77]
     양육수당 99.3% : 장애아동양육수당 0.2% : 농어촌양육수당 0.5%
     → carebn_dischild·carebn_rural 규모 산정(§4 규모 미달 판정)
  S2 주민등록 인구통계 2022.11 (params/raw/POPUL_MOIS01_*) → 출생연도별 등록인구(분모)

정합성
  §7 R06 childbn ⇒ age<8      (연령 상한 강제)
  §7 R07 infantbn·carebn·childcare 배타 (tools/a4_child.assign 이 배타 배정)
  §7 R24 yn2⇒yn1, dur∈[1,12], amt>0 ⇔ yn1=1
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, a4_child

RAW = 'params/raw'

# ── 법정단가 [1차확인] S4_2022_사업별_법정단가_welfare.csv ──────────────────
def _unit_prices():
    d = pd.read_csv(os.path.join(RAW, 'S4_2022_사업별_법정단가_welfare.csv'))
    d['값'] = pd.to_numeric(d['값'], errors='coerce')

    def one(prog, item, gubun=None):
        m = d[(d['사업'] == prog) & (d['급여항목'] == item)]
        if gubun is not None:
            m = m[m['구분'] == gubun]
        return int(m['값'].iloc[0])
    return {
        'childbn': one('아동수당', '아동수당'),                       # 100,000
        'infantbn': one('영아수당', '영아수당(현금)'),                 # 300,000
    }


# ── 아동수당 지급 개월수 (2022) ─────────────────────────────────────────────
# [1차확인] 2022년 아동수당 사업안내 PDF p.17(변경사항): 만 8세 미만(0~95개월),
#   "만 8세 생일이 도래하는 달의 전 달까지", 2022.4월 확대분은 1~3월분 소급지급
#   (2022년 M월분은 2014년 (M+1)월 출생아까지 지급) → 연중 12개월 모두 지급 가능
def _childbn_months(year, bmonth):
    start = np.where(year >= 2022, bmonth, 1)
    end = np.where(year <= 2014, bmonth - 1, 12)          # 2014년생은 만8세 도달월 전월까지
    return np.clip(end - start + 1, 0, 12).astype(np.int16), end


def generate(df, params, ctx):
    g = core.rng('B28')
    n = len(df)
    up = _unit_prices()

    # 0) 배타 배분 (B30 이 _pre_prog 로 재사용) ------------------------------
    prog, bmonth, rates, reg, counts = a4_child.assign(df, g)
    age = df['age'].to_numpy()
    yr = df['year'].to_numpy()

    out = pd.DataFrame(index=df.index)
    out['_pre_prog'] = prog
    out['_bmonth'] = bmonth

    nan = np.full(n, np.nan)

    # 1) 아동수당 childbn — 만 8세 미만 (§7 R06) -----------------------------
    # 수급률 0.98 [논리적추론]: R05 <표 5-2-3> 연간 수급자 2,767,534명은 연중
    # 만8세 도달·이탈 아동을 포함한 누적치로 2022.11.1 기준 0~7세 등록인구
    # 2,663,836명을 초과한다. R06 준수를 위해 8세 유입분을 제외하고 0~7세
    # 신청주의 미신청분(약 2%)을 반영한 값.
    P_CHILDBN = 0.98
    elig_cb = (age < 8)
    hit = core.bernoulli(g, np.where(elig_cb, P_CHILDBN, 0.0)).astype(bool)
    dur_cb, end_cb = _childbn_months(yr, bmonth)
    hit = hit & (dur_cb > 0)
    out['childbn_yn1'] = np.where(elig_cb, hit.astype(float), np.nan)
    out['childbn_dur'] = np.where(hit, dur_cb, np.nan)
    out['childbn_yn2'] = np.where(hit, (end_cb >= 12).astype(float), np.nan)
    out['childbn_amt'] = np.where(hit, dur_cb.astype(np.int64) * up['childbn'], np.nan)
    # 추출대상(= 연간 1회 이상 수급 집단) 밖은 NaN
    out.loc[~hit, ['childbn_yn1', 'childbn_yn2', 'childbn_dur', 'childbn_amt']] = np.nan

    # 2) 영아수당(현금) infantbn — 2022년 출생아, 출생월부터 12월까지 --------
    m_inf = (prog == 'infant')
    dur_inf = np.clip(13 - bmonth, 1, 12).astype(np.int16)
    out['infantbn_yn1'] = np.where(m_inf, 1.0, np.nan)
    out['infantbn_yn2'] = np.where(m_inf, 1.0, np.nan)      # 2022년생은 12월에도 0~11개월
    out['infantbn_dur'] = np.where(m_inf, dur_inf, np.nan)
    out['infantbn_amt'] = np.where(m_inf, dur_inf.astype(np.int64) * up['infantbn'], np.nan)

    # 3) 가정양육수당 carebn — 월령별 단가 합산 ------------------------------
    m_car = (prog == 'care')
    amt_car = np.zeros(n, dtype=np.int64)
    dur_car = np.zeros(n, dtype=np.int16)
    dec_ok = np.zeros(n, dtype=bool)
    for t in range(1, 13):
        w = a4_child.care_monthly_won(yr, bmonth, t)
        amt_car += np.where(m_car, w, 0)
        dur_car += np.where(m_car & (w > 0), 1, 0).astype(np.int16)
        if t == 12:
            dec_ok = m_car & (w > 0)
    ok_car = m_car & (dur_car > 0)
    out['carebn_yn1'] = np.where(ok_car, 1.0, np.nan)
    out['carebn_yn2'] = np.where(ok_car, dec_ok.astype(float), np.nan)
    out['carebn_dur'] = np.where(ok_car, dur_car, np.nan)
    out['carebn_amt'] = np.where(ok_car, amt_car, np.nan)

    # 4) 장애아동 양육수당 / 농어촌 양육수당 — 규모 미달 → 전량 NaN ---------
    #    R01 <표 2-19>[1차확인]: 양육수당 구성비 일반 99.3% / 장애아동 0.2% / 농어촌 0.5%
    #    → 2022년 R05 가정양육수당 280,267명 기준 장애아동 ≈ 564명, 농어촌 ≈ 1,411명.
    #    표본 추출률(표본인원/주민등록인구 ≈ 1.85e-4) 적용 시 기대 수급자
    #    각각 0.10명 · 0.26명 (< 3명) → §4 규모 미달 규칙에 따라 전량 NaN.
    for v in ('carebn_dischild', 'carebn_rural'):
        for s in ('yn1', 'yn2', 'dur', 'amt'):
            out[f'{v}_{s}'] = nan

    # 5) 정합성 강제 ---------------------------------------------------------
    for pre in ('childbn', 'infantbn', 'carebn'):
        y1, y2 = out[f'{pre}_yn1'], out[f'{pre}_yn2']
        out.loc[(y2 == 1) & (y1 != 1), f'{pre}_yn2'] = 0.0            # R24 yn2⇒yn1
        d = out[f'{pre}_dur']
        out.loc[d.notna(), f'{pre}_dur'] = d[d.notna()].clip(1, 12)   # R24 dur∈[1,12]
        out[f'{pre}_amt'] = out[f'{pre}_amt'].round(-3)               # 코드북: 천원 라운딩

    for c in ('childbn_dur', 'carebn_dur', 'infantbn_dur'):
        out[c] = out[c].astype('Float64').astype(float)
    for c in ('childbn_amt', 'carebn_amt', 'infantbn_amt'):
        out[c] = np.where(out[c].notna(), out[c].fillna(0).astype('int64'), np.nan)

    # 6) 진단 로그 -----------------------------------------------------------
    if 'indwgt' in df.columns:
        w = df['indwgt'].to_numpy()
        ctx.setdefault('B28_report', {})
        ctx['B28_report'] = {
            'childbn_N': float(np.nansum(w * (out['childbn_yn1'] == 1))),
            'childbn_amt_백만원': float(np.nansum(w * out['childbn_amt'].fillna(0)) / 1e6),
            'infantbn_N': float(np.nansum(w * (out['infantbn_yn1'] == 1))),
            'carebn_N': float(np.nansum(w * (out['carebn_yn1'] == 1))),
            'childcare_N(배정)': float(np.nansum(w * (prog == 'childcare'))),
            'rates': rates,
        }
    return out
