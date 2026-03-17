"""
PDF 파서: MIDAS Gen + BeST.RC/BeST.Steel 구조계산서에서 부재 데이터 추출

지원 형식:
  - MIDAS Gen RC Beam Strength Checking Result
  - MIDAS Gen RC Column Checking Result
  - BeST.RC (보)
  - BeST.Steel (기둥)
"""
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BeamResult:
    member: str = ""
    source: str = ""           # "MIDAS Gen" | "BeST.RC"
    span_m: Optional[float] = None   # m
    fck: Optional[float] = None      # MPa
    fy: Optional[float] = None       # MPa
    fys: Optional[float] = None      # MPa
    B_mm: Optional[float] = None     # mm (웹 폭 또는 직사각형 폭)
    H_mm: Optional[float] = None     # mm (전체 높이)
    # (-) 부 모멘트: (END-I, MID, END-J), kN·m
    Mu_neg: Optional[tuple] = None
    Mu_neg_lc: Optional[tuple] = None  # 지배 하중조합 번호
    # (+) 정 모멘트
    Mu_pos: Optional[tuple] = None
    Mu_pos_lc: Optional[tuple] = None
    # 전단
    Vu: Optional[tuple] = None        # kN (END-I, MID, END-J)
    Vu_lc: Optional[tuple] = None

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ColumnResult:
    member: str = ""
    source: str = ""           # "MIDAS Gen" | "BeST.Steel"
    height_m: Optional[float] = None  # m (KLu)
    fck: Optional[float] = None
    fy: Optional[float] = None
    Cx_mm: Optional[float] = None
    Cy_mm: Optional[float] = None
    Pu_kN: Optional[float] = None
    Mux_kNm: Optional[float] = None
    Muy_kNm: Optional[float] = None
    lc: Optional[str] = None

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# 정규식 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _f(pattern, text, group=1, flags=re.IGNORECASE):
    """패턴 첫 매치의 group 반환 (없으면 None)"""
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


def _float(s):
    """문자열 → float, 실패 시 None"""
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _three_floats(pattern, text):
    """패턴 뒤에 숫자 3개가 오는 경우 (END-I MID END-J)"""
    m = re.search(pattern + r'\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', text)
    if m:
        return (_float(m.group(1)), _float(m.group(2)), _float(m.group(3)))
    return None


