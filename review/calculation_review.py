"""
구조계산서 검토 모드 — 독립 계산 로직

기존 엔진(beam_engine.py, column_engine.py)을 수정하지 않고,
KDS 수식을 검토 전용으로 별도 구현합니다.

검토 모드 특징:
- 부재력(Mu, Vu, Pu)을 PDF에서 직접 가져와 사용
- 단면 크기 고정 (수렴루프 없음)
- 보: END-I / MID / END-J 위치별 독립 설계
- 기둥: Pu/Mux/Muy 직접 사용
- 슬래브: 1방향 모멘트 계수법 독립 계산 + BeST 비교
"""

import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# 공용 상수 / 유틸
# ═══════════════════════════════════════════════════════════════════════

REBAR_SPECS = {
    "D10": {"diameter": 9.53,  "area": 71.33},
    "D13": {"diameter": 12.7,  "area": 126.7},
    "D16": {"diameter": 15.9,  "area": 198.6},
    "D19": {"diameter": 19.1,  "area": 286.5},
    "D22": {"diameter": 22.2,  "area": 387.1},
    "D25": {"diameter": 25.4,  "area": 506.7},
    "D29": {"diameter": 28.6,  "area": 642.4},
    "D32": {"diameter": 31.8,  "area": 794.2},
    "D35": {"diameter": 35.8,  "area": 1006.0},
}

REBAR_DB_TABLE = [
    (12.7, 126.7), (15.9, 198.6), (19.1, 286.5),
    (22.2, 387.1), (25.4, 506.7), (28.6, 642.4), (31.8, 794.2),
]


def _get_alpha1_beta1(fc_k):
    """KDS 14 20 20 표 4.1-2 등가직사각형 압축응력블록 계수.
    반환: (alpha1, beta1)
    """
    if fc_k <= 40:
        return 0.80, 0.80
    elif fc_k <= 90:
        alpha1 = 0.80 - 0.004 * (fc_k - 40)
        beta1 = 0.80 - 0.006 * (fc_k - 40)
        return max(alpha1, 0.60), max(beta1, 0.50)
    else:
        return 0.60, 0.50


def _get_epsilon_cu(fc_k):
    """KDS 14 20 20 극한변형률.
    fck ≤ 40: 0.0033, 40 초과 시 10MPa당 0.0001 감소.
    """
    if fc_k <= 40:
        return 0.0033
    else:
        return max(0.0033 - 0.0001 * ((fc_k - 40) / 10.0), 0.0026)


def _calc_phi(epsilon_t, fy, phi_comp=0.65, phi_tens=0.85):
    """KDS 14 20 10 강도감소계수 φ 계산.
    - 인장지배: εt ≥ εt_limit → φ = phi_tens (0.85)
    - 압축지배: εt ≤ 0.002 → φ = phi_comp (0.65)
    - 전이구간: 선형보간 φ = phi_comp + (εt - 0.002)/0.003 × (phi_tens - phi_comp)
    - fy > 400MPa: 인장지배한계 = 2.5 × εy (KDS 14 20 20)
    """
    eps_y = fy / 200000.0
    # 인장지배변형률 한계  # KDS 14 20 20
    if fy > 400:
        et_limit = 2.5 * eps_y  # fy=440 → 0.0055, fy=500 → 0.00625
    else:
        et_limit = 0.005
    # 압축지배변형률 한계 = 0.002 (KDS 14 20 10)
    et_comp = 0.002

    if epsilon_t >= et_limit:
        return phi_tens
    elif epsilon_t <= et_comp:
        return phi_comp
    else:
        return phi_comp + (epsilon_t - et_comp) / (et_limit - et_comp) * (phi_tens - phi_comp)


def _round_down_50(value):
    """값을 50mm 단위로 내림. 최소 100mm."""
    return max(np.floor(value / 50.0) * 50.0, 100.0)


def _parse_steel_section(section_str):
    """SRC 강재 각관 섹션 파싱. 'ㅁ-26x26x11x11' → dict.
    형식: ㅁ-B×H×tv×th (mm 단위)
    반환: {B, H, tv, th, As, Ix, Iy, Aw} 또는 None
    """
    import re as _re
    if not section_str:
        return None
    s = str(section_str).strip()
    # "ㅁ-26x26x11x11" 또는 "ㅁ-26x26x11x11" (여러 구분자)
    m = _re.match(r'[ㅁ□]\s*[-‐]\s*(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)', s)
    if not m:
        return None
    B = float(m.group(1))   # mm
    H = float(m.group(2))   # mm
    tv = float(m.group(3))  # 수직 두께 (mm)
    th = float(m.group(4))  # 수평 두께 (mm)
    if B <= 2 * tv or H <= 2 * th:
        return None
    # 단면적
    As = B * H - (B - 2 * tv) * (H - 2 * th)
    # 관성모멘트
    Ix = B * H ** 3 / 12.0 - (B - 2 * tv) * (H - 2 * th) ** 3 / 12.0
    Iy = H * B ** 3 / 12.0 - (H - 2 * th) * (B - 2 * tv) ** 3 / 12.0
    # 웹 면적 (전단용): 양쪽 웹 × 전체 높이 (BeST.Steel 기준)
    Aw = 2 * tv * H
    return {'B': B, 'H': H, 'tv': tv, 'th': th, 'As': As, 'Ix': Ix, 'Iy': Iy, 'Aw': Aw}


# ═══════════════════════════════════════════════════════════════════════
# 보 검토 — 휨 설계
# ═══════════════════════════════════════════════════════════════════════

def _review_flexural(Mu, b, h, fc_k, fy, cover=40.0, Loc=None):
    """
    KDS 41 20 22 §4.2 — 단일 위치의 휨 설계 (검토 모드).

    Args:
        Mu:    계수 휨모멘트 (kN·m). 0이면 최소철근비만 적용.
        b:     보 폭 (mm)
        h:     보 춤 (mm)
        fc_k:  콘크리트 압축강도 (MPa)
        fy:    철근 항복강도 (MPa)
        cover: 순피복두께 (mm), 기본 40

    Returns:
        (As_req, warnings, flexural_steps)
    """
    warnings = []
    steps = {}

    # 재료 강도 방어
    if fc_k <= 0 or fy <= 0:
        warnings.append("오류: fck 또는 fy가 0 이하입니다.")
        return 0.0, warnings, steps

    Mu_Nmm = abs(Mu) * 1e6  # kN·m → N·mm
    steps['Mu_Nmm'] = Mu_Nmm
    alpha1, _beta1_f = _get_alpha1_beta1(fc_k)  # KDS 14 20 20 표 4.1-2

    # Mu=0 처리: 최소철근비만 적용
    if Mu_Nmm < 1e-3:
        rho_min1 = (0.25 * np.sqrt(fc_k)) / fy
        rho_min2 = 1.4 / fy
        rho_min = max(rho_min1, rho_min2)
        _stir_r = 10.0
        _dc_init = cover + _stir_r + 25.4 / 2.0
        d = h - _dc_init
        As_req = rho_min * b * d if d > 0 else 0.0
        steps.update({
            'd_c': _dc_init, 'd_c_db_est': 25.4, 'd': d,
            'phi': 0.85, 'phi_iters': 0,
            'Mn_Nmm': 0.0, 'Rn': 0.0, 'discriminant': 1.0,
            'rho_req_calculated': 0.0,
            'rho_min1': rho_min1, 'rho_min2': rho_min2, 'rho_min': rho_min,
            'rho_req_final': rho_min,
            'As_calculated': As_req,
            'beta1': 0.85 if fc_k <= 28 else max(0.65, 0.85 - 0.007 * (fc_k - 28)),
            'a': 0.0, 'c': 0.0, 'epsilon_t': 0.005,
            'rho_max': 0.0, 'rho_max_ok': True,
        })
        warnings.append("정보: 해당 위치 모멘트가 0 → 최소철근비만 적용됩니다.")
        return As_req, warnings, steps

    phi = 0.85  # 초기값 (인장지배 가정)

    # ── 피복 + 유효깊이(d): 2-패스 추정 ──
    _stir_r = 10.0  # D10 늑근
    _dc_init = cover + _stir_r + 25.4 / 2.0  # D25 초기 가정
    _d_init = h - _dc_init
    if _d_init > 0.0:
        _Rn_est = (Mu_Nmm / 0.85) / (b * _d_init ** 2)
        _disc_est = 1.0 - (2.0 * _Rn_est) / (alpha1 * fc_k)
        if _disc_est > 0.0:
            _rho_est = (alpha1 * fc_k / fy) * (1.0 - np.sqrt(_disc_est))
            _rho_est = max(_rho_est, 1.4 / fy)
            _As_est = _rho_est * b * _d_init
        else:
            _As_est = 0.0
    else:
        _As_est = 0.0

    _db_est = 25.4
    for _db_c, _Ab_c in REBAR_DB_TABLE:
        if 2.0 * _Ab_c >= _As_est:
            _db_est = _db_c
            break

    # Loc가 주어지면 d = h - Loc (구조계산서 기준)
    if Loc and Loc > 0:
        d_c = Loc
        d = h - Loc
        steps['d_c'] = d_c
        steps['d_c_db_est'] = _db_est
        steps['d'] = d
        steps['d_method'] = 'Loc'
    else:
        d_c = cover + _stir_r + _db_est / 2.0
        d = h - d_c
        steps['d_c'] = d_c
        steps['d_c_db_est'] = _db_est
        steps['d'] = d
        steps['d_method'] = 'cover'

    if d <= 0:
        warnings.append("경고: 유효깊이(d)가 0 이하입니다. 단면 치수를 확인하세요.")
        return 0.0, warnings, steps

    # alpha1, beta1  (KDS 14 20 20 표 4.1-2) — 위에서 이미 alpha1 구함
    beta1 = _beta1_f
    steps['beta1'] = beta1
    steps['alpha1'] = alpha1

    epsilon_cu = _get_epsilon_cu(fc_k)  # KDS 14 20 20

    # ── φ-εt 수렴 루프 (KDS 41 20 20 4.2.2) ──
    discriminant = 1.0
    rho_req = 0.0
    _phi_iter = 0
    for _phi_iter in range(10):
        Mn_Nmm = Mu_Nmm / phi
        Rn = Mn_Nmm / (b * d ** 2)
        discriminant = 1 - (2 * Rn) / (alpha1 * fc_k)
        if discriminant < 0:
            break

        rho_req = (alpha1 * fc_k / fy) * (1 - np.sqrt(discriminant))

        As_iter = rho_req * b * d
        a_iter = (As_iter * fy) / (alpha1 * fc_k * b)
        c_iter = a_iter / beta1
        epsilon_t_iter = epsilon_cu * (d - c_iter) / c_iter if c_iter > 0 else 0.005
        phi_new = _calc_phi(epsilon_t_iter, fy)  # KDS 14 20 10

        if abs(phi_new - phi) < 1e-4:
            phi = phi_new
            break
        phi = phi_new

    steps['phi'] = phi
    steps['phi_iters'] = _phi_iter + 1
    steps['Mn_Nmm'] = Mu_Nmm / phi if discriminant >= 0 else 0
    steps['Rn'] = (Mu_Nmm / phi) / (b * d ** 2) if discriminant >= 0 else 0
    steps['discriminant'] = discriminant

    if discriminant < 0:
        warnings.append("오류: 단면이 너무 작아 휨모멘트를 버틸 수 없습니다 (NG).")
        return 0.0, warnings, steps

    steps['rho_req_calculated'] = rho_req

    # 최소 철근비
    rho_min1 = (0.25 * np.sqrt(fc_k)) / fy
    rho_min2 = 1.4 / fy
    rho_min = max(rho_min1, rho_min2)
    steps['rho_min1'] = rho_min1
    steps['rho_min2'] = rho_min2
    steps['rho_min'] = rho_min

    if rho_req < rho_min:
        rho_req = rho_min
        warnings.append(f"정보: 최소 철근비({rho_min:.4f}) 미달 → 상향 조정.")
    steps['rho_req_final'] = rho_req

    As = rho_req * b * d
    steps['As_calculated'] = As

    # 최종 ε_t 재계산
    a = (As * fy) / (alpha1 * fc_k * b)
    c = a / beta1
    epsilon_t = epsilon_cu * (d - c) / c if c > 0 else 0.005
    steps['a'] = a
    steps['c'] = c
    steps['epsilon_t'] = epsilon_t

    if epsilon_t < 0.004:
        warnings.append(f"경고: εt={epsilon_t:.4f} < 0.004 — 최대 철근비 초과 (NG).")

    rho_max = (0.85 * beta1 * fc_k / fy) * (0.003 / (0.003 + 0.004))
    steps['rho_max'] = rho_max
    steps['rho_max_ok'] = epsilon_t >= 0.004

    return As, warnings, steps


# ═══════════════════════════════════════════════════════════════════════
# 보 검토 — 배근 상세
# ═══════════════════════════════════════════════════════════════════════

def _review_rebar(As_req, b, cover=40.0, d_b_stirrup=10.0, max_agg_size=25.0):
    """
    KDS 기준 철근 배치 (검토 모드).

    Returns:
        (rebar_string, As_provided, layer, warnings, rebar_steps)
    """
    warnings = []
    steps = {}

    rebar_sizes = ["D13", "D16", "D19", "D22", "D25", "D29", "D32"]
    min_clear_spacing_agg = (4 / 3) * max_agg_size
    b_net = b - 2 * cover - 2 * d_b_stirrup
    steps['cover'] = cover
    steps['d_b_stirrup'] = d_b_stirrup
    steps['max_agg_size'] = max_agg_size
    steps['min_clear_spacing_agg'] = min_clear_spacing_agg
    steps['b_net'] = b_net

    As_provided = 0.0
    rebar_string = "N/A"
    layer = 1
    found = False

    for size_name in rebar_sizes:
        spec = REBAR_SPECS[size_name]
        d_b = spec["diameter"]
        A_b = spec["area"]
        S_min = max(min_clear_spacing_agg, d_b)

        n = int(max(np.ceil(As_req / A_b), 2))
        req_width = n * d_b + (n - 1) * S_min

        if req_width <= b_net:
            As_provided = n * A_b
            rebar_string = f"{n}-{size_name}"
            steps['selected_rebar_diameter'] = d_b
            found = True
            break

    if not found:
        layer = 2
        d_b_D25 = REBAR_SPECS["D25"]["diameter"]
        A_b_D25 = REBAR_SPECS["D25"]["area"]
        n = int(max(np.ceil(As_req / A_b_D25), 2))
        As_provided = n * A_b_D25
        rebar_string = f"{n}-D25"
        steps['selected_rebar_diameter'] = d_b_D25
        warnings.append("경고: 1단 배근 불가 → D25 2단 배근 적용.")

    steps['As_provided'] = As_provided
    steps['rebar_string'] = rebar_string
    steps['layer'] = layer

    return rebar_string, As_provided, layer, warnings, steps


