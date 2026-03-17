import numpy as np
from beam_engine import BeamAnalyzer, round_up_to_50
from column_engine import ColumnAnalyzer
from slab_engine import SlabAnalyzer


# ────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 처짐 검토를 포함한 보 설계 반복 루프
# ────────────────────────────────────────────────────────────────────────────
def _design_beam_with_deflection(L, S_slab, t_slab, DL_area, LL_area,
                                  fc_k, fy, beam_type, max_iter=10, n_zones=3,
                                  h_beam_fixed=None, b_beam_fixed=None):
    """
    KDS 41 20 30 설계 순서에 따른 보 설계 (처짐·폭 수렴 루프 포함).

    설계 흐름:
        1. L/28 최적화 시작점 초기 단면 (h_beam_start), b=h×0.5 시작
        2. 휨 설계 — 상부근 (M_neg), 하부근 (M_pos)
        3. 철근 배근 결정
           ❌ 1단 배근 불가 또는 휨 강도 부족 → b += 50mm 후 2번부터 재설계
        4. 처짐 검토 (KDS 41 20 30 4.3)
           ✅ 만족 → 전단 설계 후 반환
           ❌ 불만족 → h += 50mm, b 리셋 후 2번부터 재설계
        5. 전단 설계 (처짐 만족 확정 후)

    Returns:
        dict (results['beam_x'] / results['beam_y'] 구조와 동일)
    """
    # ── 사용자 지정 사이즈: 수렴 루프 제어 ──────────────────────
    # h와 b 모두 지정 시 수렴 루프 건너뛰기, 부분 지정 시 나머지만 최적화
    _h_locked = h_beam_fixed is not None  # h 고정 여부
    _b_locked = b_beam_fixed is not None  # b 고정 여부
    _skip_convergence = (_h_locked and _b_locked)
    h_override = h_beam_fixed  # None이면 자동결정
    b_override = b_beam_fixed
    if _skip_convergence:
        max_iter = 1  # 고정 사이즈 → 1회 계산만
    deflection_governed = False
    width_governed = False
    n_iter = 0
    defl = {'ok': False}  # 루프 미수렴 시 defl 미정의 방지
    _d_unified = 25.4    # 루프 진입 전 기본값 (수렴 실패 방어)

    for n_iter in range(max_iter):
        # ── 1·2. 단면 가정 + 하중 ──────────────────────────────────
        analyzer = BeamAnalyzer(L, S_slab, t_slab, DL_area, LL_area,
                                fc_k, fy, beam_type,
                                h_beam_override=h_override,
                                b_beam_override=b_override)
        dp = analyzer.get_design_parameters()
        mf = analyzer.calculate_member_forces()

        # ── 3. 휨 설계 ──────────────────────────────────────────────
        # 상부근 (지점부 M_neg)
        As_top, warn_top, flex_top = analyzer.calculate_flexural_design(
            mf['M_neg'], dp['b_beam'], dp['h_beam'], fc_k, fy)
        rb_str_top, As_prov_top, lyr_top, rb_warn_top, rb_steps_top = \
            analyzer.calculate_rebar_detailing(As_top, dp['b_beam'])

        # 하부근 (중앙부 M_pos)
        As_bot, warn_bot, flex_bot = analyzer.calculate_flexural_design(
            mf['M_pos'], dp['b_beam'], dp['h_beam'], fc_k, fy)
        rb_str_bot, As_prov_bot, lyr_bot, rb_warn_bot, rb_steps_bot = \
            analyzer.calculate_rebar_detailing(As_bot, dp['b_beam'])

        # ── 3b. 강도 검토: discriminant<0 → h 증가 ─────────────────
        if As_top == 0.0 or As_bot == 0.0:
            if _skip_convergence or _h_locked:
                warn_top.append("⚠️ 지정 단면에서 휨 강도 부족 — 단면 증가 필요")
                break
            h_override = dp['h_beam'] + 50.0
            b_override = b_beam_fixed  # b 고정이면 유지, None이면 자동
            deflection_governed = True
            continue

        # ── 3c-1. 직경 통일: max(d_top, d_bot)으로 재배근 ───────────
        # 상·하부근이 한 보 안에서 동일 직경을 사용하도록 통일
        _d_top = rb_steps_top.get('selected_rebar_diameter', 25.4)
        _d_bot = rb_steps_bot.get('selected_rebar_diameter', 25.4)
        _d_unified = max(_d_top, _d_bot)

        if _d_top < _d_unified:
            # 상부근을 통일 직경으로 재계산
            rb_str_top, As_prov_top, lyr_top, rb_warn_top, rb_steps_top = \
                analyzer.calculate_rebar_detailing(
                    As_top, dp['b_beam'], force_diameter=_d_unified)
            rb_warn_top.append(
                f"정보: 직경 통일 적용 — D{int(_d_top)}→D{int(_d_unified)} "
                f"(하부근 직경에 맞춤)")

        if _d_bot < _d_unified:
            # 하부근을 통일 직경으로 재계산
            rb_str_bot, As_prov_bot, lyr_bot, rb_warn_bot, rb_steps_bot = \
                analyzer.calculate_rebar_detailing(
                    As_bot, dp['b_beam'], force_diameter=_d_unified)
            rb_warn_bot.append(
                f"정보: 직경 통일 적용 — D{int(_d_bot)}→D{int(_d_unified)} "
                f"(상부근 직경에 맞춤)")

        # ── 3c-2. 폭 검토: 1단 배근 불가 → b 증가 (단, b≤h 유지) ───
        # 2단 배근 발생 시 d_c_2layer로 As 재산정 (유효깊이 감소 반영)
        if lyr_top == 2 and 'd_c_2layer' in rb_steps_top:
            _dc2 = rb_steps_top['d_c_2layer']
            As_top, warn_top, flex_top = analyzer.calculate_flexural_design(
                mf['M_neg'], dp['b_beam'], dp['h_beam'], fc_k, fy)
            # d_c 오버라이드로 재산정 (flexural_design의 d_c를 직접 수정하지 않으므로 근사)
            _d2 = dp['h_beam'] - _dc2
            if _d2 > 0:
                _Rn2 = abs(mf['M_neg']) * 1e6 / (0.85 * dp['b_beam'] * _d2 ** 2)
                _disc2 = 1.0 - 2.0 * _Rn2 / (0.85 * fc_k)
                if _disc2 > 0:
                    _rho2 = (0.85 * fc_k / fy) * (1.0 - np.sqrt(_disc2))
                    _rho_min = max(0.25 * np.sqrt(fc_k) / fy, 1.4 / fy)
                    As_top = max(_rho2, _rho_min) * dp['b_beam'] * _d2
                    rb_str_top, As_prov_top, lyr_top, rb_warn_top, rb_steps_top = \
                        analyzer.calculate_rebar_detailing(As_top, dp['b_beam'])
        if lyr_bot == 2 and 'd_c_2layer' in rb_steps_bot:
            _dc2 = rb_steps_bot['d_c_2layer']
            _d2 = dp['h_beam'] - _dc2
            if _d2 > 0:
                _Rn2 = abs(mf['M_pos']) * 1e6 / (0.85 * dp['b_beam'] * _d2 ** 2)
                _disc2 = 1.0 - 2.0 * _Rn2 / (0.85 * fc_k)
                if _disc2 > 0:
                    _rho2 = (0.85 * fc_k / fy) * (1.0 - np.sqrt(_disc2))
                    _rho_min = max(0.25 * np.sqrt(fc_k) / fy, 1.4 / fy)
                    As_bot = max(_rho2, _rho_min) * dp['b_beam'] * _d2
                    rb_str_bot, As_prov_bot, lyr_bot, rb_warn_bot, rb_steps_bot = \
                        analyzer.calculate_rebar_detailing(As_bot, dp['b_beam'])

        if lyr_top == 2 or lyr_bot == 2:
            if _skip_convergence:
                # h+b 모두 고정 — 2단 배근 경고만 출력, 사이즈 변경 안 함
                break
            if _b_locked:
                # b 고정 → b 증가 불가, h 증가로 전환
                if _h_locked:
                    break  # 둘 다 고정이면 중단
                h_override = dp['h_beam'] + 50.0
                b_override = b_beam_fixed
                deflection_governed = True
            else:
                next_b = dp['b_beam'] + 50.0
                if next_b > dp['h_beam']:
                    if _h_locked:
                        break  # h 고정인데 b>h → 더 이상 증가 불가
                    h_override = dp['h_beam'] + 50.0
                    b_override = None
                    deflection_governed = True
                else:
                    b_override = next_b
                    width_governed = True
            continue

        # ── 4. 처짐 검토 ───────────────────────────────────────────
        # 통일된 직경 기반 d_c 사용
        _db_bot   = rb_steps_bot.get('selected_rebar_diameter', 25.4)
        _d_c_defl = 40.0 + 10.0 + _db_bot / 2.0
        defl = analyzer.calculate_deflection(As_prov_bot, As_prov_top, d_c_override=_d_c_defl)

        if defl['ok']:
            # ── 4b. 전단 예비 검토: Vs_max 초과 시 단면 증가 (#63) ──
            _d_pre = flex_top['d']
            _V_pre = mf['V_max'] - analyzer.w_u * (_d_pre / 1000.0)
            _s_pre, _, _sh_pre = analyzer.calculate_shear_design(
                _V_pre, dp['b_beam'], _d_pre, fc_k, fy)
            if _s_pre == 0.0 and not _skip_convergence:
                # Vs > Vs_max → 단면 파괴 위험, 단면 증가 필요
                if _h_locked and _b_locked:
                    warn_top.append("⚠️ 전단력 초과(Vs>Vs_max) — 단면 증가 필요")
                    break
                if not _b_locked:
                    next_b = dp['b_beam'] + 50.0
                    if next_b <= dp['h_beam']:
                        b_override = next_b
                        width_governed = True
                        continue
                if not _h_locked:
                    h_override = dp['h_beam'] + 50.0
                    b_override = b_beam_fixed
                    deflection_governed = True
                    continue
            break  # 처짐+전단 만족 → 최종 전단 설계로 진행

        if _skip_convergence or _h_locked:
            # h 고정 또는 h+b 모두 고정 — 처짐 불만족 경고만
            break

        # 불만족: 보 춤 50mm 증가, b는 고정이면 유지
        h_override = dp['h_beam'] + 50.0
        b_override = b_beam_fixed  # b 고정이면 유지, None이면 h 기반 리셋
        deflection_governed = True

    # ── 5. 전단 설계 (수렴 후 1회) ──────────────────────────────────
    # KDS 41 20 22 4.3.1: 위험단면 = 지점면에서 d 떨어진 곳
    _d_shear_m = flex_top['d'] / 1000.0  # mm → m
    V_at_d = mf['V_max'] - analyzer.w_u * _d_shear_m  # 위험단면 전단력 (kN)
    s, shear_warn, shear_steps = analyzer.calculate_shear_design(
        V_at_d, dp['b_beam'], flex_top['d'], fc_k, fy)
    shear_steps['V_max_face'] = mf['V_max']
    shear_steps['V_at_d'] = V_at_d
    shear_steps['d_critical_m'] = _d_shear_m

    # ── 5-1. 구간별 늑근 설계 ────────────────────────────────────────
    stirrup_zones = analyzer.calculate_shear_zones(
        n_zones, mf['V_max'], dp['b_beam'], flex_top['d'], fc_k, fy,
        x_start=_d_shear_m)

    # ── 5-1b. 구간별 스터럽 요약 (#64) ────────────────────────────────
    # 존별 간격 리스트 + 요약 문자열 생성 (지점부→중앙부 순)
    zone_spacings = [z['s'] for z in stirrup_zones]
    stirrup_zone_summary = "D10@" + "/".join(
        str(int(sp)) if sp > 0 else "NG" for sp in zone_spacings)

    # ── 5-2. 균열 제어 검토 (KDS 14 20 50 — 철근 간격 제한) ────────
    crack_top = BeamAnalyzer.calculate_crack_control(
        rb_str_top, dp['b_beam'], rb_steps_top['cover'], fy)
    crack_bot = BeamAnalyzer.calculate_crack_control(
        rb_str_bot, dp['b_beam'], rb_steps_bot['cover'], fy)

    # ── 5-3. 정착길이 / 이음길이 (KDS 14 20 52) ─────────────────
    _db_top_dev = rb_steps_top.get('selected_rebar_diameter', 25.4)
    _db_bot_dev = rb_steps_bot.get('selected_rebar_diameter', 25.4)

    # 철근 중심간격 산정 (cb = min(피복거리, 간격/2) 용)
    def _bar_spacing(rb_str, rb_steps, d_b):
        """보 주근 중심간격(mm). "n-Dxx" 형태에서 추출."""
        if not rb_str or rb_str == 'N/A' or '-' not in rb_str:
            return None
        n = int(rb_str.split('-')[0])
        if n < 2:
            return None
        name = rb_str.split('-')[1]
        S_min = rb_steps.get(f'S_min_{name}', max(33.3, d_b))
        return d_b + S_min  # center-to-center

    _sp_top = _bar_spacing(rb_str_top, rb_steps_top, _db_top_dev)
    _sp_bot = _bar_spacing(rb_str_bot, rb_steps_bot, _db_bot_dev)

    dev_top = BeamAnalyzer.calculate_development_length(
        _db_top_dev, fy, fc_k, position='top',
        cover=rb_steps_top['cover'], spacing=_sp_top,
        As_req=As_top, As_prov=As_prov_top)
    dev_bot = BeamAnalyzer.calculate_development_length(
        _db_bot_dev, fy, fc_k, position='bottom',
        cover=rb_steps_bot['cover'], spacing=_sp_bot,
        As_req=As_bot, As_prov=As_prov_bot)

    # ── 6. 최소 배근 (시각화용 — 통일직경 2가닥) ──────────────────
    # 지점부 하부 / 중앙부 상부에 배치하는 구조적 최소철근 (보의 통일직경 기준)
    _rebar_specs  = rb_steps_top['rebar_specs']
    _unified_name = rb_str_top.split('-')[1]       # e.g. "D25"
    _unified_Ab   = _rebar_specs[_unified_name]['area']
    rebar_string_min = f"2-{_unified_name}"
    As_provided_min  = 2.0 * _unified_Ab
    rebar_steps_min  = {
        'cover':                         rb_steps_top['cover'],
        'rebar_specs':                   _rebar_specs,
        f'n_final_{_unified_name}': 2,
        'selected_rebar_diameter':       _d_unified,
    }
    layer_min = 1

    return {
        'analyzer': analyzer,
        'design_params': dp,
        'member_forces': mf,
        # 상부근 (지점부 M_neg)
        'As_top': As_top,
        'warnings_top': warn_top,
        'flexural_steps_top': flex_top,
        'rebar_string_top': rb_str_top,
        'As_provided_top': As_prov_top,
        'layer_top': lyr_top,
        'rebar_warnings_top': rb_warn_top,
        'rebar_steps_top': rb_steps_top,
        # 하부근 (중앙부 M_pos)
        'As_bot': As_bot,
        'warnings_bot': warn_bot,
        'flexural_steps_bot': flex_bot,
        'rebar_string_bot': rb_str_bot,
        'As_provided_bot': As_prov_bot,
        'layer_bot': lyr_bot,
        'rebar_warnings_bot': rb_warn_bot,
        'rebar_steps_bot': rb_steps_bot,
        # 전단
        's': s,
        'shear_warnings': shear_warn,
        'shear_steps': shear_steps,
        'stirrup_zones': stirrup_zones,
        'stirrup_zone_summary': stirrup_zone_summary,
        'zone_spacings': zone_spacings,
        # 균열 제어
        'crack_top': crack_top,
        'crack_bot': crack_bot,
        # 정착길이/이음길이
        'dev_top': dev_top,
        'dev_bot': dev_bot,
        # 처짐
        'deflection': defl,
        'deflection_governed': deflection_governed,
        'deflection_n_iter': n_iter,
        # 폭 최적화
        'width_governed': width_governed,
        # 사용자 지정 사이즈 여부
        'size_fixed': _skip_convergence,
        'h_fixed': _h_locked,
        'b_fixed': _b_locked,
        # 최소 배근 (시각화용: 지점부 하부 / 중앙부 상부 — 통일직경 2가닥)
        'rebar_string_min': rebar_string_min,
        'As_provided_min':  As_provided_min,
        'rebar_steps_min':  rebar_steps_min,
        'layer_min':        layer_min,
    }


