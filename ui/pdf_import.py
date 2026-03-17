import streamlit as st
import os
import tempfile
import pandas as pd

def _pdf_import_section():
    """구조계산서(PDF) 가져오기 — 파싱 결과를 session_state에 저장"""
    with st.expander("📂 구조계산서(PDF)에서 불러오기", expanded=False):
        uploaded = st.file_uploader(
            "MIDAS Gen / BeST.RC 구조계산서 PDF",
            type="pdf",
            help="MIDAS Gen RC Beam/Column Checking Result 또는 BeST.RC/BeST.Steel 형식을 지원합니다.",
            key="pdf_uploader"
        )
        if not uploaded:
            st.info("PDF 파일을 업로드하면 스팬·기둥 높이·재료강도·설계하중을 자동으로 추출합니다.")
            return

        try:
            from parsers.pdf_parser import parse_pdf
        except ImportError:
            st.error("pdf_parser.py 또는 pdfplumber가 설치되지 않았습니다: pip install pdfplumber")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner("PDF 파싱 중..."):
                result = parse_pdf(tmp_path)
        except Exception as e:
            st.error(f"파싱 오류: {e}")
            return
        finally:
            os.unlink(tmp_path)

        beams = result['beams']
        cols  = result['columns']
        st.success(f"파싱 완료: {result['pages_parsed']}/{result['pages_total']} 페이지 인식  "
                   f"| 보 {len(beams)}개 · 기둥 {len(cols)}개")

        # ── 보 테이블 ──────────────────────────────────────────────────────
        if beams:
            st.markdown("**보 부재**")
            rows = []
            for b in beams:
                mu_vals = [abs(v) for v in (b.Mu_neg or (0,0,0)) if v is not None]
                vu_vals = [abs(v) for v in (b.Vu    or (0,0,0)) if v is not None]
                rows.append({
                    "부재":       b.member,
                    "출처":       b.source,
                    "스팬(m)":   b.span_m,
                    "B(mm)":     b.B_mm,
                    "H(mm)":     b.H_mm,
                    "fck(MPa)":  b.fck,
                    "fy(MPa)":   b.fy,
                    "Mu_max(kN·m)": round(max(mu_vals), 2) if mu_vals else None,
                    "Vu_max(kN)":   round(max(vu_vals), 2) if vu_vals else None,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── 기둥 테이블 ────────────────────────────────────────────────────
        if cols:
            st.markdown("**기둥 부재**")
            rows = []
            for c in cols:
                rows.append({
                    "부재":       c.member,
                    "출처":       c.source,
                    "높이(m)":   c.height_m,
                    "Cx(mm)":    c.Cx_mm,
                    "Cy(mm)":    c.Cy_mm,
                    "fck(MPa)":  c.fck,
                    "Pu(kN)":    c.Pu_kN,
                    "Mux(kN·m)": c.Mux_kNm,
                    "Muy(kN·m)": c.Muy_kNm,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── 입력 적용 ─────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("**📌 입력값에 적용**")
        beam_names = [b.member for b in beams]
        col_names  = [c.member for c in cols]

        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            bx_sel = st.selectbox("X방향 보 (→ L_x)", ["(선택 안 함)"] + beam_names, key="pdf_sel_bx")
        with ic2:
            by_sel = st.selectbox("Y방향 보 (→ L_y)", ["(선택 안 함)"] + beam_names, key="pdf_sel_by")
        with ic3:
            co_sel = st.selectbox("기둥 (→ H_col, Pu, Mu)", ["(선택 안 함)"] + col_names, key="pdf_sel_col")

        if st.button("✅ 위 선택으로 입력 적용", type="primary", key="pdf_apply"):
            bx = next((b for b in beams if b.member == bx_sel), None)
            by = next((b for b in beams if b.member == by_sel), None)
            co = next((c for c in cols  if c.member == co_sel),  None)
            if bx:
                if bx.span_m: st.session_state['pdf_L_x']  = int(round(bx.span_m * 1000 / 100) * 100)
                if bx.fck:    st.session_state['pdf_fc_k'] = float(bx.fck)
                if bx.fy:     st.session_state['pdf_fy']   = float(bx.fy)
                # 보 단면 사이즈 (부재 사이즈 직접 지정용)
                if bx.H_mm:   st.session_state['pdf_h_beam_x'] = int(bx.H_mm)
                if bx.B_mm:   st.session_state['pdf_b_beam_x'] = int(bx.B_mm)
            if by:
                if by.span_m: st.session_state['pdf_L_y'] = int(round(by.span_m * 1000 / 100) * 100)
                if by.H_mm:   st.session_state['pdf_h_beam_y'] = int(by.H_mm)
                if by.B_mm:   st.session_state['pdf_b_beam_y'] = int(by.B_mm)
            if co:
                if co.height_m: st.session_state['pdf_h_col'] = int(round(co.height_m * 1000 / 100) * 100)
                if co.Pu_kN:    st.session_state['pdf_Pu']    = float(co.Pu_kN)
                if co.Mux_kNm:  st.session_state['pdf_Mux']   = float(co.Mux_kNm)
                if co.Muy_kNm:  st.session_state['pdf_Muy']   = float(co.Muy_kNm)
                # 기둥 단면 사이즈
                if co.Cx_mm:    st.session_state['pdf_c_column'] = int(co.Cx_mm)
                # col_load_list도 PDF 값으로 초기화 (첫 번째 기둥 교체)
                st.session_state['col_load_list'] = [
                    {
                        '기둥명': co.member or '기둥 1',
                        'Pu_add':  float(co.Pu_kN or 0.0),
                        'Mux_add': float(co.Mux_kNm or 0.0),
                        'Muy_add': float(co.Muy_kNm or 0.0),
                    }
                ]
            st.success("적용 완료! 아래 입력값이 업데이트됩니다.")
            st.rerun()
