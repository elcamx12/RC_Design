import streamlit as st
from .pdf_import import _pdf_import_section


def _colored_input(label, key, orig_key=None):
    """색상 인디케이터가 있는 text_input.
    - 🔴 빨간바: 구조계산서에서 못 찾은 값 (원본=0 또는 None)
    - 🟡 노란바: 사용자가 직접 수정한 값 (현재 != 원본)
    - 표시없음: 구조계산서에서 정상적으로 가져온 값
    반환: float (변환 실패 시 0.0)
    """
    _orig_key = orig_key or f"{key}_orig"
    orig_val = st.session_state.get(_orig_key, 0.0)

    # text_input 렌더링
    val_str = st.text_input(label, key=key)

    # 현재값
    try:
        cur_val = float(val_str.strip()) if val_str and val_str.strip() else 0.0
    except ValueError:
        cur_val = 0.0

    # 색상 인디케이터
    orig_f = float(orig_val) if orig_val else 0.0
    if orig_f == 0.0 and cur_val == 0.0:
        st.markdown('<div style="height:3px;background:#ff4444;border-radius:2px;margin-top:-10px;"></div>',
                    unsafe_allow_html=True)
    elif abs(cur_val - orig_f) > 0.001:
        st.markdown('<div style="height:3px;background:#ffaa00;border-radius:2px;margin-top:-10px;"></div>',
                    unsafe_allow_html=True)

    return cur_val


def _pick_size(override_key):
    """부재별 개별 추적: modified_sizes에 포함된 부재만 고정, 나머지는 수렴설계."""
    member = override_key.replace('override_', '')
    modified = st.session_state.get('modified_sizes', set())
    if member not in modified:
        return None  # 이 부재는 수렴설계
    override_val = st.session_state.get(override_key, 0)
    if override_val and override_val > 0:
        return override_val
    return None


