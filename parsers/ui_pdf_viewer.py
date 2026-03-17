"""
ui_pdf_viewer.py
────────────────
구조계산서 AI 분석 결과 표시 UI (Streamlit)
app.py의 "구조계산서 분석" 탭에서 호출됨
"""
import os
import tempfile
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 내장 API 키 — .streamlit/secrets.toml 에서 로드 (코드에 키를 넣지 마세요)
# ─────────────────────────────────────────────────────────────────────────────
def _get_builtin_key():
    """st.secrets → 환경변수 순으로 내장 API 키 조회."""
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", "")


def _get_login_password():
    """st.secrets → 환경변수 순으로 로그인 비밀번호 조회."""
    try:
        return st.secrets["LOGIN_PASSWORD"]
    except Exception:
        return os.environ.get("LOGIN_PASSWORD", "")


# ─────────────────────────────────────────────────────────────────────────────
# 값 표시 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
def _sv(v, fmt=None):
    """None → '-', 숫자 → 포맷 적용"""
    if v is None:
        return "-"
    if fmt and isinstance(v, (int, float)):
        try:
            return fmt.format(v)
        except Exception:
            pass
    if isinstance(v, list):
        return " / ".join(str(x) for x in v)
    return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# 보 테이블
# ─────────────────────────────────────────────────────────────────────────────
def _render_beam_table(beams: list):
    st.markdown("#### 🔵 보 부재")

    rows = []
    for b in beams:
        sec = b.get("section", {}) or {}
        mat = b.get("material", {}) or {}
        geo = b.get("geometry", {}) or {}
        df  = b.get("design_forces", {}) or {}
        lc  = b.get("load_combinations", {}) or {}
        rb  = b.get("rebar", {}) or {}
        cr  = b.get("check_ratio", {}) or {}

        rows.append({
            "부재명":          b.get("name", "-"),
            "출처":            b.get("software", "-"),
            "스팬(m)":        _sv(geo.get("span_m"), "{:.2f}"),
            "B(mm)":          _sv(sec.get("B_mm")),
            "H(mm)":          _sv(sec.get("H_mm")),
            "fck(MPa)":       _sv(mat.get("fck_MPa")),
            "fy(MPa)":        _sv(mat.get("fy_MPa")),
            # 부 모멘트 (-)
            "Mu(-) I":        _sv(df.get("Mu_neg_I_kNm"),   "{:.2f}"),
            "Mu(-) MID":      _sv(df.get("Mu_neg_MID_kNm"), "{:.2f}"),
            "Mu(-) J":        _sv(df.get("Mu_neg_J_kNm"),   "{:.2f}"),
            "LC Mu(-)":       _sv(lc.get("Mu_neg_lc")),
            # 정 모멘트 (+)
            "Mu(+) I":        _sv(df.get("Mu_pos_I_kNm"),   "{:.2f}"),
            "Mu(+) MID":      _sv(df.get("Mu_pos_MID_kNm"), "{:.2f}"),
            "Mu(+) J":        _sv(df.get("Mu_pos_J_kNm"),   "{:.2f}"),
            "LC Mu(+)":       _sv(lc.get("Mu_pos_lc")),
            # 전단
            "Vu I(kN)":       _sv(df.get("Vu_I_kN"),   "{:.2f}"),
            "Vu MID(kN)":     _sv(df.get("Vu_MID_kN"), "{:.2f}"),
            "Vu J(kN)":       _sv(df.get("Vu_J_kN"),   "{:.2f}"),
            "LC Vu":          _sv(lc.get("Vu_lc")),
            # 배근
            "상부배근":        _sv(rb.get("top")),
            "하부배근":        _sv(rb.get("bottom")),
            "스터럽":          _sv(rb.get("stirrup")),
            # 검토비
            "M 검토비":        _sv(cr.get("moment"), "{:.3f}"),
            "V 검토비":        _sv(cr.get("shear"),  "{:.3f}"),
        })

    df_table = pd.DataFrame(rows)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    with st.expander("📋 개별 부재 상세 (JSON)"):
        names = [b.get("name", f"[{i}]") for i, b in enumerate(beams)]
        sel = st.selectbox("부재 선택", names, key="detail_beam_sel")
        obj = next((b for b in beams if b.get("name") == sel), None)
        if obj:
            st.json(obj)


