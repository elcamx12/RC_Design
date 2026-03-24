"""
구조계산서 검토 모드 — 독립 계산 로직

기존 엔진(beam_engine.py, column_engine.py)을 수정하지 않고,
KDS 수식을 검토 전용으로 별도 구현합니다.

검토 모드 특징:
- 부재력(Mu, Vu, Pu)을 PDF에서 직접 가져와 사용
- 단면 크기 고정 (수렴루프 없음)
- 보: END-I / MID / END-J 위치별 독립 설계
- 기둥: Pu/Mux/Muy 직접 사용
- 슬래브 설계 제외
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


def _round_down_50(value):
    """값을 50mm 단위로 내림. 최소 100mm."""
    return max(np.floor(value / 50.0) * 50.0, 100.0)


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
        _disc_est = 1.0 - (2.0 * _Rn_est) / (0.85 * fc_k)
        if _disc_est > 0.0:
            _rho_est = (0.85 * fc_k / fy) * (1.0 - np.sqrt(_disc_est))
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

    # beta1  (KDS 41 20 20 4.1.1)
    if fc_k <= 28:
        beta1 = 0.85
    else:
        beta1 = max(0.65, 0.85 - 0.007 * (fc_k - 28))
    steps['beta1'] = beta1

    epsilon_cu = 0.003  # KDS 41 20 기준

    # ── φ-εt 수렴 루프 (KDS 41 20 20 4.2.2) ──
    discriminant = 1.0
    rho_req = 0.0
    _phi_iter = 0
    for _phi_iter in range(10):
        Mn_Nmm = Mu_Nmm / phi
        Rn = Mn_Nmm / (b * d ** 2)
        discriminant = 1 - (2 * Rn) / (0.85 * fc_k)
        if discriminant < 0:
            break

        rho_req = (0.85 * fc_k / fy) * (1 - np.sqrt(discriminant))

        As_iter = rho_req * b * d
        a_iter = (As_iter * fy) / (0.85 * fc_k * b)
        c_iter = a_iter / beta1
        epsilon_t_iter = epsilon_cu * (d - c_iter) / c_iter if c_iter > 0 else 0.005

        _eps_y = fy / 200000.0  # KDS: epsilon_y = fy/Es
        if epsilon_t_iter >= 0.005:
            phi_new = 0.85
        elif epsilon_t_iter <= _eps_y:
            phi_new = 0.65
        else:
            phi_new = 0.65 + (epsilon_t_iter - _eps_y) * 0.20 / (0.005 - _eps_y)

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
    a = (As * fy) / (0.85 * fc_k * b)
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

def _review_shear(Vu, b, d, fc_k, fy_t=400.0):
    """
    KDS 41 20 22 §4.3 — 전단 설계 (검토 모드).

    검토 모드에서 Vu는 이미 설계 전단력 (V_at_d 계산 불필요).

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

    Vc_N = (1 / 6) * lambda_factor * np.sqrt(fc_k) * b * d
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
    """주어진 As로 φMn 계산 (KDS 41 20 22). 반환: (phi_Mn_kNm, phi, a, c, epsilon_t)"""
    if As <= 0 or b <= 0 or d <= 0 or fc_k <= 0 or fy <= 0:
        return 0.0, 0.85, 0.0, 0.0, 0.005
    beta1 = 0.85 if fc_k <= 28 else max(0.65, 0.85 - 0.007 * (fc_k - 28))  # KDS 41 20 20 4.1.1
    a = (As * fy) / (0.85 * fc_k * b)
    c = a / beta1
    epsilon_t = 0.003 * (d - c) / c if c > 0 else 0.1
    # φ 결정 (KDS 41 20 20) — epsilon_y를 fy에서 동적 계산
    eps_y = fy / 200000.0  # Es = 200,000 MPa
    if epsilon_t >= 0.005:
        phi = 0.85
    elif epsilon_t <= eps_y:
        phi = 0.65
    else:
        phi = 0.65 + (epsilon_t - eps_y) * (0.85 - 0.65) / (0.005 - eps_y)
    phi_Mn = phi * As * fy * (d - a / 2.0) / 1e6  # N·mm → kN·m
    return phi_Mn, phi, a, c, epsilon_t


