import re
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import ui
import calculation_manager

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
    st.title("🏗️ 1경간 양단 고정보 해석 및 RC 단면 설계")

    # ── 패치노트 (접기/펼치기) ──
    _render_patch_notes()

    # ──────────────────────────────────────────────────────────────────────
    # 최상위 탭: RC 설계 / 구조계산서 분석
    # ──────────────────────────────────────────────────────────────────────
    tab_design, tab_pdf = st.tabs(["🔨 RC 단면 설계", "📄 구조계산서 AI 분석"])

    # ── 탭 1: RC 단면 설계 (기존 기능) ───────────────────────────────────
    with tab_design:

        # ==================================================================
        # 1. 입력 조건
        # ==================================================================
        inputs = ui.render_input_section()

        # ==================================================================
        # 2. 계산 실행
        # ==================================================================
        results = calculation_manager.perform_calculations(inputs)

        # ==================================================================
        # 3. 결과 출력
        # ==================================================================
        ui.render_output_section(results, inputs)

    # ── 탭 2: 구조계산서 AI 분석 ──────────────────────────────────────────
    with tab_pdf:
        try:
            from parsers import ui_pdf_viewer
            ui_pdf_viewer.render_pdf_analysis_tab()
        except ImportError as e:
            st.error(f"ui_pdf_viewer 모듈 로드 오류: {e}")


if __name__ == "__main__":
    main()
