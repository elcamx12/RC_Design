"""
PDF 파서: MIDAS Gen + BeST.RC/BeST.Steel 구조계산서에서 부재 데이터 추출

**위치 기반 파싱**: pdfplumber의 글자/단어 좌표를 활용하여 안정적으로 값 추출.
텍스트 순서가 아닌 (x, y) 좌표로 라벨-값 매핑.

지원 형식:
  - MIDAS Gen RC Beam Strength Checking Result
  - MIDAS Gen RC Column Checking Result (TODO)
  - BeST.RC (보)
  - BeST.Steel (기둥)
"""
import re
from dataclasses import dataclass
from typing import Optional, List

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
    # T형보 추가 치수
    B_top_mm: Optional[float] = None  # mm (T형 상부 폭)
    H_top_mm: Optional[float] = None  # mm (T형 상부 높이)
    # Loc (피복+스터럽+주근반경, mm)
    Loc_top_mm: Optional[float] = None
    Loc_bot_mm: Optional[float] = None
    # 배근 정보 (위치별 — MIDAS는 I/MID/J 각각 다를 수 있음)
    rebar_top: Optional[tuple] = None     # ("3-D19", "3-D19", "3-D19") 또는 단일 str
    rebar_bot: Optional[tuple] = None
    stirrup: Optional[tuple] = None       # ("2-D10 @125", "2-D10 @150", "2-D10 @125")
    skin_rebar: Optional[str] = None    # "1/1 - D13"
    total_As_mm2: Optional[float] = None
    rho_st: Optional[float] = None
    # (-) 부 모멘트: (END-I, MID, END-J), kN·m
    Mu_neg: Optional[tuple] = None
    Mu_neg_lc: Optional[tuple] = None
    # (+) 정 모멘트
    Mu_pos: Optional[tuple] = None
    Mu_pos_lc: Optional[tuple] = None
    # 전단
    Vu: Optional[tuple] = None        # kN (END-I, MID, END-J)
    Vu_lc: Optional[tuple] = None
    # 설계강도
    phi_Mn_neg: Optional[tuple] = None
    phi_Mn_pos: Optional[tuple] = None
    phi_Vc: Optional[tuple] = None
    phi_Vs: Optional[tuple] = None
    check_ratio_neg: Optional[tuple] = None
    check_ratio_pos: Optional[tuple] = None
    check_ratio_shear: Optional[tuple] = None
    # BeST 상세 (단일값)
    phi: Optional[float] = None           # 강도감소계수
    cb_mm: Optional[float] = None         # 균형축깊이
    c_mm: Optional[float] = None          # 중립축깊이
    epsilon_t: Optional[float] = None     # 인장변형률
    Ts_kN: Optional[float] = None         # 인장철근력
    Cs_kN: Optional[float] = None         # 압축철근력
    Cc_kN: Optional[float] = None         # 압축콘크리트력
    phi_Mn_best: Optional[float] = None   # BeST ΦMn (단일값, kN·m)
    check_ratio_best: Optional[float] = None  # Mu/ΦMn
    phi_Vc_best: Optional[float] = None   # BeST ΦVc (단일값)
    Vs_req_best: Optional[float] = None   # Vs,req
    stirrup_req: Optional[str] = None     # Required stirrup
    crack_smax: Optional[float] = None    # 균열 smax
    crack_s: Optional[float] = None       # 균열 s
    crack_ok: Optional[bool] = None

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ColumnResult:
    member: str = ""
    source: str = ""
    height_m: Optional[float] = None  # m (KLu)
    fck: Optional[float] = None
    fy: Optional[float] = None
    fys: Optional[float] = None
    Cx_mm: Optional[float] = None
    Cy_mm: Optional[float] = None
    Pu_kN: Optional[float] = None
    Mux_kNm: Optional[float] = None
    Muy_kNm: Optional[float] = None
    lc: Optional[str] = None
    # 배근 정보
    rebar_vert: Optional[str] = None   # "12EA - 4R - D19"
    rebar_As: Optional[float] = None   # mm²
    hoop: Optional[str] = None         # "D10 @ 50"
    clear_cover_mm: Optional[float] = None
    # 강재 (SRC)
    steel_section: Optional[str] = None  # "ㅁ-26x26x11x11"
    # 설계 결과
    EI_eff: Optional[float] = None     # kN·m²
    Po_kN: Optional[float] = None
    Pe_kN: Optional[float] = None
    phi_Pn_max: Optional[float] = None
    phi_Mnx: Optional[float] = None    # kN·m
    phi_Mny: Optional[float] = None    # kN·m
    R_com: Optional[float] = None      # 검토비 Mux/ΦMnx + Muy/ΦMny
    # 전단
    Vuy_kN: Optional[float] = None
    phi_Vny_kN: Optional[float] = None
    check_ratio_shear: Optional[float] = None

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ─────────────────────────────────────────────────────────────────────────────
# 위치 기반 유틸리티 함수
# ─────────────────────────────────────────────────────────────────────────────

def _get_words(page, x_tol=3, y_tol=3):
    """페이지의 모든 단어를 좌표와 함께 추출"""
    return page.extract_words(x_tolerance=x_tol, y_tolerance=y_tol)


def _find_word(words, *texts, exact=False):
    """여러 텍스트를 순서대로 포함하는 단어 행을 찾아 첫 단어 반환.
    exact=True면 첫 텍스트를 정확히 일치시킴 (부분매칭 방지).
    예: _find_word(words, 'Moment', '(Mu)') → 'Moment' 단어의 위치
    예: _find_word(words, 'M', exact=True) → 정확히 'M'인 단어만"""
    for i, w in enumerate(words):
        if exact:
            match = (w['text'] == texts[0])
        else:
            match = (texts[0] in w['text'])
        if match:
            if len(texts) == 1:
                return w
            # 나머지 텍스트가 같은 y 근처에 있는지 확인
            matched = True
            for t in texts[1:]:
                found = False
                for j in range(max(0, i-5), min(len(words), i+10)):
                    if t in words[j]['text'] and abs(words[j]['top'] - w['top']) < 5:
                        found = True
                        break
                if not found:
                    matched = False
                    break
            if matched:
                return w
    return None