# ────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 세장비 검토를 포함한 기둥 설계 반복 루프
# ────────────────────────────────────────────────────────────────────────────
def _design_column_with_slenderness(h_column, b_beam_x, b_beam_y,
                                     fc_k, fy, Pu, Mux, Muy, max_iter=8,
                                     beta_d=None, c_column_fixed=None):
    """
    KDS 41 20 40 세장비 검토 순서에 따른 기둥 설계 (세장비 수렴 루프 포함).

    설계 흐름:
        1. 보 폭 기반 초기 단면
        2. 세장비 검토 (λ = kl_u/r)
           λ > 100 또는 좌굴 불안정 → c += 50mm 후 재시작
        3. 세장 기둥이면 Mu를 δ_ns로 증폭
        4. P-M 주철근 설계 (내부에서 c 증가 가능)
           c 증가 시 → 세장비 재검토
        5. 띠철근 설계 후 반환

    Mux, Muy: 각 방향별 설계 휨모멘트(kN·m). SRSS 조합은 ColumnAnalyzer 내에서 수행.

    Returns:
        dict (results['columns'][i] 구조)
    """
    # ── 사용자 지정 사이즈: 수렴 루프 건너뛰기 ──────────────────────
    _skip_col_convergence = (c_column_fixed is not None)
    c_override = c_column_fixed  # None이면 자동결정
    if _skip_col_convergence:
        max_iter = 1  # 고정 사이즈 → 1회 계산만
    slenderness_governed = False
    n_iter = 0
    # 마지막 반복 결과를 보존하기 위한 변수
    slend = None
    column_axial_moment = {}
    column_rebar_design = {}

    for n_iter in range(max_iter):
        analyzer = ColumnAnalyzer(
            h_column, b_beam_x, b_beam_y, fc_k, fy,
            Pu=Pu, Mux=Mux, Muy=Muy, c_column_override=c_override,
            beta_d=beta_d)

        # ── 2. 세장비 검토 ──────────────────────────────────────────
        slend = analyzer.calculate_slenderness()

        if not slend['ok']:
            if _skip_col_convergence:
                # 지정 단면 고정 — 세장비 초과 경고만
                break
            # λ > 100 또는 좌굴 불안정 → 단면 50mm 증가
            c_override = analyzer.c_column + 50.0
            slenderness_governed = True
            continue

        # ── 3. Mu 증폭 (세장 기둥) — 방향별 독립 적용 (#58) ─────────
        if slend['delta_ns'] is not None and slend['delta_ns'] > 1.0:
            _dns = slend['delta_ns']
            # 각 방향 독립 증폭 후 SRSS 재조합
            if analyzer.Mux is not None and analyzer.Muy is not None:
                analyzer.Mux = _dns * analyzer.Mux
                analyzer.Muy = _dns * analyzer.Muy
                analyzer.Mu  = float(np.sqrt(analyzer.Mux**2 + analyzer.Muy**2))
            else:
                analyzer.Mu = _dns * analyzer.Mu
            slenderness_governed = True

        # ── 4. 주철근 설계 (내부 c 증가 가능) ────────────────────────
        c_before = analyzer.c_column
        column_axial_moment = analyzer.calculate_axial_load_and_moment()
        column_rebar_design = analyzer.calculate_rebar_design()
        c_after = analyzer.c_column

        if c_after > c_before:
            if _skip_col_convergence:
                # 지정 단면 고정 — P-M 강도 부족 경고만
                break
            # 단면 증가 → 세장비 재검토
            c_override = c_after
            slenderness_governed = True
            continue

        # ── 5. 수렴 완료 → 띠철근 설계 ─────────────────────────────
        column_tie_rebar_design = analyzer.calculate_tie_rebar_design()
        column_member_forces    = analyzer.calculate_member_forces_arrays()

        return {
            'analyzer':            analyzer,
            'dimensions':          analyzer.get_column_dimensions(),
            'axial_moment':        column_axial_moment,
            'member_forces':       column_member_forces,
            'rebar_design':        column_rebar_design,
            'tie_rebar_design':    column_tie_rebar_design,
            'slenderness':         slend,
            'slenderness_governed': slenderness_governed,
            'slenderness_n_iter':  n_iter,
            'size_fixed': _skip_col_convergence,
        }

    # max_iter 초과 (수렴 실패 — 마지막 analyzer로 강제 설계 후 반환)
    # 마지막 analyzer 에 rebar_design 이 호출되지 않았을 수 있으므로 여기서 보장
    if not column_rebar_design:
        column_axial_moment  = analyzer.calculate_axial_load_and_moment()
        column_rebar_design  = analyzer.calculate_rebar_design()
    column_tie_rebar_design = analyzer.calculate_tie_rebar_design()
    column_member_forces    = analyzer.calculate_member_forces_arrays()
    return {
        'analyzer':            analyzer,
        'dimensions':          analyzer.get_column_dimensions(),
        'axial_moment':        column_axial_moment,
        'member_forces':       column_member_forces,
        'rebar_design':        column_rebar_design,
        'tie_rebar_design':    column_tie_rebar_design,
        'slenderness':         slend,
        'slenderness_governed': slenderness_governed,
        'slenderness_n_iter':  n_iter,
        'convergence_failed':  True,
        'size_fixed': _skip_col_convergence,
    }


