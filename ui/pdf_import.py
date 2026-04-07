import streamlit as st
import os
import tempfile
import pandas as pd


def _rebuild_ai_analysis_result():
    """코드 기반 + AI 기반 누적 결과를 통합하여 ai_analysis_result에 저장.
    코드 기반 결과는 _render_auto_analysis에서 직접 구축하므로,
    여기서는 AI 기반 결과만 모아서 저장한다.
    (코드 기반에서 호출 시 최종적으로 덮어쓰므로 순서 무관)
    """
    all_members = []
    for _h in st.session_state.get('ai_parse_results', []):
        _members = _h.get('result', {}).get('members', [])
        all_members.extend(_members)
    # 기존 코드 기반 결과가 있으면 그것도 포함
    # → 실제로는 코드 기반 _render_auto_analysis가 마지막에 덮어쓰므로
    #   여기서는 AI 결과만 넣어도 됨. 코드 기반이 나중에 최종 합산.
    st.session_state['ai_analysis_result'] = {"members": all_members}

def _pdf_import_section():
    """구조계산서 업로드 — AI 기반 추출 + 코드 기반 추출 통합 UI"""
    with st.expander("📂 구조계산서 업로드", expanded=False):
        # ── 누적 결과 초기화 ─────────────────────────────────────────────
        if 'pdf_upload_count' not in st.session_state:
            st.session_state['pdf_upload_count'] = 0
        if 'auto_parse_results' not in st.session_state:
            st.session_state['auto_parse_results'] = []   # [{idx, filename, result}]
        if 'ai_parse_results' not in st.session_state:
            st.session_state['ai_parse_results'] = []     # [{idx, filename, result}]

        # ── 공용 PDF 업로더 ──────────────────────────────────────────────
        # 분석 완료 시 _uploader_ver 증가 → key 변경 → 업로더 자동 리셋 (중복 분석 방지)
        if 'pdf_uploader_ver' not in st.session_state:
            st.session_state['pdf_uploader_ver'] = 0
        uploaded = st.file_uploader(
            "MIDAS Gen / BeST.RC 구조계산서 PDF",
            type="pdf",
            help="MIDAS Gen RC Beam/Column Checking Result 또는 BeST.RC/BeST.Steel 형식을 지원합니다.",
            key=f"pdf_uploader_{st.session_state['pdf_uploader_ver']}"
        )

        # ── 누적 현황 + 초기화 버튼 ─────────────────────────────────────
        _total_parsed = len(st.session_state['auto_parse_results']) + len(st.session_state['ai_parse_results'])
        if _total_parsed > 0:
            _hist_col1, _hist_col2 = st.columns([4, 1])
            with _hist_col1:
                _labels = []
                for _h in st.session_state['auto_parse_results']:
                    _labels.append(f"#{_h['idx']} {_h['filename']} (코드)")
                for _h in st.session_state['ai_parse_results']:
                    _labels.append(f"#{_h['idx']} {_h['filename']} (AI)")
                st.caption("📋 분석 이력: " + " / ".join(_labels))
            with _hist_col2:
                if st.button("🗑️ 전체 초기화", key="pdf_reset_all"):
                    st.session_state['pdf_upload_count'] = 0
                    st.session_state['auto_parse_results'] = []
                    st.session_state['ai_parse_results'] = []
                    st.session_state.pop('auto_parse_result', None)
                    st.session_state.pop('ai_analysis_result', None)
                    st.session_state['pdf_uploader_ver'] = st.session_state.get('pdf_uploader_ver', 0) + 1
                    st.rerun()

        _has_results = (len(st.session_state['auto_parse_results']) > 0
                        or len(st.session_state['ai_parse_results']) > 0)

        if not uploaded and not _has_results:
            st.info("PDF 파일을 업로드하면 AI 기반 추출 또는 코드 기반 추출로 설계 데이터를 가져옵니다.")
            return

        # ── 분석 방식 선택 탭 ────────────────────────────────────────────
        tab_auto, tab_ai = st.tabs(["⚙️ 코드 기반 추출", "🤖 AI 기반 추출"])

        # ═══════════════════════════════════════════════════════════════
        # 코드 기반 추출 탭
        # ═══════════════════════════════════════════════════════════════
        with tab_auto:
            _render_auto_analysis(uploaded)

        # ═══════════════════════════════════════════════════════════════
        # AI 기반 추출 탭
        # ═══════════════════════════════════════════════════════════════
        with tab_ai:
            _render_ai_analysis(uploaded)