def _find_all_words(words, text):
    """특정 텍스트를 포함하는 모든 단어 반환"""
    return [w for w in words if text in w['text']]


def _words_at_y(words, y, tol=5):
    """특정 y좌표의 모든 단어를 x 순서로 반환"""
    row = [w for w in words if abs(w['top'] - y) < tol]
    return sorted(row, key=lambda w: w['x0'])


def _numbers_at_y(words, y, tol=5):
    """특정 y좌표의 숫자들을 x 순서로 반환"""
    row = _words_at_y(words, y, tol)
    nums = []
    for w in row:
        try:
            nums.append(float(w['text'].replace(',', '')))
        except ValueError:
            pass
    return nums


def _number_near(words, x, y, x_tol=30, y_tol=5):
    """(x, y) 근처의 숫자 반환"""
    candidates = []
    for w in words:
        if abs(w['top'] - y) < y_tol:
            cx = (w['x0'] + w['x1']) / 2
            if abs(cx - x) < x_tol:
                try:
                    val = float(w['text'].replace(',', ''))
                    candidates.append((abs(cx - x), val))
                except ValueError:
                    pass
    if candidates:
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]
    return None


def _text_near(words, x, y, x_tol=30, y_tol=5):
    """(x, y) 근처의 텍스트 반환"""
    candidates = []
    for w in words:
        if abs(w['top'] - y) < y_tol:
            cx = (w['x0'] + w['x1']) / 2
            if abs(cx - x) < x_tol:
                candidates.append((abs(cx - x), w['text']))
    if candidates:
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]
    return None


def _column_centers(words, labels):
    """테이블 헤더 라벨들의 x 중심 좌표를 딕셔너리로 반환.
    예: {'END-I': 277, 'MID': 367, 'END-J': 447}"""
    centers = {}
    for label in labels:
        for w in words:
            if w['text'] == label or w['text'] == f'[{label}]':
                centers[label] = (w['x0'] + w['x1']) / 2
                break
    return centers


def _three_values_at_row(words, y, col_centers, tol_y=5, tol_x=30):
    """테이블의 한 행에서 3개 컬럼(END-I, MID, END-J) 값을 읽기"""
    vals = []
    for label in ['END-I', 'MID', 'END-J']:
        cx = col_centers.get(label)
        if cx is None:
            vals.append(None)
            continue
        v = _number_near(words, cx, y, x_tol=tol_x, y_tol=tol_y)
        vals.append(v)
    return tuple(vals) if any(v is not None for v in vals) else None


def _three_ints_at_row(words, y, col_centers, tol_y=5, tol_x=30):
    """테이블의 한 행에서 3개 정수 컬럼 값을 읽기"""
    vals = _three_values_at_row(words, y, col_centers, tol_y, tol_x)
    if vals:
        return tuple(int(v) if v is not None else None for v in vals)
    return None


def _vertical_values(chars, x, y_min, y_max, size_max=4.0):
    """세로 텍스트를 y좌표 gap으로 분리하여 읽기.
    반환: 값 리스트 (아래→위로 읽은 숫자들)"""
    # 해당 x좌표, 해당 y범위, 작은 글씨만
    vchars = [c for c in chars
              if abs(c['x0'] - x) < 3
              and y_min < c['top'] < y_max
              and c.get('size', 99) < size_max]
    if len(vchars) < 3:
        return []

    vchars.sort(key=lambda c: c['top'])

    # y좌표 gap으로 그룹 분리
    groups = [[vchars[0]]]
    for i in range(1, len(vchars)):
        gap = vchars[i]['top'] - vchars[i-1]['top']
        if gap > 15:  # 큰 gap이면 새 그룹
            groups.append([vchars[i]])
        else:
            groups[-1].append(vchars[i])

    # 각 그룹을 아래→위로 읽기
    values = []
    for g in groups:
        text_up = ''.join(c['text'] for c in reversed(g))
        try:
            values.append(float(text_up))
        except ValueError:
            pass
    return values


def _sfloat(text):
    """안전한 float 변환"""
    if text is None:
        return None
    try:
        return float(str(text).replace(',', '').strip())
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 페이지 분류
# ─────────────────────────────────────────────────────────────────────────────

def _classify_page(text):
    if 'midas Gen' in text and 'Beam' in text and 'Strength' in text:
        return 'midas_beam'
    if 'midas Gen' in text and 'Column' in text:
        return 'midas_column'
    if 'BeST.RC' in text or ('MEMBER' in text and 'Bending Moment Capacity' in text):
        return 'best_rc_beam'
    if 'BeST.Steel' in text or 'P-M Interaction' in text:
        return 'best_steel'
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MIDAS Gen Beam — 위치 기반 파싱
# ─────────────────────────────────────────────────────────────────────────────

