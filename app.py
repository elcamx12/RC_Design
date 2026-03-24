import re
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import ui
import calculation_manager
from review import perform_review

# ──────────────────────────────────────────────────────────────────────────
# 패치노트 주간 그룹핑 (목요일~수요일 기준, 수요일 회의 보고용)
# ──────────────────────────────────────────────────────────────────────────
_WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']

def _render_patch_notes():
    """패치노트.md를 읽고 주간(목~수) 탭으로 그룹핑하여 표시."""
    patch_path = Path(__file__).parent / '패치노트.md'
    if not patch_path.exists():
        return
    content = patch_path.read_text(encoding='utf-8')

    # ── 버전 섹션 분리 ──
    # "## v0.6.5 — 2026-03-17" 형태의 헤더로 분할
    raw_sections = re.split(r'(?=^## v)', content, flags=re.MULTILINE)
    header_re = re.compile(
        r'^## (v[\d.]+(?:\s+이전)?)\s*[—\-]+\s*(\d{4}-\d{2}-\d{2})')

    entries = []  # [(date, version_label, markdown_body), ...]
    for sec in raw_sections:
        m = header_re.match(sec.strip())
        if m:
            version = m.group(1)
            date = datetime.strptime(m.group(2), '%Y-%m-%d').date()
            # 본문: ## 헤더 줄 제거, --- 구분선 제거
            body = sec.strip()
            body = re.sub(r'^## .+\n*', '', body)     # 첫 줄 헤더 제거
            body = re.sub(r'^---\s*$', '', body, flags=re.MULTILINE).strip()
            entries.append((date, version, body))

    if not entries:
        return

    # ── 주간 그룹핑 (목요일 시작) ──
    def _week_thursday(d):
        """해당 날짜가 속하는 주의 목요일 반환."""
        # weekday: 0=Mon … 3=Thu … 6=Sun
        days_since_thu = (d.weekday() - 3) % 7
        return d - timedelta(days=days_since_thu)

    weeks = {}  # {thu_date: [(date, version, body), ...]}
    for date, ver, body in entries:
        thu = _week_thursday(date)
        weeks.setdefault(thu, []).append((date, ver, body))

    # 최신 주 먼저
    sorted_weeks = sorted(weeks.items(), key=lambda x: x[0], reverse=True)

    # ── 렌더링 ──
    with st.expander("📋 패치노트", expanded=False):
        # 탭 라벨 생성: "3/12(목)~3/18(수)"
        tab_labels = []
        for thu, _ in sorted_weeks:
            wed = thu + timedelta(days=6)
            label = (f"{thu.month}/{thu.day}({_WEEKDAY_KR[thu.weekday()]})"
                     f"~{wed.month}/{wed.day}({_WEEKDAY_KR[wed.weekday()]})")
            tab_labels.append(label)

        tabs = st.tabs(tab_labels)
        for tab, (thu, week_entries) in zip(tabs, sorted_weeks):
            with tab:
                # 해당 주 내에서 최신 날짜 순
                week_entries.sort(key=lambda x: x[0], reverse=True)
                for date, ver, body in week_entries:
                    day_kr = _WEEKDAY_KR[date.weekday()]
                    st.markdown(
                        f"**{ver}** — {date.month}/{date.day}({day_kr})")
                    st.markdown(body)
                    st.divider()


def main():
    st.set_page_config(page_title="RC 보-기둥 구조 설계", layout="wide")

    # ==================================================================
    # 사이드바: 모드 선택 + 입력 조건 + 패치노트
    # ==================================================================
    with st.sidebar:
        st.header("🏗️ RC 구조 설계")
        design_mode = st.radio(
            "모드 선택",
            ["📐 분포하중 설계", "📄 구조계산서 검토"],
            horizontal=True,
            key="design_mode_radio",
        )
        st.divider()

        inputs = None
        review_inputs = None

        if design_mode == "📐 분포하중 설계":
            inputs = ui.render_input_section()
        else:
            review_inputs = ui.render_review_input_section()

        st.divider()
        _render_patch_notes()

    # ==================================================================
    # 메인 영역: 계산 + 결과
    # ==================================================================
    if design_mode == "📐 분포하중 설계":
        if inputs is not None:
            results = calculation_manager.perform_calculations(inputs)
            ui.render_output_section(results, inputs)
    else:
        if review_inputs is not None:
            # 디버그: 계산 입력값 확인
            with st.expander("🔍 검토 입력값 디버그", expanded=False):
                st.json(review_inputs)
            results = perform_review(review_inputs)
            # 디버그: 계산 결과값 확인
            with st.expander("🔍 검토 결과값 디버그", expanded=False):
                import json
                # numpy 호환을 위한 변환
                def _conv(o):
                    import numpy as _np
                    if isinstance(o, (_np.integer,)): return int(o)
                    if isinstance(o, (_np.floating,)): return float(o)
                    if isinstance(o, (_np.ndarray,)): return o.tolist()
                    return str(o)
                st.text(json.dumps(results, indent=2, default=_conv, ensure_ascii=False)[:5000])
            ui.render_review_output_section(results)
        else:
            st.info("📄 사이드바에서 부재력을 입력하고 '검토 실행' 버튼을 누르세요.")


if __name__ == "__main__":
    main()
