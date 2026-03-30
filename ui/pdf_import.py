import streamlit as st
import os
import tempfile
import pandas as pd

def _pdf_import_section():
    """구조계산서 업로드 — AI 기반 추출 + 코드 기반 추출 통합 UI"""
    with st.expander("📂 구조계산서 업로드", expanded=False):
        # ── 공용 PDF 업로더 ──────────────────────────────────────────────
        uploaded = st.file_uploader(
            "MIDAS Gen / BeST.RC 구조계산서 PDF",
            type="pdf",
            help="MIDAS Gen RC Beam/Column Checking Result 또는 BeST.RC/BeST.Steel 형식을 지원합니다.",
            key="pdf_uploader"
        )
        if not uploaded:
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

    # ── API 키 관리 ──────────────────────────────────────────────────
    builtin_key = _get_builtin_key()
    login_pw = _get_login_password()
    api_key = None

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

    if not api_key:
        st.info("API 키가 필요합니다. 로그인하거나 직접 입력하세요.")
        return

    # ── 분석 실행 ────────────────────────────────────────────────────
    if st.button("🤖 AI 기반 추출 실행", type="primary", key="ai_run_btn"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            with st.spinner("Claude AI가 구조계산서를 분석 중..."):
                result = parse_pdf_with_ai(tmp_path, api_key)
            st.session_state['ai_analysis_result'] = result
            st.session_state['ai_analysis_filename'] = uploaded.name
        except Exception as e:
            st.error(f"AI 추출 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)

    # ── 결과 표시 ────────────────────────────────────────────────────
    result = st.session_state.get('ai_analysis_result')
    if not result:
        return

    if result.get('error'):
        st.error(result['error'])
        return

    members = result.get('members', [])
    if not members:
        st.warning("분석 결과에서 부재를 찾지 못했습니다.")
        return

    _img_sent = result.get('images_sent', 0)
    _img_label = f" | 📷 이미지 {_img_sent}장 전송" if _img_sent > 0 else " | ⚠️ 이미지 미전송"
    st.success(f"AI 추출 완료: {result.get('pages_used', '?')}/{result.get('pages_total', '?')} 페이지 | {len(members)}개 부재 인식{_img_label}")

    beams = [m for m in members if m.get('type') == 'beam']
    columns = [m for m in members if m.get('type') == 'column']
    others = [m for m in members if m.get('type') not in ('beam', 'column')]

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

    if st.button("⚙️ 코드 기반 추출 실행", type="primary", key="auto_parse_btn"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            with st.spinner("PDF 파싱 중..."):
                result = parse_pdf(tmp_path)
            st.session_state['auto_parse_result'] = result
        except Exception as e:
            st.error(f"파싱 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)

    result = st.session_state.get('auto_parse_result')
    if not result:
        return

    beams = result['beams']
    cols  = result['columns']
    st.success(f"파싱 완료: {result['pages_parsed']}/{result['pages_total']} 페이지 인식  "
               f"| 보 {len(beams)}개 · 기둥 {len(cols)}개")

    # ── 보 테이블 ────────────────────────────────────────────────────
    if beams:
        st.markdown("**보 부재**")
        for b in beams:
            with st.expander(f"🔵 {b.member} [{b.source}]", expanded=False):
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
            with st.expander(f"🟠 {c.member} [{c.source}]", expanded=False):
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

    # ── 검토 모드 연동 — 코드 기반 추출 결과를 AI 형식으로 변환하여 저장 ──
    # 검토 모드(input.py render_review_input_section)가 session_state['ai_analysis_result']를 읽으므로
    # 코드 기반 추출 결과도 같은 형식으로 저장하면 검토 모드에서도 사용 가능
    ai_format_members = []
    for b in beams:
        _mn = b.Mu_neg or (0, 0, 0)
        _mp = b.Mu_pos or (None, None, None)
        _vu = b.Vu or (0, 0, 0)
        ai_format_members.append({
            "name": f"{b.member} [{b.source}]",
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
                "stirrup": b.stirrup[0] if isinstance(b.stirrup, tuple) else b.stirrup,
                "skin": b.skin_rebar,
            },
            "load_combinations": {
                "Mu_neg_lc": b.Mu_neg_lc if b.Mu_neg_lc else None,
                "Mu_pos_lc": b.Mu_pos_lc if b.Mu_pos_lc else None,
                "Vu_lc": b.Vu_lc if b.Vu_lc else None,
            },
        })
    for c in cols:
        ai_format_members.append({
            "name": f"{c.member} [{c.source}]",
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
    st.session_state['ai_analysis_result'] = {"members": ai_format_members}

    # 설계 모드 입력 적용 UI 제거됨 — 검토 모드에서 "검토 부재 설정"으로 통합