def _parse_midas_beam(page):
    """MIDAS Gen RC Beam — 위치 기반 파싱"""
    r = BeamResult(source="MIDAS Gen")
    words = _get_words(page)
    chars = page.chars
    text = page.extract_text() or ''

    # ── 부재명 + 스팬 ──
    prop_w = _find_word(words, 'Section', 'Property')
    if prop_w:
        row = _words_at_y(words, prop_w['top'])
        for i, w in enumerate(row):
            if w['text'] == 'Property' and i+1 < len(row):
                r.member = row[i+1]['text']
        span_w = _find_word(words, 'Beam', 'Span')
        if span_w:
            span_row = _words_at_y(words, span_w['top'])
            for w in span_row:
                m = re.match(r'([\d.]+)m', w['text'])
                if m:
                    r.span_m = _sfloat(m.group(1))

    # ── 재료 (KPa → MPa) ──
    mat_w = _find_word(words, 'Material', 'Data')
    if mat_w:
        # 같은 행 또는 아래 행(+15 이내)에서 fck/fy/fys 검색
        mat_area = [w for w in words if mat_w['top'] - 2 < w['top'] < mat_w['top'] + 20]
        mat_text = ' '.join(w['text'] for w in sorted(mat_area, key=lambda w: (w['top'], w['x0'])))
        fck_m = re.search(r'fck\s*=\s*([\d.]+)', mat_text)
        fy_m = re.search(r'fy\s*=\s*([\d.]+)', mat_text)
        fys_m = re.search(r'fys\s*=\s*([\d.]+)', mat_text)
        if fck_m: r.fck = _sfloat(fck_m.group(1)) / 1000.0
        if fy_m:  r.fy  = _sfloat(fy_m.group(1))  / 1000.0
        if fys_m: r.fys = _sfloat(fys_m.group(1)) / 1000.0

    # ── 배근 (단면도 아래 3세트: END-I / MID / END-J) ──
    # MIDAS: 단면도 아래에 각 위치별 TOP/BOT/STIRRUPS가 반복됨
    # 하지만 보통 3곳 모두 동일 → 첫번째에서 가져오고, Using Stirrups Spacing에서 위치별 확인
    top_words = _find_all_words(words, 'TOP')
    if top_words:
        rebar_tops = []
        for tw in top_words:
            row = _words_at_y(words, tw['top'])
            for w in row:
                if re.match(r'\d+-D\d+', w['text']):
                    rebar_tops.append(w['text'])
                    break
        if rebar_tops:
            # 중복 제거 후 3개 세트로
            r.rebar_top = tuple(rebar_tops[:3]) if len(rebar_tops) >= 3 else rebar_tops[0]

    bot_words = _find_all_words(words, 'BOT')
    if bot_words:
        rebar_bots = []
        for bw in bot_words:
            row = _words_at_y(words, bw['top'])
            for w in row:
                if re.match(r'\d+-D\d+', w['text']):
                    rebar_bots.append(w['text'])
                    break
        if rebar_bots:
            r.rebar_bot = tuple(rebar_bots[:3]) if len(rebar_bots) >= 3 else rebar_bots[0]

    # ── Loc (세로 텍스트) ──
    # 단면도 영역: [END-I] ~ 첫번째 TOP 라벨 사이
    endi_w = _find_word(words, '[END-I]')
    y_end = None  # 단면 폭 검색에서도 사용
    if endi_w:
        y_start = endi_w['top']
        # 첫번째 "TOP" 라벨의 y좌표 = 단면도 아래 끝
        top_first = _find_word(words, 'TOP', exact=True)
        y_end = top_first['top'] if top_first else y_start + 200
        # size < 4.0인 글자의 x좌표 그룹 찾기
        from collections import defaultdict
        x_groups = defaultdict(list)
        for c in chars:
            if y_start < c['top'] < y_end and c.get('size', 99) < 4.0:
                x_key = round(c['x0'], 0)
                x_groups[x_key].append(c)

        # Loc: 정확히 2개 값, 각각 0.02~0.15 범위 (20~150mm)
        # H: 정확히 1개 값, 0.1~3.0 범위 (100~3000mm)
        # 두 패턴을 별도 x그룹에서 찾아야 함 (같은 x에서 겹치면 안 됨)
        loc_found_x = None
        for x_key in sorted(x_groups.keys()):
            vals = _vertical_values(chars, x_key, y_start, y_end, size_max=4.0)
            if len(vals) == 2 and all(0.02 < v < 0.15 for v in vals):
                r.Loc_top_mm = vals[0] * 1000  # m → mm
                r.Loc_bot_mm = vals[1] * 1000
                loc_found_x = x_key
                break

        # 단면 H: Loc과 다른 x그룹에서, 1개 값
        for x_key in sorted(x_groups.keys()):
            if loc_found_x is not None and abs(x_key - loc_found_x) < 5:
                continue  # Loc과 같은 x → 건너뜀
            vals = _vertical_values(chars, x_key, y_start, y_end, size_max=5.0)
            if len(vals) == 1 and 0.1 < vals[0] < 3.0:
                h_from_vertical = vals[0] * 1000  # m → mm
                if r.H_mm is None:
                    r.H_mm = h_from_vertical
                break

    # ── 단면 폭 (가로 텍스트 "0.25" — [END-I] 아래 ~ TOP 사이) ──
    top_w_first = _find_word(words, 'TOP', exact=True)
    if endi_w and top_w_first:
        b_search_start = endi_w['top'] + 50  # 단면도 중간 이후
        b_search_end = top_w_first['top']     # TOP 라벨 직전
        for w in words:
            if b_search_start < w['top'] < b_search_end:
                v = _sfloat(w['text'])
                if v and 0.1 < v < 3.0 and r.B_mm is None:
                    r.B_mm = v * 1000  # m → mm

    # ── 2. Bending Moment Capacity 테이블 ──
    col_c = {}  # 컬럼 중심 좌표 (Shear에서도 사용)
    bending_w = _find_word(words, 'Bending', 'Moment')
    if bending_w:
        # Bending 아래에서 END-I/MID/END-J 헤더 찾기
        header_words = [w for w in words if bending_w['top'] < w['top'] < bending_w['top'] + 30]
        col_c = _column_centers(header_words, ['END-I', 'MID', 'END-J'])
        if not col_c:
            col_c = _column_centers(words, ['END-I', 'MID', 'END-J'])

        if col_c:
            # (-) 하중조합
            neg_lc_w = _find_word(words, '(-)', 'Load')
            if neg_lc_w:
                r.Mu_neg_lc = _three_ints_at_row(words, neg_lc_w['top'], col_c)

            # (-) Moment (Mu)
            # "(-)" 다음 "Moment (Mu)" 행
            neg_mu_w = None
            if neg_lc_w:
                mu_words = _find_all_words(words, 'Moment')
                for mw in mu_words:
                    if mw['top'] > neg_lc_w['top'] and mw['top'] < neg_lc_w['top'] + 25:
                        neg_mu_w = mw
                        break
            if neg_mu_w:
                r.Mu_neg = _three_values_at_row(words, neg_mu_w['top'], col_c)

            # (-) Factored Strength (φMn)
            if neg_mu_w:
                fs_words = [w for w in words if 'Factored' in w['text'] and w['top'] > neg_mu_w['top'] and w['top'] < neg_mu_w['top'] + 25]
                if fs_words:
                    r.phi_Mn_neg = _three_values_at_row(words, fs_words[0]['top'], col_c)

            # (-) Check Ratio
            if neg_mu_w:
                cr_words = [w for w in words if 'Check' in w['text'] and w['top'] > neg_mu_w['top'] and w['top'] < neg_mu_w['top'] + 40]
                if cr_words:
                    r.check_ratio_neg = _three_values_at_row(words, cr_words[0]['top'], col_c)

            # (+) 하중조합
            pos_lc_w = _find_word(words, '(+)', 'Load')
            if pos_lc_w:
                r.Mu_pos_lc = _three_ints_at_row(words, pos_lc_w['top'], col_c)

            # (+) Moment (Mu)
            pos_mu_w = None
            if pos_lc_w:
                mu_words = _find_all_words(words, 'Moment')
                for mw in mu_words:
                    if mw['top'] > pos_lc_w['top'] and mw['top'] < pos_lc_w['top'] + 25:
                        pos_mu_w = mw
                        break
            if pos_mu_w:
                r.Mu_pos = _three_values_at_row(words, pos_mu_w['top'], col_c)

            # (+) Factored Strength
            if pos_mu_w:
                fs_words = [w for w in words if 'Factored' in w['text'] and w['top'] > pos_mu_w['top'] and w['top'] < pos_mu_w['top'] + 25]
                if fs_words:
                    r.phi_Mn_pos = _three_values_at_row(words, fs_words[0]['top'], col_c)

            # (+) Check Ratio
            if pos_mu_w:
                cr_words = [w for w in words if 'Check' in w['text'] and w['top'] > pos_mu_w['top'] and w['top'] < pos_mu_w['top'] + 40]
                if cr_words:
                    r.check_ratio_pos = _three_values_at_row(words, cr_words[0]['top'], col_c)

    # ── 3. Shear Capacity 테이블 ──
    shear_w = _find_word(words, 'Shear', 'Capacity')
    if shear_w:
        # Shear 섹션의 END-I/MID/END-J 헤더
        shear_header = [w for w in words if shear_w['top'] < w['top'] < shear_w['top'] + 30]
        shear_col = _column_centers(shear_header, ['END-I', 'MID', 'END-J'])
        if not shear_col:
            shear_col = col_c if col_c else {}

        if shear_col:
            # 전단 하중조합
            shear_lc_words = [w for w in words if 'Load' in w['text'] and w['top'] > shear_w['top'] and w['top'] < shear_w['top'] + 40]
            if shear_lc_words:
                r.Vu_lc = _three_ints_at_row(words, shear_lc_words[0]['top'], shear_col)

            # Factored Shear Force (Vu) — "Shear" 또는 "Force" 키워드로 Bending의 Factored와 구분
            vu_w = [w for w in words if 'Factored' in w['text'] and w['top'] > shear_w['top'] + 15 and w['top'] < shear_w['top'] + 60
                    and any('Shear' in ww['text'] or 'Force' in ww['text'] for ww in _words_at_y(words, w['top']))]
            if vu_w:
                r.Vu = _three_values_at_row(words, vu_w[0]['top'], shear_col)

            # φVc
            vc_w = [w for w in words if 'Conc' in w['text'] and w['top'] > shear_w['top']]
            if vc_w:
                r.phi_Vc = _three_values_at_row(words, vc_w[0]['top'], shear_col)

            # φVs
            vs_w = [w for w in words if 'Rebar' in w['text'] and w['top'] > shear_w['top'] and 'Strength' in ' '.join(ww['text'] for ww in _words_at_y(words, w['top']))]
            if vs_w:
                r.phi_Vs = _three_values_at_row(words, vs_w[0]['top'], shear_col)

            # Using Stirrups Spacing (위치별)
            stir_sp_w = [w for w in words if 'Stirrups' in w['text'] and 'Using' in ' '.join(ww['text'] for ww in _words_at_y(words, w['top'])) and w['top'] > shear_w['top']]
            if stir_sp_w:
                stir_row = _words_at_y(words, stir_sp_w[0]['top'])
                # "2-D10" + "@125" 쌍을 x좌표 순서로 수집
                stir_pairs = []
                i_sr = 0
                while i_sr < len(stir_row):
                    w = stir_row[i_sr]
                    if re.match(r'\d+-D\d+', w['text']):
                        pair = w['text']
                        if i_sr + 1 < len(stir_row) and stir_row[i_sr+1]['text'].startswith('@'):
                            pair += ' ' + stir_row[i_sr+1]['text']
                            i_sr += 1
                        stir_pairs.append(pair)
                    i_sr += 1
                if stir_pairs:
                    r.stirrup = tuple(stir_pairs[:3]) if len(stir_pairs) >= 3 else stir_pairs[0]

            # Shear Check Ratio
            shear_cr = [w for w in words if 'Check' in w['text'] and w['top'] > shear_w['top'] + 50]
            if shear_cr:
                r.check_ratio_shear = _three_values_at_row(words, shear_cr[0]['top'], shear_col)

    return r