def render_input_section():
    _pdf_import_section()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. 기하 조건")
        L_x = st.number_input("X방향 보의 경간 길이 (L_x) [mm]", min_value=1000, max_value=20000,
                               value=st.session_state.get('pdf_L_x', 6000), step=100)
        L_y = st.number_input("Y방향 보의 경간 길이 (L_y) [mm]", min_value=1000, max_value=20000,
                               value=st.session_state.get('pdf_L_y', 4500), step=100)
        h_column = st.number_input("기둥 높이 (H_column) [mm]", min_value=2000, max_value=10000,
                                   value=st.session_state.get('pdf_h_col', 3000), step=100)

    with col2:
        st.subheader("2. 하중 조건")
        st.markdown("**🏢 천장보 (상부보) 하중**")
        DL_area = st.number_input("추가 마감하중 (DL) [kN/m²]", min_value=0.0, max_value=10.0, value=2.0, step=0.1)
        LL_area = st.number_input("사용 용도에 따른 활하중 (LL) [kN/m²]", min_value=0.0, max_value=20.0, value=2.5, step=0.1)
        st.markdown("---")
    st.subheader("2-1. 바닥보 설계")
    show_ground_beam = st.checkbox("바닥보 설계 포함", value=True)
    if show_ground_beam:
        st.caption("💡 바닥보는 천장보와 독립적으로 설계됩니다. 하중이 다를 경우 아래에서 별도 입력하세요.")
        _gb_toggle_col, _gb_hint_col = st.columns([1, 3])
        with _gb_toggle_col:
            _gb_separate = st.checkbox("바닥보 별도 하중 입력", value=False)
        with _gb_hint_col:
            if not _gb_separate:
                st.info("현재: 천장보와 동일한 하중 적용 (DL={:.1f}, LL={:.1f} kN/m²)".format(DL_area, LL_area))
    else:
        _gb_separate = False
    if _gb_separate:
        _gb_c1, _gb_c2 = st.columns(2)
        with _gb_c1:
            st.markdown("**🏠 바닥보 하중**")
            DL_area_ground = st.number_input("바닥보 마감하중 (DL_ground) [kN/m²]",
                                             min_value=0.0, max_value=10.0,
                                             value=DL_area, step=0.1,
                                             key="DL_ground")
        with _gb_c2:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            LL_area_ground = st.number_input("바닥보 활하중 (LL_ground) [kN/m²]",
                                             min_value=0.0, max_value=20.0,
                                             value=LL_area, step=0.1,
                                             key="LL_ground")
    else:
        DL_area_ground = DL_area
        LL_area_ground = LL_area

    st.subheader("2-2. 기둥별 설계 추가 하중")
    st.caption("💡 기둥 최종 축하중 = 입력 추가 축하중 + 보 단부 반력 + 기둥 자중")
    st.caption("💡 기둥 최종 휨모멘트 = 입력 추가 모멘트 + 보 단부 모멘트 (강접합, SRSS 조합)")
    st.caption("💡 기둥 추가(➕) 버튼으로 기둥을 추가합니다. 이름은 자유롭게 수정 가능합니다.")
    st.caption("💡 Pu_add: 상부층 하중, Mux_add: X방향 횡력 모멘트, Muy_add: Y방향 횡력 모멘트 (보 단부 반력은 자동 합산)")

    # ── 세션 상태 초기화 ────────────────────────────────────────────
    if 'col_load_list' not in st.session_state:
        st.session_state['col_load_list'] = [
            {'기둥명': '기둥 1',
             'Pu_add': st.session_state.get('pdf_Pu', 0.0),
             'Mux_add': st.session_state.get('pdf_Mux', 100.0),
             'Muy_add': st.session_state.get('pdf_Muy', 0.0)}
        ]

    # ── 추가 / 삭제 버튼 ────────────────────────────────────────────
    _btn_add, _btn_del = st.columns(2)
    with _btn_add:
        if len(st.session_state['col_load_list']) < 4:
            if st.button("➕ 기둥 추가", key="col_add_btn"):
                _next_n = len(st.session_state['col_load_list']) + 1
                st.session_state['col_load_list'].append(
                    {'기둥명': f'기둥 {_next_n}', 'Pu_add': 0.0, 'Mux_add': 0.0, 'Muy_add': 0.0}
                )
                st.rerun()
        else:
            st.caption("최대 4개")
    with _btn_del:
        if len(st.session_state['col_load_list']) > 1:
            if st.button("➖ 마지막 삭제", key="col_del_btn"):
                st.session_state['col_load_list'].pop()
                st.rerun()

    # ── 기둥별 입력 (탭 or 단일 컨테이너) ──────────────────────────
    _cl = st.session_state['col_load_list']
    if len(_cl) == 1:
        _col_input_ctxs = [st.container()]
    else:
        _col_input_ctxs = st.tabs([c['기둥명'] for c in _cl])

    column_loads = []
    for _ci, (_ctx, _cd) in enumerate(zip(_col_input_ctxs, _cl)):
        with _ctx:
            _inp_n, _inp_pu, _inp_mux, _inp_muy = st.columns([2, 1, 1, 1])
            with _inp_n:
                st.caption("기둥명")
                _col_name = st.text_input(
                    "기둥명", value=_cd['기둥명'], key=f"col_name_{_ci}",
                    label_visibility="collapsed",
                    placeholder="기둥명 입력"
                )
            with _inp_pu:
                _pu_val = st.number_input(
                    "Pu_add [kN]", min_value=0.0, max_value=50000.0,
                    value=float(_cd['Pu_add']), step=10.0, format="%.1f",
                    key=f"col_pu_{_ci}"
                )
            with _inp_mux:
                _mux_val = st.number_input(
                    "Mux_add [kN·m]", min_value=0.0, max_value=5000.0,
                    value=float(_cd['Mux_add']), step=5.0, format="%.1f",
                    key=f"col_mux_{_ci}"
                )
            with _inp_muy:
                _muy_val = st.number_input(
                    "Muy_add [kN·m]", min_value=0.0, max_value=5000.0,
                    value=float(_cd['Muy_add']), step=5.0, format="%.1f",
                    key=f"col_muy_{_ci}"
                )
        # 세션 상태 갱신
        st.session_state['col_load_list'][_ci] = {
            '기둥명': _col_name, 'Pu_add': _pu_val, 'Mux_add': _mux_val, 'Muy_add': _muy_val
        }
        column_loads.append({
            '기둥명': _col_name, 'Pu_add': _pu_val, 'Mux_add': _mux_val, 'Muy_add': _muy_val
        })

    if not column_loads:
        column_loads = [{'기둥명': '기둥 1', 'Pu_add': 0.0, 'Mux_add': 100.0, 'Muy_add': 0.0}]

    st.subheader("3. 재료 조건")
    c1, c2 = st.columns(2)
    with c1:
        fc_k = st.number_input("콘크리트 압축강도 (f_ck) [MPa]", min_value=18.0, max_value=60.0,
                               value=st.session_state.get('pdf_fc_k', 24.0), step=1.0)
    with c2:
        fy = st.number_input("철근 항복강도 (f_y) [MPa]", min_value=240.0, max_value=600.0,
                             value=st.session_state.get('pdf_fy', 400.0), step=10.0)

    st.subheader("3-1. 내진 설계")
    _seis_c1, _seis_c2 = st.columns([1, 3])
    with _seis_c1:
        seismic_enabled = st.checkbox("지진하중 적용", value=False, key="seismic_enabled")
    with _seis_c2:
        if seismic_enabled:
            frame_type = st.radio("골조 유형", ['OMF', 'IMF'], horizontal=True, key="frame_type")
        else:
            frame_type = 'OMF'
    if seismic_enabled:
        st.caption("💡 기둥별 지진하중(E)을 입력하면 1.2D+1.0E+1.0L / 0.9D+1.0E 조합이 자동 추가됩니다.")
        _se_tabs = st.tabs([c['기둥명'] for c in column_loads]) if len(column_loads) > 1 else [st.container()]
        for _si, (_stab, _cd) in enumerate(zip(_se_tabs, column_loads)):
            with _stab:
                _se1, _se2, _se3 = st.columns(3)
                with _se1:
                    _cd['E_Pu'] = st.number_input(
                        "E_Pu [kN]", min_value=0.0, max_value=50000.0,
                        value=float(_cd.get('E_Pu', 0.0)), step=10.0,
                        format="%.1f", key=f"col_epu_{_si}")
                with _se2:
                    _cd['E_Mux'] = st.number_input(
                        "E_Mux [kN·m]", min_value=0.0, max_value=5000.0,
                        value=float(_cd.get('E_Mux', 0.0)), step=5.0,
                        format="%.1f", key=f"col_emux_{_si}")
                with _se3:
                    _cd['E_Muy'] = st.number_input(
                        "E_Muy [kN·m]", min_value=0.0, max_value=5000.0,
                        value=float(_cd.get('E_Muy', 0.0)), step=5.0,
                        format="%.1f", key=f"col_emuy_{_si}")

    st.subheader("4. 늑근 구간 분할")
    _nz_c1, _nz_c2 = st.columns([1, 2])
    with _nz_c1:
        n_zones = st.radio(
            "늑근 구간 수",
            options=[2, 3, 4],
            index=1,          # 기본값 3구간
            horizontal=True,
            key="n_zones_radio"
        )
    with _nz_c2:
        _zone_desc = {
            2: "경간을 **2등분** — 지점부(L/2) · 중앙부(L/2)",
            3: "경간을 **3등분** — 지점부(L/3) · 중앙부(L/3) · 지점부(L/3)  ← 권장",
            4: "경간을 **4등분** — 지점부(L/4) · 내부(L/4) · 내부(L/4) · 지점부(L/4)",
        }
        st.info(_zone_desc[n_zones])

    st.divider()

    return {
        'L_x': L_x,
        'L_y': L_y,
        'h_column': h_column,
        'DL_area': DL_area,
        'LL_area': LL_area,
        'show_ground_beam': show_ground_beam,
        'DL_area_ground': DL_area_ground,
        'LL_area_ground': LL_area_ground,
        'column_loads': column_loads,
        'fc_k': fc_k,
        'fy': fy,
        'n_zones': n_zones,
        'seismic_enabled': seismic_enabled,
        'frame_type': frame_type,
        # 부재 사이즈: output.py의 "1. 자동결정된 단면" override 입력 사용
        'h_beam_x': _pick_size('override_h_beam_x'),
        'b_beam_x': _pick_size('override_b_beam_x'),
        'h_beam_y': _pick_size('override_h_beam_y'),
        'b_beam_y': _pick_size('override_b_beam_y'),
        'c_column_size': _pick_size('override_c_column'),
        't_slab_size': _pick_size('override_t_slab'),
    }