# ────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 1방향 슬래브 구조설계
# ────────────────────────────────────────────────────────────────────────────
def _design_slab(L_short, t_slab, DL_area, LL_area, fc_k, fy):
    """1방향 슬래브 구조설계 (1m 스트립, 고정단)."""
    analyzer = SlabAnalyzer(L_short, t_slab, DL_area, LL_area, fc_k, fy)
    dp = analyzer.get_design_parameters()
    mf = analyzer.calculate_member_forces()

    # 휨 설계 — 지점부 상부근 (M_neg)
    As_top, warn_top, flex_top = analyzer.calculate_flexural_design(mf['M_neg'])
    rb_str_top, As_prov_top, rb_warn_top, rb_steps_top = \
        analyzer.calculate_rebar_detailing(As_top)

    # 휨 설계 — 중앙부 하부근 (M_pos)
    As_bot, warn_bot, flex_bot = analyzer.calculate_flexural_design(mf['M_pos'])
    rb_str_bot, As_prov_bot, rb_warn_bot, rb_steps_bot = \
        analyzer.calculate_rebar_detailing(As_bot)

    # 배력근 (수축·온도 철근, 경간 직각 방향)
    if fy >= 400:
        rho_dist = 0.0018
    elif fy <= 300:
        rho_dist = 0.0020
    else:
        rho_dist = 0.0020 - 0.0002 * (fy - 300.0) / 100.0
    # KDS 41 20 20: 수축온도 철근은 전체 단면적(Ag = b × h) 기준
    As_dist = rho_dist * 1000.0 * t_slab
    rb_str_dist, As_prov_dist, rb_warn_dist, rb_steps_dist = \
        analyzer.calculate_rebar_detailing(As_dist)

    # 전단 검토 (실제 배근 철근경으로 유효깊이 산정)
    _d_b_bot_actual = rb_steps_bot.get('selected_diameter', 9.53)
    shear_ok, shear_warn, shear_steps = analyzer.calculate_shear_check(
        mf['V_max'], d_b_actual=_d_b_bot_actual, w_u=analyzer.w_u)

    # 균열 제어 검토 (KDS 14 20 50)
    crack_top = SlabAnalyzer.calculate_crack_control(rb_str_top, 20.0, fy)
    crack_bot = SlabAnalyzer.calculate_crack_control(rb_str_bot, 20.0, fy)

    # 정착길이 (KDS 14 20 52) — 슬래브 배근 직경·간격 파싱
    _slab_rebar_specs = {"D10": 9.53, "D13": 12.7, "D16": 15.9}
    _slab_db_top = _slab_rebar_specs.get(rb_str_top.split('@')[0], 12.7) if rb_str_top else 12.7
    _slab_db_bot = _slab_rebar_specs.get(rb_str_bot.split('@')[0], 12.7) if rb_str_bot else 12.7
    # 슬래브 간격: "D10@200" → 200mm
    _slab_sp_top = float(rb_str_top.split('@')[1]) if rb_str_top and '@' in rb_str_top else None
    _slab_sp_bot = float(rb_str_bot.split('@')[1]) if rb_str_bot and '@' in rb_str_bot else None
    dev_top_slab = BeamAnalyzer.calculate_development_length(
        _slab_db_top, fy, fc_k, position='top', cover=20.0,
        spacing=_slab_sp_top, As_req=As_top, As_prov=As_prov_top)
    dev_bot_slab = BeamAnalyzer.calculate_development_length(
        _slab_db_bot, fy, fc_k, position='bottom', cover=20.0,
        spacing=_slab_sp_bot, As_req=As_bot, As_prov=As_prov_bot)

    # 처짐 검토
    defl = analyzer.calculate_deflection(As_prov_bot, As_prov_top, d_b_bot=_slab_db_bot)

    return {
        'design_params': dp,
        'member_forces': mf,
        # 상부근 (M_neg, 지점부)
        'As_top': As_top,
        'warnings_top': warn_top,
        'flexural_steps_top': flex_top,
        'rebar_string_top': rb_str_top,
        'As_provided_top': As_prov_top,
        'rebar_warnings_top': rb_warn_top,
        'rebar_steps_top': rb_steps_top,
        # 하부근 (M_pos, 중앙부)
        'As_bot': As_bot,
        'warnings_bot': warn_bot,
        'flexural_steps_bot': flex_bot,
        'rebar_string_bot': rb_str_bot,
        'As_provided_bot': As_prov_bot,
        'rebar_warnings_bot': rb_warn_bot,
        'rebar_steps_bot': rb_steps_bot,
        # 배력근 (수축·온도)
        'rebar_string_dist': rb_str_dist,
        'As_provided_dist': As_prov_dist,
        'rebar_warnings_dist': rb_warn_dist,
        'rebar_steps_dist': rb_steps_dist,
        # 전단
        'shear_ok': shear_ok,
        'shear_warnings': shear_warn,
        'shear_steps': shear_steps,
        # 균열 제어
        'crack_top': crack_top,
        'crack_bot': crack_bot,
        # 정착길이/이음길이
        'dev_top': dev_top_slab,
        'dev_bot': dev_bot_slab,
        # 처짐
        'deflection': defl,
    }


