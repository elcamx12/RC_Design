import streamlit as st
from .pdf_import import _pdf_import_section


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
    st.header("📝 입력 조건")

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
    _btn_add, _btn_del, _spacer = st.columns([1, 1, 6])
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