def _three_ints(pattern, text):
    """패턴 뒤에 정수 3개"""
    m = re.search(pattern + r'\s+(\d+)\s+(\d+)\s+(\d+)', text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 페이지 파서 (형식별)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_midas_beam(text: str) -> BeamResult:
    """MIDAS Gen RC Beam Strength Checking Result 파싱"""
    r = BeamResult(source="MIDAS Gen")

    # 부재명 + 스팬
    m = re.search(r'Section Property\s+(\S+)\s+\(No\s*:\s*\d+\)\s+Beam Span\s+([\d.]+)m', text)
    if m:
        r.member = m.group(1)
        r.span_m = _float(m.group(2))

    # 재료 (단위: KPa → MPa: /1000)
    fck_raw = _f(r'fck\s*=\s*([\d.]+)', text)
    fy_raw  = _f(r'fy\s*=\s*([\d.]+)',  text)
    fys_raw = _f(r'fys\s*=\s*([\d.]+)', text)
    if fck_raw: r.fck  = _float(fck_raw) / 1000.0
    if fy_raw:  r.fy   = _float(fy_raw)  / 1000.0
    if fys_raw: r.fys  = _float(fys_raw) / 1000.0

    # (-) 부 모멘트 하중조합 + Mu
    neg_lc = _three_ints(r'\(-\)\s+Load Combination No\.', text)
    neg_mu = _three_floats(r'(?<!\+\))\s*Moment \(Mu\)', text)
    if neg_lc: r.Mu_neg_lc = neg_lc
    if neg_mu: r.Mu_neg    = neg_mu

    # (+) 정 모멘트 — 두 번째 "Load Combination No."와 두 번째 "Moment (Mu)"
    pos_blocks = re.findall(
        r'\(\+\)\s+Load Combination No\.\s+(\d+)\s+(\d+)\s+(\d+)\s+'
        r'Moment \(Mu\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
        text
    )
    if pos_blocks:
        g = pos_blocks[0]
        r.Mu_pos_lc = (int(g[0]), int(g[1]), int(g[2]))
        r.Mu_pos    = (_float(g[3]), _float(g[4]), _float(g[5]))

    # 전단
    shear_lc = _three_ints(r'(?:3\.\s+Shear Capacity\s+)?(?:END-I\s+MID\s+END-J\s+)?Load Combination No\.', text)
    # 전단 하중조합은 페이지에서 세 번째 "Load Combination No." 라인
    lc_matches = re.findall(r'Load Combination No\.\s+(\d+)\s+(\d+)\s+(\d+)', text)
    if len(lc_matches) >= 3:
        g = lc_matches[2]
        r.Vu_lc = (int(g[0]), int(g[1]), int(g[2]))

    vu_m = re.search(r'Factored Shear Force \(Vu\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', text)
    if vu_m:
        r.Vu = (_float(vu_m.group(1)), _float(vu_m.group(2)), _float(vu_m.group(3)))

    return r


def _parse_midas_column(text: str) -> ColumnResult:
    """MIDAS Gen RC Column Checking Result 파싱"""
    r = ColumnResult(source="MIDAS Gen")

    # 부재명
    m = re.search(r'Section Property\s*:\s*(\S+)', text)
    if m: r.member = m.group(1)

    # 기둥 높이
    h = _f(r'Column Height\s*:\s*([\d.]+)\s*m', text)
    if h: r.height_m = _float(h)

    # 재료 (KPa → MPa)
    fck_raw = _f(r'fck\s*=\s*([\d.]+)', text)
    fy_raw  = _f(r'fy\s*=\s*([\d.]+)',  text)
    if fck_raw: r.fck = _float(fck_raw) / 1000.0
    if fy_raw:  r.fy  = _float(fy_raw)  / 1000.0

    # 지배 하중조합
    lc = _f(r'Load Combination\s*:\s*(\d+)', text)
    if lc: r.lc = lc

    # 단면 치수 — MIDAS Gen 기둥 페이지 내 P-M 상관도 좌측에 mm 단위로 표기
    # "Section Property : PC1 (No : 1)" 아래에 단면 크기가 없으면 None 유지
    # P-M table 앞 숫자에서 시도
    sec_m = re.search(r'(\d+)\s*\n\s*(\d+)\s*\n.*?midas Gen RC Column', text, re.DOTALL)
    if sec_m:
        # 첫 두 숫자가 단면 크기일 가능성 있으나 신뢰도 낮으므로 스킵
        pass

    # Pu (Axial Load Ratio 라인에서 분자)
    pu = _f(r'Pu\s*/\s*φPn\s*=\s*([\d.]+)', text)
    if pu: r.Pu_kN = _float(pu)

    # Mc (combined moment) — Mcz, Mcy 분리 추출
    mcz = _f(r'Mcz\s*/\s*φMnz\s*=\s*([\d.]+)', text)
    mcy = _f(r'Mcy\s*/\s*φMny\s*=\s*([\d.]+)', text)
    if mcy: r.Mux_kNm = _float(mcy)
    if mcz: r.Muy_kNm = _float(mcz)

    return r


def _parse_best_rc_beam(text: str) -> BeamResult:
    """BeST.RC 보 계산서 파싱"""
    r = BeamResult(source="BeST.RC")

    # 부재명
    m = re.search(r'MEMBER\s*[:：]\s*(\S+)', text)
    if m: r.member = m.group(1)

    # 재료
    fck = _f(r'f\s*(?:ck)?\s*=\s*([\d.]+)\s*N/mm2', text)
    fy  = _f(r'f\s*y\s*=\s*([\d.]+)', text)
    fys = _f(r'f\s*ys\s*=\s*([\d.]+)', text)
    if fck: r.fck  = _float(fck)
    if fy:  r.fy   = _float(fy)
    if fys: r.fys  = _float(fys)

    # 재료 한 줄 파싱: "f = 500, f = 400 N/mm2"
    mat_line = re.search(r'f\s*=\s*([\d.]+)\s*,\s*f\s*=\s*([\d.]+)\s*N/mm2', text)
    if mat_line and not r.fy:
        r.fy  = _float(mat_line.group(1))
        r.fys = _float(mat_line.group(2))

    # 단면 (직사각형): "B = 250 mm H = 250 mm"
    sec = re.search(r'B\s*=\s*([\d.]+)\s*mm\s+H\s*=\s*([\d.]+)\s*mm', text)
    if sec:
        r.B_mm = _float(sec.group(1))
        r.H_mm = _float(sec.group(2))

    # T형 단면 하부 폭/높이 (bot): "B = 250 mm H = 200 mm bot"
    bot_sec = re.search(r'B\s*=\s*([\d.]+)\s*mm\s+H\s*=\s*([\d.]+)\s*mm\s+bot', text, re.IGNORECASE)
    if bot_sec:
        r.B_mm = _float(bot_sec.group(1))
        r.H_mm = _float(bot_sec.group(2))

    # 설계력: "M = -69.0 kN·m"
    mu = _f(r'M\s*u?\s*=\s*(-?[\d.]+)\s*kN', text)
    if mu:
        val = _float(mu)
        r.Mu_neg = (val, val, val)  # BeST.RC는 단일 대표값

    # 전단: "V = 48.0 kN"
    vu = _f(r'V\s*u?\s*=\s*([\d.]+)\s*kN', text)
    if vu:
        val = _float(vu)
        r.Vu = (val, val, val)

    return r


def _parse_best_steel_column(text: str) -> ColumnResult:
    """BeST.Steel 기둥(SRC) 계산서 파싱"""
    r = ColumnResult(source="BeST.Steel")

    # 부재명
    m = re.search(r'MEMBER\s*[:：]\s*(\S+)', text)
    if m: r.member = m.group(1)

    # 재료
    fck = _f(r'f\s*(?:ck)?\s*=\s*([\d.]+)\s*N/mm2', text)
    if fck: r.fck = _float(fck)

    # 단면: "C = 250 mm C = 250 mm"
    sec = re.search(r'C\s*(?:x)?\s*=\s*([\d.]+)\s*mm\s+C\s*(?:y)?\s*=\s*([\d.]+)\s*mm', text, re.IGNORECASE)
    if sec:
        r.Cx_mm = _float(sec.group(1))
        r.Cy_mm = _float(sec.group(2))

    # 기둥 높이: "KL = 3.06 m"
    klu = _f(r'KL\s*u?\s*=\s*([\d.]+)\s*m', text)
    if klu: r.height_m = _float(klu)

    # 축력: "P = 286.6 kN"
    pu = _f(r'P\s*u?\s*=\s*([\d.]+)\s*kN', text)
    if pu: r.Pu_kN = _float(pu)

    # 모멘트: "M = 33.5, M = 103.5 kN·m"
    mom = re.search(r'M\s*(?:ux)?\s*=\s*([\d.]+)\s*,\s*M\s*(?:uy)?\s*=\s*([\d.]+)\s*kN', text)
    if mom:
        r.Mux_kNm = _float(mom.group(1))
        r.Muy_kNm = _float(mom.group(2))

    return r


# ─────────────────────────────────────────────────────────────────────────────
# 페이지 분류
# ─────────────────────────────────────────────────────────────────────────────

def _classify_page(text: str) -> str:
    """페이지 텍스트 → 형식 식별자"""
    if 'midas Gen RC Beam Strength Checking Result' in text:
        return 'midas_beam'
    if 'midas Gen RC Column Checking Result' in text:
        return 'midas_column'
    if 'BeST.Steel' in text and 'MEMBER' in text:
        return 'best_steel'
    if 'BeST.RC' in text and 'MEMBER' in text:
        if 'Slab Dim.' in text or 'Slab Thk' in text or 'Applied Loads' in text:
            return 'best_slab'   # 슬래브/기초 (현재 미사용)
        return 'best_rc_beam'
    return 'unknown'


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str) -> dict:
    """
    PDF 파일에서 구조 부재 데이터를 추출.

    반환:
        {
          "beams":   [BeamResult, ...],
          "columns": [ColumnResult, ...],
          "pages_parsed": int,
          "pages_total":  int,
        }
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber가 설치되지 않았습니다: pip install pdfplumber")

    beams: list[BeamResult]    = []
    columns: list[ColumnResult] = []
    pages_parsed = 0

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            kind = _classify_page(text)
            if kind == 'midas_beam':
                beams.append(_parse_midas_beam(text))
                pages_parsed += 1
            elif kind == 'midas_column':
                columns.append(_parse_midas_column(text))
                pages_parsed += 1
            elif kind == 'best_rc_beam':
                beams.append(_parse_best_rc_beam(text))
                pages_parsed += 1
            elif kind == 'best_steel':
                columns.append(_parse_best_steel_column(text))
                pages_parsed += 1

    # BeST.RC 데이터를 MIDAS Gen 데이터와 병합 (같은 부재명 기준)
    _merge_beam_data(beams)
    _merge_column_data(columns)

    # 중복 제거: MIDAS Gen + BeST.RC가 같은 부재명이면 하나만
    beams   = _deduplicate(beams,   prefer="MIDAS Gen")
    columns = _deduplicate(columns, prefer="MIDAS Gen")

    return {
        "beams":        beams,
        "columns":      columns,
        "pages_parsed": pages_parsed,
        "pages_total":  total,
    }


def _merge_beam_data(beams: list):
    """같은 부재명의 MIDAS Gen / BeST.RC 결과 병합 (MIDAS Gen에 BeST.RC 단면 추가)"""
    midas = {b.member: b for b in beams if b.source == "MIDAS Gen"}
    for b in beams:
        if b.source == "BeST.RC" and b.member in midas:
            mg = midas[b.member]
            if mg.B_mm is None and b.B_mm is not None:
                mg.B_mm = b.B_mm
            if mg.H_mm is None and b.H_mm is not None:
                mg.H_mm = b.H_mm
            if mg.fck is None and b.fck is not None:
                mg.fck = b.fck


def _merge_column_data(cols: list):
    """같은 부재명의 MIDAS Gen / BeST.Steel 결과 병합"""
    midas = {c.member: c for c in cols if c.source == "MIDAS Gen"}
    for c in cols:
        if c.source == "BeST.Steel" and c.member in midas:
            mg = midas[c.member]
            if mg.Cx_mm is None:  mg.Cx_mm    = c.Cx_mm
            if mg.Cy_mm is None:  mg.Cy_mm    = c.Cy_mm
            if mg.Pu_kN is None:  mg.Pu_kN    = c.Pu_kN
            if mg.Mux_kNm is None: mg.Mux_kNm = c.Mux_kNm
            if mg.Muy_kNm is None: mg.Muy_kNm = c.Muy_kNm


def _deduplicate(members: list, prefer: str) -> list:
    """같은 부재명이 있으면 prefer source를 우선 유지"""
    seen = {}
    for m in members:
        key = m.member
        if key not in seen:
            seen[key] = m
        elif m.source == prefer:
            seen[key] = m
    return list(seen.values())


# ─────────────────────────────────────────────────────────────────────────────
# CLI (테스트용)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("사용법: python pdf_parser.py <PDF경로>")
        sys.exit(1)

    result = parse_pdf(sys.argv[1])
    print(f"\n파싱 완료: {result['pages_parsed']}/{result['pages_total']} 페이지")

    print(f"\n[보 부재 {len(result['beams'])}개]")
    for b in result['beams']:
        print(f"  {b.member:10s} span={b.span_m}m  B={b.B_mm}×H={b.H_mm}mm  "
              f"fck={b.fck}  Mu_neg={b.Mu_neg}  Vu={b.Vu}")

    print(f"\n[기둥 부재 {len(result['columns'])}개]")
    for c in result['columns']:
        print(f"  {c.member:10s} H={c.height_m}m  {c.Cx_mm}×{c.Cy_mm}mm  "
              f"Pu={c.Pu_kN}kN  Mux={c.Mux_kNm}  Muy={c.Muy_kNm}")