# ═══════════════════════════════════════════════════════════════════════
# 보 검토 — 전단 설계
# ═══════════════════════════════════════════════════════════════════════

def _review_shear(Vu, b, d, fc_k, fy_t=400.0, As_tension=0.0, Mu=0.0):
    """
    KDS 14 20 22 §4.3 — 전단 설계 (검토 모드).

    As_tension, Mu가 제공되면 상세식 사용:
      Vc = (0.16√fck + 17.6ρw·Vud/Mu) × bw × d  (KDS 14 20 22 4.3.2)
    제공되지 않으면 간편식:
      Vc = (1/6)√fck × bw × d

    Returns:
        (s_final, warnings, shear_steps)
    """
    warnings = []
    steps = {}

    if b <= 0 or d <= 0 or fc_k <= 0 or fy_t <= 0:
        warnings.append("오류: b, d, fck, fy 중 0 이하 값이 있습니다.")
        return 0.0, warnings, steps

    phi = 0.75
    lambda_factor = 1.0
    A_sb = 71.33  # D10
    A_v = 2 * A_sb
    steps['phi'] = phi
    steps['fy_t'] = fy_t
    steps['d'] = d
    steps['A_v'] = A_v

    Vu_N = abs(Vu) * 1000
    steps['Vu_N'] = Vu_N

    Vn_N = Vu_N / phi
    steps['Vn_N'] = Vn_N

    # Vc 계산: 상세식 또는 간편식  # KDS 14 20 22 4.3.2
    if As_tension > 0 and abs(Mu) > 0.01:
        rho_w = As_tension / (b * d)
        Mu_Nmm = abs(Mu) * 1e6  # kN·m → N·mm
        Vud_over_Mu = min(Vu_N * d / Mu_Nmm, 1.0)  # ≤ 1.0 제한
        Vc_N = (0.16 * lambda_factor * np.sqrt(fc_k)
                + 17.6 * rho_w * Vud_over_Mu) * b * d
        steps['shear_formula'] = 'detailed'
        steps['rho_w'] = rho_w
        steps['Vud_over_Mu'] = Vud_over_Mu
    else:
        Vc_N = (1.0 / 6.0) * lambda_factor * np.sqrt(fc_k) * b * d
        steps['shear_formula'] = 'simplified'
    # 상한: Vc ≤ (5/18)√fck × bw × d  # KDS 14 20 22
    Vc_max_N = (5.0 / 18.0) * np.sqrt(fc_k) * b * d
    Vc_N = min(Vc_N, Vc_max_N)
    steps['Vc_N'] = Vc_N

    Vs_N = Vn_N - Vc_N
    steps['Vs_N'] = Vs_N

    Vs_max_N = (2 / 3) * np.sqrt(fc_k) * b * d
    steps['Vs_max_N'] = Vs_max_N

    if Vs_N > Vs_max_N:
        warnings.append("오류: 전단력이 너무 커서 단면 파괴 (NG).")
        return 0.0, warnings, steps

    if Vs_N > 0:
        s_req = (A_v * fy_t * d) / Vs_N
    else:
        s_req = 1e6
        warnings.append("정보: 콘크리트 전단강도로 충분 → 최소 전단철근 규정 적용.")
    steps['s_req'] = s_req

    s_max_Av = (A_v * fy_t) / max(0.0625 * np.sqrt(fc_k) * b, 0.35 * b)
    steps['s_max_Av'] = s_max_Av

    Vc_limit_N = (1 / 3) * np.sqrt(fc_k) * b * d
    steps['Vc_limit_N'] = Vc_limit_N

    if Vs_N <= Vc_limit_N:
        s_max_geom = min(d / 2, 600.0)
    else:
        s_max_geom = min(d / 4, 300.0)
    steps['s_max_geom'] = s_max_geom

    s_raw = min(s_req, s_max_Av, s_max_geom)
    steps['s_raw'] = s_raw

    s_final = max(np.floor(s_raw / 50.0) * 50.0, 100.0)
    steps['s_final'] = s_final

    return s_final, warnings, steps


# ═══════════════════════════════════════════════════════════════════════
# 보 — 위치별 검토
# ═══════════════════════════════════════════════════════════════════════

def _parse_rebar_string(rebar_str):
    """배근 문자열에서 면적 계산. 예: '3-D19' → (3, 19.1, 859.5)"""
    import re as _re
    if not rebar_str:
        return 0, 0.0, 0.0
    m = _re.match(r'(\d+)-D(\d+)', str(rebar_str).strip())
    if not m:
        return 0, 0.0, 0.0
    n = int(m.group(1))
    d_num = int(m.group(2))
    # 철근 직경 매핑
    _dia_map = {10: 9.53, 13: 12.7, 16: 15.9, 19: 19.1, 22: 22.2, 25: 25.4, 29: 28.6, 32: 31.8, 35: 35.8}
    dia = _dia_map.get(d_num, d_num * 1.0)
    area = n * (np.pi / 4.0) * dia ** 2
    return n, dia, area


def _parse_stirrup_string(stir_str):
    """스터럽 문자열 파싱. 예: '2-D10@125' → (n_legs, dia, spacing, Av)"""
    import re as _re
    if not stir_str:
        return 2, 9.53, 0.0, 142.66  # 기본값 2-D10
    m = _re.match(r'(\d+)-D(\d+)\s*@\s*(\d+)', str(stir_str).strip())
    if not m:
        return 2, 9.53, 0.0, 142.66
    n_legs = int(m.group(1))
    d_num = int(m.group(2))
    spacing = float(m.group(3))
    _dia_map = {10: 9.53, 13: 12.7, 16: 15.9}
    dia = _dia_map.get(d_num, d_num * 1.0)
    Av = n_legs * (np.pi / 4.0) * dia ** 2
    return n_legs, dia, spacing, Av


def _calc_phi_Mn(As, b, d, fc_k, fy):
    """주어진 As로 φMn 계산 (단철근 모델, KDS 14 20 20). 반환: (phi_Mn_kNm, phi, a, c, epsilon_t)"""
    if As <= 0 or b <= 0 or d <= 0 or fc_k <= 0 or fy <= 0:
        return 0.0, 0.85, 0.0, 0.0, 0.005
    alpha1, beta1 = _get_alpha1_beta1(fc_k)  # KDS 14 20 20 표 4.1-2
    ecu = _get_epsilon_cu(fc_k)  # KDS 14 20 20
    a = (As * fy) / (alpha1 * fc_k * b)
    c = a / beta1
    epsilon_t = ecu * (d - c) / c if c > 0 else 0.1
    phi = _calc_phi(epsilon_t, fy)  # KDS 14 20 10
    phi_Mn = phi * As * fy * (d - a / 2.0) / 1e6  # N·mm → kN·m
    return phi_Mn, phi, a, c, epsilon_t


def _calc_phi_Mn_doubly(As, As_comp, b, d, d_prime, fc_k, fy):
    """복철근 보 φMn 계산 (KDS 14 20 20).
    As: 인장철근 면적 (mm²)
    As_comp: 압축철근 면적 (mm²)
    d: 인장철근 유효깊이 (mm)
    d_prime: 압축철근 깊이 (mm, 압축연단~압축철근 도심)
    반환: dict {phi_Mn, phi, a, c, epsilon_t, cb, Ts_kN, Cs_kN, Cc_kN}
    """
    if As <= 0 or b <= 0 or d <= 0 or fc_k <= 0 or fy <= 0:
        return {'phi_Mn': 0, 'phi': 0.85, 'a': 0, 'c': 0, 'epsilon_t': 0.005,
                'cb': 0, 'Ts_kN': 0, 'Cs_kN': 0, 'Cc_kN': 0}

    alpha1, beta1 = _get_alpha1_beta1(fc_k)  # KDS 14 20 20 표 4.1-2
    ecu = _get_epsilon_cu(fc_k)  # KDS 14 20 20
    Es = 200000.0  # MPa
    eps_y = fy / Es

    # 이분법으로 c 탐색 (힘 평형: Cc + Cs = Ts)  # KDS 14 20 20
    c_lo, c_hi = 1e-6, d * 2.0
    for _ in range(80):
        c = (c_lo + c_hi) / 2.0
        a = beta1 * c
        Cc = alpha1 * fc_k * a * b  # N
        eps_s_comp = ecu * (c - d_prime) / c if c > 0 else 0
        fs_comp = min(max(eps_s_comp * Es, -fy), fy)
        Cs = As_comp * fs_comp  # N
        Ts = As * fy  # N
        residual = Cc + Cs - Ts
        if residual > 0:
            c_hi = c
        else:
            c_lo = c
        if abs(residual) < 1.0:
            break

    c = (c_lo + c_hi) / 2.0
    a = beta1 * c
    Cc = alpha1 * fc_k * a * b
    eps_s_comp = ecu * (c - d_prime) / c if c > 0 else 0
    fs_comp = min(max(eps_s_comp * Es, -fy), fy)
    Cs = As_comp * fs_comp
    Ts = As * fy

    epsilon_t = ecu * (d - c) / c if c > 0 else 0.1
    cb = ecu / (ecu + eps_y) * d

    phi = _calc_phi(epsilon_t, fy)  # KDS 14 20 10

    Mn = Cc * (d - a / 2.0) + Cs * (d - d_prime)  # N·mm
    phi_Mn = phi * Mn / 1e6  # kN·m

    return {
        'phi_Mn': phi_Mn, 'phi': phi, 'a': a, 'c': c, 'epsilon_t': epsilon_t,
        'cb': cb, 'Ts_kN': Ts / 1000.0, 'Cs_kN': Cs / 1000.0, 'Cc_kN': Cc / 1000.0,
    }


def _calc_phi_Mn_layers(layers, b, h, fc_k, fy):
    """Layer별 복철근 φMn 계산 (KDS 14 20 20).
    각 철근층의 위치별 변형률·응력을 개별 계산.

    Args:
        layers: [(As_mm2, d_from_comp_edge_mm), ...] 각 철근층 (압축연단 기준 거리)
                예: [(859.5, 215), (253.4, 125), (595.8, 35)]
                    상부근 d=215, Skin d=125, 하부근 d=35
        b: 폭 (mm)
        h: 전체 높이 (mm)
        fc_k, fy: 재료 강도 (MPa)

    Returns:
        dict {phi_Mn, phi, a, c, epsilon_t, cb, Ts_kN, Cs_kN, Cc_kN, layers_detail}
    """
    if not layers or b <= 0 or fc_k <= 0 or fy <= 0:
        return {'phi_Mn': 0, 'phi': 0.85, 'a': 0, 'c': 0, 'epsilon_t': 0.005,
                'cb': 0, 'Ts_kN': 0, 'Cs_kN': 0, 'Cc_kN': 0}

    alpha1, beta1 = _get_alpha1_beta1(fc_k)
    ecu = _get_epsilon_cu(fc_k)
    Es = 200000.0
    eps_y = fy / Es

    # 최대 d (가장 먼 인장철근)
    d_max = max(d_i for _, d_i in layers)

    # 이분법으로 c 탐색 (힘 평형)
    c_lo, c_hi = 1e-6, h * 2.0
    for _ in range(100):
        c = (c_lo + c_hi) / 2.0
        a = min(beta1 * c, h)
        Cc = alpha1 * fc_k * a * b  # N

        F_rebar = 0.0  # 철근 합력 (인장 양수, 압축 음수)
        for As_i, d_i in layers:
            eps_i = ecu * (d_i - c) / c if c > 0 else 0  # 양수=인장, 음수=압축
            fs_i = min(max(eps_i * Es, -fy), fy)
            F_rebar += As_i * fs_i  # N

        # 평형: Cc - F_rebar = 0 (Cc는 압축, F_rebar은 인장-압축 합산)
        residual = Cc - F_rebar
        if residual > 0:
            c_hi = c
        else:
            c_lo = c
        if abs(residual) < 1.0:
            break

    # 수렴된 c로 최종 계산
    c = (c_lo + c_hi) / 2.0
    a = min(beta1 * c, h)
    Cc = alpha1 * fc_k * a * b

    total_Ts = 0.0  # 인장 합계 (kN)
    total_Cs = 0.0  # 압축 합계 (kN)
    Mn = Cc * (d_max - a / 2.0)  # 콘크리트 기여 (압축연단~인장근 기준)

    layers_detail = []
    for As_i, d_i in layers:
        eps_i = ecu * (d_i - c) / c if c > 0 else 0
        fs_i = min(max(eps_i * Es, -fy), fy)
        F_i = As_i * fs_i  # N
        Mn += F_i * (d_i - d_max)  # 인장근 기준 모멘트 (d_max 기준이면 부호 주의)
        if F_i > 0:
            total_Ts += F_i / 1000.0
        else:
            total_Cs += F_i / 1000.0  # 음수
        layers_detail.append({'As': As_i, 'd': d_i, 'eps': eps_i, 'fs': fs_i, 'F_kN': F_i / 1000.0})

    # 모멘트 재계산: 압축연단 기준 (더 정확)
    Mn = 0.0
    for As_i, d_i in layers:
        eps_i = ecu * (d_i - c) / c if c > 0 else 0
        fs_i = min(max(eps_i * Es, -fy), fy)
        Mn += As_i * fs_i * d_i  # N·mm
    Mn += Cc * (a / 2.0)  # Cc의 합력 위치는 압축연단에서 a/2
    # 실제로는: Mn = Σ(F_i × d_i) - Cc × (a/2) 가 아니라
    # 압축연단 기준: Mn = Σ(T_i × d_i) + Cc×(a/2)... 부호 정리 필요

    # 깔끔하게: 단면 도심이 아닌, 각 힘의 모멘트를 직접 합산
    # 압축연단(하단=0) 기준으로 모멘트 합산
    Mn = 0.0
    for As_i, d_i in layers:
        eps_i = ecu * (d_i - c) / c if c > 0 else 0
        fs_i = min(max(eps_i * Es, -fy), fy)
        Mn += As_i * fs_i * d_i  # 인장: +, 압축: -
    Mn -= Cc * (a / 2.0)  # Cc는 압축(-)이지만 d=a/2 위치에서 작용, 반시계 모멘트
    # 정리: Mn = Σ(As_i * fs_i * d_i) - Cc * (a/2)
    # 이것은 압축연단 기준 모멘트. 인장근이 멀수록 Mn 증가.

    epsilon_t = ecu * (d_max - c) / c if c > 0 else 0.1
    cb = ecu / (ecu + eps_y) * d_max

    phi = _calc_phi(epsilon_t, fy)  # KDS 14 20 10

    phi_Mn = phi * abs(Mn) / 1e6  # kN·m

    return {
        'phi_Mn': phi_Mn, 'phi': phi, 'a': a, 'c': c, 'epsilon_t': epsilon_t,
        'cb': cb,
        'Ts_kN': total_Ts, 'Cs_kN': abs(total_Cs), 'Cc_kN': Cc / 1000.0,
        'layers_detail': layers_detail,
    }