def _render_ai_analysis(uploaded):
    """AI(Claude Haiku) 기반 PDF 분석"""
    try:
        from parsers.ui_pdf_viewer import (
            _get_builtin_key, _get_login_password,
            _render_beam_table, _render_column_table, _render_other_table,
            _sv
        )
        from parsers.ai_pdf_parser import parse_pdf_with_ai
    except ImportError as e:
        st.error(f"AI 추출 모듈 로드 오류: {e}")
        return

    # ── API 키 관리 (새 파일 업로드 시에만 표시) ─────────────────────
    api_key = None
    if uploaded:
        builtin_key = _get_builtin_key()
        login_pw = _get_login_password()

        if builtin_key and login_pw:
            logged_in = st.session_state.get('ai_logged_in', False)
            if logged_in:
                st.success("✅ 로그인됨")
                if st.button("로그아웃", key="ai_logout_btn"):
                    st.session_state['ai_logged_in'] = False
                    st.rerun()
                api_key = builtin_key
            else:
                tab_login, tab_manual = st.tabs(["🔐 로그인", "🔑 직접 입력"])
                with tab_login:
                    pw = st.text_input("비밀번호", type="password", key="ai_login_pw")
                    if st.button("로그인", key="ai_login_btn"):
                        if pw == login_pw:
                            st.session_state['ai_logged_in'] = True
                            st.rerun()
                        else:
                            st.error("비밀번호가 올바르지 않습니다.")
                with tab_manual:
                    manual_key = st.text_input("Anthropic API Key", type="password",
                                              key="ai_manual_api_key",
                                              placeholder="sk-ant-api03-...")
                    if manual_key:
                        api_key = manual_key
        else:
            # secrets에 키가 없으면 직접 입력만
            manual_key = st.text_input("Anthropic API Key", type="password",
                                      key="ai_manual_api_key_only",
                                      placeholder="sk-ant-api03-...")
            if manual_key:
                api_key = manual_key

    # ── 분석 실행 (파일 + API 키 모두 있을 때만) ─────────────────────
    if uploaded and api_key and st.button("🤖 AI 기반 추출 실행", type="primary", key="ai_run_btn"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            with st.spinner("Claude AI가 구조계산서를 분석 중..."):
                result = parse_pdf_with_ai(tmp_path, api_key)
            # ── 누적 저장 ──
            st.session_state['pdf_upload_count'] = st.session_state.get('pdf_upload_count', 0) + 1
            _idx = st.session_state['pdf_upload_count']
            # 부재명에 #N 태깅
            _tagged_members = []
            for _m in result.get('members', []):
                _mc = dict(_m)
                _orig_name = _mc.get('name', '')
                # 이미 [] 안에 source가 있으면 그 뒤에 #N 추가, 없으면 그냥 #N 붙이기
                if '[' in _orig_name and ']' in _orig_name:
                    _mc['name'] = _orig_name.replace(']', f' #{_idx}]')
                else:
                    _mc['name'] = f"{_orig_name} #{_idx}"
                _tagged_members.append(_mc)
            _tagged_result = dict(result)
            _tagged_result['members'] = _tagged_members
            st.session_state['ai_parse_results'].append({
                'idx': _idx,
                'filename': uploaded.name,
                'result': _tagged_result,
            })
            # 통합 ai_analysis_result 재구축 (코드 기반 + AI 기반 모두 포함)
            _rebuild_ai_analysis_result()
            st.session_state['ai_analysis_filename'] = uploaded.name
            # 업로더 리셋 — key 변경으로 파일 제거 (중복 분석 방지)
            st.session_state['pdf_uploader_ver'] += 1
        except Exception as e:
            st.error(f"AI 추출 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)
        st.rerun()

    # ── 결과 표시 ────────────────────────────────────────────────────
    ai_history = st.session_state.get('ai_parse_results', [])
    if not ai_history:
        return

    # 각 파일별 헤더 + 결과 표시
    for _h in ai_history:
        _hidx = _h['idx']
        _hfn = _h['filename']
        _hr = _h['result']
        st.markdown(f"### #{_hidx} ({_hfn})")

        _h_members = _hr.get('members', [])
        if _hr.get('error'):
            st.error(_hr['error'])
            continue
        if not _h_members:
            st.warning("분석 결과에서 부재를 찾지 못했습니다.")
            continue

        _img_sent = _hr.get('images_sent', 0)
        _img_label = f" | 📷 이미지 {_img_sent}장 전송" if _img_sent > 0 else " | ⚠️ 이미지 미전송"
        st.success(f"AI 추출: {_hr.get('pages_used', '?')}/{_hr.get('pages_total', '?')} 페이지 | {len(_h_members)}개 부재 인식{_img_label}")

        beams = [m for m in _h_members if m.get('type') == 'beam']
        columns = [m for m in _h_members if m.get('type') == 'column']
        others = [m for m in _h_members if m.get('type') not in ('beam', 'column')]

        if beams:
            _render_beam_table(beams)
        if columns:
            _render_column_table(columns)
        if others:
            _render_other_table(others)

    # ── 입력 적용 (설계 모드에서만 표시) ──
    _is_review = st.session_state.get('design_mode_radio') == '📄 구조계산서 검토'
    if _is_review:
        st.info("✅ AI 추출 결과가 아래 검토 부재 설정에 자동 반영됩니다.")
        return

    # 설계 모드 적용용 — 전체 누적 멤버에서 보/기둥 추출
    _all_ai_members = []
    for _h in ai_history:
        _all_ai_members.extend(_h.get('result', {}).get('members', []))
    beams = [m for m in _all_ai_members if m.get('type') == 'beam']
    columns = [m for m in _all_ai_members if m.get('type') == 'column']

    st.markdown("---")
    st.markdown("**📌 입력값에 적용 (설계 모드)**")
    beam_names = [b.get("name", f"beam_{i}") for i, b in enumerate(beams)]
    col_names  = [c.get("name", f"col_{i}")  for i, c in enumerate(columns)]

    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        ai_bx = st.selectbox("X방향 보", ["(선택 안 함)"] + beam_names, key="ai_sel_bx")
    with ic2:
        ai_by = st.selectbox("Y방향 보", ["(선택 안 함)"] + beam_names, key="ai_sel_by")
    with ic3:
        ai_co = st.selectbox("기둥", ["(선택 안 함)"] + col_names, key="ai_sel_col")

    if st.button("✅ 위 선택으로 입력 적용", type="primary", key="ai_apply_btn"):
        bx = next((b for b in beams   if b.get("name") == ai_bx), None)
        by = next((b for b in beams   if b.get("name") == ai_by), None)
        co = next((c for c in columns if c.get("name") == ai_co), None)
        if bx:
            sec = bx.get("section", {}) or {}
            mat = bx.get("material", {}) or {}
            geo = bx.get("geometry", {}) or {}
            if geo.get("span_m"):
                st.session_state['pdf_L_x'] = int(round(float(geo["span_m"]) * 1000 / 100) * 100)
            if mat.get("fck_MPa"):
                st.session_state['pdf_fc_k'] = float(mat["fck_MPa"])
            if mat.get("fy_MPa"):
                st.session_state['pdf_fy'] = float(mat["fy_MPa"])
            if sec.get("H_mm"):
                st.session_state['pdf_h_beam_x'] = int(sec["H_mm"])
            if sec.get("B_mm"):
                st.session_state['pdf_b_beam_x'] = int(sec["B_mm"])
        if by:
            sec = by.get("section", {}) or {}
            geo = by.get("geometry", {}) or {}
            if geo.get("span_m"):
                st.session_state['pdf_L_y'] = int(round(float(geo["span_m"]) * 1000 / 100) * 100)
            if sec.get("H_mm"):
                st.session_state['pdf_h_beam_y'] = int(sec["H_mm"])
            if sec.get("B_mm"):
                st.session_state['pdf_b_beam_y'] = int(sec["B_mm"])
        if co:
            sec = co.get("section", {}) or {}
            geo = co.get("geometry", {}) or {}
            df  = co.get("design_forces", {}) or {}
            if geo.get("height_m"):
                st.session_state['pdf_h_col'] = int(round(float(geo["height_m"]) * 1000 / 100) * 100)
            if df.get("Pu_kN"):
                st.session_state['pdf_Pu'] = float(df["Pu_kN"])
            if df.get("Mux_kNm"):
                st.session_state['pdf_Mux'] = float(df["Mux_kNm"])
            if df.get("Muy_kNm"):
                st.session_state['pdf_Muy'] = float(df["Muy_kNm"])
            if sec.get("Cx_mm"):
                st.session_state['pdf_c_column'] = int(sec["Cx_mm"])
            st.session_state['col_load_list'] = [
                {
                    '기둥명': co.get("name") or '기둥 1',
                    'Pu_add':  float(df.get("Pu_kN") or 0.0),
                    'Mux_add': float(df.get("Mux_kNm") or 0.0),
                    'Muy_add': float(df.get("Muy_kNm") or 0.0),
                }
            ]
        st.success("적용 완료! 아래 입력값이 업데이트됩니다.")
        st.rerun()


def _render_auto_analysis(uploaded):
    """pdfplumber 기반 자동 파싱 분석"""
    try:
        from parsers.pdf_parser import parse_pdf
    except ImportError:
        st.error("pdf_parser.py 또는 pdfplumber가 설치되지 않았습니다: pip install pdfplumber")
        return

    if uploaded and st.button("⚙️ 코드 기반 추출 실행", type="primary", key="auto_parse_btn"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            with st.spinner("PDF 파싱 중..."):
                result = parse_pdf(tmp_path)
            # ── 누적 저장 ──
            st.session_state['pdf_upload_count'] = st.session_state.get('pdf_upload_count', 0) + 1
            _idx = st.session_state['pdf_upload_count']
            st.session_state['auto_parse_results'].append({
                'idx': _idx,
                'filename': uploaded.name,
                'result': result,
            })
            # 하위 호환용 (단일 결과 참조하는 코드 대비)
            st.session_state['auto_parse_result'] = result
            # 업로더 리셋 — key 변경으로 파일 제거 (중복 분석 방지)
            st.session_state['pdf_uploader_ver'] += 1
        except Exception as e:
            st.error(f"파싱 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)
        st.rerun()

    # ── 누적된 모든 결과 표시 ──
    all_history = st.session_state.get('auto_parse_results', [])
    if not all_history:
        return

    # 전체 누적 통계
    _all_beams = []
    _all_cols = []
    _all_slabs = []
    for _h in all_history:
        _r = _h['result']
        _all_beams.extend(_r.get('beams', []))
        _all_cols.extend(_r.get('columns', []))
        _all_slabs.extend(_r.get('slabs', []))
    _slab_msg = f" · 슬래브 {len(_all_slabs)}개" if _all_slabs else ""
    st.success(f"코드 기반 추출 누적: {len(all_history)}개 파일 | "
               f"보 {len(_all_beams)}개 · 기둥 {len(_all_cols)}개{_slab_msg}")

    # ── 각 파일별 결과 표시 ──────────────────────────────────────────
    for _h in all_history:
        _hidx = _h['idx']
        _hfn = _h['filename']
        _hr = _h['result']
        st.markdown(f"### #{_hidx} ({_hfn})")
        _pp = _hr.get('pages_parsed', '?')
        _pt = _hr.get('pages_total', '?')
        _hbeams = _hr.get('beams', [])
        _hcols = _hr.get('columns', [])
        _hslabs = _hr.get('slabs', [])
        _hs_msg = f" · 슬래브 {len(_hslabs)}개" if _hslabs else ""
        st.caption(f"{_pp}/{_pt} 페이지 인식 | 보 {len(_hbeams)}개 · 기둥 {len(_hcols)}개{_hs_msg}")

    # ── 보 테이블 ────────────────────────────────────────────────────
    beams = _all_beams
    cols = _all_cols
    slabs = _all_slabs
    # 부재명에 #N 태깅 (표시용 매핑)
    _beam_idx_map = {}  # id(b) → idx
    _col_idx_map = {}
    _slab_idx_map = {}
    for _h in all_history:
        for b in _h['result'].get('beams', []):
            _beam_idx_map[id(b)] = _h['idx']
        for c in _h['result'].get('columns', []):
            _col_idx_map[id(c)] = _h['idx']
        for s in _h['result'].get('slabs', []):
            _slab_idx_map[id(s)] = _h['idx']

    if beams:
        st.markdown("**보 부재**")
        for b in beams:
            _bi = _beam_idx_map.get(id(b), '')
            _btag = f" #{_bi}" if _bi else ""
            with st.expander(f"🔵 {b.member} [{b.source}{_btag}]", expanded=False):
                # 기본 정보 — 한 줄 요약
                _span = f"L={b.span_m}m" if b.span_m else ""
                _sec = f"B={b.B_mm:.0f}×H={b.H_mm:.0f}mm" if b.B_mm and b.H_mm else ""
                _mat = f"fck={b.fck:.0f} fy={b.fy:.0f}MPa" if b.fck and b.fy else ""
                _loc = f"Loc={b.Loc_top_mm:.0f}/{b.Loc_bot_mm:.0f}mm" if b.Loc_top_mm else ""
                st.markdown(f"**{_span}　{_sec}　{_mat}　{_loc}**")

                # T형보
                if b.B_top_mm:
                    st.caption(f"T형보: 상부 B={b.B_top_mm:.0f}×H={b.H_top_mm:.0f}mm")

                # 배근
                if b.rebar_top:
                    _rt = b.rebar_top[0] if isinstance(b.rebar_top, tuple) else b.rebar_top
                    _rb = b.rebar_bot[0] if isinstance(b.rebar_bot, tuple) else (b.rebar_bot or "-")
                    _st = b.stirrup[0] if isinstance(b.stirrup, tuple) else (b.stirrup or "-")
                    st.markdown(f"TOP **{_rt}** / BOT **{_rb}** / STIRRUPS **{_st}**")

                # 부재력 테이블 (END-I / MID / END-J)
                if b.Mu_neg and isinstance(b.Mu_neg, tuple) and len(b.Mu_neg) == 3:
                    st.markdown("**부재력 (END-I / MID / END-J)**")
                    force_rows = []
                    labels = ['END-I', 'MID', 'END-J']
                    for i, loc in enumerate(labels):
                        row = {"위치": loc}
                        if b.Mu_neg: row["Mu(-) kN·m"] = b.Mu_neg[i]
                        if b.Mu_pos: row["Mu(+) kN·m"] = b.Mu_pos[i]
                        if b.Vu: row["Vu kN"] = b.Vu[i]
                        if b.phi_Mn_neg: row["φMn(-) kN·m"] = b.phi_Mn_neg[i]
                        if b.phi_Mn_pos: row["φMn(+) kN·m"] = b.phi_Mn_pos[i]
                        if b.phi_Vc: row["φVc kN"] = b.phi_Vc[i]
                        if b.phi_Vs: row["φVs kN"] = b.phi_Vs[i]
                        if b.check_ratio_neg: row["CR(-)"] = b.check_ratio_neg[i]
                        if b.check_ratio_pos: row["CR(+)"] = b.check_ratio_pos[i]
                        if b.check_ratio_shear: row["CR(전단)"] = b.check_ratio_shear[i]
                        if b.Mu_neg_lc: row["LC(-)"] = b.Mu_neg_lc[i]
                        if b.Mu_pos_lc: row["LC(+)"] = b.Mu_pos_lc[i]
                        if b.Vu_lc: row["LC(전단)"] = b.Vu_lc[i]
                        force_rows.append(row)
                    st.dataframe(pd.DataFrame(force_rows), width='stretch', hide_index=True)

                # BeST 상세 (단일값)
                if b.source == 'BeST.RC':
                    if b.phi_Mn_best or b.check_ratio_best or b.phi_Vc_best:
                        st.markdown("**BeST.RC 설계 결과**")
                        bc1, bc2, bc3, bc4 = st.columns(4)
                        bc1.metric("φMn", f"{b.phi_Mn_best} kN·m" if b.phi_Mn_best else "-")
                        bc2.metric("Mu/φMn", f"{b.check_ratio_best}" if b.check_ratio_best else "-")
                        bc3.metric("φVc", f"{b.phi_Vc_best} kN" if b.phi_Vc_best else "-")
                        bc4.metric("Vs,req", f"{b.Vs_req_best} kN" if b.Vs_req_best else "-")
                    if b.stirrup_req:
                        st.caption(f"Required Stirrup: {b.stirrup_req}")
                    if b.crack_smax:
                        _cr_status = "✅ O.K." if b.crack_ok else "❌ N.G."
                        st.caption(f"균열: smax={b.crack_smax}mm > s={b.crack_s}mm → {_cr_status}")

                # 위치별 스터럽 (MIDAS)
                if isinstance(b.stirrup, tuple) and len(b.stirrup) == 3:
                    if not (b.stirrup[0] == b.stirrup[1] == b.stirrup[2]):
                        st.caption(f"스터럽: END-I={b.stirrup[0]} / MID={b.stirrup[1]} / END-J={b.stirrup[2]}")

    # ── 기둥 테이블 ──────────────────────────────────────────────────
    if cols:
        st.markdown("**기둥 부재**")
        for c in cols:
            _ci = _col_idx_map.get(id(c), '')
            _ctag = f" #{_ci}" if _ci else ""
            with st.expander(f"🟠 {c.member} [{c.source}{_ctag}]", expanded=False):
                # 기본 정보 — 한 줄 요약
                _csec = f"Cx={c.Cx_mm:.0f}×Cy={c.Cy_mm:.0f}mm" if c.Cx_mm else ""
                _ch = f"H={c.height_m}m" if c.height_m else ""
                _cmat = f"fck={c.fck:.0f} fy={c.fy:.0f}MPa" if c.fck and c.fy else ""
                st.markdown(f"**{_csec}　{_ch}　{_cmat}**")

                # 설계력
                _pu = f"Pu={c.Pu_kN}kN" if c.Pu_kN else ""
                _mux = f"Mux={c.Mux_kNm}kN·m" if c.Mux_kNm else ""
                _muy = f"Muy={c.Muy_kNm}kN·m" if c.Muy_kNm else ""
                st.markdown(f"설계력: **{_pu}　{_mux}　{_muy}**")

                # 배근
                if c.rebar_vert or c.hoop:
                    _rv = f"수직근: {c.rebar_vert}" if c.rebar_vert else ""
                    _hp = f"후프: {c.hoop}" if c.hoop else ""
                    _cv = f"Cover={c.clear_cover_mm}mm" if c.clear_cover_mm else ""
                    st.markdown(f"{_rv}　{_hp}　{_cv}")

                # 강재 (SRC)
                if c.steel_section:
                    st.caption(f"강재: {c.steel_section}")

                # 설계 결과
                if c.phi_Mnx or c.phi_Mny or c.R_com:
                    _mnx = f"φMnx={c.phi_Mnx}" if c.phi_Mnx else ""
                    _mny = f"φMny={c.phi_Mny}" if c.phi_Mny else ""
                    _rcom = f"R_com={c.R_com}" if c.R_com else ""
                    _ppn = f"φPn,max={c.phi_Pn_max}kN" if c.phi_Pn_max else ""
                    st.markdown(f"설계결과: **{_mnx}　{_mny}　{_rcom}　{_ppn}**")

                # 전단
                if c.Vuy_kN:
                    st.markdown(f"전단: Vuy={c.Vuy_kN}kN　φVny={c.phi_Vny_kN}kN　CR={c.check_ratio_shear}")

    # ── 슬래브 테이블 ──────────────────────────────────────────────
    if slabs:
        st.markdown("**슬래브 부재**")
        for s in slabs:
            _si = _slab_idx_map.get(id(s), '')
            _stag = f" #{_si}" if _si else ""
            with st.expander(f"🟢 {s.member} [{s.source}{_stag}]", expanded=False):
                _dim = f"Lx={s.Lx_mm:.0f}×Ly={s.Ly_mm:.0f}×H={s.H_mm:.0f}mm" if s.Lx_mm else ""
                _smat = f"fck={s.fck:.0f} fy={s.fy:.0f}MPa" if s.fck else ""
                _scc = f"cc={s.cover_mm:.0f}mm" if s.cover_mm else ""
                st.markdown(f"**{_dim}　{_smat}　{_scc}**")

                # Edge Beams
                _edges = []
                for _dir, _val in [('UP', s.edge_UP), ('DN', s.edge_DN), ('LT', s.edge_LT), ('RT', s.edge_RT)]:
                    if _val:
                        _edges.append(f"{_dir}={_val}")
                if _edges:
                    st.caption(f"Edge Beams: {' / '.join(_edges)}")

                # 하중
                if s.Wu_kNm2:
                    st.markdown(f"하중: Wd={s.Wd_kNm2} / Wl={s.Wl_kNm2} → **Wu={s.Wu_kNm2} kN/m²**")

                # 최소 두께
                if s.h_req_mm:
                    _thk_status = "✅ O.K." if s.thk_ok else "❌ N.G."
                    st.caption(f"최소 두께: β={s.beta}, h_req={s.h_req_mm:.0f}mm, H={s.H_mm:.0f}mm → {_thk_status}")

                # Flexure table
                if s.flexure_rows:
                    _fl_rows = []
                    for fr in s.flexure_rows:
                        _fl_rows.append({
                            "방향": fr['direction'],
                            "위치": fr['location'],
                            "Mu (kN·m/m)": fr['Mu'],
                            "ρ (%)": fr['rho'],
                            "Ast (mm²/m)": fr['Ast'],
                        })
                    st.dataframe(pd.DataFrame(_fl_rows), width='stretch', hide_index=True)

                # 전단
                if s.Vux_kN:
                    _sx = "✅" if s.shear_x_ok else "❌"
                    _sy = "✅" if s.shear_y_ok else "❌"
                    st.caption(f"전단: Vux={s.Vux_kN} < φVc={s.phi_Vcx_kN} {_sx} / Vuy={s.Vuy_kN} < φVc={s.phi_Vcy_kN} {_sy}")

    # ── 검토 모드 연동 — 코드 기반 추출 결과를 AI 형식으로 변환하여 저장 ──
    # 검토 모드(input.py render_review_input_section)가 session_state['ai_analysis_result']를 읽으므로
    # 코드 기반 추출 결과도 같은 형식으로 저장하면 검토 모드에서도 사용 가능
    ai_format_members = []
    # AI 기반 추출 결과가 있으면 먼저 포함 (누적)
    for _ai_h in st.session_state.get('ai_parse_results', []):
        _ai_members = _ai_h.get('result', {}).get('members', [])
        ai_format_members.extend(_ai_members)

    for b in beams:
        _mn = b.Mu_neg or (0, 0, 0)
        _mp = b.Mu_pos or (None, None, None)
        _vu = b.Vu or (0, 0, 0)
        _bi = _beam_idx_map.get(id(b), '')
        _btag = f" #{_bi}" if _bi else ""
        ai_format_members.append({
            "name": f"{b.member} [{b.source}{_btag}]",
            "type": "beam",
            "software": b.source,
            "section": {"B_mm": b.B_mm, "H_mm": b.H_mm, "Cx_mm": None, "Cy_mm": None,
                        "Loc_top_mm": b.Loc_top_mm, "Loc_bot_mm": b.Loc_bot_mm,
                        "B_top_mm": b.B_top_mm, "H_top_mm": b.H_top_mm},
            "material": {"fck_MPa": b.fck, "fy_MPa": b.fy, "fys_MPa": b.fys},
            "geometry": {"span_m": b.span_m, "height_m": None},
            "design_forces": {
                "Mu_neg_I_kNm": _mn[0], "Mu_neg_MID_kNm": _mn[1], "Mu_neg_J_kNm": _mn[2],
                "Mu_pos_I_kNm": _mp[0], "Mu_pos_MID_kNm": _mp[1], "Mu_pos_J_kNm": _mp[2],
                "Vu_I_kN": _vu[0], "Vu_MID_kN": _vu[1], "Vu_J_kN": _vu[2],
            },
            "rebar": {
                "top": b.rebar_top[0] if isinstance(b.rebar_top, tuple) else b.rebar_top,
                "bottom": b.rebar_bot[0] if isinstance(b.rebar_bot, tuple) else b.rebar_bot,
                "stirrup": (b.stirrup[0] if isinstance(b.stirrup, tuple) else b.stirrup)
                           or b.stirrup_req,
                "skin": b.skin_rebar,
            },
            "load_combinations": {
                "Mu_neg_lc": b.Mu_neg_lc if b.Mu_neg_lc else None,
                "Mu_pos_lc": b.Mu_pos_lc if b.Mu_pos_lc else None,
                "Vu_lc": b.Vu_lc if b.Vu_lc else None,
            },
        })
    for c in cols:
        _ci = _col_idx_map.get(id(c), '')
        _ctag = f" #{_ci}" if _ci else ""
        ai_format_members.append({
            "name": f"{c.member} [{c.source}{_ctag}]",
            "type": "column",
            "software": c.source,
            "section": {"B_mm": None, "H_mm": None, "Cx_mm": c.Cx_mm, "Cy_mm": c.Cy_mm,
                        "clear_cover_mm": c.clear_cover_mm},
            "material": {"fck_MPa": c.fck, "fy_MPa": c.fy, "fy_stl_MPa": c.fys},
            "steel_section": c.steel_section,
            "geometry": {"span_m": None, "height_m": c.height_m},
            "design_forces": {
                "Pu_kN": c.Pu_kN, "Mux_kNm": c.Mux_kNm, "Muy_kNm": c.Muy_kNm,
                "Vu_I_kN": c.Vuy_kN,
            },
            "rebar": {
                "top": c.rebar_vert, "bottom": None,
                "stirrup": c.hoop,
            },
        })
    for s in slabs:
        _si = _slab_idx_map.get(id(s), '')
        _stag = f" #{_si}" if _si else ""
        ai_format_members.append({
            "name": f"{s.member} [{s.source}{_stag}]",
            "type": "slab",
            "software": s.source,
            "slab_dim": {"Lx_mm": s.Lx_mm, "Ly_mm": s.Ly_mm, "H_mm": s.H_mm, "cover_mm": s.cover_mm},
            "material": {"fck_MPa": s.fck, "fy_MPa": s.fy},
            "edge_beams": {"UP": s.edge_UP, "DN": s.edge_DN, "LT": s.edge_LT, "RT": s.edge_RT},
            "loads": {"Wd": s.Wd_kNm2, "Wl": s.Wl_kNm2, "Wu": s.Wu_kNm2},
            "min_thk": {"beta": s.beta, "h_req": s.h_req_mm, "ok": s.thk_ok},
            "flexure_rows": s.flexure_rows,
            "rho_min": s.rho_min, "Ast_min": s.Ast_min, "min_spacings": s.min_spacings,
            "spacing_headers": s.spacing_headers,
            "shear": {"Vux": s.Vux_kN, "phi_Vcx": s.phi_Vcx_kN,
                      "Vuy": s.Vuy_kN, "phi_Vcy": s.phi_Vcy_kN},
        })
    st.session_state['ai_analysis_result'] = {"members": ai_format_members}

    # 설계 모드 입력 적용 UI 제거됨 — 검토 모드에서 "검토 부재 설정"으로 통합