# ─────────────────────────────────────────────────────────────────────────────
# BeST.RC Beam — 위치 기반 파싱
# ─────────────────────────────────────────────────────────────────────────────

def _parse_best_rc_beam(page):
    """BeST.RC 보 — 위치 기반 파싱"""
    r = BeamResult(source="BeST.RC")
    words = _get_words(page)
    text = page.extract_text() or ''

    # ── 부재명 — "MEMBER :XXX" 또는 ":XXX" 패턴 ──
    member_w = _find_word(words, 'MEMBER')
    if member_w:
        row = _words_at_y(words, member_w['top'])
        for w in row:
            if w['text'].startswith(':') and len(w['text']) > 1:
                r.member = w['text'][1:]
                break
    if not r.member:
        for w in words:
            if w['text'].startswith(':') and len(w['text']) > 1 and w['top'] < 100:
                r.member = w['text'][1:]
                break

    # ── 재료 ──
    # BeST.RC 재료는 "Material Data" 아래에 2행:
    #   행1: "f_ck = 30 N/mm2 (β1 = 0.800)"
    #   행2: "f_y = 500, f_ys = 400 N/mm2"
    mat_w = _find_word(words, 'Material', 'Data')
    if mat_w:
        mat_area = [w for w in words if mat_w['top'] + 5 < w['top'] < mat_w['top'] + 45]
        # fck: 첫번째 행에서 = 뒤의 숫자 (N/mm2와 같은 행, β 앞)
        nmm2_words = [w for w in mat_area if 'N/mm2' in w['text']]
        if nmm2_words:
            # 첫번째 N/mm2 행 = fck
            fck_row = _words_at_y(mat_area, nmm2_words[0]['top'])
            for i, w in enumerate(fck_row):
                if w['text'] == '=' and i + 1 < len(fck_row):
                    v = _sfloat(fck_row[i+1]['text'])
                    if v and v < 100:
                        r.fck = v
                        break
            # 두번째 N/mm2 행 = fy, fys (있다면)
            if len(nmm2_words) >= 2:
                fy_row = _words_at_y(mat_area, nmm2_words[1]['top'])
                fy_text = ' '.join(w['text'] for w in fy_row)
                m = re.search(r'=\s*([\d.]+)\s*,.*?=\s*([\d.]+)', fy_text)
                if m:
                    r.fy = _sfloat(m.group(1))
                    r.fys = _sfloat(m.group(2))

    # ── 단면 ──
    sec_w = _find_word(words, 'Section', 'Data')
    if sec_w:
        # "B = xxx mm H = xxx mm" 행을 모두 찾고 top/bot 라벨로 구분
        sec_area = [w for w in words if sec_w['top'] + 5 < w['top'] < sec_w['top'] + 45]
        # "top"/"bot" 라벨 위치 확인 (B=행보다 y가 조금 아래)
        top_label_y = None
        bot_label_y = None
        for w in sec_area:
            # "top"/"bot"은 B=행 바로 아래(+3~5pt)에 위치, x < 200
            if w['text'].lower() == 'top' and w['x0'] < 200:
                # top 라벨이 B=행과 가까이(+5 이내) 있는지 확인
                for bh_y, _, _ in [(round(ww['top']), 0, 0) for ww in sec_area if ww['text'] == 'B']:
                    if 0 < w['top'] - bh_y < 8:
                        top_label_y = w['top']
                        break
            if w['text'].lower() == 'bot' and w['x0'] < 200:
                for bh_y, _, _ in [(round(ww['top']), 0, 0) for ww in sec_area if ww['text'] == 'B']:
                    if 0 < w['top'] - bh_y < 8:
                        bot_label_y = w['top']
                        break

        # B = xxx mm H = xxx mm 패턴 행 찾기
        # 중복 제거: 같은 B/H 값이면 스킵 (같은 행이 미세 y차이로 2번 잡힌 경우)
        bh_rows = []
        for line_y in sorted(set(round(w['top']) for w in sec_area)):
            row = _words_at_y(sec_area, line_y, tol=3)
            row_text = ' '.join(w['text'] for w in row)
            bm = re.search(r'B\s*=\s*([\d.]+)\s*mm\s+H\s*=\s*([\d.]+)\s*mm', row_text)
            if bm:
                b_val = _sfloat(bm.group(1))
                h_val = _sfloat(bm.group(2))
                # 같은 B/H 값이 이미 있으면 중복 → 스킵
                if not any(bv == b_val and hv == h_val for _, bv, hv in bh_rows):
                    bh_rows.append((line_y, b_val, h_val))

        if len(bh_rows) == 2 and top_label_y and bot_label_y:
            # T형보 — top_label에 가까운 행 = top, bot_label에 가까운 행 = bot
            for y, b, h in bh_rows:
                if abs(y - top_label_y) < 8:
                    r.B_top_mm = b
                    r.H_top_mm = h
                elif abs(y - bot_label_y) < 8:
                    r.B_mm = b
                    r.H_mm = h
        elif len(bh_rows) == 1:
            # 직사각형
            r.B_mm = bh_rows[0][1]
            r.H_mm = bh_rows[0][2]
        elif len(bh_rows) == 2 and not top_label_y:
            # top/bot 라벨 없이 2행 → 두번째가 bot(웹)
            r.B_top_mm = bh_rows[0][1]
            r.H_top_mm = bh_rows[0][2]
            r.B_mm = bh_rows[1][1]
            r.H_mm = bh_rows[1][2]

    # ── 배근 + Loc ──
    upper_w = _find_word(words, 'Upper')
    if upper_w:
        row = _words_at_y(words, upper_w['top'])
        for w in row:
            if re.match(r'\d+-D\d+', w['text']):
                r.rebar_top = w['text']
        # Loc
        for w in row:
            v = _sfloat(w['text'])
            if v and 10 < v < 200 and w['x0'] > 200:
                r.Loc_top_mm = v

    lower_w = _find_word(words, 'Lower')
    if lower_w:
        row = _words_at_y(words, lower_w['top'])
        for w in row:
            if re.match(r'\d+-D\d+', w['text']):
                r.rebar_bot = w['text']
        for w in row:
            v = _sfloat(w['text'])
            if v and 10 < v < 200 and w['x0'] > 200:
                r.Loc_bot_mm = v

    # Skin rebar
    skin_w = _find_word(words, 'Skin')
    if skin_w:
        row = _words_at_y(words, skin_w['top'])
        parts = [w['text'] for w in row if w['text'] not in ('Skin', ':')]
        if parts:
            r.skin_rebar = ' '.join(parts)

    # Total Rebar Area + ρ
    total_w = _find_word(words, 'Total', 'Rebar')
    if total_w:
        row = _words_at_y(words, total_w['top'])
        row_text = ' '.join(w['text'] for w in row)
        am = re.search(r'=\s*([\d.]+)\s*mm', row_text)
        if am:
            r.total_As_mm2 = _sfloat(am.group(1))
        rm = re.search(r'=\s*(0\.\d+)\)', row_text)
        if rm:
            r.rho_st = _sfloat(rm.group(1))

    # ── 설계력 ──
    # BeST.RC는 단일 지배 모멘트만 제공 → Mu_neg에만 저장, Mu_pos=None
    # 호출자는 Mu_pos=None일 때 "BeST에서 미제공"으로 처리해야 함
    # "M_u = -69.0 kN·m, T_u = 0.0 kN·m" (같은 행)
    # "V_u = 48.0 kN" (다음 행)
    force_w = _find_word(words, 'Design', 'Force')
    if force_w:
        force_area = [w for w in words if force_w['top'] + 5 < w['top'] < force_w['top'] + 50]
        # M 행: "M" 뒤 "=" 뒤의 첫번째 숫자 = Mu (T = 0.0 혼동 방지)
        # 텍스트: "M = -69.0 kN·m, T = 0.0 kN·m"
        # "M" → "=" → 숫자 순서로 추적
        for w in force_area:
            if w['text'] == 'M' and w['x0'] < 100:
                row = _words_at_y(force_area, w['top'])
                # "M" 바로 다음 "=" 찾고, 그 다음 숫자 = Mu
                found_eq = False
                for rw in row:
                    if rw['x0'] <= w['x0']:
                        continue  # M 이전 단어 건너뜀
                    if rw['text'] == '=':
                        found_eq = True
                        continue
                    if found_eq:
                        v = _sfloat(rw['text'])
                        if v is not None:
                            r.Mu_neg = (abs(v), abs(v), abs(v))
                            break
                        found_eq = False  # 숫자가 아니면 리셋
                break

        # V 행: 같은 방식
        for w in force_area:
            if w['text'] == 'V' and w['x0'] < 100:
                row = _words_at_y(force_area, w['top'])
                found_eq = False
                for rw in row:
                    if rw['x0'] <= w['x0']:
                        continue
                    if rw['text'] == '=':
                        found_eq = True
                        continue
                    if found_eq:
                        v = _sfloat(rw['text'])
                        if v is not None:
                            r.Vu = (abs(v), abs(v), abs(v))  # abs: 음수 방지
                            break
                        found_eq = False
                break

    # ── Φ, cb, c, εt ──
    # Bending 섹션의 Strength Reduction Factor (Shear 섹션에도 있으므로 구분 필요)
    bending_check_w = _find_word(words, 'Check', 'Bending')
    if bending_check_w:
        # Bending 섹션 아래 첫번째 "Strength Reduction"
        sr_words = [w for w in words if 'Strength' in w['text'] and w['top'] > bending_check_w['top'] and w['top'] < bending_check_w['top'] + 30]
        if sr_words:
            row = _words_at_y(words, sr_words[0]['top'])
            for w in row:
                v = _sfloat(w['text'])
                if v and 0.5 < v < 1.0:
                    r.phi = v
                    break

    cb_w = _find_word(words, 'Balanced', 'Axis')
    if cb_w:
        row = _words_at_y(words, cb_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and 10 < v < 1000:
                r.cb_mm = v

    c_w = _find_word(words, 'Neutral', 'Axis')
    if c_w:
        row = _words_at_y(words, c_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and 10 < v < 1000:
                r.c_mm = v

    et_w = _find_word(words, 'Tensile', 'strain')
    if et_w:
        row = _words_at_y(words, et_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and 0.001 < v < 0.1:
                r.epsilon_t = v
                break

    # ── ΦMn, Mu/ΦMn ──
    dmn_w = _find_word(words, 'Design', 'Moment', 'Capacity')
    if dmn_w:
        row = _words_at_y(words, dmn_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and abs(v) > 5:
                r.phi_Mn_best = abs(v)
                break

    ratio_w = _find_word(words, '/ΦM')
    if not ratio_w:
        ratio_w = _find_word(words, 'ΦM')
    if ratio_w:
        # Mu/ΦMn = 0.895 행
        row = _words_at_y(words, ratio_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and 0.01 < v < 5.0:
                r.check_ratio_best = v
                break

    # ── ΦVc, Vs,req ──
    vc_w = _find_word(words, 'ΦV')
    if vc_w:
        # 첫 번째 ΦV가 ΦVc
        row = _words_at_y(words, vc_w['top'])
        for w in row:
            v = _sfloat(w['text'])
            if v and v > 1:
                r.phi_Vc_best = v
                break

    # ── Required Stirrup ("Required Stirrup Reinf. : 2 - D10 @ 70 mm") ──
    req_stir_w = _find_word(words, 'Required', 'Stirrup')
    if req_stir_w:
        row = _words_at_y(words, req_stir_w['top'])
        stir_parts = []
        after_colon = False
        for w in row:
            if ':' in w['text']:
                after_colon = True
                continue
            if after_colon:
                if w['text'] == 'mm':
                    break
                stir_parts.append(w['text'])
        if stir_parts:
            r.stirrup_req = ' '.join(stir_parts)

    # ── Vs,req 추출 ──
    vs_req_w = _find_word(words, 'ΦV')
    if vs_req_w:
        # 두번째 ΦV 행이 Vs,req (첫번째가 ΦVc)
        all_phiv = [w for w in words if 'ΦV' in w['text']]
        if len(all_phiv) >= 2:
            vs_row = _words_at_y(words, all_phiv[1]['top'])
            for w in vs_row:
                v = _sfloat(w['text'])
                if v and v > 0.1:
                    r.Vs_req_best = v
                    break

    # ── 균열 ──
    crack_w = _find_word(words, 'Check', 'Crack')
    if crack_w:
        crack_line = [w for w in words if w['top'] > crack_w['top'] + 5 and w['top'] < crack_w['top'] + 25]
        crack_text = ' '.join(w['text'] for w in sorted(crack_line, key=lambda w: w['x0']))
        smax_m = re.search(r'=\s*([\d.]+)\s*>', crack_text)
        s_m = re.search(r'>\s*s\s*=\s*([\d.]+)', crack_text)
        if smax_m:
            r.crack_smax = _sfloat(smax_m.group(1))
        if s_m:
            r.crack_s = _sfloat(s_m.group(1))
        r.crack_ok = 'O.K.' in crack_text

    return r


# ─────────────────────────────────────────────────────────────────────────────
# BeST.Steel Column — 위치 기반 파싱 (다중 페이지 지원)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_best_steel_column(pages):
    """BeST.Steel 기둥 — pages는 같은 부재의 연속 페이지 리스트"""
    r = ColumnResult(source="BeST.Steel")

    for page in pages:
        words = _get_words(page)
        text = page.extract_text() or ''

        # ── 부재명 (첫 페이지에서) ──
        if not r.member:
            # 전각 페이지 번호 제외: :１, :２, :３, :４, :５ 및 반각 :1~:9
            _page_markers = {':１', ':２', ':３', ':４', ':５', ':1', ':2', ':3', ':4', ':5', ':6', ':7', ':8', ':9'}
            for w in words:
                if w['text'].startswith(':') and len(w['text']) > 1 and w['text'] not in _page_markers:
                    r.member = w['text'][1:]
                    break

        # ── 재료 ──
        if r.fck is None:
            fck_w = _find_word(words, 'f', '=')
            if fck_w:
                for w in words:
                    if 'N/mm2' in w['text'] and abs(w['top'] - fck_w['top']) < 5:
                        row = _words_at_y(words, fck_w['top'])
                        for rw in row:
                            v = _sfloat(rw['text'])
                            if v and 10 < v < 100:
                                r.fck = v
                                break
                        break

        # F_y,Bar — "y,Bar" 아래첨자가 있는 행에서 숫자 추출
        if r.fy is None:
            for w in words:
                if 'y,Bar' in w['text']:
                    # 아래첨자보다 y가 조금 위인 행이 F = 440 행
                    fy_row = _words_at_y(words, w['top'] - 3, tol=5)
                    for rw in fy_row:
                        v = _sfloat(rw['text'])
                        if v and 100 < v < 1000:
                            r.fy = v
                            break
                    break

        # ── 단면 Cx, Cy ──
        if r.Cx_mm is None:
            sec_w = _find_word(words, 'Section', 'Data')
            if sec_w:
                # Section Data 아래 "C = 250 mm C = 250 mm" 행 탐색
                for w in words:
                    if w['text'] == 'C' and w['top'] > sec_w['top'] and w['top'] < sec_w['top'] + 25:
                        row = _words_at_y(words, w['top'])
                        # "C = 250 mm C = 250 mm" → 숫자 2개 추출
                        nums = [_sfloat(rw['text']) for rw in row if _sfloat(rw['text']) and _sfloat(rw['text']) > 50]
                        if len(nums) >= 2:
                            r.Cx_mm = nums[0]
                            r.Cy_mm = nums[1]
                        elif len(nums) == 1:
                            r.Cx_mm = nums[0]
                            r.Cy_mm = nums[0]
                        break

        # KLu
        if r.height_m is None:
            klu_w = _find_word(words, 'KL')
            if klu_w:
                row = _words_at_y(words, klu_w['top'])
                for w in row:
                    v = _sfloat(w['text'])
                    if v and 0.5 < v < 50:
                        r.height_m = v

        # ── 배근 ──
        if r.rebar_vert is None:
            vert_w = _find_word(words, 'Vert')
            if vert_w:
                row = _words_at_y(words, vert_w['top'], tol=3)
                # "12EA - 4R - D19" 추출 (아래첨자 제외)
                parts = []
                for w in row:
                    if w['text'] in ('Vert', ':', '(A', 'mm2)'):
                        continue
                    if w['text'] == '=':
                        break  # "(A = 3438 mm2)" 시작 → 중단
                    parts.append(w['text'])
                if parts:
                    r.rebar_vert = ' '.join(parts)
                # As 값
                for w in row:
                    if w['text'] == '=' and w['x0'] > 250:
                        # = 다음 숫자
                        next_words = [nw for nw in row if nw['x0'] > w['x1']]
                        if next_words:
                            r.rebar_As = _sfloat(next_words[0]['text'])

        if r.hoop is None:
            hoop_w = _find_word(words, 'Hoop')
            if hoop_w:
                row = _words_at_y(words, hoop_w['top'], tol=3)
                # "D10 @ 50" 만 추출 (x < 300 범위, 세로 텍스트 "250" 같은 건 제외)
                parts = [w['text'] for w in row if w['text'] not in ('Hoop', ':') and w['x0'] < 300]
                if parts:
                    r.hoop = ' '.join(parts)

        if r.clear_cover_mm is None:
            cc_w = _find_word(words, 'Clear', 'Cover')
            if cc_w:
                row = _words_at_y(words, cc_w['top'])
                for w in row:
                    v = _sfloat(w['text'])
                    if v and 5 < v < 100:
                        r.clear_cover_mm = v

        # ── 강재 ──
        if r.steel_section is None:
            dim_w = _find_word(words, 'Dim')
            if dim_w:
                row = _words_at_y(words, dim_w['top'])
                for w in row:
                    if 'ㅁ' in w['text'] or '-' in w['text']:
                        r.steel_section = w['text']

        # ── 설계력 ──
        if r.Pu_kN is None:
            pu_w = _find_word(words, 'P')
            if pu_w:
                force_w = _find_word(words, 'Design', 'Force')
                if force_w:
                    force_lines = [w for w in words if force_w['top'] + 5 < w['top'] < force_w['top'] + 40]
                    for w in force_lines:
                        v = _sfloat(w['text'])
                        if v and v > 0.1:
                            if r.Pu_kN is None:
                                r.Pu_kN = v
                            break

        if r.Mux_kNm is None:
            # "M = 33.5, M = 103.5 kN·m"
            m_line = re.search(r'M\s*=\s*([\d.]+)\s*,\s*M\s*=\s*([\d.]+)', text)
            if m_line:
                r.Mux_kNm = _sfloat(m_line.group(1))
                r.Muy_kNm = _sfloat(m_line.group(2))

        # ── ΦMnx, ΦMny ──
        # NOTE: 정규식 사용 — 다중 페이지에 걸친 값이라 위치 기반보다 안정적
        # "Y-Y Axis" 텍스트로 X/Y 구분
        mnx_m = re.search(r'ΦM\s*=.*?=\s*([\d.]+)\s*kN·m', text)
        if mnx_m and r.phi_Mnx is None:
            r.phi_Mnx = _sfloat(mnx_m.group(1))

        # Y-Y Axis ΦMny
        yy_start = text.find('Y-Y Axis')
        if yy_start > 0:
            yy_text = text[yy_start:]
            mny_m = re.search(r'ΦM\s*=.*?=\s*([\d.]+)\s*kN·m', yy_text)
            if mny_m:
                r.phi_Mny = _sfloat(mny_m.group(1))

        # ΦPn(max)
        pn_m = re.search(r'ΦP\s*=.*?=\s*([\d.]+)', text)
        if pn_m and r.phi_Pn_max is None:
            r.phi_Pn_max = _sfloat(pn_m.group(1))

        # R_com (검토비)
        rcom_m = re.search(r'R\s*=.*?=\s*([\d.]+)\s*<', text)
        if rcom_m and r.R_com is None:
            r.R_com = _sfloat(rcom_m.group(1))

        # ── 전단 ──
        vuy_m = re.search(r'V\s*=\s*([\d.]+)\s*kN', text)
        if vuy_m and r.Vuy_kN is None and 'Shear' in text:
            r.Vuy_kN = _sfloat(vuy_m.group(1))

        pvn_m = re.search(r'ΦV\s*=.*?=\s*([\d.]+)\s*kN', text)
        if pvn_m and r.phi_Vny_kN is None:
            r.phi_Vny_kN = _sfloat(pvn_m.group(1))

        ratio_m = re.search(r'V\s*/ΦV\s*=\s*([\d.]+)', text)
        if ratio_m:
            r.check_ratio_shear = _sfloat(ratio_m.group(1))

    return r


# ─────────────────────────────────────────────────────────────────────────────
# 메인 파서
# ─────────────────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str) -> dict:
    """PDF 파일에서 구조 부재 데이터를 위치 기반으로 추출.

    반환:
        {
          "beams":        [BeamResult, ...],
          "columns":      [ColumnResult, ...],
          "pages_parsed": int,
          "pages_total":  int,
        }
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber가 설치되지 않았습니다: pip install pdfplumber")

    beams: list = []
    columns: list = []
    pages_parsed = 0

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        i = 0
        while i < total:
            page = pdf.pages[i]
            text = page.extract_text() or ''
            kind = _classify_page(text)

            if kind == 'midas_beam':
                beams.append(_parse_midas_beam(page))
                pages_parsed += 1
                i += 1

            elif kind == 'best_rc_beam':
                beams.append(_parse_best_rc_beam(page))
                pages_parsed += 1
                i += 1

            elif kind == 'best_steel':
                # BeST.Steel은 여러 페이지에 걸칠 수 있음 — 연속 페이지 수집
                steel_pages = [page]
                j = i + 1
                while j < total:
                    next_text = pdf.pages[j].extract_text() or ''
                    next_kind = _classify_page(next_text)
                    if next_kind == 'best_steel':
                        # 같은 부재의 연속 페이지인지 확인 (Page :2, :3, :４ 등)
                        # 전각/반각 숫자 모두 대응
                        is_continuation = False
                        for pg_marker in [':２', ':３', ':４', ':５', ':2', ':3', ':4', ':5']:
                            if pg_marker in next_text:
                                is_continuation = True
                                break
                        if is_continuation:
                            steel_pages.append(pdf.pages[j])
                            j += 1
                        else:
                            break
                    else:
                        break
                columns.append(_parse_best_steel_column(steel_pages))
                pages_parsed += len(steel_pages)
                i = j

            elif kind == 'midas_column':
                # TODO: MIDAS Gen Column 파서 (현재 PDF에 없음)
                pages_parsed += 1
                i += 1

            else:
                i += 1

    return {
        "beams":        beams,
        "columns":      columns,
        "pages_parsed": pages_parsed,
        "pages_total":  total,
    }
