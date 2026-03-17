"""
report_generator.py
───────────────────
구조계산서 형태의 HTML 보고서를 생성하는 모듈.
ui/output.py에서 호출되며, results와 inputs를 받아 HTML 문자열을 반환한다.
"""
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# CSS 스타일
# ─────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
  @page { size: A4; margin: 20mm; }
  * { box-sizing: border-box; }
  body {
    font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #222;
    max-width: 210mm;
    margin: 0 auto;
    padding: 20mm;
  }

  /* 표지 */
  .cover { text-align: center; page-break-after: always; padding-top: 80mm; }
  .cover h1 { font-size: 24pt; margin-bottom: 10mm; }
  .cover .subtitle { font-size: 14pt; color: #555; margin-bottom: 30mm; }
  .cover .meta { font-size: 11pt; color: #666; line-height: 2; }

  /* 목차 */
  .toc { page-break-after: always; }
  .toc h2 { border-bottom: 2px solid #333; padding-bottom: 3mm; }
  .toc ul { list-style: none; padding-left: 0; }
  .toc li { padding: 2mm 0; border-bottom: 1px dotted #ccc; }
  .toc li span.page { float: right; color: #888; }

  /* 섹션 헤더 */
  h2 { font-size: 14pt; border-left: 4px solid #2196F3; padding-left: 8px;
       margin-top: 12mm; margin-bottom: 4mm; page-break-after: avoid; }
  h3 { font-size: 12pt; color: #333; margin-top: 8mm; margin-bottom: 3mm; }
  h4 { font-size: 10.5pt; color: #555; margin-top: 5mm; }

  /* 테이블 */
  table { width: 100%; border-collapse: collapse; margin: 4mm 0; font-size: 9.5pt; }
  th, td { border: 1px solid #bbb; padding: 3px 6px; text-align: center; }
  th { background: #e3f2fd; font-weight: bold; }
  td.left { text-align: left; }
  td.right { text-align: right; }

  /* 수식 블록 */
  .formula { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px;
             padding: 6px 12px; margin: 3mm 0; font-family: 'Cambria Math', serif; }

  /* 판정 */
  .ok { color: #2e7d32; font-weight: bold; }
  .ng { color: #c62828; font-weight: bold; }

  /* 페이지 나누기 */
  .page-break { page-break-before: always; }

  /* 푸터 */
  .footer { text-align: center; font-size: 8pt; color: #999;
            border-top: 1px solid #ccc; padding-top: 3mm; margin-top: 10mm; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(val, fmt_str="{:.1f}"):
    """숫자 포맷팅. None이면 '-'."""
    if val is None:
        return "-"
    try:
        return fmt_str.format(float(val))
    except (ValueError, TypeError):
        return str(val)


def _judgment(ok: bool):
    """OK/NG HTML 태그."""
    if ok:
        return '<span class="ok">✔ OK</span>'
    return '<span class="ng">✘ NG</span>'


# ─────────────────────────────────────────────────────────────────────────────
# 표지
# ─────────────────────────────────────────────────────────────────────────────
def _section_cover(inputs):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    return f"""
    <div class="cover">
      <h1>RC 구조 설계 계산서</h1>
      <div class="subtitle">1경간 양단 고정보 — 보·기둥·슬래브 단면설계</div>
      <div class="meta">
        <p>설계 기준: KDS 41 20 00 (건축물 콘크리트구조 설계기준)</p>
        <p>하중 기준: KDS 41 10 15 (건축물 하중)</p>
        <p>작성일: {today}</p>
        <p>작성: RC_Design 자동설계 시스템</p>
      </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 목차
# ─────────────────────────────────────────────────────────────────────────────
def _section_toc():
    return """
    <div class="toc">
      <h2>목 차</h2>
      <ul>
        <li>1. 설계 조건 <span class="page"></span></li>
        <li>&emsp;1.1 기하 조건</li>
        <li>&emsp;1.2 재료 강도</li>
        <li>&emsp;1.3 하중 조건</li>
        <li>2. 하중 산정 및 부재력 <span class="page"></span></li>
        <li>&emsp;2.1 하중 조합</li>
        <li>&emsp;2.2 보 부재력</li>
        <li>&emsp;2.3 기둥 부재력</li>
        <li>3. 슬래브 설계 <span class="page"></span></li>
        <li>4. 보 설계 <span class="page"></span></li>
        <li>&emsp;4.1 X방향 보</li>
        <li>&emsp;4.2 Y방향 보</li>
        <li>5. 기둥 설계 <span class="page"></span></li>
        <li>6. 설계 결과 요약 <span class="page"></span></li>
      </ul>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 1. 설계 조건
# ─────────────────────────────────────────────────────────────────────────────
def _section_design_conditions(inputs, common):
    L_x = inputs.get('L_x', 0)
    L_y = inputs.get('L_y', 0)
    h_col = inputs.get('h_column', 0)
    fc_k = inputs.get('fc_k', 0)
    fy = inputs.get('fy', 0)
    DL = inputs.get('DL_area', 0)
    LL = inputs.get('LL_area', 0)

    return f"""
    <div class="page-break"></div>
    <h2>1. 설계 조건</h2>

    <h3>1.1 기하 조건</h3>
    <table>
      <tr><th>항목</th><th>기호</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">X방향 경간</td><td>L<sub>x</sub></td><td>{L_x}</td><td>mm</td></tr>
      <tr><td class="left">Y방향 경간</td><td>L<sub>y</sub></td><td>{L_y}</td><td>mm</td></tr>
      <tr><td class="left">기둥 높이</td><td>H<sub>col</sub></td><td>{h_col}</td><td>mm</td></tr>
    </table>

    <h3>1.2 재료 강도</h3>
    <table>
      <tr><th>항목</th><th>기호</th><th>값</th><th>단위</th><th>비고</th></tr>
      <tr><td class="left">콘크리트 설계기준강도</td><td>f<sub>ck</sub></td>
          <td>{fc_k:.0f}</td><td>MPa</td><td>KDS 41 20 10</td></tr>
      <tr><td class="left">철근 항복강도</td><td>f<sub>y</sub></td>
          <td>{fy:.0f}</td><td>MPa</td><td>KDS 41 20 10</td></tr>
      <tr><td class="left">탄성계수</td><td>E<sub>c</sub></td>
          <td>{_fmt(common.get('Ec'), '{:.0f}')}</td><td>MPa</td><td>8500·(f<sub>ck</sub>+4)<sup>1/3</sup></td></tr>
    </table>

    <h3>1.3 하중 조건</h3>
    <table>
      <tr><th>항목</th><th>기호</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">추가 고정하중</td><td>DL<sub>area</sub></td><td>{DL:.2f}</td><td>kN/m²</td></tr>
      <tr><td class="left">활하중</td><td>LL<sub>area</sub></td><td>{LL:.2f}</td><td>kN/m²</td></tr>
      <tr><td class="left">슬래브 두께</td><td>t<sub>slab</sub></td><td>{common.get('t_slab', 0):.0f}</td><td>mm</td></tr>
    </table>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 2. 하중 산정 및 부재력
# ─────────────────────────────────────────────────────────────────────────────
def _section_loads(results, inputs):
    beam_x = results['beam_x']
    beam_y = results['beam_y']

    def _beam_forces_row(label, beam):
        dp = beam['design_params']
        mf = beam.get('member_forces', {})
        return f"""
        <tr>
          <td class="left">{label}</td>
          <td>{_fmt(dp.get('w_u'), '{:.2f}')}</td>
          <td>{_fmt(mf.get('M_neg'), '{:.2f}')}</td>
          <td>{_fmt(mf.get('M_pos'), '{:.2f}')}</td>
          <td>{_fmt(mf.get('V_max'), '{:.2f}')}</td>
        </tr>"""

    return f"""
    <h2>2. 하중 산정 및 부재력</h2>

    <h3>2.1 하중 조합 (KDS 41 10 15)</h3>
    <div class="formula">
      w<sub>u</sub> = 1.2·D + 1.6·L
    </div>

    <h3>2.2 보 부재력 (양단 고정보)</h3>
    <div class="formula">
      M<sub>neg</sub> = w<sub>u</sub>·L²/12 ,&emsp;
      M<sub>pos</sub> = w<sub>u</sub>·L²/24 ,&emsp;
      V<sub>max</sub> = w<sub>u</sub>·L/2
    </div>
    <table>
      <tr><th>부재</th><th>w<sub>u</sub> (kN/m)</th>
          <th>M<sub>neg</sub> (kN·m)</th><th>M<sub>pos</sub> (kN·m)</th>
          <th>V<sub>max</sub> (kN)</th></tr>
      {_beam_forces_row('X방향 보', beam_x)}
      {_beam_forces_row('Y방향 보', beam_y)}
    </table>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 3. 슬래브 설계
# ─────────────────────────────────────────────────────────────────────────────
def _section_slab(results):
    slab = results.get('slab', {})
    dp = slab.get('design_params', {})
    defl = slab.get('deflection', {})

    return f"""
    <div class="page-break"></div>
    <h2>3. 슬래브 설계</h2>

    <h3>3.1 설계 조건</h3>
    <table>
      <tr><th>항목</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">슬래브 두께 (t)</td><td>{_fmt(dp.get('t_slab'))}</td><td>mm</td></tr>
      <tr><td class="left">유효깊이 (d)</td><td>{_fmt(dp.get('d'))}</td><td>mm</td></tr>
      <tr><td class="left">계수하중 (w<sub>u</sub>)</td><td>{_fmt(dp.get('w_u'), '{:.2f}')}</td><td>kN/m</td></tr>
    </table>

    <h3>3.2 휨 설계</h3>
    <p><i>— 상세 내용은 추후 추가 예정 —</i></p>

    <h3>3.3 전단 검토</h3>
    <p><i>— 상세 내용은 추후 추가 예정 —</i></p>

    <h3>3.4 처짐 검토</h3>
    <table>
      <tr><th>항목</th><th>값</th><th>판정</th></tr>
      <tr><td class="left">즉시 처짐 δ<sub>i</sub></td>
          <td>{_fmt(defl.get('delta_i'), '{:.2f}')} mm</td><td>—</td></tr>
      <tr><td class="left">장기 처짐 δ<sub>total</sub></td>
          <td>{_fmt(defl.get('delta_total'), '{:.2f}')} mm</td>
          <td>{_judgment(defl.get('ok', False))}</td></tr>
      <tr><td class="left">허용 처짐 δ<sub>allow</sub></td>
          <td>{_fmt(defl.get('delta_allow'), '{:.2f}')} mm</td><td>L/480</td></tr>
    </table>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 4. 보 설계
# ─────────────────────────────────────────────────────────────────────────────
def _section_beam(beam, direction_label):
    dp = beam['design_params']
    defl = beam.get('deflection', {})
    mf = beam.get('member_forces', {})
    rb_top_str = beam.get('rebar_string_top', '-')
    rb_bot_str = beam.get('rebar_string_bot', '-')

    return f"""
    <h3>4.{'1' if 'X' in direction_label else '2'} {direction_label}</h3>

    <h4>단면 제원</h4>
    <table>
      <tr><th>항목</th><th>기호</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">보 춤</td><td>h</td><td>{_fmt(dp.get('h_beam'))}</td><td>mm</td></tr>
      <tr><td class="left">보 폭</td><td>b</td><td>{_fmt(dp.get('b_beam'))}</td><td>mm</td></tr>
    </table>

    <h4>휨 설계 (KDS 41 20 20)</h4>
    <table>
      <tr><th>위치</th><th>M<sub>u</sub> (kN·m)</th><th>A<sub>s,req</sub> (mm²)</th>
          <th>배근</th><th>A<sub>s,prov</sub> (mm²)</th></tr>
      <tr><td>지점부 (상부근)</td>
          <td>{_fmt(mf.get('M_neg'), '{:.2f}')}</td>
          <td>{_fmt(beam.get('As_top'), '{:.1f}')}</td>
          <td>{rb_top_str}</td>
          <td>{_fmt(beam.get('As_provided_top'), '{:.1f}')}</td></tr>
      <tr><td>중앙부 (하부근)</td>
          <td>{_fmt(mf.get('M_pos'), '{:.2f}')}</td>
          <td>{_fmt(beam.get('As_bot'), '{:.1f}')}</td>
          <td>{rb_bot_str}</td>
          <td>{_fmt(beam.get('As_provided_bot'), '{:.1f}')}</td></tr>
    </table>

    <h4>전단 설계 (KDS 41 20 22)</h4>
    <p><i>— 상세 내용은 추후 추가 예정 —</i></p>

    <h4>처짐 검토 (KDS 41 20 30)</h4>
    <table>
      <tr><th>항목</th><th>값</th><th>판정</th></tr>
      <tr><td class="left">장기 처짐 δ<sub>total</sub></td>
          <td>{_fmt(defl.get('delta_total'), '{:.2f}')} mm</td>
          <td>{_judgment(defl.get('ok', False))}</td></tr>
      <tr><td class="left">허용 처짐</td>
          <td>{_fmt(defl.get('delta_allow'), '{:.2f}')} mm</td>
          <td>L/480</td></tr>
    </table>
    """


def _section_beams(results):
    html = '<div class="page-break"></div>\n<h2>4. 보 설계</h2>\n'
    html += _section_beam(results['beam_x'], 'X방향 보')
    html += _section_beam(results['beam_y'], 'Y방향 보')
    return html


# ─────────────────────────────────────────────────────────────────────────────
# 5. 기둥 설계
# ─────────────────────────────────────────────────────────────────────────────
def _section_column(results):
    columns = results.get('columns', [results.get('column', {})])
    col = columns[0]
    dims = col.get('dimensions', {})
    am = col.get('axial_moment', {})
    slend = col.get('slenderness', {})
    pm = col.get('rebar_design', {})

    return f"""
    <div class="page-break"></div>
    <h2>5. 기둥 설계</h2>

    <h3>5.1 단면 제원</h3>
    <table>
      <tr><th>항목</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">기둥 단면 (정방형)</td><td>{_fmt(dims.get('c_column'))} × {_fmt(dims.get('c_column'))}</td><td>mm</td></tr>
      <tr><td class="left">기둥 높이</td><td>{_fmt(dims.get('h_column'))}</td><td>mm</td></tr>
    </table>

    <h3>5.2 설계 하중</h3>
    <table>
      <tr><th>항목</th><th>기호</th><th>값</th><th>단위</th></tr>
      <tr><td class="left">축력</td><td>P<sub>u</sub></td><td>{_fmt(am.get('Pu'), '{:.1f}')}</td><td>kN</td></tr>
      <tr><td class="left">모멘트 (X)</td><td>M<sub>ux</sub></td><td>{_fmt(am.get('Mux'), '{:.1f}')}</td><td>kN·m</td></tr>
      <tr><td class="left">모멘트 (Y)</td><td>M<sub>uy</sub></td><td>{_fmt(am.get('Muy'), '{:.1f}')}</td><td>kN·m</td></tr>
    </table>

    <h3>5.3 세장비 검토 (KDS 41 20 40)</h3>
    <table>
      <tr><th>항목</th><th>값</th><th>판정</th></tr>
      <tr><td class="left">세장비 λ</td>
          <td>{_fmt(slend.get('lambda_ratio'), '{:.1f}')}</td>
          <td>{slend.get('category', '-')}</td></tr>
      <tr><td class="left">δ<sub>ns</sub></td>
          <td>{_fmt(slend.get('delta_ns'), '{:.3f}')}</td>
          <td>—</td></tr>
    </table>

    <h3>5.4 P-M 설계 (KDS 41 20 20)</h3>
    <table>
      <tr><th>항목</th><th>값</th></tr>
      <tr><td class="left">배근</td><td>{pm.get('rebar_string_col', '-')}</td></tr>
      <tr><td class="left">철근비 ρ</td><td>{_fmt(pm.get('rho'), '{:.4f}')}</td></tr>
      <tr><td class="left">P-M 안전성</td><td>{_judgment(pm.get('pm_safe', False))}</td></tr>
    </table>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 6. 설계 결과 요약
# ─────────────────────────────────────────────────────────────────────────────
def _section_summary(results):
    beam_x = results['beam_x']
    beam_y = results['beam_y']
    columns = results.get('columns', [results.get('column', {})])
    col = columns[0]
    slab = results.get('slab', {})

    def _beam_summary_row(label, beam):
        dp = beam['design_params']
        defl = beam.get('deflection', {})
        return f"""
        <tr>
          <td class="left">{label}</td>
          <td>{_fmt(dp.get('h_beam'))} × {_fmt(dp.get('b_beam'))}</td>
          <td>{beam.get('rebar_string_top', '-')}</td>
          <td>{beam.get('rebar_string_bot', '-')}</td>
          <td>{_judgment(defl.get('ok', False))}</td>
        </tr>"""

    col_dims = col.get('dimensions', {})
    slab_dp = slab.get('design_params', {})
    slab_defl = slab.get('deflection', {})

    return f"""
    <div class="page-break"></div>
    <h2>6. 설계 결과 요약</h2>

    <h3>보 설계 요약</h3>
    <table>
      <tr><th>부재</th><th>단면 h×b (mm)</th><th>상부근</th><th>하부근</th><th>처짐</th></tr>
      {_beam_summary_row('X방향 보', beam_x)}
      {_beam_summary_row('Y방향 보', beam_y)}
    </table>

    <h3>기둥 설계 요약</h3>
    <table>
      <tr><th>부재</th><th>단면 (mm)</th><th>배근</th><th>P-M 판정</th></tr>
      <tr>
        <td class="left">기둥</td>
        <td>{_fmt(col_dims.get('c_column'))} × {_fmt(col_dims.get('c_column'))}</td>
        <td>{col.get('rebar_design', {}).get('rebar_string_col', '-')}</td>
        <td>{_judgment(col.get('rebar_design', {}).get('pm_safe', False))}</td>
      </tr>
    </table>

    <h3>슬래브 설계 요약</h3>
    <table>
      <tr><th>항목</th><th>값</th><th>판정</th></tr>
      <tr><td class="left">두께</td><td>{_fmt(slab_dp.get('t_slab'))} mm</td><td>—</td></tr>
      <tr><td class="left">처짐</td>
          <td>{_fmt(slab_defl.get('delta_total'), '{:.2f}')} mm</td>
          <td>{_judgment(slab_defl.get('ok', False))}</td></tr>
    </table>

    <div class="footer">
      <p>RC_Design 자동설계 시스템 — KDS 41 20 00 기반</p>
      <p>이 보고서는 자동 생성되었으며, 설계자의 검토가 필요합니다.</p>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 메인 생성 함수
# ─────────────────────────────────────────────────────────────────────────────
def generate_html_report(results, inputs):
    """
    설계 결과를 HTML 구조계산서로 생성.

    Parameters
    ----------
    results : dict  — calculation_manager.perform_calculations() 반환값
    inputs  : dict  — ui/input.py render_input_section() 반환값

    Returns
    -------
    str : 완성된 HTML 문자열
    """
    common = results.get('common', {})

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="UTF-8">',
        "<title>RC 구조 설계 계산서</title>",
        _CSS,
        "</head>",
        "<body>",
        _section_cover(inputs),
        _section_toc(),
        _section_design_conditions(inputs, common),
        _section_loads(results, inputs),
        _section_slab(results),
        _section_beams(results),
        _section_column(results),
        _section_summary(results),
        "</body>",
        "</html>",
    ]

    return "\n".join(html_parts)