# ─────────────────────────────────────────────────────────────────────────────
# 기둥 테이블
# ─────────────────────────────────────────────────────────────────────────────
def _render_column_table(cols: list):
    st.markdown("#### 🟠 기둥 부재")

    rows = []
    for c in cols:
        sec = c.get("section", {}) or {}
        mat = c.get("material", {}) or {}
        geo = c.get("geometry", {}) or {}
        df  = c.get("design_forces", {}) or {}
        lc  = c.get("load_combinations", {}) or {}
        rb  = c.get("rebar", {}) or {}
        cr  = c.get("check_ratio", {}) or {}

        rows.append({
            "부재명":       c.get("name", "-"),
            "출처":         c.get("software", "-"),
            "높이(m)":     _sv(geo.get("height_m"), "{:.2f}"),
            "Cx(mm)":      _sv(sec.get("Cx_mm")),
            "Cy(mm)":      _sv(sec.get("Cy_mm")),
            "fck(MPa)":    _sv(mat.get("fck_MPa")),
            "fy(MPa)":     _sv(mat.get("fy_MPa")),
            "Pu(kN)":      _sv(df.get("Pu_kN"),   "{:.2f}"),
            "Mux(kN·m)":   _sv(df.get("Mux_kNm"), "{:.2f}"),
            "Muy(kN·m)":   _sv(df.get("Muy_kNm"), "{:.2f}"),
            "LC 축력":      _sv(lc.get("axial_lc")),
            "배근":         _sv(rb.get("top")),
            "후프":         _sv(rb.get("stirrup")),
            "P 검토비":     _sv(cr.get("axial"),  "{:.3f}"),
            "M 검토비":     _sv(cr.get("moment"), "{:.3f}"),
            "V 검토비":     _sv(cr.get("shear"),  "{:.3f}"),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("📋 개별 부재 상세 (JSON)"):
        names = [c.get("name", f"[{i}]") for i, c in enumerate(cols)]
        sel = st.selectbox("부재 선택", names, key="detail_col_sel")
        obj = next((c for c in cols if c.get("name") == sel), None)
        if obj:
            st.json(obj)


# ─────────────────────────────────────────────────────────────────────────────
# 기타 부재 (슬래브, 기초 등)
# ─────────────────────────────────────────────────────────────────────────────
def _render_other_table(others: list):
    st.markdown("#### ⚪ 기타 부재 (슬래브 / 기초 / 기타)")
    for m in others:
        with st.expander(f"{m.get('name', '?')}  ({m.get('type', '?')})  — {m.get('software', '?')}"):
            st.json(m)


# ─────────────────────────────────────────────────────────────────────────────
# 부재 유형별 렌더링
# ─────────────────────────────────────────────────────────────────────────────
def _render_members(members: list):
    beams  = [m for m in members if m.get("type") == "beam"]
    cols_m = [m for m in members if m.get("type") == "column"]
    others = [m for m in members if m.get("type") not in ("beam", "column")]

    tab_labels = []
    if beams:  tab_labels.append(f"🔵 보  ({len(beams)}개)")
    if cols_m: tab_labels.append(f"🟠 기둥 ({len(cols_m)}개)")
    if others: tab_labels.append(f"⚪ 기타 ({len(others)}개)")
    if not tab_labels:
        st.warning("추출된 부재가 없습니다.")
        return

    tabs = st.tabs(tab_labels)
    ti = 0
    if beams:
        with tabs[ti]: _render_beam_table(beams)
        ti += 1
    if cols_m:
        with tabs[ti]: _render_column_table(cols_m)
        ti += 1
    if others:
        with tabs[ti]: _render_other_table(others)


# ─────────────────────────────────────────────────────────────────────────────
# 메인 탭 렌더러 (app.py에서 호출)
# ─────────────────────────────────────────────────────────────────────────────
def render_pdf_analysis_tab():
    st.header("📄 구조계산서 AI 분석")
    st.caption(
        "MIDAS Gen / BeST.RC / BeST.Steel 형식의 구조계산서 PDF를 업로드하면 "
        "AI(Claude Haiku)가 부재 정보를 자동으로 추출합니다."
    )

    # ── API 키 설정 (로그인 / st.secrets / 환경변수 / 수동입력) ──────────────
    active_key = ""

    # 로그인 상태 확인
    logged_in = st.session_state.get('ai_logged_in', False)

    if logged_in:
        st.success("✅ 로그인됨 — 내장 API 키 사용 중")
        if st.button("로그아웃", key="ai_logout_btn"):
            st.session_state['ai_logged_in'] = False
            st.rerun()
        active_key = _get_builtin_key()
    else:
        tab_login, tab_manual = st.tabs(["🔐 로그인", "🔑 직접 입력"])

        with tab_login:
            _pwd = _get_login_password()
            if not _pwd:
                st.warning("로그인 기능을 사용하려면 `.streamlit/secrets.toml`에 LOGIN_PASSWORD를 설정하세요.")
            else:
                st.caption("비밀번호를 입력하면 내장 API 키가 활성화됩니다.")
                pw = st.text_input("비밀번호", type="password", key="ai_login_pw")
                if st.button("로그인", type="primary", key="ai_login_btn"):
                    if pw == _pwd:
                        st.session_state['ai_logged_in'] = True
                        st.rerun()
                    else:
                        st.error("❌ 비밀번호가 틀렸습니다.")

        with tab_manual:
            # 기존 환경변수/secrets 방식 유지
            api_key_secrets = ""
            try:
                api_key_secrets = st.secrets.get("ANTHROPIC_API_KEY", "")
            except Exception:
                pass
            api_key_env = api_key_secrets or os.environ.get("ANTHROPIC_API_KEY", "")

            if api_key_env:
                st.success("✅ 환경변수에서 API 키 감지됨")
                use_env = st.checkbox("설정된 키 사용", value=True, key="ai_use_env_key")
            else:
                use_env = False
                st.info(
                    "API 키를 아래에 직접 입력하세요.  \n"
                    "키 발급: https://console.anthropic.com"
                )

            if not use_env:
                manual_key = st.text_input(
                    "API 키 입력",
                    type="password",
                    placeholder="sk-ant-...",
                    key="ai_manual_api_key",
                )
                active_key = manual_key
            else:
                active_key = api_key_env

    # ── 파일 업로드 ───────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "구조계산서 PDF 업로드",
        type="pdf",
        key="ai_pdf_uploader_main",
        help="MIDAS Gen RC Beam/Column Checking Result, BeST.RC, BeST.Steel 계산서를 지원합니다.",
    )

    if not uploaded:
        st.info("📁 PDF 파일을 업로드하면 분석 버튼이 활성화됩니다.")
        return

    # ── 분석 버튼 ─────────────────────────────────────────────────────────
    col_btn, col_meta = st.columns([1, 4])
    with col_btn:
        run = st.button("🤖 AI 분석 시작", type="primary", key="ai_run_btn")
    with col_meta:
        st.caption(f"파일명: **{uploaded.name}**  |  크기: {uploaded.size / 1024:.1f} KB")

    # 분석 실행 → session_state에 결과 저장
    if run:
        if not active_key:
            st.error("❌ API 키를 입력하거나 환경변수 ANTHROPIC_API_KEY를 설정하세요.")
            return

        try:
            from parsers.ai_pdf_parser import parse_pdf_with_ai
        except ImportError as e:
            st.error(f"모듈 오류: {e}")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner("🤖 AI가 구조계산서를 분석 중입니다... (약 10~30초 소요)"):
                result = parse_pdf_with_ai(tmp_path, api_key=active_key)
        except Exception as e:
            st.error(f"분석 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)

        # 결과를 session_state에 저장 (rerun 후에도 유지)
        st.session_state['ai_analysis_result'] = result
        st.session_state['ai_analysis_filename'] = uploaded.name

    # ── 저장된 결과 표시 ─────────────────────────────────────────────────
    result = st.session_state.get('ai_analysis_result')
    if result is None:
        return

    # 다른 파일 업로드 시 이전 결과 자동 제거
    if st.session_state.get('ai_analysis_filename') != uploaded.name:
        del st.session_state['ai_analysis_result']
        del st.session_state['ai_analysis_filename']
        return

    # ── 오류 표시 ─────────────────────────────────────────────────────────
    if result.get("error"):
        st.warning(f"⚠️ JSON 파싱 경고: {result['error']}")

    # ── 요약 지표 ─────────────────────────────────────────────────────────
    members = result.get("members", [])
    beams   = [m for m in members if m.get("type") == "beam"]
    cols_m  = [m for m in members if m.get("type") == "column"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📄 전체 페이지",   result.get("pages_total", "-"))
    c2.metric("🔍 분석 페이지",   result.get("pages_used",  "-"))
    c3.metric("📦 전체 부재",     len(members))
    c4.metric("🔵 보",           len(beams))
    c5.metric("🟠 기둥",         len(cols_m))

    st.divider()

    if members:
        _render_members(members)
    else:
        st.warning("부재가 추출되지 않았습니다. 아래 디버그 정보를 확인하세요.")

    # ── RC 설계 탭에 적용 ────────────────────────────────────────────────
    if beams or cols_m:
        st.divider()
        st.markdown("### 📌 RC 설계 입력에 적용")
        st.caption("아래에서 부재를 선택하고 '적용' 버튼을 누르면 RC 설계 탭 입력값이 업데이트됩니다.")

        beam_names = [b.get("name", f"beam_{i}") for i, b in enumerate(beams)]
        col_names  = [c.get("name", f"col_{i}")  for i, c in enumerate(cols_m)]

        _ac1, _ac2, _ac3 = st.columns(3)
        with _ac1:
            ai_bx_sel = st.selectbox(
                "X방향 보 (→ L_x, 단면)",
                ["(선택 안 함)"] + beam_names,
                key="ai_sel_bx",
            )
        with _ac2:
            ai_by_sel = st.selectbox(
                "Y방향 보 (→ L_y, 단면)",
                ["(선택 안 함)"] + beam_names,
                key="ai_sel_by",
            )
        with _ac3:
            ai_co_sel = st.selectbox(
                "기둥 (→ H_col, Pu, Mu, 단면)",
                ["(선택 안 함)"] + col_names,
                key="ai_sel_col",
            )

        if st.button("✅ RC 설계 탭에 적용", type="primary", key="ai_apply_btn"):
            bx = next((b for b in beams  if b.get("name") == ai_bx_sel), None)
            by = next((b for b in beams  if b.get("name") == ai_by_sel), None)
            co = next((c for c in cols_m if c.get("name") == ai_co_sel), None)

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
                # col_load_list도 PDF 값으로 초기화
                st.session_state['col_load_list'] = [
                    {
                        '기둥명': co.get("name") or '기둥 1',
                        'Pu_add':  float(df.get("Pu_kN") or 0.0),
                        'Mux_add': float(df.get("Mux_kNm") or 0.0),
                        'Muy_add': float(df.get("Muy_kNm") or 0.0),
                    }
                ]

            st.success("적용 완료! 'RC 설계' 탭으로 이동하면 입력값이 반영됩니다.")
            st.rerun()

    # ── 디버그 정보 ───────────────────────────────────────────────────────
    with st.expander("🔍 AI에 전달된 텍스트 (관련 페이지만)"):
        raw = result.get("raw_text", "")
        st.text_area("원본 텍스트", raw, height=300, label_visibility="collapsed")

    with st.expander("🤖 AI 원본 응답 (JSON)"):
        st.code(result.get("raw_response", ""), language="json")