def _parse_skin_rebar(skin_str):
    """Skin 배근 파싱. '1/1 - D13' → (n_each_side, dia, As_total).
    n/n - Dxx 형식: 각 측면 n개, 양측 합산."""
    import re as _re
    if not skin_str:
        return 0, 0.0, 0.0
    s = str(skin_str).strip()
    m = _re.match(r'(\d+)/(\d+)\s*-?\s*D(\d+)', s)
    if m:
        n1 = int(m.group(1))
        n2 = int(m.group(2))
        d_num = int(m.group(3))
        spec = REBAR_SPECS.get(f"D{d_num}", {})
        dia = spec.get('diameter', d_num * 1.0)
        area_each = spec.get('area', (np.pi / 4.0) * dia ** 2)
        n_total = n1 + n2
        return n_total, dia, n_total * area_each
    return 0, 0.0, 0.0


def _review_beam_location(Mu_neg, Mu_pos, Vu, b, h, fc_k, fy, cover=40.0,
                           Loc_top=None, Loc_bot=None,
                           rebar_top_str=None, rebar_bot_str=None,
                           stirrup_str=None, skin_rebar_str=None,
                           b_top=0, h_top=0):
    """
    단일 위치 (END-I / MID / END-J) 검토.
    구조계산서 배근(rebar_top_str/rebar_bot_str)이 주어지면 그걸로 φMn 계산.
    skin_rebar_str이 있으면 Skin As를 인장철근에 포함.

    Returns:
        dict with flexural_neg, flexural_pos, shear, ok_overall
    """
    result = {}

    # 방어: fck=0 또는 fy=0이면 빈 결과 반환
    if fc_k <= 0 or fy <= 0 or b <= 0 or h <= 0:
        _empty = {'Mu': 0, 'As_req': 0, 'rebar_string': '-', 'As_provided': 0,
                  'phi_Mn': 0, 'phi': 0, 'a': 0, 'c': 0, 'epsilon_t': 0,
                  'cb': 0, 'Ts_kN': 0, 'Cs_kN': 0, 'Cc_kN': 0,
                  'Mcr_kNm': 0, '1.2Mcr': 0, 'ok_12Mcr': True,
                  'ok': False, 'check_ratio': 999,
                  'warnings': ['오류: fck, fy, b, h 중 0 이하 값이 있습니다.'],
                  'flexural_steps': {}}
        result['flexural_neg'] = _empty.copy()
        result['flexural_pos'] = _empty.copy()
        result['shear'] = {'Vu': 0, 's': 0, 'phi_Vc': 0, 'phi_Vs': 0,
                           'phi_Vs_req': 0, 'phi_Vs_provided': 0,
                           'ok': False, 'warnings': [], 'shear_steps': {}}
        result['crack'] = {'fs': 0, 'cc': 0, 's_rebar': 0, 'smax': 0, 'ok': False}
        result['ok_overall'] = False
        return result

    _alpha1, _beta1_local = _get_alpha1_beta1(fc_k)  # KDS 14 20 20 표 4.1-2

    # 1.2Mcr 계산 (KDS 14 20 20)  # fr = 0.63√fck, Mcr = fr×Ig/yt
    _fr = 0.63 * np.sqrt(fc_k)  # MPa (파괴계수)
    _Ig = b * h ** 3 / 12.0  # mm4
    _yt = h / 2.0  # mm
    _Mcr_kNm = _fr * _Ig / _yt / 1e6  # kN·m
    _12Mcr = 1.2 * _Mcr_kNm

    # 균열 제어 검사 (KDS 14 20 50 4.3)
    # fs = (2/3)*fy (사용하중 근사), cc = 순피복두께
    _fs_crack = (2.0 / 3.0) * fy
    # cc: cover가 Loc 기반이면 역산, 아니면 직접 사용
    _cc_crack = cover  # 기본값은 입력 cover
    # 철근 간격 s: 인장철근 기준
    n_top_crack, dia_top_crack, _ = _parse_rebar_string(rebar_top_str)
    _stir_n_c, _stir_dia_c, _, _ = _parse_stirrup_string(stirrup_str)
    if n_top_crack >= 2 and dia_top_crack > 0:
        _s_rebar = (b - 2 * _cc_crack - 2 * _stir_dia_c - n_top_crack * dia_top_crack) / max(n_top_crack - 1, 1)
    else:
        _s_rebar = 0.0
    _smax1 = 380.0 * (280.0 / _fs_crack) - 2.5 * _cc_crack
    _smax2 = 300.0 * (280.0 / _fs_crack)
    _smax = min(_smax1, _smax2)
    _crack_ok = _smax >= _s_rebar if _s_rebar > 0 else True
    _crack_result = {
        'fs': _fs_crack, 'cc': _cc_crack,
        's_rebar': _s_rebar, 'smax': _smax,
        'ok': _crack_ok,
    }

    # Skin 철근 파싱 (BeST: 총 As에 포함)
    _skin_n, _skin_dia, _skin_As = _parse_skin_rebar(skin_rebar_str)

    # ── 상부근 (부모멘트: 상부=인장, 하부=압축) ──
    As_neg, warn_neg, steps_neg = _review_flexural(Mu_neg, b, h, fc_k, fy, cover, Loc=Loc_top)
    d_neg = steps_neg.get('d', h - 60.0)

    # 구조계산서 배근 파싱
    n_top, dia_top, As_doc_top = _parse_rebar_string(rebar_top_str)
    n_bot, dia_bot, As_doc_bot = _parse_rebar_string(rebar_bot_str)

    # Skin As를 인장철근에 포함 (BeST 방식: 전체 Skin을 인장측에 합산)
    As_doc_top_with_skin = As_doc_top + _skin_As if As_doc_top > 0 else As_doc_top

    # 부모멘트 시 하부근=압축측 위치 (압축연단에서의 거리)
    d_bot_for_layer = Loc_bot if Loc_bot and Loc_bot > 0 else 35.0

    if As_doc_top > 0:
        _neg_rebar_str = rebar_top_str
        _neg_As_prov = As_doc_top_with_skin  # Skin 포함

        if _skin_As > 0 and As_doc_bot > 0:
            # Layer별 계산 (Skin 있을 때 — 각 층 위치별 변형률 계산)
            _layers_neg = [
                (As_doc_top, d_neg),                  # 상부근 (인장)
                (_skin_As, h / 2.0),                  # Skin (단면 중간)
                (As_doc_bot, d_bot_for_layer),        # 하부근 (압축)
            ]
            _dr = _calc_phi_Mn_layers(_layers_neg, b, h, fc_k, fy)
            _neg_phi_Mn = _dr['phi_Mn']
            _neg_phi = _dr['phi']
            _neg_a = _dr['a']
            _neg_c = _dr['c']
            _neg_et = _dr['epsilon_t']
            _neg_cb = _dr['cb']
            _neg_Ts = _dr['Ts_kN']
            _neg_Cs = _dr['Cs_kN']
            _neg_Cc = _dr['Cc_kN']
        elif As_doc_bot > 0 and Loc_bot and Loc_bot > 0:
            # 복철근 모델 (Skin 없음): 상부=인장, 하부=압축
            d_prime_neg = d_bot_for_layer
            _dr = _calc_phi_Mn_doubly(As_doc_top, As_doc_bot, b, d_neg, d_prime_neg, fc_k, fy)
            _neg_phi_Mn = _dr['phi_Mn']
            _neg_phi = _dr['phi']
            _neg_a = _dr['a']
            _neg_c = _dr['c']
            _neg_et = _dr['epsilon_t']
            _neg_cb = _dr['cb']
            _neg_Ts = _dr['Ts_kN']
            _neg_Cs = _dr['Cs_kN']
            _neg_Cc = _dr['Cc_kN']
        else:
            # 단철근 모델
            _neg_phi_Mn, _neg_phi, _neg_a, _neg_c, _neg_et = _calc_phi_Mn(As_doc_top, b, d_neg, fc_k, fy)
            _neg_cb = (_get_epsilon_cu(fc_k) / (_get_epsilon_cu(fc_k) + fy / 200000.0)) * d_neg
            _neg_Ts = As_doc_top * fy / 1000.0
            _neg_Cc = _alpha1 * fc_k * _neg_a * b / 1000.0 if _neg_a > 0 else 0
            _neg_Cs = _neg_Ts - _neg_Cc

        _neg_ok = (abs(Mu_neg) <= _neg_phi_Mn + 0.01) if Mu_neg != 0 else True
        warn_neg_final = []
        if _neg_et < 0.004 and Mu_neg != 0:
            warn_neg_final.append(f"주의: 제공 배근 εt={_neg_et:.4f} < 0.004")
        if not _neg_ok and Mu_neg != 0:
            warn_neg_final.append(f"NG: φMn={_neg_phi_Mn:.2f} < Mu={abs(Mu_neg):.2f}")
    else:
        # 구조계산서 배근 없음 → As_req 기반 (단철근)
        _neg_rebar_str, _neg_As_prov, _neg_layer, _neg_warn_rb, _neg_steps_rb = _review_rebar(As_neg, b, cover)
        _neg_phi_Mn, _neg_phi, _neg_a, _neg_c, _neg_et = _calc_phi_Mn(_neg_As_prov, b, d_neg, fc_k, fy)
        _neg_ok = (abs(Mu_neg) <= _neg_phi_Mn + 0.01) if Mu_neg != 0 else True
        warn_neg_final = warn_neg + (_neg_warn_rb if '_neg_warn_rb' in locals() else [])
        _neg_cb = (_get_epsilon_cu(fc_k) / (_get_epsilon_cu(fc_k) + fy / 200000.0)) * d_neg
        _neg_Ts = _neg_As_prov * fy / 1000.0
        _neg_Cc = _alpha1 * fc_k * _neg_a * b / 1000.0 if _neg_a > 0 else 0
        _neg_Cs = _neg_Ts - _neg_Cc

    result['flexural_neg'] = {
        'Mu': Mu_neg,
        'As_req': As_neg,
        'rebar_string': _neg_rebar_str,
        'As_provided': _neg_As_prov,
        'phi_Mn': _neg_phi_Mn,
        'phi': _neg_phi,
        'a': _neg_a, 'c': _neg_c, 'epsilon_t': _neg_et,
        'cb': _neg_cb, 'Ts_kN': _neg_Ts, 'Cs_kN': _neg_Cs, 'Cc_kN': _neg_Cc,
        'Mcr_kNm': _Mcr_kNm, '1.2Mcr': _12Mcr,
        'ok_12Mcr': _neg_phi_Mn >= _12Mcr if _neg_phi_Mn > 0 else True,
        'ok': _neg_ok,
        'check_ratio': abs(Mu_neg) / _neg_phi_Mn if _neg_phi_Mn > 0 else 999,
        'warnings': warn_neg_final,
        'flexural_steps': steps_neg,
    }

    # ── 하부근 (정모멘트: 하부=인장, 상부=압축) ──
    # T형보: 정모멘트에서 압축 = 상부 플랜지 → b_top 사용
    b_eff_pos = b_top if b_top > 0 and h_top > 0 else b
    As_pos, warn_pos, steps_pos = _review_flexural(Mu_pos, b_eff_pos, h, fc_k, fy, cover, Loc=Loc_bot)
    d_pos = steps_pos.get('d', h - 60.0)

    # n_bot, As_doc_bot은 위에서 이미 파싱됨
    As_doc_bot_with_skin = As_doc_bot + _skin_As if As_doc_bot > 0 else As_doc_bot
    d_top_for_layer = Loc_top if Loc_top and Loc_top > 0 else 35.0

    if As_doc_bot > 0:
        _pos_rebar_str = rebar_bot_str
        _pos_As_prov = As_doc_bot_with_skin  # Skin 포함

        if _skin_As > 0 and As_doc_top > 0:
            # Layer별 계산 (Skin 있을 때 — 정모멘트: 압축연단=상부)
            # 정모멘트에서는 압축연단이 상부이므로 d를 상부 기준으로 재정의
            _layers_pos = [
                (As_doc_top, d_top_for_layer),       # 상부근 (압축) — 압축연단에서 가까움
                (_skin_As, h / 2.0),                  # Skin (단면 중간)
                (As_doc_bot, d_pos),                  # 하부근 (인장) — 압축연단에서 멀음
            ]
            _dr = _calc_phi_Mn_layers(_layers_pos, b_eff_pos, h, fc_k, fy)
            _pos_phi_Mn = _dr['phi_Mn']
            _pos_phi = _dr['phi']
            _pos_a = _dr['a']
            _pos_c = _dr['c']
            _pos_et = _dr['epsilon_t']
            _pos_cb = _dr['cb']
            _pos_Ts = _dr['Ts_kN']
            _pos_Cs = _dr['Cs_kN']
            _pos_Cc = _dr['Cc_kN']
        elif As_doc_top > 0 and Loc_top and Loc_top > 0:
            # 복철근 모델 (Skin 없음): 하부=인장, 상부=압축
            d_prime_pos = d_top_for_layer
            _dr = _calc_phi_Mn_doubly(As_doc_bot, As_doc_top, b_eff_pos, d_pos, d_prime_pos, fc_k, fy)
            _pos_phi_Mn = _dr['phi_Mn']
            _pos_phi = _dr['phi']
            _pos_a = _dr['a']
            _pos_c = _dr['c']
            _pos_et = _dr['epsilon_t']
            _pos_cb = _dr['cb']
            _pos_Ts = _dr['Ts_kN']
            _pos_Cs = _dr['Cs_kN']
            _pos_Cc = _dr['Cc_kN']
        else:
            # 단철근 모델 — T형보면 b_eff_pos 사용
            _pos_phi_Mn, _pos_phi, _pos_a, _pos_c, _pos_et = _calc_phi_Mn(As_doc_bot, b_eff_pos, d_pos, fc_k, fy)
            _pos_cb = (_get_epsilon_cu(fc_k) / (_get_epsilon_cu(fc_k) + fy / 200000.0)) * d_pos
            _pos_Ts = As_doc_bot * fy / 1000.0
            _pos_Cc = _alpha1 * fc_k * _pos_a * b_eff_pos / 1000.0 if _pos_a > 0 else 0
            _pos_Cs = _pos_Ts - _pos_Cc

        _pos_ok = (abs(Mu_pos) <= _pos_phi_Mn + 0.01) if Mu_pos != 0 else True
        warn_pos_final = []
        if _pos_et < 0.004 and Mu_pos != 0:
            warn_pos_final.append(f"주의: 제공 배근 εt={_pos_et:.4f} < 0.004")
        if not _pos_ok and Mu_pos != 0:
            warn_pos_final.append(f"NG: φMn={_pos_phi_Mn:.2f} < Mu={abs(Mu_pos):.2f}")
    else:
        _pos_rebar_str, _pos_As_prov, _pos_layer, _pos_warn_rb, _pos_steps_rb = _review_rebar(As_pos, b, cover)
        _pos_phi_Mn, _pos_phi, _pos_a, _pos_c, _pos_et = _calc_phi_Mn(_pos_As_prov, b, d_pos, fc_k, fy)
        _pos_ok = (abs(Mu_pos) <= _pos_phi_Mn + 0.01) if Mu_pos != 0 else True
        warn_pos_final = warn_pos + (_pos_warn_rb if '_pos_warn_rb' in locals() else [])
        _pos_cb = (_get_epsilon_cu(fc_k) / (_get_epsilon_cu(fc_k) + fy / 200000.0)) * d_pos
        _pos_Ts = _pos_As_prov * fy / 1000.0
        _pos_Cc = _alpha1 * fc_k * _pos_a * b / 1000.0 if _pos_a > 0 else 0
        _pos_Cs = _pos_Ts - _pos_Cc

    result['flexural_pos'] = {
        'Mu': Mu_pos,
        'As_req': As_pos,
        'rebar_string': _pos_rebar_str,
        'As_provided': _pos_As_prov,
        'phi_Mn': _pos_phi_Mn,
        'phi': _pos_phi,
        'a': _pos_a, 'c': _pos_c, 'epsilon_t': _pos_et,
        'cb': _pos_cb, 'Ts_kN': _pos_Ts, 'Cs_kN': _pos_Cs, 'Cc_kN': _pos_Cc,
        'Mcr_kNm': _Mcr_kNm, '1.2Mcr': _12Mcr,
        'ok_12Mcr': _pos_phi_Mn >= _12Mcr if _pos_phi_Mn > 0 else True,
        'ok': _pos_ok,
        'check_ratio': abs(Mu_pos) / _pos_phi_Mn if _pos_phi_Mn > 0 else 999,
        'warnings': warn_pos_final,
        'flexural_steps': steps_pos,
    }

    # 전단 (항상 상세식 사용)  # KDS 14 20 22
    d_for_shear = steps_neg.get('d', h - 60.0)
    _As_tens_for_shear = _neg_As_prov if _neg_As_prov > 0 else (As_doc_top_with_skin if As_doc_top > 0 else 0)
    _Mu_for_shear = abs(Mu_neg) if abs(Mu_neg) > 0 else abs(Mu_pos)
    s_final, warn_shear, steps_shear = _review_shear(
        Vu, b, d_for_shear, fc_k,
        As_tension=_As_tens_for_shear, Mu=_Mu_for_shear)
    _shear_phi = steps_shear.get('phi', 0.75)
    _phi_Vc = _shear_phi * steps_shear.get('Vc_N', 0) / 1000.0  # N → kN
    _Vs_actual = steps_shear.get('Vs_N', 0)
    _phi_Vs_req = _shear_phi * max(_Vs_actual, 0) / 1000.0  # 필요 φVs (N → kN)

    # 구조계산서 스터럽 기반 제공 φVs
    _phi_Vs_provided = 0.0
    if stirrup_str:
        _s_n, _s_dia, _s_spacing, _s_Av = _parse_stirrup_string(stirrup_str)
        if _s_spacing > 0 and d_for_shear > 0:
            _fy_t = steps_shear.get('fy_t', 400.0)
            _Vs_prov_N = _s_Av * _fy_t * d_for_shear / _s_spacing
            _phi_Vs_provided = _shear_phi * _Vs_prov_N / 1000.0  # N → kN

    result['shear'] = {
        'Vu': Vu,
        's': s_final,
        'phi_Vc': _phi_Vc,
        'phi_Vs': _phi_Vs_provided if _phi_Vs_provided > 0 else _phi_Vs_req,
        'phi_Vs_req': _phi_Vs_req,
        'phi_Vs_provided': _phi_Vs_provided,
        'ok': s_final > 0 and len(warn_shear) == 0,
        'warnings': warn_shear,
        'shear_steps': steps_shear,
    }

    # 균열 제어
    result['crack'] = _crack_result

    # 종합 판정
    result['ok_overall'] = (
        result['flexural_neg']['ok']
        and result['flexural_pos']['ok']
        and result['shear']['ok']
    )

    return result