def _review_beam_location(Mu_neg, Mu_pos, Vu, b, h, fc_k, fy, cover=40.0,
                           Loc_top=None, Loc_bot=None,
                           rebar_top_str=None, rebar_bot_str=None,
                           stirrup_str=None):
    """
    단일 위치 (END-I / MID / END-J) 검토.
    구조계산서 배근(rebar_top_str/rebar_bot_str)이 주어지면 그걸로 φMn 계산.

    Returns:
        dict with flexural_neg, flexural_pos, shear, ok_overall
    """
    result = {}

    # ── 상부근 (부모멘트) ──
    As_neg, warn_neg, steps_neg = _review_flexural(Mu_neg, b, h, fc_k, fy, cover, Loc=Loc_top)
    d_neg = steps_neg.get('d', h - 60.0)

    # 구조계산서 배근 기반 φMn
    n_top, dia_top, As_doc_top = _parse_rebar_string(rebar_top_str)
    if As_doc_top > 0:
        _neg_phi_Mn, _neg_phi, _neg_a, _neg_c, _neg_et = _calc_phi_Mn(As_doc_top, b, d_neg, fc_k, fy)
        _neg_ok = (abs(Mu_neg) <= _neg_phi_Mn + 0.01) if Mu_neg != 0 else True
        _neg_rebar_str = rebar_top_str
        _neg_As_prov = As_doc_top
        # 제공 배근 기반 경고만 생성 (As_req 경고 무시)
        warn_neg_final = []
        if _neg_et < 0.004 and Mu_neg != 0:
            warn_neg_final.append(f"주의: 제공 배근 εt={_neg_et:.4f} < 0.004")
        if not _neg_ok and Mu_neg != 0:
            warn_neg_final.append(f"NG: φMn={_neg_phi_Mn:.2f} < Mu={abs(Mu_neg):.2f}")
    else:
        # 구조계산서 배근 없음 → As_req 기반
        _neg_rebar_str, _neg_As_prov, _neg_layer, _neg_warn_rb, _neg_steps_rb = _review_rebar(As_neg, b, cover)
        _neg_phi_Mn, _neg_phi, _neg_a, _neg_c, _neg_et = _calc_phi_Mn(_neg_As_prov, b, d_neg, fc_k, fy)
        _neg_ok = (abs(Mu_neg) <= _neg_phi_Mn + 0.01) if Mu_neg != 0 else True
        warn_neg_final = warn_neg + (_neg_warn_rb if '_neg_warn_rb' in locals() else [])

    result['flexural_neg'] = {
        'Mu': Mu_neg,
        'As_req': As_neg,
        'rebar_string': _neg_rebar_str,
        'As_provided': _neg_As_prov,
        'phi_Mn': _neg_phi_Mn,
        'phi': _neg_phi,
        'ok': _neg_ok,
        'check_ratio': abs(Mu_neg) / _neg_phi_Mn if _neg_phi_Mn > 0 else 999,
        'warnings': warn_neg_final,
        'flexural_steps': steps_neg,
    }

    # ── 하부근 (정모멘트) ──
    As_pos, warn_pos, steps_pos = _review_flexural(Mu_pos, b, h, fc_k, fy, cover, Loc=Loc_bot)
    d_pos = steps_pos.get('d', h - 60.0)

    n_bot, dia_bot, As_doc_bot = _parse_rebar_string(rebar_bot_str)
    if As_doc_bot > 0:
        _pos_phi_Mn, _pos_phi, _pos_a, _pos_c, _pos_et = _calc_phi_Mn(As_doc_bot, b, d_pos, fc_k, fy)
        _pos_ok = (abs(Mu_pos) <= _pos_phi_Mn + 0.01) if Mu_pos != 0 else True
        _pos_rebar_str = rebar_bot_str
        _pos_As_prov = As_doc_bot
        # 제공 배근 기반 경고만 생성
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

    result['flexural_pos'] = {
        'Mu': Mu_pos,
        'As_req': As_pos,
        'rebar_string': _pos_rebar_str,
        'As_provided': _pos_As_prov,
        'phi_Mn': _pos_phi_Mn,
        'phi': _pos_phi,
        'ok': _pos_ok,
        'check_ratio': abs(Mu_pos) / _pos_phi_Mn if _pos_phi_Mn > 0 else 999,
        'warnings': warn_pos_final,
        'flexural_steps': steps_pos,
    }

    # 전단
    # d는 상부근 기준 (Vu는 보통 지점부에서 최대, 상부근이 인장)
    d_for_shear = steps_neg.get('d', h - 60.0)
    s_final, warn_shear, steps_shear = _review_shear(Vu, b, d_for_shear, fc_k)
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