# ────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼: 하중조합 생성 (KDS 41 10 15)
# ────────────────────────────────────────────────────────────────────────────
def _build_column_load_combos(V_DL_x, V_LL_x, V_DL_y, V_LL_y,
                               M_DL_neg_x, M_LL_neg_x, M_DL_neg_y, M_LL_neg_y,
                               Pu_add, Mux_add, Muy_add, P_self,
                               E_Pu=0.0, E_Mux=0.0, E_Muy=0.0,
                               seismic_enabled=False):
    """
    기둥 설계용 하중조합 생성.

    NOTE: Pu_add, Mux_add, Muy_add는 사용자가 직접 입력하는 **이미 계수된** 상부층
    전달 하중(kN, kN·m)입니다. 따라서 모든 조합에 계수 없이 그대로 더합니다.

    Returns: [{'name': str, 'Pu': float, 'Mux': float, 'Muy': float}, ...]
    """
    combos = []

    # LC1: 1.2D + 1.6L (항상)
    Pu_12D16L = (Pu_add + 1.2 * (V_DL_x + V_DL_y) + 1.6 * (V_LL_x + V_LL_y)
                 + 1.2 * P_self)
    Mux_12D16L = Mux_add + 1.2 * M_DL_neg_x + 1.6 * M_LL_neg_x
    Muy_12D16L = Muy_add + 1.2 * M_DL_neg_y + 1.6 * M_LL_neg_y
    combos.append({
        'name': '1.2D+1.6L',
        'Pu': Pu_12D16L, 'Mux': Mux_12D16L, 'Muy': Muy_12D16L
    })

    # LC0: 1.4D
    Pu_14D = 1.4 * (V_DL_x + V_DL_y + P_self) + Pu_add
    Mux_14D = Mux_add + 1.4 * M_DL_neg_x
    Muy_14D = Muy_add + 1.4 * M_DL_neg_y
    combos.append({
        'name': '1.4D',
        'Pu': Pu_14D, 'Mux': Mux_14D, 'Muy': Muy_14D
    })

    if seismic_enabled:
        # LC2: 1.2D + 1.0E + 1.0L
        Pu_12DE = (Pu_add + 1.2 * (V_DL_x + V_DL_y) + 1.0 * (V_LL_x + V_LL_y)
                   + 1.2 * P_self + E_Pu)
        Mux_12DE = Mux_add + 1.2 * M_DL_neg_x + 1.0 * M_LL_neg_x + E_Mux
        Muy_12DE = Muy_add + 1.2 * M_DL_neg_y + 1.0 * M_LL_neg_y + E_Muy
        combos.append({
            'name': '1.2D+1.0E+1.0L',
            'Pu': Pu_12DE, 'Mux': Mux_12DE, 'Muy': Muy_12DE
        })

        # LC3: 0.9D + 1.0E
        Pu_09DE = 0.9 * (V_DL_x + V_DL_y + P_self) + E_Pu + Pu_add
        Mux_09DE = Mux_add + 0.9 * M_DL_neg_x + E_Mux
        Muy_09DE = Muy_add + 0.9 * M_DL_neg_y + E_Muy
        combos.append({
            'name': '0.9D+1.0E',
            'Pu': Pu_09DE, 'Mux': Mux_09DE, 'Muy': Muy_09DE
        })

    return combos