def _review_beam(beam_input, fc_k, fy):
    """
    보 1개 전체 검토 (END-I / MID / END-J).

    Args:
        beam_input: {name, h_beam, b_beam, locations: {END_I, MID, END_J}}
        fc_k, fy: 재료

    Returns:
        dict
    """
    name = beam_input.get('name', 'Beam')
    h = float(beam_input['h_beam'])
    b = float(beam_input['b_beam'])
    cover = float(beam_input.get('cover', 40.0))
    Loc_top = float(beam_input.get('Loc_top', 0) or 0)
    Loc_bot = float(beam_input.get('Loc_bot', 0) or 0)
    rebar_top_str = beam_input.get('rebar_top', '')
    rebar_bot_str = beam_input.get('rebar_bot', '')
    stirrup_str = beam_input.get('stirrup', '')
    locations = beam_input.get('locations', {})

    result = {
        'name': name,
        'h_beam': h,
        'b_beam': b,
        'fc_k': fc_k,
        'fy': fy,
        'cover': cover,
        'locations': {},
        # 메타데이터 패스스루 (출력 형식용)
        'software': beam_input.get('software', ''),
        'span_m': beam_input.get('span_m', 0),
        'fys': beam_input.get('fys', 0),
        'stirrup': stirrup_str,
        'rebar_top': rebar_top_str,
        'rebar_bot': rebar_bot_str,
        'skin_rebar': beam_input.get('skin_rebar', ''),
        'b_top': float(beam_input.get('b_top', 0) or 0),
        'h_top': float(beam_input.get('h_top', 0) or 0),
        'load_combinations': beam_input.get('load_combinations', {}),
    }

    for loc_name in ['END_I', 'MID', 'END_J']:
        loc_data = locations.get(loc_name, {})
        Mu_neg = float(loc_data.get('Mu_neg', 0.0))
        Mu_pos = float(loc_data.get('Mu_pos', 0.0))
        Vu = float(loc_data.get('Vu', 0.0))

        result['locations'][loc_name] = _review_beam_location(
            Mu_neg, Mu_pos, Vu, b, h, fc_k, fy, cover=cover,
            Loc_top=Loc_top if Loc_top > 0 else None,
            Loc_bot=Loc_bot if Loc_bot > 0 else None,
            rebar_top_str=rebar_top_str,
            rebar_bot_str=rebar_bot_str,
            stirrup_str=stirrup_str,
            skin_rebar_str=beam_input.get('skin_rebar', ''),
            b_top=float(beam_input.get('b_top', 0) or 0),
            h_top=float(beam_input.get('h_top', 0) or 0),
        )

    # 전체 OK 판정
    result['ok_overall'] = all(
        result['locations'][loc]['ok_overall']
        for loc in result['locations']
    )

    # 검토 불가 항목
    result['not_available'] = {
        'deflection': '분포하중 정보 없이 처짐 검토 불가',
        'crack_control': '사용하중 정보 없이 균열 검토 불가',
        'development_length': '정착길이는 설계모드에서만 검토',
        'imf_detailing': 'IMF 상세는 설계모드에서만 검토',
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# 기둥 검토 — P-M 설계
# ═══════════════════════════════════════════════════════════════════════

def _parse_column_rebar_string(rebar_str):
    """기둥 주근 문자열 파싱. 'N-Dxx' 또는 'NNEa-NR-Dxx' (BeST) 형식 지원.
    반환: (n_col, rebar_type_str, diameter, area_each)
    """
    import re as _re
    if not rebar_str:
        return 0, "", 0.0, 0.0
    s = str(rebar_str).strip()
    # 일반 형식: "8-D25"
    m = _re.match(r'(\d+)\s*-\s*D(\d+)', s)
    if m:
        n = int(m.group(1))
        d_num = int(m.group(2))
        rtype = f"D{d_num}"
        spec = REBAR_SPECS.get(rtype, {})
        dia = spec.get('diameter', d_num * 1.0)
        area = spec.get('area', (np.pi / 4.0) * dia ** 2)
        return n, rtype, dia, area
    # BeST 형식: "12EA - 4R - D19" 또는 "12EA-4R-D19"
    m2 = _re.match(r'(\d+)\s*EA.*?D(\d+)', s, _re.IGNORECASE)
    if m2:
        n = int(m2.group(1))
        d_num = int(m2.group(2))
        rtype = f"D{d_num}"
        spec = REBAR_SPECS.get(rtype, {})
        dia = spec.get('diameter', d_num * 1.0)
        area = spec.get('area', (np.pi / 4.0) * dia ** 2)
        return n, rtype, dia, area
    return 0, "", 0.0, 0.0


def _parse_hoop_string(hoop_str):
    """띠철근 문자열 파싱. 'D10@200' 또는 '2-D10@125' 형식 지원.
    반환: (tie_type_str, tie_diameter, tie_spacing)
    """
    import re as _re
    if not hoop_str:
        return "D10", 9.53, 200.0  # 기본값
    s = str(hoop_str).strip()
    m = _re.match(r'(?:\d+-)?D(\d+)\s*@\s*(\d+)', s)
    if m:
        d_num = int(m.group(1))
        spacing = float(m.group(2))
        rtype = f"D{d_num}"
        spec = REBAR_SPECS.get(rtype, {})
        dia = spec.get('diameter', d_num * 1.0)
        return rtype, dia, spacing
    return "D10", 9.53, 200.0


def _review_column(col_input, fc_k, fy):
    """
    기둥 1개 검토: 입력된 배근 기반 P-M 포락선 OK/NG 판정.

    단면 고정, 배근 고정 (자동 탐색 없음).

    Args:
        col_input: {name, c_column, h_column, Pu, Mux, Muy, rebar_vert, hoop}
        fc_k, fy: 재료

    Returns:
        dict
    """
    name = col_input.get('name', 'Column')
    c_column = float(col_input['c_column'])
    h_column = float(col_input.get('h_column', 0) or 0)
    if h_column <= 0:
        h_column = 0.0  # 값 없음 — 버튼 비활성화로 여기 도달 안 함
    if c_column <= 0:
        c_column = 0.0
    Pu = float(col_input.get('Pu', 0))
    Mux_input = float(col_input.get('Mux', 0))  # 원본 입력값
    Muy_input = float(col_input.get('Muy', 0))  # 원본 입력값
    Mux = Mux_input
    Muy = Muy_input
    Vu_col = float(col_input.get('Vu', 0))
    Mu = float(np.sqrt(Mux ** 2 + Muy ** 2))  # SRSS

    Ag = c_column * c_column

    # SRC 판단 (세장비 검토 전에 필요)
    _steel_str_early = col_input.get('steel_section', '')
    _fy_stl_early = float(col_input.get('fy_stl', 0) or 0)
    _is_src_early = bool(_steel_str_early and _fy_stl_early > 0 and _parse_steel_section(_steel_str_early))

    # ── 세장비 검토 ──
    k = 1.0
    l_u = h_column
    r = 0.3 * c_column
    lambda_ratio = k * l_u / r

    Ec = 8500.0 * (fc_k + 4.0) ** (1.0 / 3.0)
    Ig = c_column ** 4 / 12.0
    beta_d = 0.6  # KDS 기본값
    EI = 0.4 * Ec * Ig / (1.0 + beta_d)
    Pc_N = np.pi ** 2 * EI / (k * l_u) ** 2
    Pc_kN = Pc_N / 1000.0
    Cm = 1.0
    Pu_N = Pu * 1000.0

    slenderness = {
        'k': k, 'l_u': l_u, 'r': r,
        'lambda_ratio': lambda_ratio,
        'Ec': Ec, 'Ig': Ig, 'beta_d': beta_d,
        'EI': EI, 'Pc_kN': Pc_kN, 'Cm': Cm,
    }

    if _is_src_early:
        # SRC: 좌굴은 Pe 기반으로 ΦPn(max)에 이미 반영됨. δ_ns 미적용
        slenderness['category'] = 'src_buckling'
        slenderness['delta_ns'] = 1.0
        slenderness['ok'] = True
    elif lambda_ratio <= 22:
        slenderness['category'] = 'short'
        slenderness['delta_ns'] = 1.0
        slenderness['ok'] = True
    elif lambda_ratio <= 100:
        slenderness['category'] = 'slender'
        if Pu_N < 0.75 * Pc_N:
            delta_ns = max(Cm / (1.0 - Pu_N / (0.75 * Pc_N)), 1.0)
            slenderness['delta_ns'] = delta_ns
            slenderness['ok'] = True
            Mu = delta_ns * Mu
            Mux = delta_ns * Mux
            Muy = delta_ns * Muy
        else:
            slenderness['delta_ns'] = None
            slenderness['ok'] = False
    else:
        slenderness['category'] = 'prohibited'
        slenderness['delta_ns'] = None
        slenderness['ok'] = False

    # ── 입력 배근 파싱 (검토 모드: 자동 탐색 없음) ──
    # SRC: 강구조 기준 φ (KBC 0709)
    # RC: 콘크리트 기준 φ (KDS 14 20 20)
    steel_section_str = col_input.get('steel_section', '')
    fy_stl = float(col_input.get('fy_stl', 0) or 0)
    stl = _parse_steel_section(steel_section_str) if steel_section_str else None
    is_src = stl is not None and fy_stl > 0
    if is_src:
        phi_comp = 0.90  # SRC: P-M 곡선 전체 φ=0.90 (KBC 강구조)
        phi_tens = 0.90
    else:
        phi_comp = 0.65
        phi_tens = 0.85
    alpha1, beta1 = _get_alpha1_beta1(fc_k)  # KDS 14 20 20 표 4.1-2

    _col_cover = float(col_input.get('cover', 0) or 0)

    # 주근 파싱
    rebar_vert_str = col_input.get('rebar_vert', '')
    n_col, rebar_type_col, rebar_diameter_col, rebar_area_col = _parse_column_rebar_string(rebar_vert_str)

    # 띠철근 파싱
    hoop_str = col_input.get('hoop', '')
    tie_type, tie_dia, tie_spacing = _parse_hoop_string(hoop_str)
    _tie_dia_c = tie_dia

    # 최소 편심  # KDS 41 20 22 4.3.4
    e_min = 15 + 0.03 * c_column
    Mu_design = Mu
    is_min_ecc_applied = False
    if Pu > 0:
        e_actual = (Mu * 1000 / Pu)
        if e_actual < e_min:
            Mu_design = (Pu * e_min) / 1000.0
            is_min_ecc_applied = True
    else:
        e_actual = None

    # ── 입력 배근 기반 P-M 검토 (1회, 탐색 없음) ──
    As_total = n_col * rebar_area_col
    As_stl = stl['As'] if is_src else 0.0
    Ac = Ag - As_total - As_stl if is_src else Ag - As_total  # 콘크리트 순면적
    rho = As_total / Ag if Ag > 0 else 0

    cover_approx = _col_cover + _tie_dia_c + rebar_diameter_col / 2.0
    d_eff = c_column - cover_approx
    d_prime = cover_approx
    As_half = As_total / 2.0

    # SRC: EIeff 재계산 + 좌굴 검토 덮어쓰기
    src_data = {}
    if is_src:
        _Es = 200000.0
        # 철근 관성모멘트 (정밀: 각 철근 위치별 Σ A_bar × y_i²)
        # 정사각형 둘레 배치: n_col개 철근, 각 변에 n_per_side개
        _Ab = rebar_area_col  # 1개 면적
        _d_edge = _col_cover + _tie_dia_c + rebar_diameter_col / 2.0  # 연단~철근 중심
        _h2 = c_column / 2.0
        _n_side = int(np.ceil(n_col / 4)) + 1 if n_col > 0 else 2
        Isr = 0.0
        # 상변/하변 철근: y = ±(_h2 - _d_edge)
        _y_top = _h2 - _d_edge
        _y_bot = -(_h2 - _d_edge)
        # 좌변/우변 철근: x = ±(_h2 - _d_edge)
        _x_side = _h2 - _d_edge
        # 상변: _n_side개
        for _i in range(_n_side):
            Isr += _Ab * _y_top ** 2  # y 기준 관성모멘트 (X-X)
        # 하변: _n_side개
        for _i in range(_n_side):
            Isr += _Ab * _y_bot ** 2
        # 좌/우변: 각 (_n_side - 2)개 (코너 중복 제외)
        _n_web = max(_n_side - 2, 0)
        if _n_web > 0:
            for _j in range(_n_web):
                _y_j = _y_bot + (_y_top - _y_bot) * (_j + 1) / (_n_web + 1)
                Isr += _Ab * _y_j ** 2  # 좌변
                Isr += _Ab * _y_j ** 2  # 우변
        Ic = c_column ** 4 / 12.0 - stl['Ix'] - Isr
        if Ic < 0:
            Ic = c_column ** 4 / 12.0 * 0.5  # 안전장치
        C1 = 0.1 + 2.0 * (As_stl / (Ac + As_stl)) if (Ac + As_stl) > 0 else 0.1
        EIeff = _Es * stl['Ix'] + 0.5 * _Es * Isr + C1 * Ec * Ic  # N·mm²
        Pe_N = np.pi ** 2 * EIeff / (k * l_u) ** 2
        Pe_kN = Pe_N / 1000.0

        # Po (SRC)
        Po_N = As_stl * fy_stl + As_total * fy + 0.85 * fc_k * Ac
        Po_kN = Po_N / 1000.0

        # ΦPn(max) (SRC 좌굴 공식)
        if Pe_N >= 0.44 * Po_N:
            Pn_src = Po_N * 0.658 ** (Po_N / Pe_N)
        else:
            Pn_src = 0.877 * Pe_N
        phi_Pn_max_src = 0.75 * Pn_src / 1000.0  # kN

        # 세장비 dict 덮어쓰기
        slenderness['EIeff_src'] = EIeff / 1e6  # kN·m²
        slenderness['Pe_kN'] = Pe_kN
        slenderness['Po_kN'] = Po_kN
        slenderness['C1'] = C1

        src_data = {
            'is_src': True, 'steel_section': steel_section_str, 'fy_stl': fy_stl,
            'As_stl': As_stl, 'Ac': Ac, 'C1': C1,
            'EIeff_kNm2': EIeff / 1e9, 'Pe_kN': Pe_kN, 'Po_kN': Po_kN,
            'phi_Pn_max_src': phi_Pn_max_src,
        }
    h_half = c_column / 2.0

    # 점 A: 순수 압축  # KDS 41 20 22 4.3.3
    if is_src:
        Pn_max = src_data['Po_kN'] * 1000.0  # N (Po)
        phi_Pn_max = src_data['phi_Pn_max_src']  # kN (SRC 좌굴 공식)
    else:
        Pn_max = alpha1 * fc_k * (Ag - As_total) + fy * As_total
        phi_Pn_max = 0.80 * phi_comp * Pn_max / 1000.0

    # 점 B: 균형 파괴  # KDS 14 20 20
    ecu = _get_epsilon_cu(fc_k)
    _Es = 200000.0
    _ecu_Es = ecu * _Es
    eps_y_col = fy / _Es
    c_b = (ecu / (ecu + eps_y_col)) * d_eff
    _stl_arg = stl if is_src else None
    _fystl_arg = fy_stl if is_src else 0
    Pn_b, Mn_b = _src_forces_at_c(c_b, c_column, d_eff, d_prime, As_half,
                                    alpha1, beta1, fc_k, fy, _ecu_Es, _stl_arg, _fystl_arg)
    phi_Pn_b = phi_comp * Pn_b / 1000.0
    phi_Mn_b = phi_comp * Mn_b / 1e6

    # 점 C: 순수 휨 (이분법)
    _c_lo, _c_hi = 1e-6, c_column
    for _ in range(60):
        _c_mid = (_c_lo + _c_hi) / 2.0
        _Pn_c, _ = _src_forces_at_c(_c_mid, c_column, d_eff, d_prime, As_half,
                                     alpha1, beta1, fc_k, fy, _ecu_Es, _stl_arg, _fystl_arg)
        if _Pn_c < 0.0:
            _c_lo = _c_mid
        else:
            _c_hi = _c_mid
        if _c_hi - _c_lo < 0.01:
            break
    c_o = (_c_lo + _c_hi) / 2.0
    _, Mn_o = _src_forces_at_c(c_o, c_column, d_eff, d_prime, As_half,
                                alpha1, beta1, fc_k, fy, _ecu_Es, _stl_arg, _fystl_arg)
    phi_Mn_o = phi_tens * Mn_o / 1e6

    eps_y = fy / 200000.0

    # ── P-M 포락선 검토 (1회) ──
    safe = False
    if Pu <= phi_Pn_max:
        if Pu >= phi_Pn_b:
            M_limit = (phi_Pn_max - Pu) * (phi_Mn_b / (phi_Pn_max - phi_Pn_b)) if phi_Pn_max != phi_Pn_b else phi_Mn_b
            if Mu_design <= M_limit:
                safe = True
        else:
            N_bc = 50
            c_vals = np.linspace(c_b, 1e-6, N_bc + 1)
            P_prev = phi_Pn_b
            M_prev = phi_Mn_b
            M_limit = phi_Mn_o
            for c_i in c_vals[1:]:
                Pn_i, Mn_i = _src_forces_at_c(c_i, c_column, d_eff, d_prime, As_half,
                                               alpha1, beta1, fc_k, fy, _ecu_Es, _stl_arg, _fystl_arg)
                eps_t_i = ecu * max(d_eff - c_i, 0.0) / c_i
                phi_i = _calc_phi(eps_t_i, fy, phi_comp, phi_tens)  # KDS 14 20 10
                P_cur = phi_i * Pn_i / 1000.0
                M_cur = phi_i * Mn_i / 1e6
                if P_cur <= Pu <= P_prev:
                    t = (Pu - P_cur) / (P_prev - P_cur) if P_prev != P_cur else 0.0
                    M_limit = M_cur + t * (M_prev - M_cur)
                    break
                P_prev = P_cur
                M_prev = M_cur
            if Mu_design <= M_limit:
                safe = True

    # ── X-X / Y-Y 분리 검토 ──
    # P-M 곡선에서 Pu에서의 ΦMn 한계값 (정사각형이므로 X=Y 동일)
    if Pu <= phi_Pn_max and safe:
        # M_limit은 위에서 이미 계산됨
        phi_Mnx = M_limit  # X-X 축 ΦMn (Pu에서의 한계)
        phi_Mny = M_limit  # Y-Y 축 ΦMn (정사각형이므로 동일)
    else:
        phi_Mnx = phi_Mn_o if phi_Mn_o > 0 else 0
        phi_Mny = phi_Mn_o if phi_Mn_o > 0 else 0

    # Rcom = Mux/ΦMnx + Muy/ΦMny (BeST.Steel 검토비)
    Rcom = 0.0
    if phi_Mnx > 0 and phi_Mny > 0:
        Rcom = abs(Mux) / phi_Mnx + abs(Muy) / phi_Mny
    ok_Rcom = Rcom <= 1.0 if Rcom > 0 else True

    # X-X / Y-Y 분리 P-M 곡선 (정사각형이므로 동일 곡선, 키만 분리)
    pm_Px, pm_Mx, pm_Pnx, pm_Mnx = _build_pm_curve(
        c_column, As_total, d_eff, d_prime, beta1, Ag, fc_k, fy,
        phi_comp, phi_tens, eps_y, stl=stl if is_src else None, fy_stl=fy_stl)
    pm_Py, pm_My, pm_Pny, pm_Mny = pm_Px, pm_Mx, pm_Pnx, pm_Mnx  # 정사각형

    # Bresler 2축 휨 검토  # KDS 41 20 22 4.3.5
    bresler = None
    if Mux > 0 and Muy > 0 and Pu > 0:
        bresler = _bresler_check(
            Pu, Mux, Muy, As_total,
            d_eff, d_prime, beta1, c_column, Ag, fc_k, fy,
            phi_comp, phi_tens, eps_y,
            stl=stl if is_src else None, fy_stl=fy_stl)
        if not bresler['safe']:
            safe = False

    As_provided_col = As_total
    rebar_string_col = f"{n_col}-{rebar_type_col}" if n_col > 0 else rebar_vert_str
    rho_final = rho

    # 배근 배치 검토
    _n_per_side = int(np.ceil(n_col / 4)) + 1 if n_col > 0 else 2
    _s_min_col = max(40.0, 1.5 * rebar_diameter_col) if rebar_diameter_col > 0 else 40.0
    _avail_col = c_column - 2.0 * (_col_cover + _tie_dia_c + rebar_diameter_col / 2.0)
    _req_col = (_n_per_side - 1) * (rebar_diameter_col + _s_min_col)
    _fit_ok = _avail_col >= _req_col

    # ── P-M 포락선 시각화 데이터 ──
    pm_P, pm_M, pm_Pn, pm_Mn = _build_pm_curve(
        c_column, As_provided_col, d_eff, d_prime, beta1, Ag, fc_k, fy,
        phi_comp, phi_tens, eps_y, stl=stl if is_src else None, fy_stl=fy_stl)

    # ── 기둥 전단 검토 ──
    col_shear = {}
    if Vu_col > 0 and d_eff > 0 and is_src:
        # SRC 전단: Vn = 0.6·Fy,stl·Aw + Fy,Bar·Av·(d/s)
        _phi_shear = 0.75
        _Vn_stl = 0.6 * fy_stl * stl['Aw']  # N (강재 웹)
        _s_n_sh, _s_dia_sh, _s_spacing_sh, _s_Av_sh = _parse_stirrup_string(
            f"2-{tie_type}@{int(tie_spacing)}")
        _Vn_rebar = _s_Av_sh * fy * d_eff / tie_spacing if tie_spacing > 0 else 0  # N
        _Vn_total = _Vn_stl + _Vn_rebar
        _phi_Vn = _phi_shear * _Vn_total / 1000.0  # kN
        _shear_ok = Vu_col <= _phi_Vn
        _shear_ratio = Vu_col / _phi_Vn if _phi_Vn > 0 else 999
        col_shear = {
            'Vu': Vu_col, 'phi_Vc': 0, 'phi_Vs': 0,
            'Vn_stl': _Vn_stl / 1000.0, 'Vn_rebar': _Vn_rebar / 1000.0,
            'phi_Vn': _phi_Vn, 'ok': _shear_ok, 'ratio': _shear_ratio,
            'is_src': True,
        }
    elif Vu_col > 0 and d_eff > 0:
        # RC 전단
        _phi_shear = 0.75
        _Vc_N = (1.0 / 6.0) * np.sqrt(fc_k) * c_column * d_eff  # N
        _phi_Vc = _phi_shear * _Vc_N / 1000.0  # kN
        # 띠철근 기반 Vs
        _s_n_sh, _s_dia_sh, _s_spacing_sh, _s_Av_sh = _parse_stirrup_string(
            f"2-{tie_type}@{int(tie_spacing)}")
        _Vs_N = _s_Av_sh * fy * d_eff / tie_spacing if tie_spacing > 0 else 0
        _phi_Vs = _phi_shear * _Vs_N / 1000.0  # kN
        _phi_Vn = _phi_Vc + _phi_Vs
        _shear_ok = Vu_col <= _phi_Vn
        _shear_ratio = Vu_col / _phi_Vn if _phi_Vn > 0 else 999
        col_shear = {
            'Vu': Vu_col, 'phi_Vc': _phi_Vc, 'phi_Vs': _phi_Vs,
            'phi_Vn': _phi_Vn, 'ok': _shear_ok, 'ratio': _shear_ratio,
        }

    # 결과 조립
    result = {
        'name': name,
        'c_column': c_column,
        'h_column': h_column,
        'fc_k': fc_k, 'fy': fy,
        'cover': _col_cover,
        'Pu': Pu, 'Mux': Mux, 'Muy': Muy, 'Mu': Mu,
        'Mux_input': Mux_input, 'Muy_input': Muy_input,
        'Mu_design': Mu_design,
        'is_min_ecc_applied': is_min_ecc_applied,
        'e_min': e_min, 'e_actual': e_actual,
        'dimensions': {'c_column': c_column, 'Ag': Ag},
        'src_data': src_data,  # SRC 강재 정보 (빈 dict이면 RC)
        'rebar_design': {
            'rebar_string_col': rebar_string_col,
            'rebar_vert_input': rebar_vert_str,  # 구조계산서 원본 문자열
            'n_col': n_col,
            'rebar_type_col': rebar_type_col,
            'rebar_diameter_col': rebar_diameter_col,
            'As_provided_col': As_provided_col,
            'rho': rho_final,
            'phi_Pn_max': phi_Pn_max,
            'phi_Pn_b': phi_Pn_b,
            'phi_Mn_b': phi_Mn_b,
            'phi_Mn_o': phi_Mn_o,
            'pm_safe': safe,
            'pm_curve_P': pm_P,
            'pm_curve_M': pm_M,
            'pm_nominal_P': pm_Pn,
            'pm_nominal_M': pm_Mn,
            'fit_ok': _fit_ok,
            'n_per_side': _n_per_side,
            'bresler': bresler,
            # X-X / Y-Y 분리
            'phi_Mnx': phi_Mnx,
            'phi_Mny': phi_Mny,
            'Rcom': Rcom,
            'ok_Rcom': ok_Rcom,
            'pm_curve_Px': pm_Px, 'pm_curve_Mx': pm_Mx,
            'pm_nominal_Px': pm_Pnx, 'pm_nominal_Mx': pm_Mnx,
            'pm_curve_Py': pm_Py, 'pm_curve_My': pm_My,
            'pm_nominal_Py': pm_Pny, 'pm_nominal_My': pm_Mny,
        },
        'slenderness': slenderness,
        'tie_rebar_design': {
            'tie_rebar_type': tie_type,
            'tie_rebar_diameter': tie_dia,
            'tie_rebar_spacing': tie_spacing,
        },
        'col_shear': col_shear,
        'ok_pm': safe,
        'ok_slenderness': slenderness.get('ok', True),
        'ok_Rcom': ok_Rcom,
        'ok_shear': col_shear.get('ok', True) if col_shear else True,
        'ok_overall': safe and slenderness.get('ok', True) and _fit_ok and ok_Rcom and col_shear.get('ok', True) if col_shear else safe and slenderness.get('ok', True) and _fit_ok and ok_Rcom,
        'not_available': {
            'joint_shear': '보 정보 없이 접합부 전단 검토 불가',
            'scwb': '보 Mn 정보 없이 강기둥-약보 검토 불가',
            'imf_column': 'IMF 기둥 상세는 설계모드에서만 검토',
        },
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# 기둥 — Bresler 이축 휨 검토
# ═══════════════════════════════════════════════════════════════════════

def _src_forces_at_c(c_mid, c_column, d_eff, d_prime, As_half,
                     alpha1, beta1, fc_k, fy, _ecu_Es,
                     stl=None, fy_stl=0):
    """주어진 중립축 c에서 (Pn, Mn) 계산. SRC면 강재 기여 포함."""
    h_half = c_column / 2.0
    a_i = min(beta1 * c_mid, c_column)
    # 콘크리트
    Cc = alpha1 * fc_k * a_i * c_column
    Mc = Cc * (h_half - a_i / 2.0)
    # 철근
    fs_p = min(max(_ecu_Es * (c_mid - d_prime) / c_mid, -fy), fy)
    fs_t = min(max(_ecu_Es * (d_eff - c_mid) / c_mid, -fy), fy)
    Pr = As_half * fs_p - As_half * fs_t
    Mr = As_half * fs_p * (h_half - d_prime) + As_half * fs_t * (d_eff - h_half)
    # 강재 (SRC)
    Ps = 0.0; Ms = 0.0
    if stl and fy_stl > 0:
        _B = stl['B']; _H = stl['H']; _tv = stl['tv']; _th = stl['th']
        # 상부 플랜지: y = h_half - (h_half - _H/2) = _H/2 from center?
        # 강재 중심 = 단면 중심 (h_half)
        # 상부 플랜지 중심: y_top_f = h_half - _H/2 + _th/2 (압축연단 기준)
        # 아니, 압축연단 = 상단(y=c_column), 하단=0
        # 강재 중심 = h_half
        # 상부 플랜지 중심 = h_half + (_H/2 - _th/2)
        # 하부 플랜지 중심 = h_half - (_H/2 - _th/2)
        _y_tf = h_half + (_H / 2.0 - _th / 2.0)  # 상부 플랜지 (압축연단에서 먼 쪽)
        _y_bf = h_half - (_H / 2.0 - _th / 2.0)  # 하부 플랜지 (압축연단에 가까운 쪽)
        _A_flange = _B * _th  # 플랜지 면적
        _A_web = 2 * _tv * (_H - 2 * _th)  # 웹 면적 (양쪽)
        # 각 부분의 변형률 → 응력
        ecu = _ecu_Es / 200000.0
        # 상부 플랜지 (d = _y_tf from 압축연단? 아니, 압축연단=상단)
        # 변형률: ε = εcu × (위치 - c) / c  (위치: 압축연단에서의 거리)
        # 여기서 좌표: 하단=0, 상단=c_column
        # 압축연단 = 상단이므로, 압축연단에서의 거리 = c_column - y
        # ε(y) = εcu × (c_mid - (c_column - y)) / c_mid = εcu × (y - (c_column - c_mid)) / c_mid
        # 간단하게: 하단=0 기준, 압축연단=c_column
        # d_from_comp = c_column - y
        # ε = εcu × (c_mid - d_from_comp) / c_mid
        _eps_tf = ecu * (c_mid - (c_column - _y_tf)) / c_mid
        _eps_bf = ecu * (c_mid - (c_column - _y_bf)) / c_mid
        _eps_web = ecu * (c_mid - (c_column - h_half)) / c_mid  # 웹 중심

        _fs_tf = min(max(_eps_tf * 200000.0, -fy_stl), fy_stl)
        _fs_bf = min(max(_eps_bf * 200000.0, -fy_stl), fy_stl)
        _fs_web = min(max(_eps_web * 200000.0, -fy_stl), fy_stl)

        Ps = _A_flange * _fs_tf + _A_flange * _fs_bf + _A_web * _fs_web
        Ms = (_A_flange * _fs_tf * (_y_tf - h_half)
              + _A_flange * _fs_bf * (_y_bf - h_half)
              + _A_web * _fs_web * 0)  # 웹 중심=단면 중심

    Pn = Cc + Pr + Ps
    Mn = Mc + Mr + Ms
    return Pn, Mn


def _find_Pn_at_eccentricity(e_target, As_total, d_eff, d_prime, beta1,
                              c_column, Ag, fc_k, fy,
                              stl=None, fy_stl=0):
    """주어진 편심(mm)에서 Pn(N)을 이분법으로 탐색."""
    alpha1, _ = _get_alpha1_beta1(fc_k)
    _ecu_Es = _get_epsilon_cu(fc_k) * 200000.0
    As_half = As_total / 2.0
    h_half = c_column / 2.0
    c_lo, c_hi = 1e-3, c_column * 3.0

    for _ in range(60):
        c_mid = (c_lo + c_hi) / 2.0
        Pn, Mn = _src_forces_at_c(c_mid, c_column, d_eff, d_prime, As_half,
                                   alpha1, beta1, fc_k, fy, _ecu_Es, stl, fy_stl)
        if Pn <= 0:
            c_lo = c_mid
            continue
        e_calc = Mn / Pn
        if e_calc > e_target:
            c_lo = c_mid
        else:
            c_hi = c_mid
        if c_hi - c_lo < 0.01:
            break
    return max(Pn, 0.0)


def _bresler_check(Pu, Mux, Muy, As_total, d_eff, d_prime, beta1,
                   c_column, Ag, fc_k, fy, phi_comp, phi_tens, eps_y,
                   stl=None, fy_stl=0):
    """Bresler 역수하중법: 1/Pn = 1/Pnx + 1/Pny - 1/Pno"""
    alpha1, _ = _get_alpha1_beta1(fc_k)
    Pu_N = Pu * 1000.0
    ex = Mux * 1e6 / Pu_N if Pu_N > 0 else 0.0
    ey = Muy * 1e6 / Pu_N if Pu_N > 0 else 0.0

    Pnx = _find_Pn_at_eccentricity(ex, As_total, d_eff, d_prime, beta1, c_column, Ag, fc_k, fy, stl, fy_stl)
    Pny = _find_Pn_at_eccentricity(ey, As_total, d_eff, d_prime, beta1, c_column, Ag, fc_k, fy, stl, fy_stl)
    As_half = As_total / 2.0
    As_stl = stl['As'] if stl else 0
    Pno = alpha1 * fc_k * (Ag - As_total - As_stl) + fy * As_total + fy_stl * As_stl if stl else alpha1 * fc_k * (Ag - As_total) + fy * As_total

    if Pnx > 0 and Pny > 0 and Pno > 0:
        inv_Pn = 1.0 / Pnx + 1.0 / Pny - 1.0 / Pno
        Pn_bresler = 1.0 / inv_Pn if inv_Pn > 0 else Pno
    else:
        Pn_bresler = 0.0

    phi = phi_comp
    phi_Pn = phi * Pn_bresler / 1000.0
    safe = Pu <= phi_Pn

    return {
        'safe': safe,
        'Pn_bresler': Pn_bresler / 1000.0,
        'Pnx': Pnx / 1000.0,
        'Pny': Pny / 1000.0,
        'Pno': Pno / 1000.0,
        'phi_Pn': phi_Pn,
        'ratio': Pu / phi_Pn if phi_Pn > 0 else float('inf'),
    }


# ═══════════════════════════════════════════════════════════════════════
# 기둥 — P-M 포락선 시각화 데이터
# ═══════════════════════════════════════════════════════════════════════

def _build_pm_curve(c_column, As_total, d_eff, d_prime, beta1, Ag, fc_k, fy,
                    phi_comp, phi_tens, eps_y,
                    stl=None, fy_stl=0):
    """P-M 포락선 다점 데이터 생성 (시각화용). SRC면 강재 기여 포함."""
    alpha1, _ = _get_alpha1_beta1(fc_k)
    _ecu_Es = _get_epsilon_cu(fc_k) * 200000.0
    As_half = As_total / 2.0
    h_half = c_column / 2.0
    As_stl = stl['As'] if stl else 0

    _Pno = alpha1 * fc_k * (Ag - As_total - As_stl) + fy * As_total + fy_stl * As_stl if stl else alpha1 * fc_k * (Ag - As_total) + fy * As_total
    _Pn_cap_kN = 0.80 * _Pno / 1000.0  # 공칭 캡
    _phi_Pn_cap_kN = 0.80 * phi_comp * _Pno / 1000.0  # 설계 캡

    ecu = _get_epsilon_cu(fc_k)
    _ecu_Es = ecu * 200000.0

    # c를 큰 값(순수 압축)부터 작은 값(순수 인장)까지 sweep
    # 작은 c 영역에 더 많은 점 배치 (곡률이 큰 구간)
    _c_max = c_column * 3.0
    _c_min = 1e-3
    # 대수 간격으로 작은 c에 점 집중
    _c_arr = np.concatenate([
        np.linspace(_c_max, c_column, 30, endpoint=False),
        np.linspace(c_column, c_column * 0.3, 100, endpoint=False),
        np.linspace(c_column * 0.3, c_column * 0.05, 100, endpoint=False),
        np.linspace(c_column * 0.05, _c_min, 50),
    ])

    # 순수 인장 점 (c → ∞ 의미: 전단면 인장)
    _Pt_stl = fy_stl * As_stl if stl else 0
    _Pt_rebar = fy * As_total
    _Pn_tension = -(_Pt_rebar + _Pt_stl)  # N (음수)

    pm_P, pm_M, pm_Pn, pm_Mn = [], [], [], []

    for _c_i in _c_arr:
        _Pn_i, _Mn_i = _src_forces_at_c(_c_i, c_column, d_eff, d_prime, As_half,
                                         alpha1, beta1, fc_k, fy, _ecu_Es, stl, fy_stl)

        # 공칭값 (Pn 캡 적용)
        _Pn_kN = _Pn_i / 1000.0
        _Mn_kNm = abs(_Mn_i) / 1e6
        if _Pn_kN > _Pn_cap_kN:
            # 캡 초과 → Pn=캡, Mn 보간
            _Mn_kNm = _Mn_kNm * (_Pn_cap_kN / _Pn_kN) if _Pn_kN > 0 else 0
            _Pn_kN = _Pn_cap_kN
        pm_Pn.append(_Pn_kN)
        pm_Mn.append(_Mn_kNm)

        # 설계값 (φ 적용 + 캡)
        _eps_ti = ecu * max(d_eff - _c_i, 0.0) / _c_i if _c_i > 0 else 0.1
        _phi_i = _calc_phi(_eps_ti, fy, phi_comp, phi_tens)  # KDS 14 20 10

        _phiPn_kN = _phi_i * _Pn_i / 1000.0
        _phiMn_kNm = abs(_phi_i * _Mn_i) / 1e6
        if _phiPn_kN > _phi_Pn_cap_kN:
            _phiMn_kNm = _phiMn_kNm * (_phi_Pn_cap_kN / _phiPn_kN) if _phiPn_kN > 0 else 0
            _phiPn_kN = _phi_Pn_cap_kN
        pm_P.append(_phiPn_kN)
        pm_M.append(_phiMn_kNm)

    # 순수 인장 점
    pm_Pn.append(_Pn_tension / 1000.0)
    pm_Mn.append(0.0)
    pm_P.append(phi_tens * _Pn_tension / 1000.0)
    pm_M.append(0.0)

    return pm_P, pm_M, pm_Pn, pm_Mn


# ═══════════════════════════════════════════════════════════════════════
# 1방향 슬래브 검토
# ═══════════════════════════════════════════════════════════════════════

def _get_moment_coefficients(boundary):
    """1방향 슬래브 모멘트 계수 (KDS 14 20 22 4.3.2 근사해석법).

    Args:
        boundary: "양단연속" | "1단연속" | "양단단순" | "캔틸레버"

    Returns:
        dict: {cont: 연속단 계수, pos: 중앙부 계수}
        부호 규약: cont < 0 (부모멘트), pos > 0 (정모멘트)
    """
    # KDS 14 20 22 — 연속 1방향 슬래브 근사 모멘트 계수
    if boundary == "양단연속":
        return {'cont': -1.0 / 11.0, 'pos': 1.0 / 16.0}  # 내부 스팬
    elif boundary == "1단연속":
        return {'cont': -1.0 / 10.0, 'pos': 1.0 / 11.0}
    elif boundary == "양단단순":
        return {'cont': 0.0, 'pos': 1.0 / 8.0}
    elif boundary == "캔틸레버":
        return {'cont': -1.0 / 2.0, 'pos': 0.0}
    else:
        return {'cont': -1.0 / 11.0, 'pos': 1.0 / 16.0}


def _calc_min_slab_thickness(Ln_mm, boundary, fy):
    """처짐 제어 면제 최소 두께 (KDS 14 20 22 표).

    Args:
        Ln_mm: 순경간 (mm)
        boundary: 지점 조건
        fy: 철근 항복강도 (MPa)

    Returns:
        float: 최소 두께 (mm)
    """
    # KDS 14 20 22 표 — 처짐 계산 면제 최소 두께
    if boundary == "양단단순":
        ratio = 20.0
    elif boundary == "1단연속":
        ratio = 24.0
    elif boundary == "양단연속":
        ratio = 28.0
    elif boundary == "캔틸레버":
        ratio = 10.0
    else:
        ratio = 28.0

    h_min = Ln_mm / ratio
    # fy ≠ 400 보정 (KDS 14 20 22)
    if abs(fy - 400.0) > 1.0:
        h_min *= (0.4 + fy / 700.0)
    return h_min


def _calc_rebar_As_per_m(combo, spacing_mm):
    """간격별 제공 철근량 (mm²/m).

    Args:
        combo: "D10", "D10+D13", "D13", "D13+D16", "D16", "D16+D19", "D19", "D19+D22", "D22"
        spacing_mm: 간격 (mm)
    """
    if spacing_mm <= 0:
        return 0.0
    n_per_m = 1000.0 / spacing_mm

    if '+' in combo:
        parts = combo.split('+')
        a1 = REBAR_SPECS.get(parts[0], {}).get('area', 0.0)
        a2 = REBAR_SPECS.get(parts[1], {}).get('area', 0.0)
        return n_per_m * (a1 + a2) / 2.0
    else:
        a = REBAR_SPECS.get(combo, {}).get('area', 0.0)
        return n_per_m * a


def _review_slab(slab_input, fc_k, fy):
    """1방향 슬래브 검토 (KDS 14 20 22).

    Args:
        slab_input: {name, Lx, Ly, H, fc_k, fy, cover, Wd, Wl,
                     edge_UP/DN/LT/RT, boundary, selected_rebar, flexure_rows_best}
        fc_k, fy: 재료

    Returns:
        dict — 슬래브 검토 결과
    """
    import re as _re

    name = slab_input.get('name', 'Slab')
    Lx = float(slab_input.get('Lx', 0) or 0)   # 단변 mm
    Ly = float(slab_input.get('Ly', 0) or 0)   # 장변 mm
    H = float(slab_input.get('H', 0) or 0)      # 두께 mm
    cover = float(slab_input.get('cover', 0) or 0)
    Wd = float(slab_input.get('Wd', 0))      # kN/m²
    Wl = float(slab_input.get('Wl', 0))      # kN/m²
    boundary = slab_input.get('boundary', '양단연속')

    # Edge beams → 보 폭 추출 (순경간 계산용)
    def _beam_width(edge_str):
        if not edge_str:
            return 0.0
        m = _re.match(r'(\d+)x(\d+)', str(edge_str))
        return float(m.group(1)) if m else 0.0

    edge_UP = slab_input.get('edge_UP', '')
    edge_DN = slab_input.get('edge_DN', '')
    edge_LT = slab_input.get('edge_LT', '')
    edge_RT = slab_input.get('edge_RT', '')

    # 순경간 (단변): Lx - 보폭/2 양쪽
    _bw_up = _beam_width(edge_UP)
    _bw_dn = _beam_width(edge_DN)
    Ln_x = Lx - _bw_up / 2.0 - _bw_dn / 2.0  # 단변 순경간 mm
    Ln_x = max(Ln_x, Lx * 0.8)  # 안전장치

    # 순경간 (장변)
    _bw_lt = _beam_width(edge_LT)
    _bw_rt = _beam_width(edge_RT)
    Ln_y = Ly - _bw_lt / 2.0 - _bw_rt / 2.0
    Ln_y = max(Ln_y, Ly * 0.8)

    # ── 기본 계산 ──
    Wu = 1.2 * Wd + 1.6 * Wl  # KDS 14 20 10 하중조합
    beta = Ly / Lx if Lx > 0 else 2.0

    # 유효 깊이 (주근 D10 기준)
    d = H - cover - 9.53 / 2.0  # mm

    alpha1, beta1 = _get_alpha1_beta1(fc_k)  # KDS 14 20 20
    ecu = _get_epsilon_cu(fc_k)

    # ── 1. 최소 두께 검토 ──
    h_min = _calc_min_slab_thickness(Ln_x, boundary, fy)
    thk_ok = H >= h_min

    # ── 2. 모멘트 계수법으로 독립 Mu 계산 ── (KDS 14 20 22)
    coeff = _get_moment_coefficients(boundary)
    Mu_short_cont = abs(coeff['cont']) * Wu * (Ln_x / 1000.0) ** 2  # kN·m/m
    Mu_short_pos = coeff['pos'] * Wu * (Ln_x / 1000.0) ** 2
    # 장변: 1방향 슬래브에서 장변은 온도/건조수축 철근 (최소 배근 지배)
    # 장변 모멘트는 매우 작으므로 BeST 값이 있으면 BeST ��� 사용, 없으면 0
    Mu_long_cont = 0.0
    Mu_long_pos = 0.0

    # 독립 계산 Mu 모음
    independent_Mu = {
        'short_cont': round(Mu_short_cont, 2),
        'short_pos': round(Mu_short_pos, 2),
        'long_cont': round(Mu_long_cont, 2),
        'long_pos': round(Mu_long_pos, 2),
    }

    # ��─ 3. BeST Mu 비교 ──
    best_Mu = {'short_cont': 0, 'short_pos': 0, 'long_cont': 0, 'long_pos': 0}
    _best_rows = slab_input.get('flexure_rows_best', []) or []
    _dir_loc_map = {
        ('Short', 'Cont'): 'short_cont', ('Short', 'Pos'): 'short_pos',
        ('Long', 'Cont'): 'long_cont', ('Long', 'Pos'): 'long_pos',
    }
    for fr in _best_rows:
        key = _dir_loc_map.get((fr.get('direction', ''), fr.get('location', '')))
        if key and fr.get('Mu') is not None and str(fr['Mu']).strip():
            try:
                best_Mu[key] = float(fr['Mu'])
            except (ValueError, TypeError):
                pass

    # ── 4. 최소 철근비 ── (KDS 14 20 20)
    # fy ≤ 400: ρ_min = 0.002, fy > 400: ρ_min = 0.0018
    rho_min = 0.002 if fy <= 400 else 0.0018  # KDS 14 20 20 4.5.1
    Ast_min = rho_min * 1000.0 * H  # mm²/m (전체 두께 기준)

    # ── 5. 위치별 배근 검토 ──
    b_unit = 1000.0  # 단위폭 1m
    selected_rebar = slab_input.get('selected_rebar', {})
    positions = ['short_cont', 'short_pos', 'long_cont', 'long_pos']
    pos_labels = {
        'short_cont': ('Short', 'Cont'), 'short_pos': ('Short', 'Pos'),
        'long_cont': ('Long', 'Cont'), 'long_pos': ('Long', 'Pos'),
    }

    flexure_results = {}
    for pos in positions:
        # 설계 Mu: 독립 계산 값 사용
        Mu_design = independent_Mu[pos]

        # 선택된 배근
        sel = selected_rebar.get(pos, {})
        combo = sel.get('combo', '')
        _sp_raw = sel.get('spacing', 0)
        try:
            spacing = float(_sp_raw) if str(_sp_raw).strip() else 0.0
        except (ValueError, TypeError):
            spacing = 0.0

        # 제공 As
        As_provided = _calc_rebar_As_per_m(combo, spacing)
        As_provided = max(As_provided, 0.01)  # 0 방지

        # 최소 철근량 이상인지
        As_gov = max(Ast_min, 0.01)  # 최소 철근비 지배

        # φMn 계산 (b=1000mm/m)
        phi_Mn, phi, a, c, epsilon_t = _calc_phi_Mn(As_provided, b_unit, d, fc_k, fy)

        # 소요 Ast 계산 (Mu에서 역산)
        Mu_N_mm = abs(Mu_design) * 1e6  # kN·m/m → N·mm/m
        # 근사 역산: a = d - sqrt(d² - 2Mu/(α₁·fck·b·φ))
        _phi_est = 0.85
        _denom = alpha1 * fc_k * b_unit * _phi_est
        if _denom > 0 and d > 0:
            _disc = d ** 2 - 2.0 * Mu_N_mm / _denom
            if _disc > 0:
                a_req = d - np.sqrt(_disc)
                Ast_req = alpha1 * fc_k * b_unit * a_req / fy
            else:
                Ast_req = 0.0
        else:
            Ast_req = 0.0
        Ast_req = max(Ast_req, 0.0)

        # 판정
        ok_flexure = phi_Mn >= abs(Mu_design) if Mu_design != 0 else True
        ok_min_As = As_provided >= Ast_min

        flexure_results[pos] = {
            'direction': pos_labels[pos][0],
            'location': pos_labels[pos][1],
            'Mu_independent': Mu_design,
            'Mu_best': best_Mu[pos],
            'Mu_diff_pct': round((Mu_design - best_Mu[pos]) / best_Mu[pos] * 100, 1) if best_Mu[pos] != 0 else 0,
            'Ast_req': round(Ast_req, 1),
            'Ast_min': round(Ast_min, 1),
            'combo': combo,
            'spacing': spacing,
            'As_provided': round(As_provided, 1),
            'phi_Mn': round(phi_Mn, 2),
            'phi': round(phi, 3),
            'a': round(a, 1),
            'c': round(c, 1) if c else 0,
            'epsilon_t': round(epsilon_t, 5),
            'ok_flexure': ok_flexure,
            'ok_min_As': ok_min_As,
            'ok': ok_flexure and ok_min_As,
        }

    # ── 6. 전단 검토 ── (KDS 14 20 22)
    # Vu = Wu × Ln/2 (kN/m)
    Vu_x = Wu * (Ln_x / 1000.0) / 2.0  # kN/m
    Vu_y = Wu * (Ln_y / 1000.0) / 2.0  # kN/m

    # Vc = (1/6)√fck × b × d (N/m) → kN/m
    Vc_x = (1.0 / 6.0) * np.sqrt(fc_k) * b_unit * d / 1000.0  # kN/m  # KDS 14 20 22
    Vc_y = Vc_x  # 같은 단면 (d는 단변 기준)
    phi_shear = 0.75
    phi_Vc_x = phi_shear * Vc_x
    phi_Vc_y = phi_shear * Vc_y

    shear_x_ok = Vu_x <= phi_Vc_x
    shear_y_ok = Vu_y <= phi_Vc_y

    shear_result = {
        'Vu_x': round(Vu_x, 1),
        'phi_Vc_x': round(phi_Vc_x, 1),
        'ok_x': shear_x_ok,
        'Vu_y': round(Vu_y, 1),
        'phi_Vc_y': round(phi_Vc_y, 1),
        'ok_y': shear_y_ok,
        'phi': phi_shear,
    }

    # ── 종합 ──
    ok_overall = (thk_ok
                  and all(fr['ok'] for fr in flexure_results.values())
                  and shear_x_ok and shear_y_ok)

    return {
        'name': name,
        'software': slab_input.get('software', 'BeST.RC'),
        'Lx': Lx, 'Ly': Ly, 'H': H,
        'cover': cover,
        'fc_k': fc_k, 'fy': fy,
        'Wd': Wd, 'Wl': Wl, 'Wu': round(Wu, 2),
        'beta': round(beta, 4),
        'Ln_x': round(Ln_x, 1), 'Ln_y': round(Ln_y, 1),
        'edge_UP': edge_UP, 'edge_DN': edge_DN,
        'edge_LT': edge_LT, 'edge_RT': edge_RT,
        'boundary': boundary,
        # 최소 두께
        'h_min': round(h_min, 1),
        'thk_ok': thk_ok,
        # 배근 검토
        'alpha1': alpha1, 'beta1': beta1,
        'd': round(d, 1),
        'rho_min': rho_min,
        'Ast_min': round(Ast_min, 1),
        'independent_Mu': independent_Mu,
        'best_Mu': best_Mu,
        'flexure': flexure_results,
        # 전단
        'shear': shear_result,
        # 종합
        'ok_overall': ok_overall,
        # 메타데이터 패스스루
        'spacing_headers': slab_input.get('spacing_headers', []),
        'flexure_rows_best': _best_rows,
        'min_spacings_best': slab_input.get('min_spacings', slab_input.get('min_spacings_best', {})),
        'rho_min_best': slab_input.get('rho_min', slab_input.get('rho_min_best', 0)),
        'Ast_min_best': slab_input.get('Ast_min', slab_input.get('Ast_min_best', 0)),
    }


# ═════════════════════════════════════════════════════════════════════��═
# 메인 오케스트레이터
# ══════════════════════════════════════════════════════════════════════���

def perform_review(review_inputs):
    """
    구조계산서 검토 모드 메인 함수.

    Args:
        review_inputs: {
            'fc_k': float, 'fy': float,
            'beams': [{'name', 'h_beam', 'b_beam', 'locations': {END_I, MID, END_J}}],
            'columns': [{'name', 'c_column', 'h_column', 'Pu', 'Mux', 'Muy'}]
        }

    Returns:
        dict — 검토 결과
    """
    _default_fck = float(review_inputs.get('fc_k', 24.0))
    _default_fy = float(review_inputs.get('fy', 400.0))

    review_beams = []
    for beam_input in review_inputs.get('beams', []):
        _b_fck = float(beam_input.get('fc_k', _default_fck))
        _b_fy = float(beam_input.get('fy', _default_fy))
        review_beams.append(_review_beam(beam_input, _b_fck, _b_fy))

    review_columns = []
    for col_input in review_inputs.get('columns', []):
        _c_fck = float(col_input.get('fc_k', _default_fck))
        _c_fy = float(col_input.get('fy', _default_fy))
        review_columns.append(_review_column(col_input, _c_fck, _c_fy))

    review_slabs = []
    for slab_input in review_inputs.get('slabs', []):
        _s_fck = float(slab_input.get('fc_k', _default_fck))
        _s_fy = float(slab_input.get('fy', _default_fy))
        review_slabs.append(_review_slab(slab_input, _s_fck, _s_fy))

    result = {
        'mode': 'review',
        'fc_k': _default_fck,
        'fy': _default_fy,
        'review_slabs': review_slabs,
        'review_beams': review_beams,
        'review_columns': review_columns,
    }

    # frame_mapping이 있으면 3D 배근도용 데이터 변환
    fm = review_inputs.get('frame_mapping')
    if fm:
        result['frame_3d'] = _build_frame_3d_data(
            fm, review_beams, review_columns, review_inputs)

    return result


# ═══════════════════════════════════════════════════════════════════════
# 3D 배근도 데이터 어댑터 — review 결과 → frame_3d 호환 형식
# ═══════════════════════════════════════════════════════════════════════

# 철근 사양 (frame_3d에서 사용하는 rebar_specs 형식)
_REBAR_SPECS = {
    'D10': {'diameter': 9.53,  'area': 71.33},
    'D13': {'diameter': 12.7,  'area': 126.7},
    'D16': {'diameter': 15.9,  'area': 198.6},
    'D19': {'diameter': 19.1,  'area': 286.5},
    'D22': {'diameter': 22.2,  'area': 387.1},
    'D25': {'diameter': 25.4,  'area': 506.7},
    'D29': {'diameter': 28.6,  'area': 642.4},
    'D32': {'diameter': 31.8,  'area': 794.2},
}


def _parse_rebar_for_3d(rebar_string):
    """배근 문자열 (예: '3-D19') → n, rebar_type, diameter. 값 없으면 (0, '', 0)"""
    import re
    m = re.match(r'(\d+)\s*-\s*(D\d+)', str(rebar_string or ''))
    if not m:
        return 0, '', 0  # 값 없음
    n = int(m.group(1))
    rtype = m.group(2)
    dia = _REBAR_SPECS.get(rtype, {}).get('diameter', 19.1)
    return n, rtype, dia


def _parse_stirrup_for_3d(stirrup_string):
    """스터럽 문자열 (예: '2-D10 @125') → legs, type, diameter, spacing. 값 없으면 (0, '', 0, 0)"""
    import re
    m = re.match(r'(\d+)\s*-\s*(D\d+)\s*@\s*(\d+)', str(stirrup_string or ''))
    if not m:
        return 0, '', 0, 0  # 값 없음
    legs = int(m.group(1))
    rtype = m.group(2)
    dia = _REBAR_SPECS.get(rtype, {}).get('diameter', 9.53)
    spacing = int(m.group(3))
    return legs, rtype, dia, spacing


def _make_beam_compat(beam_input, beam_result):
    """검토 모드의 보 입력+결과 → frame_3d가 이해하는 설계모드 beam dict"""
    if not beam_input or not beam_result:
        return None

    h = float(beam_input.get('h_beam', 0) or 0)
    b = float(beam_input.get('b_beam', 0) or 0)
    if h <= 0 or b <= 0:
        return None  # 단면 치수 없으면 3D 렌더링 불가
    cover = float(beam_input.get('cover', 0) or 0)
    rebar_top = str(beam_input.get('rebar_top', '') or '')
    rebar_bot = str(beam_input.get('rebar_bot', '') or '')
    stirrup_str = str(beam_input.get('stirrup', '') or '')
    if not rebar_top and not rebar_bot:
        return None  # 배근 정보 없으면 3D 렌더링 불가

    n_top, rtype_top, dia_top = _parse_rebar_for_3d(rebar_top)
    n_bot, rtype_bot, dia_bot = _parse_rebar_for_3d(rebar_bot)
    _, _, stir_dia, stir_spacing = _parse_stirrup_for_3d(stirrup_str)

    # rebar_steps 호환 dict 생성
    def _make_rebar_steps(n, rtype, dia):
        _rtype_key = rtype if rtype else 'D13'
        steps = {
            'cover': cover,
            'rebar_specs': _REBAR_SPECS,
            f'n_final_{_rtype_key}': n,
            'selected_rebar_diameter': dia,
            'As_provided': n * _REBAR_SPECS.get(rtype, {}).get('area', 0),
            'rebar_string': f'{n}-{rtype}' if rtype else '',
            'layer': 1,
        }
        return steps

    return {
        'design_params': {'b_beam': b, 'h_beam': h},
        's': stir_spacing,  # frame_3d가 bx['s']로 접근
        'rebar_string_top': rebar_top,
        'rebar_string_bot': rebar_bot,
        'rebar_string_min': rebar_bot,  # 최소근 = 하부근 (검토 모드 단순화)
        'rebar_steps_top': _make_rebar_steps(n_top, rtype_top, dia_top),
        'rebar_steps_bot': _make_rebar_steps(n_bot, rtype_bot, dia_bot),
        'rebar_steps_min': _make_rebar_steps(n_bot, rtype_bot, dia_bot),
        'layer_top': 1,
        'layer_bot': 1,
        'layer_min': 1,
        'stirrup_zone_summary': stirrup_str,
        'stirrup_zones': None,  # 검토 모드: 구간별 스터럽 없음 (균일 간격)
        'dev_top': {'ls_B': 600},  # 간략 기본값
        'dev_bot': {'ls_B': 600},
    }


def _make_column_compat(col_input, col_result):
    """검토 모드의 기둥 입력+결과 → frame_3d가 이해하는 설계모드 column dict"""
    if not col_input or not col_result:
        return None

    c = float(col_input.get('c_column', 0) or 0)
    cover = float(col_input.get('cover', 0) or 0)
    if c <= 0:
        return None  # 기둥 치수 없으면 3D 렌더링 불가

    # 기둥 배근 파싱 (예: "12EA-4R-D19" 또는 "8-D22")
    import re
    rebar_str = str(col_input.get('rebar_vert', '') or col_input.get('rebar_top', '') or '')
    if not rebar_str.strip():
        return None  # 기둥 배근 없으면 3D 렌더링 불가
    m_ea = re.search(r'(\d+)\s*EA', rebar_str)
    m_simple = re.match(r'(\d+)\s*-\s*(D\d+)', rebar_str)

    if m_ea:
        n_col = int(m_ea.group(1))
        m_d = re.search(r'D(\d+)', rebar_str)
        rtype = f'D{m_d.group(1)}' if m_d else 'D22'
    elif m_simple:
        n_col = int(m_simple.group(1))
        rtype = m_simple.group(2)
    else:
        return None  # 배근 문자열 파싱 불가

    dia = _REBAR_SPECS.get(rtype, {}).get('diameter', 22.2)

    # 띠철근 파싱
    tie_str = str(col_input.get('hoop', '') or col_input.get('stirrup', '') or '')
    m_tie = re.match(r'(D\d+)\s*@\s*(\d+)', tie_str)
    if m_tie:
        tie_type = m_tie.group(1)
        tie_spacing = int(m_tie.group(2))
    else:
        tie_type = ''
        tie_spacing = 0
    tie_dia = _REBAR_SPECS.get(tie_type, {}).get('diameter', 0)

    return {
        'dimensions': {'c_column': c},
        'rebar_design': {
            'n_col': n_col,
            'rebar_diameter_col': dia,
            'rebar_type_col': rtype,
            'rho': col_result.get('rho', 0.02),
        },
        'tie_rebar_design': {
            'tie_rebar_diameter': tie_dia,
            'tie_rebar_spacing': tie_spacing,
            'tie_rebar_type': tie_type,
        },
    }


def _make_slab_compat(slab_input):
    """검토 모드의 슬래브 입력 → frame_3d가 이해하는 설계모드 slab dict.
    4개 배근 위치(short_cont/pos, long_cont/pos)를 frame_3d 호환 키로 변환."""
    if not slab_input:
        return None

    t_slab = float(slab_input.get('H', 0) or 0)
    cover = float(slab_input.get('cover', 0) or 0)
    if t_slab <= 0:
        return None  # 슬래브 두께 없으면 3D 렌더링 불가
    slab_Lx = float(slab_input.get('Lx', 0) or 0)
    slab_Ly = float(slab_input.get('Ly', 0) or 0)

    selected_rebar = slab_input.get('selected_rebar', {})

    def _combo_to_rebar_str(pos_key):
        """'D10+D13' combo + spacing → 'D10+D13@200' 형식 문자열"""
        rb = selected_rebar.get(pos_key, {})
        combo = rb.get('combo', '')
        spacing = rb.get('spacing', '')
        try:
            spacing = int(float(spacing))
        except (ValueError, TypeError):
            spacing = 300
        return f"{combo}@{spacing}"

    return {
        'design_params': {'t_slab': t_slab},
        'cover': cover,
        'slab_Lx': slab_Lx,
        'slab_Ly': slab_Ly,
        'position': slab_input.get('position', '바닥 슬래브'),
        # 4개 배근 위치 (검토모드 확장)
        'rebar_short_cont': _combo_to_rebar_str('short_cont'),   # 상부 주근 (단변 방향)
        'rebar_short_pos': _combo_to_rebar_str('short_pos'),     # 하부 주근 (단변 방향)
        'rebar_long_cont': _combo_to_rebar_str('long_cont'),     # 상부 배력근 (장변 방향)
        'rebar_long_pos': _combo_to_rebar_str('long_pos'),       # 하부 배력근 (장변 방향)
        # 설계모드 호환 키 (fallback용)
        'rebar_string_top': _combo_to_rebar_str('short_cont'),
        'rebar_string_bot': _combo_to_rebar_str('short_pos'),
        'rebar_string_dist': _combo_to_rebar_str('long_pos'),
        'dev_top': {'ls_B': 400},
        'dev_bot': {'ls_B': 400},
    }


def _build_frame_3d_data(frame_mapping, review_beams, review_columns, review_inputs):
    """frame_mapping + review 결과 → plot_3d_frame_rebar 호환 results/inputs"""
    # 부재 매핑에서 입력 데이터 찾기
    all_beams = review_inputs.get('beams', [])
    all_cols = review_inputs.get('columns', [])

    def _find_input_by_name(lst, name):
        return next((x for x in lst if x.get('name') == name), None) if name else None

    def _find_result_beam(name):
        return next((r for r in review_beams if r.get('name') == name), None) if name else None

    def _find_result_col(name):
        return next((r for r in review_columns if r.get('name') == name), None) if name else None

    ceil_x_input = frame_mapping.get('ceil_x')
    ceil_y_input = frame_mapping.get('ceil_y')
    floor_x_input = frame_mapping.get('floor_x')
    floor_y_input = frame_mapping.get('floor_y')
    col_input = frame_mapping.get('column')

    ceil_x_name = ceil_x_input.get('name') if ceil_x_input else None
    ceil_y_name = ceil_y_input.get('name') if ceil_y_input else None
    floor_x_name = floor_x_input.get('name') if floor_x_input else None
    floor_y_name = floor_y_input.get('name') if floor_y_input else None
    col_name = col_input.get('name') if col_input else None

    beam_x_compat = _make_beam_compat(ceil_x_input, _find_result_beam(ceil_x_name))
    beam_y_compat = _make_beam_compat(ceil_y_input, _find_result_beam(ceil_y_name))
    gb_x_compat = _make_beam_compat(floor_x_input, _find_result_beam(floor_x_name))
    gb_y_compat = _make_beam_compat(floor_y_input, _find_result_beam(floor_y_name))
    col_compat = _make_column_compat(col_input, _find_result_col(col_name))
    slab_compat = _make_slab_compat(frame_mapping.get('slab'))

    # ── 누락 이유 추적 ──
    missing_reasons = []

    def _diagnose_beam(label, beam_input, beam_result, compat):
        if compat:
            return
        if not beam_input:
            missing_reasons.append(f"**{label}**: 매핑에서 선택되지 않음")
        elif not beam_result:
            missing_reasons.append(f"**{label}**: 검토 결과 없음 (검토 실행 필요)")
        else:
            issues = []
            h = float(beam_input.get('h_beam', 0) or 0)
            b = float(beam_input.get('b_beam', 0) or 0)
            if h <= 0: issues.append("높이(H)=0")
            if b <= 0: issues.append("폭(B)=0")
            rt = beam_input.get('rebar_top', '')
            rb = beam_input.get('rebar_bot', '')
            if not rt and not rb: issues.append("배근 미입력")
            missing_reasons.append(f"**{label}**: {', '.join(issues)}" if issues else f"**{label}**: 데이터 부족")

    def _diagnose_col(col_input_d, col_result, compat):
        if compat:
            return
        if not col_input_d:
            missing_reasons.append("**기둥**: 매핑에서 선택되지 않음")
        elif not col_result:
            missing_reasons.append("**기둥**: 검토 결과 없음 (검토 실행 필요)")
        else:
            issues = []
            c = float(col_input_d.get('c_column', 0) or 0)
            if c <= 0: issues.append("단면 치수=0")
            rv = col_input_d.get('rebar_vert', '') or col_input_d.get('rebar_top', '')
            if not rv: issues.append("주근 미입력")
            missing_reasons.append(f"**기둥**: {', '.join(issues)}" if issues else "**기둥**: 데이터 부족")

    _diagnose_beam("장변보", ceil_x_input, _find_result_beam(ceil_x_name), beam_x_compat)
    _diagnose_beam("단변보", ceil_y_input, _find_result_beam(ceil_y_name), beam_y_compat)
    _diagnose_col(col_input, _find_result_col(col_name), col_compat)

    # 슬래브 진단 (선택사항이지만 선택했는데 실패한 경우)
    _slab_mapped = frame_mapping.get('slab')
    if _slab_mapped and not slab_compat:
        _slab_h = float(_slab_mapped.get('H', 0) or 0)
        if _slab_h <= 0:
            missing_reasons.append("**슬래브**: 두께(H)=0")
        else:
            missing_reasons.append("**슬래브**: 데이터 부족")

    # frame_3d가 기대하는 results dict
    compat_results = {}
    if beam_x_compat:
        compat_results['beam_x'] = beam_x_compat
    if beam_y_compat:
        compat_results['beam_y'] = beam_y_compat
    if gb_x_compat:
        compat_results['ground_beam_x'] = gb_x_compat
    if gb_y_compat:
        compat_results['ground_beam_y'] = gb_y_compat
    if col_compat:
        compat_results['column'] = col_compat
        compat_results['columns'] = [col_compat]
    if slab_compat:
        compat_results['slab'] = slab_compat

    # frame_3d가 기대하는 inputs dict
    def _get_span(beam_input):
        if not beam_input:
            return 0
        span_m = beam_input.get('span_m') or (beam_input.get('geometry', {}) or {}).get('span_m')
        if span_m and float(span_m) > 0:
            return float(span_m) * 1000
        return 0

    floor_x_input = frame_mapping.get('floor_x')
    floor_y_input = frame_mapping.get('floor_y')
    _Lx = _get_span(ceil_x_input)
    if _Lx <= 0:
        _Lx = _get_span(floor_x_input)
    _Ly = _get_span(ceil_y_input)
    if _Ly <= 0:
        _Ly = _get_span(floor_y_input)

    _h_col = float(col_input.get('h_column', 0) or 0) if col_input else 0

    # 경간/기둥높이 누락 진단
    if _Lx <= 0:
        missing_reasons.append("**장변보 경간(Span)**: 0 또는 미입력")
    if _Ly <= 0:
        missing_reasons.append("**단변보 경간(Span)**: 0 또는 미입력")
    if _h_col <= 0:
        missing_reasons.append("**기둥 높이(H_col)**: 0 또는 미입력")

    compat_inputs = {
        'L_x': _Lx,
        'L_y': _Ly,
        'h_column': _h_col,
    }

    return {
        'results': compat_results,
        'inputs': compat_inputs,
        'missing_reasons': missing_reasons,
    }