def _review_column(col_input, fc_k, fy):
    """
    기둥 1개 검토: P-M 포락선 + 배근 산정 + 띠철근.

    단면 고정 (c_column 변경 없음). P-M 불만족 시 NG 반환.

    Args:
        col_input: {name, c_column, h_column, Pu, Mux, Muy}
        fc_k, fy: 재료

    Returns:
        dict
    """
    name = col_input.get('name', 'Column')
    c_column = float(col_input['c_column'])
    h_column = float(col_input.get('h_column', 3000))
    if h_column <= 0:
        h_column = 3000.0  # 기본값 3m
    if c_column <= 0:
        c_column = 400.0  # 기본값 400mm
    Pu = float(col_input.get('Pu', 0))
    Mux = float(col_input.get('Mux', 0))
    Muy = float(col_input.get('Muy', 0))
    Mu = float(np.sqrt(Mux ** 2 + Muy ** 2))  # SRSS

    Ag = c_column * c_column

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

    if lambda_ratio <= 22:
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

    # ── P-M 설계 (단면 고정, 수렴루프 없이 철근만 탐색) ──
    phi_comp = 0.65
    phi_tens = 0.85
    beta1 = max(0.85 - 0.007 * (fc_k - 28), 0.65) if fc_k > 28 else 0.85

    rebar_sizes_col = ["D22", "D25", "D29", "D32"]
    _col_cover = float(col_input.get('cover', 40.0))
    _tie_dia_c = 9.53

    # 최소 편심
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

    safe = False
    n_col = 4
    _size_idx = 0
    rebar_type_col = rebar_sizes_col[_size_idx]
    rebar_area_col = REBAR_SPECS[rebar_type_col]['area']
    rebar_diameter_col = REBAR_SPECS[rebar_type_col]['diameter']

    _pm_max_iter = 60
    _pm_iter = 0
    phi_Pn_max = 0
    phi_Pn_b = 0
    phi_Mn_b = 0
    phi_Mn_o = 0
    _fit_ok = False
    _n_per_side = 2

    while not safe:
        _pm_iter += 1
        if _pm_iter > _pm_max_iter:
            break

        As_total = n_col * rebar_area_col
        rho = As_total / Ag

        if rho > 0.08:
            # 검토 모드: 단면 고정이므로 NG
            break

        cover_approx = _col_cover + _tie_dia_c + rebar_diameter_col / 2.0
        d_eff = c_column - cover_approx
        d_prime = cover_approx
        As_half = As_total / 2.0
        h_half = c_column / 2.0

        # 점 A: 순수 압축
        Pn_max = 0.85 * fc_k * (Ag - As_total) + fy * As_total
        phi_Pn_max = 0.80 * phi_comp * Pn_max / 1000.0

        # 점 B: 균형 파괴
        c_b = (600.0 / (600.0 + fy)) * d_eff
        a_b = beta1 * c_b
        fs_prime = min(600.0 * (c_b - d_prime) / c_b, fy)
        Pn_b = (0.85 * fc_k * a_b * c_column + As_half * fs_prime - As_half * fy)
        Mn_b = (0.85 * fc_k * a_b * c_column * (h_half - a_b / 2.0)
                + As_half * fs_prime * (h_half - d_prime)
                + As_half * fy * (d_eff - h_half))
        phi_Pn_b = phi_comp * Pn_b / 1000.0
        phi_Mn_b = phi_comp * Mn_b / 1e6

        # 점 C: 순수 휨 (이분법)
        _c_lo, _c_hi = 1e-6, c_column
        for _ in range(60):
            _c_mid = (_c_lo + _c_hi) / 2.0
            _fs_c = min(max(600.0 * (_c_mid - d_prime) / _c_mid, -fy), fy)
            _Pn_c = (0.85 * fc_k * beta1 * _c_mid * c_column
                     + As_half * _fs_c - As_half * fy)
            if _Pn_c < 0.0:
                _c_lo = _c_mid
            else:
                _c_hi = _c_mid
            if _c_hi - _c_lo < 0.01:
                break
        c_o = (_c_lo + _c_hi) / 2.0
        a_o = beta1 * c_o
        fs_o = min(max(600.0 * (c_o - d_prime) / c_o, -fy), fy)
        Mn_o = (0.85 * fc_k * a_o * c_column * (h_half - a_o / 2.0)
                + As_half * fs_o * (h_half - d_prime)
                + As_half * fy * (d_eff - h_half))
        phi_Mn_o = phi_tens * Mn_o / 1e6

        eps_y = fy / 200000.0

        # P-M 포락선 검토
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
                    a_i = beta1 * c_i
                    fs_p_i = min(max(600.0 * (c_i - d_prime) / c_i, -fy), fy)
                    Pn_i = (0.85 * fc_k * a_i * c_column
                            + As_half * fs_p_i - As_half * fy)
                    Mn_i = (0.85 * fc_k * a_i * c_column * (h_half - a_i / 2.0)
                            + As_half * fs_p_i * (h_half - d_prime)
                            + As_half * fy * (d_eff - h_half))
                    eps_t_i = 0.003 * max(d_eff - c_i, 0.0) / c_i
                    if eps_t_i >= 0.005:
                        phi_i = phi_tens
                    elif eps_t_i <= eps_y:
                        phi_i = phi_comp
                    else:
                        phi_i = phi_comp + (phi_tens - phi_comp) * (eps_t_i - eps_y) / (0.005 - eps_y)
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

        if not safe or rho < 0.01:
            if n_col > 12 and _size_idx < len(rebar_sizes_col) - 1:
                _size_idx += 1
                rebar_type_col = rebar_sizes_col[_size_idx]
                rebar_area_col = REBAR_SPECS[rebar_type_col]['area']
                rebar_diameter_col = REBAR_SPECS[rebar_type_col]['diameter']
                n_col = 4
            elif n_col >= 12 and _size_idx >= len(rebar_sizes_col) - 1:
                # 검토 모드: 단면 고정 → 더 이상 증가 불가 → NG
                break
            else:
                n_col += 2
            safe = False
        else:
            _n_per_side = int(np.ceil(n_col / 4)) + 1
            _s_min_col = max(40.0, 1.5 * rebar_diameter_col)
            _avail_col = c_column - 2.0 * (_col_cover + _tie_dia_c + rebar_diameter_col / 2.0)
            _req_col = (_n_per_side - 1) * (rebar_diameter_col + _s_min_col)
            _fit_ok = _avail_col >= _req_col
            if _fit_ok:
                # Bresler 검토
                if Mux > 0 and Muy > 0 and Pu > 0:
                    _br = _bresler_check(
                        Pu, Mux, Muy, n_col * rebar_area_col,
                        d_eff, d_prime, beta1, c_column, Ag, fc_k, fy,
                        phi_comp, phi_tens, eps_y)
                    if not _br['safe']:
                        if n_col >= 12 and _size_idx >= len(rebar_sizes_col) - 1:
                            break  # NG
                        elif n_col > 12 and _size_idx < len(rebar_sizes_col) - 1:
                            _size_idx += 1
                            rebar_type_col = rebar_sizes_col[_size_idx]
                            rebar_area_col = REBAR_SPECS[rebar_type_col]['area']
                            rebar_diameter_col = REBAR_SPECS[rebar_type_col]['diameter']
                            n_col = 4
                        else:
                            n_col += 2
                        safe = False
                        continue
                break
            else:
                if _size_idx < len(rebar_sizes_col) - 1:
                    _size_idx += 1
                    rebar_type_col = rebar_sizes_col[_size_idx]
                    rebar_area_col = REBAR_SPECS[rebar_type_col]['area']
                    rebar_diameter_col = REBAR_SPECS[rebar_type_col]['diameter']
                    n_col = 4
                else:
                    break  # 검토 모드: 단면 고정 → NG
                safe = False

    As_provided_col = n_col * rebar_area_col
    rebar_string_col = f"{n_col}-{rebar_type_col}"
    rho_final = As_provided_col / Ag

    # ── P-M 포락선 시각화 데이터 ──
    pm_P, pm_M, pm_Pn, pm_Mn = _build_pm_curve(
        c_column, As_provided_col, d_eff, d_prime, beta1, Ag, fc_k, fy,
        phi_comp, phi_tens, eps_y)

    # ── 띠철근 ──
    if int(rebar_type_col.replace('D', '')) <= 32:
        tie_type = "D10"
        tie_dia = 9.53
    else:
        tie_type = "D13"
        tie_dia = 12.7
    tie_spacing = int(np.floor(min(16 * rebar_diameter_col, 48 * tie_dia, c_column) / 50) * 50)

    # 결과 조립
    result = {
        'name': name,
        'c_column': c_column,
        'h_column': h_column,
        'Pu': Pu, 'Mux': Mux, 'Muy': Muy, 'Mu': Mu,
        'Mu_design': Mu_design,
        'is_min_ecc_applied': is_min_ecc_applied,
        'e_min': e_min, 'e_actual': e_actual,
        'dimensions': {'c_column': c_column, 'Ag': Ag},
        'rebar_design': {
            'rebar_string_col': rebar_string_col,
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
        },
        'slenderness': slenderness,
        'tie_rebar_design': {
            'tie_rebar_type': tie_type,
            'tie_rebar_diameter': tie_dia,
            'tie_rebar_spacing': tie_spacing,
        },
        'ok_pm': safe,
        'ok_slenderness': slenderness.get('ok', True),
        'ok_overall': safe and slenderness.get('ok', True),
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

def _find_Pn_at_eccentricity(e_target, As_total, d_eff, d_prime, beta1,
                              c_column, Ag, fc_k, fy):
    """주어진 편심(mm)에서 Pn(N)을 이분법으로 탐색."""
    As_half = As_total / 2.0
    h_half = c_column / 2.0
    c_lo, c_hi = 1e-3, c_column * 3.0

    for _ in range(60):
        c_mid = (c_lo + c_hi) / 2.0
        a_i = min(beta1 * c_mid, c_column)
        fs_p = min(max(600.0 * (c_mid - d_prime) / c_mid, -fy), fy)
        fs_t = min(max(600.0 * (d_eff - c_mid) / c_mid, -fy), fy)
        Pn = (0.85 * fc_k * a_i * c_column + As_half * fs_p - As_half * fs_t)
        Mn = (0.85 * fc_k * a_i * c_column * (h_half - a_i / 2.0)
              + As_half * fs_p * (h_half - d_prime)
              + As_half * fs_t * (d_eff - h_half))
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
                   c_column, Ag, fc_k, fy, phi_comp, phi_tens, eps_y):
    """Bresler 역수하중법: 1/Pn = 1/Pnx + 1/Pny - 1/Pno"""
    Pu_N = Pu * 1000.0
    ex = Mux * 1e6 / Pu_N if Pu_N > 0 else 0.0
    ey = Muy * 1e6 / Pu_N if Pu_N > 0 else 0.0

    Pnx = _find_Pn_at_eccentricity(ex, As_total, d_eff, d_prime, beta1, c_column, Ag, fc_k, fy)
    Pny = _find_Pn_at_eccentricity(ey, As_total, d_eff, d_prime, beta1, c_column, Ag, fc_k, fy)
    As_half = As_total / 2.0
    Pno = 0.85 * fc_k * (Ag - As_total) + fy * As_total

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
                    phi_comp, phi_tens, eps_y):
    """P-M 포락선 다점 데이터 생성 (시각화용)."""
    As_half = As_total / 2.0
    h_half = c_column / 2.0

    _Pno = 0.85 * fc_k * (Ag - As_total) + fy * As_total
    _Pn_cap_N = 0.80 * _Pno
    _phi_Pn_cap = 0.80 * phi_comp * _Pno / 1000.0

    c_b = (600.0 / (600.0 + fy)) * d_eff
    _c_trans_hi = 0.003 * d_eff / (0.003 + eps_y)
    _c_trans_lo = 0.003 * d_eff / (0.003 + 0.005)

    # Pn_cap 경계의 c 탐색
    _c_bisect_lo, _c_bisect_hi = _c_trans_hi, c_column / beta1 * 2.0
    for _ in range(40):
        _c_mid = (_c_bisect_lo + _c_bisect_hi) / 2.0
        _a_mid = min(beta1 * _c_mid, c_column)
        _fsp_mid = min(max(600.0 * (_c_mid - d_prime) / _c_mid, -fy), fy)
        _fst_mid = min(max(600.0 * (d_eff - _c_mid) / _c_mid, -fy), fy)
        _Pn_mid = (0.85 * fc_k * _a_mid * c_column + As_half * _fsp_mid - As_half * _fst_mid)
        if _Pn_mid > _Pn_cap_N:
            _c_bisect_hi = _c_mid
        else:
            _c_bisect_lo = _c_mid

    _c_sweep_hi = _c_bisect_hi
    _c_zone1 = np.linspace(_c_sweep_hi, _c_trans_hi, 40, endpoint=False)
    _c_zone2 = np.linspace(_c_trans_hi, _c_trans_lo, 30, endpoint=False)
    _c_zone3 = np.linspace(_c_trans_lo, 1e-3, 30)
    _c_arr = np.concatenate([_c_zone1, _c_zone2, _c_zone3])

    pm_P, pm_M, pm_Pn, pm_Mn = [], [], [], []

    for _c_i in _c_arr:
        _a_i = min(beta1 * _c_i, c_column)
        _fsp_i = min(max(600.0 * (_c_i - d_prime) / _c_i, -fy), fy)
        _fst_i = min(max(600.0 * (d_eff - _c_i) / _c_i, -fy), fy)
        _Pn_i = (0.85 * fc_k * _a_i * c_column + As_half * _fsp_i - As_half * _fst_i)
        _Mn_i = (0.85 * fc_k * _a_i * c_column * (h_half - _a_i / 2.0)
                 + As_half * _fsp_i * (h_half - d_prime)
                 + As_half * _fst_i * (d_eff - h_half))

        _Pn_cap = 0.80 * _Pno / 1000.0
        pm_Pn.append(min(_Pn_i / 1000.0, _Pn_cap))
        pm_Mn.append(max(_Mn_i / 1e6, 0.0))

        _eps_ti = 0.003 * max(d_eff - _c_i, 0.0) / _c_i
        if _eps_ti >= 0.005:
            _phi_i = phi_tens
        elif _eps_ti <= eps_y:
            _phi_i = phi_comp
        else:
            _phi_i = phi_comp + (phi_tens - phi_comp) * (_eps_ti - eps_y) / (0.005 - eps_y)

        pm_P.append(min(_phi_i * _Pn_i / 1000.0, _phi_Pn_cap))
        pm_M.append(max(_phi_i * _Mn_i / 1e6, 0.0))

    # 순수인장 점
    pm_P.append(-0.90 * fy * As_total / 1000.0)
    pm_M.append(0.0)
    pm_Pn.append(-fy * As_total / 1000.0)
    pm_Mn.append(0.0)

    return pm_P, pm_M, pm_Pn, pm_Mn


# ═══════════════════════════════════════════════════════════════════════
# 메인 오케스트레이터
# ═══════════════════════════════════════════════════════════════════════

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

    return {
        'mode': 'review',
        'fc_k': _default_fck,
        'fy': _default_fy,
        'review_beams': review_beams,
        'review_columns': review_columns,
    }