# ────────────────────────────────────────────────────────────────────────────
# 메인 계산 오케스트레이터
# ────────────────────────────────────────────────────────────────────────────
def perform_calculations(inputs):
    """
    모든 구조 계산 로직을 수행하고 결과를 딕셔너리로 반환합니다.
    """
    results = {}

    # 1. 입력 변수 언패킹
    L_x        = inputs['L_x']
    L_y        = inputs['L_y']
    h_column   = inputs['h_column']
    DL_area    = inputs['DL_area']
    LL_area    = inputs['LL_area']
    fc_k       = inputs['fc_k']
    fy         = inputs['fy']
    # 기둥 하중 — column_loads 리스트 우선, 없으면 레거시 단일 값 사용
    column_loads = inputs.get('column_loads', None)
    if column_loads is None or len(column_loads) == 0:
        # 하위 호환: 기존 단일 입력
        _pu  = inputs.get('Pu_column', 0.0)
        _mux = inputs.get('Mu_column', 0.0)  # 기존 Mu는 X방향으로 취급
        _muy = 0.0
        column_loads = [{'기둥명': '기둥 1', 'Pu_add': _pu, 'Mux_add': _mux, 'Muy_add': _muy}]
    # 바닥보 하중 — UI에서 별도 입력 시 해당 값, 없으면 천장보 하중과 동일
    DL_area_ground = inputs.get('DL_area_ground', DL_area)
    LL_area_ground = inputs.get('LL_area_ground', LL_area)
    # 늑근 구간 분할 수 (기본값 3)
    n_zones = inputs.get('n_zones', 3)
    # 부재 사이즈 직접 지정 (None이면 자동결정)
    _h_beam_x   = inputs.get('h_beam_x', None)
    _b_beam_x   = inputs.get('b_beam_x', None)
    _h_beam_y   = inputs.get('h_beam_y', None)
    _b_beam_y   = inputs.get('b_beam_y', None)
    _c_col_size = inputs.get('c_column_size', None)
    _t_slab_size = inputs.get('t_slab_size', None)

    # 2.1 공통 슬래브 두께 산정
    L_short    = min(L_x, L_y)
    t_slab_raw = L_short / 20.0
    t_slab     = max(round_up_to_50(t_slab_raw), 150.0)
    if _t_slab_size is not None:
        t_slab = float(_t_slab_size)  # 사용자 지정 슬래브 두께

    results['common'] = {
        'L_short':   L_short,
        't_slab_raw': t_slab_raw,
        't_slab':    t_slab,
    }

    # 2.2 슬래브 하중 분배 (1방향/2방향 자동 판별)
    L_long = max(L_x, L_y)
    aspect_ratio = L_long / L_short   # ≥ 1.0

    if aspect_ratio >= 2.0:
        # ── 1방향 슬래브: 단변 방향 보만 하중 부담, 장변보는 최소 분담폭 적용 ──
        slab_type = '1방향'
        # 장변보도 최소 1m 분담폭 적용 (보 자중만으로 비현실적 단면 방지)
        _S_min = min(1000.0, L_short / 4.0)
        if L_x >= L_y:
            S_slab_x = L_y / 2.0
            S_slab_y = _S_min
        else:
            S_slab_x = _S_min
            S_slab_y = L_x / 2.0
    else:
        # ── 2방향 슬래브: 4개 보 모두 하중 분담 (사다리꼴/삼각형 분배) ──
        # 등가등분포하중 기반 환산 분담폭 (Mmax 등가)
        #   장변보(사다리꼴): S = L_short·(3 − r²) / 6,  r = L_short/L_long
        #   단변보(삼각형)  : S = L_short / 3
        slab_type = '2방향'
        r = L_short / L_long   # ≤ 1.0
        S_long  = L_short * (3.0 - r ** 2) / 6.0   # 장변보 분담폭
        S_short = L_short / 3.0                      # 단변보 분담폭
        if L_x >= L_y:
            # X보 = 장변(사다리꼴), Y보 = 단변(삼각형)
            S_slab_x = S_long
            S_slab_y = S_short
        else:
            # Y보 = 장변(사다리꼴), X보 = 단변(삼각형)
            S_slab_x = S_short
            S_slab_y = S_long

    results['common']['slab_type']     = slab_type
    results['common']['aspect_ratio']  = aspect_ratio
    results['common']['S_slab_x']      = S_slab_x
    results['common']['S_slab_y']      = S_slab_y

    # 2.2.5 1방향 슬래브 구조설계 (경간 = L_short)
    results['slab'] = _design_slab(L_short, t_slab, DL_area, LL_area, fc_k, fy)

    # 2.3 X방향 보 설계 (처짐 수렴 루프 포함)
    results['beam_x'] = _design_beam_with_deflection(
        L_x, S_slab_x, t_slab, DL_area, LL_area, fc_k, fy, 'X', n_zones=n_zones,
        h_beam_fixed=_h_beam_x, b_beam_fixed=_b_beam_x)

    # 2.4 Y방향 보 설계 (처짐 수렴 루프 포함)
    results['beam_y'] = _design_beam_with_deflection(
        L_y, S_slab_y, t_slab, DL_area, LL_area, fc_k, fy, 'Y', n_zones=n_zones,
        h_beam_fixed=_h_beam_y, b_beam_fixed=_b_beam_y)

    # 편의 변수 (기둥 설계용)
    member_forces_x = results['beam_x']['member_forces']
    member_forces_y = results['beam_y']['member_forces']
    design_params_x = results['beam_x']['design_params']
    design_params_y = results['beam_y']['design_params']

    # 2.5 기둥 해석 및 설계 (기둥별 개별 하중 적용)
    # 1단계: 보 비계수 DL/LL 반력 분리 (하중조합용)
    w_DL_x = design_params_x['w_DL_unfactored']  # kN/m
    w_LL_x = design_params_x['w_LL_unfactored']
    w_DL_y = design_params_y['w_DL_unfactored']
    w_LL_y = design_params_y['w_LL_unfactored']
    L_x_m  = L_x / 1000.0
    L_y_m  = L_y / 1000.0

    V_DL_x = w_DL_x * L_x_m / 2.0   # 비계수 DL 전단반력 (kN)
    V_LL_x = w_LL_x * L_x_m / 2.0
    V_DL_y = w_DL_y * L_y_m / 2.0
    V_LL_y = w_LL_y * L_y_m / 2.0

    # 비계수 보 단부 모멘트 (고정단: M_neg = wL²/12)
    M_DL_neg_x = w_DL_x * L_x_m ** 2 / 12.0
    M_LL_neg_x = w_LL_x * L_x_m ** 2 / 12.0
    M_DL_neg_y = w_DL_y * L_y_m ** 2 / 12.0
    M_LL_neg_y = w_LL_y * L_y_m ** 2 / 12.0

    # 계수 합산값 (기존 호환)
    V_beam_x = member_forces_x['V_max']
    V_beam_y = member_forces_y['V_max']
    M_neg_x  = member_forces_x['M_neg']
    M_neg_y  = member_forces_y['M_neg']

    # 내진 설계 옵션
    seismic_enabled = inputs.get('seismic_enabled', False)
    frame_type = inputs.get('frame_type', 'OMF')

    # 초기 자중 산정용 단면 (보 폭 기반)
    _col_init = ColumnAnalyzer(
        h_column, design_params_x['b_beam'], design_params_y['b_beam'],
        fc_k, fy, Pu=0, Mu=0)
    c_column_init = _col_init.get_column_dimensions()['c_column']

    # 2단계: 각 기둥별 설계
    columns_results = []
    for col_load in column_loads:
        col_name   = col_load.get('기둥명', '기둥')
        Pu_add     = float(col_load.get('Pu_add', 0.0))
        Mux_add    = float(col_load.get('Mux_add', 0.0))
        Muy_add    = float(col_load.get('Muy_add', 0.0))
        E_Pu       = float(col_load.get('E_Pu', 0.0))
        E_Mux      = float(col_load.get('E_Mux', 0.0))
        E_Muy      = float(col_load.get('E_Muy', 0.0))

        # 초기 자중 산정
        P_self_col = (c_column_init / 1000.0) ** 2 * (h_column / 1000.0) * 24.0

        # beta_d = 1.2·DL / (1.2·DL + 1.6·LL) — 지속하중 비율 (KDS 41 20 40)
        _P_DL = V_DL_x + V_DL_y + P_self_col  # 비계수 DL 축력 (kN)
        _P_LL = V_LL_x + V_LL_y               # 비계수 LL 축력 (kN)
        _denom = 1.2 * _P_DL + 1.6 * _P_LL
        beta_d = (1.2 * _P_DL / _denom) if _denom > 0 else 0.6

        # 하중조합 생성
        combos = _build_column_load_combos(
            V_DL_x, V_LL_x, V_DL_y, V_LL_y,
            M_DL_neg_x, M_LL_neg_x, M_DL_neg_y, M_LL_neg_y,
            Pu_add, Mux_add, Muy_add, P_self_col,
            E_Pu, E_Mux, E_Muy, seismic_enabled)

        # 지배 조합 선택 — 각 조합별 P-M 검토 후 최불리 선택 (#43)
        # 모든 조합에 대해 예비 설계 → 최대 기둥 단면 또는 최대 철근비 조합이 지배
        _best_combo = combos[0]
        _best_severity = 0.0
        for _combo in combos:
            _Pu_c = _combo['Pu']
            _Mu_c = float(np.sqrt(_combo['Mux']**2 + _combo['Muy']**2))
            # 예비 기둥 설계 (1회만, 빠른 검토)
            _pre_ana = ColumnAnalyzer(
                h_column, design_params_x['b_beam'], design_params_y['b_beam'],
                fc_k, fy, Pu=_Pu_c, Mux=_combo['Mux'], Muy=_combo['Muy'],
                c_column_override=c_column_init if c_column_init else None,
                beta_d=beta_d)
            _pre_am = _pre_ana.calculate_axial_load_and_moment()
            _pre_rd = _pre_ana.calculate_rebar_design()
            # 심각도: 단면 크기 + 철근비 (단면 증가 필요 시 큰 값)
            _severity = _pre_ana.c_column * 1000 + _pre_rd.get('rho', 0.0) * 1e6
            if _severity > _best_severity:
                _best_severity = _severity
                _best_combo = _combo
        governing = _best_combo
        Pu_total   = governing['Pu']
        Mux_total  = governing['Mux']
        Muy_total  = governing['Muy']

        pu_breakdown = {
            'Pu_input': Pu_add,
            'V_beam_x': V_beam_x,
            'V_beam_y': V_beam_y,
            'P_self':   P_self_col,
            'Pu_total': Pu_total,
        }
        mu_breakdown = {
            'Mux_add':   Mux_add,
            'Muy_add':   Muy_add,
            'M_neg_x':   M_neg_x,
            'M_neg_y':   M_neg_y,
            'Mux_total': Mux_total,
            'Muy_total': Muy_total,
            'Mu_design': float(np.sqrt(Mux_total**2 + Muy_total**2)),
        }

        # 3단계: 세장비 검토 포함 기둥 설계 (자중 수렴 최대 2회)
        for _self_iter in range(2):
            col_result = _design_column_with_slenderness(
                h_column, design_params_x['b_beam'], design_params_y['b_beam'],
                fc_k, fy, Pu_total, Mux_total, Muy_total,
                beta_d=beta_d, c_column_fixed=_c_col_size)
            c_final    = col_result['analyzer'].c_column
            P_self_new = (c_final / 1000.0) ** 2 * (h_column / 1000.0) * 24.0

            # 자중 변경 시 조합 재생성
            combos = _build_column_load_combos(
                V_DL_x, V_LL_x, V_DL_y, V_LL_y,
                M_DL_neg_x, M_LL_neg_x, M_DL_neg_y, M_LL_neg_y,
                Pu_add, Mux_add, Muy_add, P_self_new,
                E_Pu, E_Mux, E_Muy, seismic_enabled)
            # 자중 갱신 후에도 최불리 조합 재선택 (#43)
            # 자중 수렴 루프는 빠른 판별 필요 → Pu + Mu/c 기반 간이 심각도
            _c_now = c_final or c_column_init
            governing = max(combos, key=lambda c: (
                c['Pu'] + np.sqrt(c['Mux']**2 + c['Muy']**2) * 1000.0 / max(_c_now, 1)))
            Pu_new = governing['Pu']

            if abs(Pu_new - Pu_total) < 0.5:
                P_self_col = P_self_new
                Pu_total   = Pu_new
                Mux_total  = governing['Mux']
                Muy_total  = governing['Muy']
                break
            P_self_col = P_self_new
            Pu_total   = Pu_new
            Mux_total  = governing['Mux']
            Muy_total  = governing['Muy']
        else:
            # 2회 반복 후에도 수렴하지 않은 경우 경고
            col_result.setdefault('warnings', []).append(
                f"기둥 자중 수렴 미달 (ΔPu={abs(Pu_new - Pu_total):.1f}kN)")

        # pu_breakdown / mu_breakdown 최종 자중으로 갱신
        pu_breakdown['P_self']   = P_self_col
        pu_breakdown['Pu_total'] = Pu_total
        mu_breakdown['Mux_total'] = Mux_total
        mu_breakdown['Muy_total'] = Muy_total
        mu_breakdown['Mu_design'] = float(np.sqrt(Mux_total**2 + Muy_total**2))

        # 접합부 전단 검토 (X/Y 양방향)
        c_final = col_result['analyzer'].c_column
        joint_x = ColumnAnalyzer.calculate_joint_shear(
            As_beam_top=results['beam_x']['As_provided_top'],
            fy=fy, fc_k=fc_k, c_column=c_final,
            b_beam=design_params_x['b_beam'],
            M_neg_beam=M_neg_x,
            h_column=h_column,
            frame_type=frame_type)
        joint_y = ColumnAnalyzer.calculate_joint_shear(
            As_beam_top=results['beam_y']['As_provided_top'],
            fy=fy, fc_k=fc_k, c_column=c_final,
            b_beam=design_params_y['b_beam'],
            M_neg_beam=M_neg_y,
            h_column=h_column,
            frame_type=frame_type)

        columns_results.append({
            'col_name':            col_name,
            'analyzer':            col_result['analyzer'],
            'dimensions':          col_result['dimensions'],
            'axial_moment':        col_result['axial_moment'],
            'member_forces':       col_result['member_forces'],
            'rebar_design':        col_result['rebar_design'],
            'tie_rebar_design':    col_result['tie_rebar_design'],
            'slenderness':         col_result['slenderness'],
            'slenderness_governed': col_result['slenderness_governed'],
            'slenderness_n_iter':  col_result['slenderness_n_iter'],
            'size_fixed':          col_result.get('size_fixed', False),
            'pu_breakdown':        pu_breakdown,
            'mu_breakdown':        mu_breakdown,
            'load_combos':         combos,
            'governing_combo':     governing['name'],
            'frame_type':          frame_type,
            'joint_shear_x':       joint_x,
            'joint_shear_y':       joint_y,
        })

    results['columns'] = columns_results
    # 하위 호환: 첫 번째 기둥을 'column'으로도 참조 가능하게 유지
    results['column']  = columns_results[0]

    # 2.5.1 IMF 내진 상세 검토 (frame_type == 'IMF'일 때)
    if frame_type == 'IMF':
        # 보 IMF 상세
        for key in ['beam_x', 'beam_y']:
            bm = results[key]
            _db_main = bm['rebar_steps_top'].get('selected_rebar_diameter', 25.4)
            _db_stir = 9.53  # D10
            results[key]['imf'] = BeamAnalyzer.calculate_imf_beam_detailing(
                h_beam=bm['design_params']['h_beam'],
                d=bm['flexural_steps_top']['d'],
                db_main=_db_main,
                db_stirrup=_db_stir,
                As_top=bm['As_provided_top'],
                As_bot=bm['As_provided_bot'],
                s_stirrup=bm['s'])

        # 기둥 IMF 상세 + 강기둥-약보
        # 보 공칭 휨강도 (Mn = As × fy × (d - a/2), 상부근 기준)
        def _beam_Mn(bm_result):
            As = bm_result['As_provided_top']
            d_v = bm_result['flexural_steps_top']['d']
            b_v = bm_result['design_params']['b_beam']
            a_v = As * fy / (0.85 * fc_k * b_v)
            return As * fy * (d_v - a_v / 2.0) / 1e6  # kN·m

        Mn_beam_x = _beam_Mn(results['beam_x'])
        Mn_beam_y = _beam_Mn(results['beam_y'])

        for col_r in columns_results:
            _ana = col_r['analyzer']
            _rd = col_r['rebar_design']
            _td = col_r['tie_rebar_design']
            col_r['imf'] = _ana.calculate_imf_column_detailing(
                h_column=h_column,
                db_main=_rd['rebar_diameter_col'],
                db_tie=_td['tie_rebar_diameter'],
                s_tie_normal=_td['tie_rebar_spacing'])
            col_r['scwb'] = _ana.calculate_strong_column_weak_beam(
                Pu=col_r['axial_moment']['Pu'],
                Mn_beam_x=Mn_beam_x,
                Mn_beam_y=Mn_beam_y)

    # 2.6 바닥보 독립 설계 (별도 하중 → 독립 BeamAnalyzer 인스턴스)
    if inputs.get('show_ground_beam', True):
        results['ground_beam_x'] = _design_beam_with_deflection(
            L_x, S_slab_x, t_slab, DL_area_ground, LL_area_ground, fc_k, fy, 'X', n_zones=n_zones,
            h_beam_fixed=_h_beam_x, b_beam_fixed=_b_beam_x)
        results['ground_beam_y'] = _design_beam_with_deflection(
            L_y, S_slab_y, t_slab, DL_area_ground, LL_area_ground, fc_k, fy, 'Y', n_zones=n_zones,
            h_beam_fixed=_h_beam_y, b_beam_fixed=_b_beam_y)

    return results