# ═══════════════════════════════════════════════════════════════════════
# 검토 모드 입력 섹션
# ═══════════════════════════════════════════════════════════════════════

def render_review_input_section():
    # 배근 문자열에서 철근 직경(mm) 추출
    _REBAR_DIA = {'D10':9.53,'D13':12.7,'D16':15.9,'D19':19.1,'D22':22.2,'D25':25.4,'D29':28.6,'D32':31.8}

    def _parse_bar_dia(rebar_str):
        """'3-D19' → 19.1, '2-D10@125' → 9.53"""
        if not rebar_str:
            return 0.0
        import re as _re
        m = _re.search(r'D(\d+)', str(rebar_str))
        if m:
            return _REBAR_DIA.get(f"D{m.group(1)}", 0.0)
        return 0.0

    def _estimate_cover(member):
        """AI 결과에서 cover 역산. Loc가 있으면 역산, 없으면 기본값."""
        sec = member.get('section', {}) or {}
        rebar = member.get('rebar', {}) or {}

        # Loc 값 확인 (AI 스키마에서 명시적으로 추출된 경우만)
        loc_top = sec.get('Loc_top_mm')
        loc_bot = sec.get('Loc_bot_mm')

        # Loc가 숫자이고 합리적 범위(20~100mm)인 경우만 사용
        loc = None
        for _l in [loc_top, loc_bot]:
            if isinstance(_l, (int, float)) and 20 <= _l <= 100:
                loc = _l
                break

        # clear_cover_mm 직접 제공된 경우 (BeST.Steel 기둥 등)
        clear_cover = sec.get('clear_cover_mm')
        if isinstance(clear_cover, (int, float)) and 10 <= clear_cover <= 80:
            return round(clear_cover, 1)

        if loc:
            stirrup_str = rebar.get('stirrup', '')
            main_top_str = rebar.get('top', '')
            main_bot_str = rebar.get('bottom', '')

            stirrup_dia = _parse_bar_dia(stirrup_str) if stirrup_str else 9.53
            main_dia = _parse_bar_dia(main_top_str) or _parse_bar_dia(main_bot_str) or 19.1

            cover = loc - stirrup_dia - main_dia / 2.0
            # cover가 합리적 범위(10~80mm)인 경우만 사용
            if 10 <= cover <= 80:
                return round(cover, 1)

        # Loc 없거나 역산 결과가 비합리적이면 0 (사용자가 입력해야 함)
        return 0

    """
    구조계산서 검토 모드 입력 UI.

    Returns:
        dict (review_inputs) 또는 None (아직 분석 미완료)
    """
    from ui.pdf_import import _pdf_import_section

    # PDF 업로드 + 분석
    _pdf_import_section()

    # ── 추출 결과에서 부재 목록 추출 ──
    _ai_result = st.session_state.get('ai_analysis_result')
    _all_beams = []
    _all_cols = []
    if _ai_result and not _ai_result.get('error'):
        members = _ai_result.get('members', [])
        for m in members:
            if m.get('type') == 'beam':
                _all_beams.append(m)
            elif m.get('type') == 'column':
                _all_cols.append(m)

    # 디버그: 추출 결과 전체 확인
    if _all_beams or _all_cols:
        with st.expander("🔍 추출 원본 데이터 (디버그)", expanded=False):
            for idx, m in enumerate(_all_beams + _all_cols):
                st.markdown(f"---\n**#{idx} {m.get('name')}** | type: `{m.get('type')}` | sw: `{m.get('software')}`")
                st.caption("section:")
                st.json(m.get('section', {}))
                st.caption("design_forces:")
                df = m.get('design_forces', {})
                if df:
                    # null이 아닌 값만 하이라이트
                    non_null = {k: v for k, v in df.items() if v is not None}
                    null_keys = [k for k, v in df.items() if v is None]
                    st.json(non_null)
                    if null_keys:
                        st.warning(f"null인 키: {', '.join(null_keys)}")
                else:
                    st.error("design_forces 자체가 없음!")

    st.markdown("---")
    st.subheader("검토 부재 설정 + 3D 배근도 매핑")

    # 빈 값 강조 CSS
    st.markdown("""
    <style>
    .rv-missing input[type="number"] { background-color: #fff0f0 !important; }
    </style>
    """, unsafe_allow_html=True)

    # ── 부재 이름 목록 생성 ──
    def _unique_name(m, i, prefix):
        name = m.get('name', f'{prefix}_{i}')
        sw = m.get('software', '')
        return f"{name} [{sw}]" if sw else name

    beam_names = [_unique_name(b, i, 'beam') for i, b in enumerate(_all_beams)] if _all_beams else []
    col_names = [_unique_name(c, i, 'col') for i, c in enumerate(_all_cols)] if _all_cols else []

    # ── 3D 매핑 = 부재 선택 (통합) ──
    st.caption("3D 골조 배근도에 배치할 부재를 선택하세요. 선택된 부재만 검토됩니다.")
    beam_opts = ["(없음)"] + beam_names
    col_opts = ["(없음)"] + col_names

    _m1, _m2, _m3 = st.columns(3)
    with _m1:
        st.markdown("**천장보**")
        map_ceil_x = st.selectbox("천장보 X방향", beam_opts,
                                  index=min(1, len(beam_opts)-1), key="rv_map_ceil_x")
        map_ceil_y = st.selectbox("천장보 Y방향", beam_opts,
                                  index=min(2, len(beam_opts)-1) if len(beam_opts) > 2 else min(1, len(beam_opts)-1),
                                  key="rv_map_ceil_y")
    with _m2:
        st.markdown("**바닥보**")
        map_floor_x = st.selectbox("바닥보 X방향", beam_opts, index=0, key="rv_map_floor_x")
        map_floor_y = st.selectbox("바닥보 Y방향", beam_opts, index=0, key="rv_map_floor_y")
    with _m3:
        st.markdown("**기둥**")
        map_col = st.selectbox("기둥 (4개 동일)", col_opts,
                               index=min(1, len(col_opts)-1), key="rv_map_col")

    # 선택된 부재 목록 생성 (중복 제거)
    _selected_beam_names = set()
    for nm in [map_ceil_x, map_ceil_y, map_floor_x, map_floor_y]:
        if nm != "(없음)":
            _selected_beam_names.add(nm)
    _selected_col_names = set()
    if map_col != "(없음)":
        _selected_col_names.add(map_col)

    _selected_ai_beams = [_all_beams[i] for i, nm in enumerate(beam_names) if nm in _selected_beam_names]
    _selected_ai_cols = [_all_cols[i] for i, nm in enumerate(col_names) if nm in _selected_col_names]

    # ── 선택 변경 감지: 값 강제 초기화 ──
    _sel_key = str(sorted(_selected_beam_names)) + str(sorted(_selected_col_names))
    _prev_key = st.session_state.get('_rv_prev_sel', '')
    _sel_changed = (_prev_key != _sel_key)
    if _sel_changed:
        st.session_state['_rv_prev_sel'] = _sel_key

    # ── 보 입력 ──
    st.markdown("#### 🔵 보 부재력")
    if not _selected_ai_beams and not (_all_beams or _all_cols):
        n_beams = st.number_input("보 개수", min_value=0, max_value=10, value=1, key="rv_n_beams")
        _beam_sources = [{}] * int(n_beams)
    else:
        n_beams = len(_selected_ai_beams)
        _beam_sources = _selected_ai_beams

    beams = []
    for i in range(int(n_beams)):
        _ab = _beam_sources[i] if i < len(_beam_sources) else {}
        _ab_sec = _ab.get('section', {}) or {}
        _ab_mat = _ab.get('material', {}) or {}
        _ab_df = _ab.get('design_forces', {}) or {}
        _def_name = _ab.get('name', f"B{i+1}")
        _def_h = int(_ab_sec.get('H_mm') or 0)
        _def_b = int(_ab_sec.get('B_mm') or 0)
        # T형보: H_mm가 H_bot만 들어올 수 있음 → H_top + H_bot = 전체 높이
        _t_htop = int(_ab_sec.get('H_top_mm') or 0)
        if _t_htop > 0 and _def_h > 0 and _def_h < _t_htop + _def_h:
            _def_h = _def_h + _t_htop  # 전체 높이 = H_bot + H_top
        _def_fck = float(_ab_mat.get('fck_MPa') or 0)
        _def_fy = float(_ab_mat.get('fy_MPa') or 0)
        _def_cover = _estimate_cover(_ab)

        # 선택 변경 시 session_state에 AI 값 강제 써넣기
        if _sel_changed or f"rv_bh_{i}" not in st.session_state:
            st.session_state[f"rv_bname_{i}"] = _def_name
            st.session_state[f"rv_bh_{i}"] = str(_def_h)
            st.session_state[f"rv_bb_{i}"] = str(_def_b)
            st.session_state[f"rv_bfck_{i}"] = str(_def_fck)
            st.session_state[f"rv_bfy_{i}"] = str(_def_fy)
            st.session_state[f"rv_bcover_{i}"] = str(_def_cover)
            # 원본값 저장
            st.session_state[f"rv_bh_{i}_orig"] = float(_def_h)
            st.session_state[f"rv_bb_{i}_orig"] = float(_def_b)
            st.session_state[f"rv_bfck_{i}_orig"] = float(_def_fck)
            st.session_state[f"rv_bfy_{i}_orig"] = float(_def_fy)
            st.session_state[f"rv_bcover_{i}_orig"] = float(_def_cover)
            for loc_name in ["END_I", "MID", "END_J"]:
                _loc_map = {
                    'END_I': {'mn': 'Mu_neg_I_kNm', 'mp': 'Mu_pos_I_kNm', 'vu': 'Vu_I_kN'},
                    'MID':   {'mn': 'Mu_neg_MID_kNm', 'mp': 'Mu_pos_MID_kNm', 'vu': 'Vu_MID_kN'},
                    'END_J': {'mn': 'Mu_neg_J_kNm', 'mp': 'Mu_pos_J_kNm', 'vu': 'Vu_J_kN'},
                }
                _lm = _loc_map[loc_name]
                _v_mn = abs(float(_ab_df.get(_lm['mn']) or 0))
                _v_mp = abs(float(_ab_df.get(_lm['mp']) or 0))
                _v_vu = abs(float(_ab_df.get(_lm['vu']) or 0))
                # 현재값 + 원본값 동시 저장
                st.session_state[f"rv_mn_{i}_{loc_name}"] = str(_v_mn)
                st.session_state[f"rv_mp_{i}_{loc_name}"] = str(_v_mp)
                st.session_state[f"rv_vu_{i}_{loc_name}"] = str(_v_vu)
                st.session_state[f"rv_mn_{i}_{loc_name}_orig"] = _v_mn
                st.session_state[f"rv_mp_{i}_{loc_name}_orig"] = _v_mp
                st.session_state[f"rv_vu_{i}_{loc_name}_orig"] = _v_vu

        _is_best = 'BeST' in _ab.get('software', '')

        with st.expander(f"보 {i+1}: {_def_name}", expanded=(i == 0)):
            bc1, bc2, bc3 = st.columns([2, 1, 1])
            with bc1:
                bname = st.text_input("부재명", key=f"rv_bname_{i}")
            with bc2:
                bh = _colored_input("h (mm)", f"rv_bh_{i}")
            with bc3:
                bb = _colored_input("b (mm)", f"rv_bb_{i}")

            # T형보 필드 (BeST에서 값 있을 때만)
            _def_btop = int(_ab_sec.get('B_top_mm') or 0)
            _def_htop = int(_ab_sec.get('H_top_mm') or 0)
            if _sel_changed or f"rv_btop_{i}" not in st.session_state:
                st.session_state[f"rv_btop_{i}"] = str(_def_btop)
                st.session_state[f"rv_htop_{i}"] = str(_def_htop)
                st.session_state[f"rv_btop_{i}_orig"] = float(_def_btop)
                st.session_state[f"rv_htop_{i}_orig"] = float(_def_htop)
            if _def_btop > 0 or _def_htop > 0:
                _tc1, _tc2 = st.columns(2)
                with _tc1:
                    b_top = _colored_input("B_top (mm) T형보", f"rv_btop_{i}")
                with _tc2:
                    h_top = _colored_input("H_top (mm) T형보", f"rv_htop_{i}")
            else:
                b_top = 0.0
                h_top = 0.0

            bc4, bc5 = st.columns(2)
            with bc4:
                b_fck = _colored_input("fck (MPa)", f"rv_bfck_{i}")
            with bc5:
                b_fy = _colored_input("fy (MPa)", f"rv_bfy_{i}")

            if _is_best:
                # ── BeST: 단일 부재력 입력 ──
                st.caption("**부재력**")
                _def_mu = abs(float(_ab_df.get('Mu_neg_I_kNm') or 0))
                _def_vu_s = abs(float(_ab_df.get('Vu_I_kN') or 0))
                if _sel_changed or f"rv_bmu_{i}" not in st.session_state:
                    st.session_state[f"rv_bmu_{i}"] = str(_def_mu)
                    st.session_state[f"rv_bvu_{i}"] = str(_def_vu_s)
                    st.session_state[f"rv_bmu_{i}_orig"] = _def_mu
                    st.session_state[f"rv_bvu_{i}_orig"] = _def_vu_s
                _fc1, _fc2 = st.columns(2)
                with _fc1:
                    b_mu = _colored_input("Mu (kN·m)", f"rv_bmu_{i}")
                with _fc2:
                    b_vu = _colored_input("Vu (kN)", f"rv_bvu_{i}")
                # BeST는 단일값 → END_I에만 넣고 MID/END_J는 0
                locations = {
                    'END_I': {'Mu_neg': b_mu, 'Mu_pos': 0.0, 'Vu': b_vu},
                    'MID':   {'Mu_neg': 0.0, 'Mu_pos': 0.0, 'Vu': 0.0},
                    'END_J': {'Mu_neg': 0.0, 'Mu_pos': 0.0, 'Vu': 0.0},
                }
            else:
                # ── MIDAS: 위치별 부재력 입력 (END-I / MID / END-J) ──
                st.caption("**부재력 (END-I / MID / END-J)**")
                _hdr1, _hdr2, _hdr3, _hdr4 = st.columns([1.5, 1, 1, 1])
                _hdr1.markdown("")
                _hdr2.markdown("**END-I**")
                _hdr3.markdown("**MID**")
                _hdr4.markdown("**END-J**")

                _r1, _c1i, _c1m, _c1j = st.columns([1.5, 1, 1, 1])
                _r1.markdown("(-) Mu kN·m")
                with _c1i: mn_i = _colored_input("Mu(-) I", f"rv_mn_{i}_END_I")
                with _c1m: mn_m = _colored_input("Mu(-) M", f"rv_mn_{i}_MID")
                with _c1j: mn_j = _colored_input("Mu(-) J", f"rv_mn_{i}_END_J")

                _r2, _c2i, _c2m, _c2j = st.columns([1.5, 1, 1, 1])
                _r2.markdown("(+) Mu kN·m")
                with _c2i: mp_i = _colored_input("Mu(+) I", f"rv_mp_{i}_END_I")
                with _c2m: mp_m = _colored_input("Mu(+) M", f"rv_mp_{i}_MID")
                with _c2j: mp_j = _colored_input("Mu(+) J", f"rv_mp_{i}_END_J")

                _r3, _c3i, _c3m, _c3j = st.columns([1.5, 1, 1, 1])
                _r3.markdown("Vu kN")
                with _c3i: vu_i = _colored_input("Vu I", f"rv_vu_{i}_END_I")
                with _c3m: vu_m = _colored_input("Vu M", f"rv_vu_{i}_MID")
                with _c3j: vu_j = _colored_input("Vu J", f"rv_vu_{i}_END_J")

                locations = {
                    'END_I': {'Mu_neg': mn_i, 'Mu_pos': mp_i, 'Vu': vu_i},
                    'MID':   {'Mu_neg': mn_m, 'Mu_pos': mp_m, 'Vu': vu_m},
                    'END_J': {'Mu_neg': mn_j, 'Mu_pos': mp_j, 'Vu': vu_j},
                }

            # 구조계산서 배근 + Loc
            st.caption("**구조계산서 배근 / Loc**")
            _rb_ai = _ab.get('rebar', {}) or {}
            _def_rtop = _rb_ai.get('top') or ""
            _def_rbot = _rb_ai.get('bottom') or ""
            _def_rstir = _rb_ai.get('stirrup') or ""
            _def_rskin = _rb_ai.get('skin') or ""
            _def_loc_t = _ab.get('section', {}).get('Loc_top_mm') or 0
            _def_loc_b = _ab.get('section', {}).get('Loc_bot_mm') or 0
            if _sel_changed or f"rv_rtop_{i}" not in st.session_state:
                st.session_state[f"rv_rtop_{i}"] = str(_def_rtop)
                st.session_state[f"rv_rbot_{i}"] = str(_def_rbot)
                st.session_state[f"rv_rstir_{i}"] = str(_def_rstir)
                st.session_state[f"rv_rskin_{i}"] = str(_def_rskin)
                st.session_state[f"rv_loct_{i}"] = str(float(_def_loc_t))
                st.session_state[f"rv_locb_{i}"] = str(float(_def_loc_b))
                st.session_state[f"rv_loct_{i}_orig"] = float(_def_loc_t)
                st.session_state[f"rv_locb_{i}_orig"] = float(_def_loc_b)

            _rb1, _rb2, _rb3, _rb4 = st.columns(4)
            with _rb1:
                rtop = st.text_input("TOP 배근", key=f"rv_rtop_{i}")
            with _rb2:
                rbot = st.text_input("BOT 배근", key=f"rv_rbot_{i}")
            with _rb3:
                rstir = st.text_input("STIRRUPS", key=f"rv_rstir_{i}")
            with _rb4:
                b_cover = _colored_input("cover (mm)", f"rv_bcover_{i}")
            _lc1, _lc2, _lc3 = st.columns(3)
            with _lc1:
                loc_t = _colored_input("Loc_top (mm)", f"rv_loct_{i}")
            with _lc2:
                loc_b = _colored_input("Loc_bot (mm)", f"rv_locb_{i}")
            with _lc3:
                rskin = st.text_input("Skin 배근", key=f"rv_rskin_{i}")

            beams.append({
                'name': bname, 'h_beam': bh, 'b_beam': bb,
                'fc_k': b_fck, 'fy': b_fy, 'cover': b_cover,
                'Loc_top': loc_t, 'Loc_bot': loc_b,
                'rebar_top': rtop, 'rebar_bot': rbot, 'stirrup': rstir,
                'skin_rebar': rskin,
                'b_top': b_top, 'h_top': h_top,
                'locations': locations,
                # 메타데이터 (출력 형식용)
                'software': _ab.get('software', ''),
                'span_m': float(_ab.get('geometry', {}).get('span_m') or 0),
                'fys': float(_ab.get('material', {}).get('fys_MPa') or 0),
                'load_combinations': _ab.get('load_combinations', {}),
            })

    # ── 기둥 입력 ──
    st.markdown("#### 🟠 기둥 부재력")
    if not _selected_ai_cols and not (_all_beams or _all_cols):
        n_cols = st.number_input("기둥 개수", min_value=0, max_value=10, value=1, key="rv_n_cols")
        _col_sources = [{}] * int(n_cols)
    else:
        n_cols = len(_selected_ai_cols)
        _col_sources = _selected_ai_cols

    columns = []
    for i in range(int(n_cols)):
        _ac = _col_sources[i] if i < len(_col_sources) else {}
        _ac_sec = _ac.get('section', {}) or {}
        _ac_mat = _ac.get('material', {}) or {}
        _ac_geo = _ac.get('geometry', {}) or {}
        _ac_df = _ac.get('design_forces', {}) or {}
        _def_cname = _ac.get('name', f"C{i+1}")
        _def_bx = int(_ac_sec.get('Cx_mm') or _ac_sec.get('B_mm') or 0)
        _def_by = int(_ac_sec.get('Cy_mm') or _ac_sec.get('H_mm') or _def_bx)
        _def_hcol = int(float(_ac_geo.get('height_m') or 0) * 1000)
        _def_pu = abs(float(_ac_df.get('Pu_kN') or 0))
        _def_mux = abs(float(_ac_df.get('Mux_kNm') or 0))
        _def_muy = abs(float(_ac_df.get('Muy_kNm') or 0))
        _def_cfck = float(_ac_mat.get('fck_MPa') or 0)
        _def_cfy = float(_ac_mat.get('fy_MPa') or 0)
        _def_ccover = _estimate_cover(_ac)

        # 배근 기본값 (AI/PDF 분석 결과)
        _ac_rebar = _ac.get('rebar', {}) or {}
        _def_rebar_vert = _ac_rebar.get('top') or ""
        _def_hoop = _ac_rebar.get('stirrup') or ""

        # 선택 변경 시 session_state에 AI 값 강제 써넣기
        if _sel_changed or f"rv_cbx_{i}" not in st.session_state:
            st.session_state[f"rv_cname_{i}"] = _def_cname
            st.session_state[f"rv_cbx_{i}"] = str(_def_bx)
            st.session_state[f"rv_cby_{i}"] = str(_def_by)
            st.session_state[f"rv_hcol_{i}"] = str(_def_hcol)
            st.session_state[f"rv_cfck_{i}"] = str(_def_cfck)
            st.session_state[f"rv_cfy_{i}"] = str(_def_cfy)
            st.session_state[f"rv_ccover_{i}"] = str(_def_ccover)
            st.session_state[f"rv_crebar_{i}"] = str(_def_rebar_vert)
            st.session_state[f"rv_choop_{i}"] = str(_def_hoop)
            # 원본값 저장
            st.session_state[f"rv_cbx_{i}_orig"] = float(_def_bx)
            st.session_state[f"rv_cby_{i}_orig"] = float(_def_by)
            st.session_state[f"rv_hcol_{i}_orig"] = float(_def_hcol)
            st.session_state[f"rv_cfck_{i}_orig"] = float(_def_cfck)
            st.session_state[f"rv_cfy_{i}_orig"] = float(_def_cfy)
            st.session_state[f"rv_ccover_{i}_orig"] = float(_def_ccover)

        with st.expander(f"기둥 {i+1}: {_def_cname}", expanded=(i == 0)):
            cc1, cc2, cc3 = st.columns([2, 1, 1])
            with cc1:
                cname = st.text_input("부재명", key=f"rv_cname_{i}")
            with cc2:
                cbx = _colored_input("bx (mm)", f"rv_cbx_{i}")
            with cc3:
                cby = _colored_input("by (mm)", f"rv_cby_{i}")
            cc4, cc5, cc6 = st.columns(3)
            with cc4:
                hcol = _colored_input("H_col (mm)", f"rv_hcol_{i}")
            with cc5:
                c_fck = _colored_input("fck (MPa)", f"rv_cfck_{i}")
            with cc6:
                c_fy = _colored_input("fy (MPa)", f"rv_cfy_{i}")

            # 선택 변경 시 부재력도 강제 써넣기 + 원본값 저장
            if _sel_changed or f"rv_cpu_{i}" not in st.session_state:
                st.session_state[f"rv_cpu_{i}"] = str(_def_pu)
                st.session_state[f"rv_cmux_{i}"] = str(_def_mux)
                st.session_state[f"rv_cmuy_{i}"] = str(_def_muy)
                st.session_state[f"rv_cpu_{i}_orig"] = _def_pu
                st.session_state[f"rv_cmux_{i}_orig"] = _def_mux
                st.session_state[f"rv_cmuy_{i}_orig"] = _def_muy

            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                pu = _colored_input("Pu (kN)", f"rv_cpu_{i}")
            with fc2:
                mux = _colored_input("Mux (kN·m)", f"rv_cmux_{i}")
            with fc3:
                muy = _colored_input("Muy (kN·m)", f"rv_cmuy_{i}")

            # 구조계산서 배근 (검토용)
            st.caption("**구조계산서 배근 (검토용)**")
            _cr1, _cr2, _cr3 = st.columns(3)
            with _cr1:
                c_rebar = st.text_input("주근 (예: 8-D25)", key=f"rv_crebar_{i}")
            with _cr2:
                c_hoop = st.text_input("띠철근 (예: D10@200)", key=f"rv_choop_{i}")
            with _cr3:
                c_cover = _colored_input("cover (mm)", f"rv_ccover_{i}")

            columns.append({
                'name': cname, 'bx': cbx, 'by': cby,
                'c_column': max(cbx, cby),
                'h_column': hcol,
                'fc_k': c_fck, 'fy': c_fy, 'cover': c_cover,
                'Pu': pu, 'Mux': mux, 'Muy': muy,
                'rebar_vert': c_rebar, 'hoop': c_hoop,
            })

    # ── frame_mapping 생성 ──
    # beam_names/col_names는 _all_beams/_all_cols 기반 (전체)
    # beams/columns는 _selected_ai_beams/_selected_ai_cols 기반 (선택된 것만)
    # selectbox 값 → beams/columns에서 찾기
    def _find_beam(sel_name):
        if not sel_name or sel_name == "(없음)":
            return None
        for b in beams:
            if b['name'] == sel_name:
                return b
        # text_input에서 이름이 바뀌었을 수 있으므로 인덱스 기반
        for i, b in enumerate(beams):
            # beams[i]는 _selected_ai_beams[i]에서 온 것
            if i < len(_selected_ai_beams):
                orig_name = _unique_name(_selected_ai_beams[i], 0, 'beam')
                if orig_name == sel_name:
                    return b
        return None

    def _find_col(sel_name):
        if not sel_name or sel_name == "(없음)":
            return None
        for c in columns:
            if c['name'] == sel_name:
                return c
        for i, c in enumerate(columns):
            if i < len(_selected_ai_cols):
                orig_name = _unique_name(_selected_ai_cols[i], 0, 'col')
                if orig_name == sel_name:
                    return c
        return None

    frame_mapping = {
        'ceil_x': _find_beam(map_ceil_x),
        'ceil_y': _find_beam(map_ceil_y),
        'floor_x': _find_beam(map_floor_x) or _find_beam(map_ceil_x),  # 없으면 천장보 폴백
        'floor_y': _find_beam(map_floor_y) or _find_beam(map_ceil_y),  # 없으면 천장보 폴백
        'column': _find_col(map_col),
    }

    # 검토 실행 버튼 — 기둥 배근 미입력 시 비활성화
    _col_rebar_missing = any(
        not c.get('rebar_vert', '').strip() for c in columns
    ) if columns else False
    if _col_rebar_missing:
        st.warning("기둥 주근을 입력해야 검토를 실행할 수 있습니다.")
    if st.button("▶ 검토 실행", type="primary", key="rv_run_btn",
                  disabled=_col_rebar_missing):
        review_inputs = {
            'beams': beams, 'columns': columns,
            'frame_mapping': frame_mapping,
        }
        st.session_state['rv_last_inputs'] = review_inputs
        return review_inputs

    # 버튼 안 눌렸어도 이전 입력값이 있으면 그대로 반환 (결과 유지)
    if 'rv_last_inputs' in st.session_state:
        return st.session_state['rv_last_inputs']

    return None
