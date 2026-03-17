import plotly.graph_objects as go
import numpy as np

def _draw_rebar_row(fig, b_beam, h_beam, y_center, rebar_string, rebar_steps, layer, color="Red", border_color="DarkRed"):
    """보 단면도에서 한 줄의 철근을 그리는 내부 함수"""
    cover = rebar_steps['cover']
    stirrup_diameter = rebar_steps['rebar_specs']['D10']['diameter']

    if layer == 1:
        rebar_type = rebar_string.split('-')[1]
        n = rebar_steps['n_final_' + rebar_type]
        rebar_diameter = rebar_steps['rebar_specs'][rebar_type]['diameter']
        available_width = b_beam - 2 * (cover + stirrup_diameter + rebar_diameter / 2)
        spacing = available_width / (n - 1) if n > 1 else 0
        for i in range(n):
            x_pos = (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing if n > 1 else b_beam / 2
            fig.add_shape(type="circle", x0=x_pos - rebar_diameter/2, y0=y_center - rebar_diameter/2, x1=x_pos + rebar_diameter/2, y1=y_center + rebar_diameter/2, fillcolor=color, line=dict(color=border_color, width=1))
    else:
        rebar_type = "D25"
        n = rebar_steps['fallback_n']
        rebar_diameter = rebar_steps['rebar_specs'][rebar_type]['diameter']
        available_width = b_beam - 2 * (cover + stirrup_diameter + rebar_diameter / 2)
        n1 = n // 2 + (n % 2)
        n2 = n - n1
        spacing1 = available_width / (n1 - 1) if n1 > 1 else 0
        for i in range(n1):
            x_pos = (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing1 if n1 > 1 else b_beam / 2
            fig.add_shape(type="circle", x0=x_pos - rebar_diameter/2, y0=y_center - rebar_diameter/2, x1=x_pos + rebar_diameter/2, y1=y_center + rebar_diameter/2, fillcolor=color, line=dict(color=border_color, width=1))
        if n2 > 0:
            spacing2 = available_width / (n2 - 1) if n2 > 1 else 0
            # [수정] h_beam 기준으로 상/하 방향 판별: y < h/2이면 하부근(위로), y > h/2이면 상부근(아래로)
            y_offset = y_center + (25 + rebar_diameter) if y_center < h_beam / 2 else y_center - (25 + rebar_diameter)
            for i in range(n2):
                x_pos = (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing2 if n2 > 1 else b_beam / 2
                fig.add_shape(type="circle", x0=x_pos - rebar_diameter/2, y0=y_offset - rebar_diameter/2, x1=x_pos + rebar_diameter/2, y1=y_offset + rebar_diameter/2, fillcolor=color, line=dict(color=border_color, width=1))

def plot_rebar_section(b_beam, h_beam, rebar_string_top, rebar_steps_top, layer_top,
                       rebar_string_bot, rebar_steps_bot, layer_bot, beam_type, s_final,
                       section_location='combined',
                       rebar_string_min=None, rebar_steps_min=None, layer_min=1):
    """보 단면도를 실제 구조 도면 스타일로 렌더링합니다.

    Args:
        section_location : 'support' (지점부), 'midspan' (중앙부), 'combined' (전체)
        rebar_string_min : 통일직경 2가닥 최소 배근 문자열 (e.g. "2-D25")
        rebar_steps_min  : 최소 배근 rebar_steps dict
        layer_min        : 최소 배근 층수 (항상 1)
    """
    fig = go.Figure()
    cover     = rebar_steps_bot['cover']
    stirrup_d = rebar_steps_bot['rebar_specs']['D10']['diameter']

    # 색상 설정 (모든 철근 동일 색상)
    color_bar, border_bar = 'Red', 'DarkRed'

    if section_location == 'support':
        title = f'{beam_type}보 지점부 단면 (M⁻)'
    elif section_location == 'midspan':
        title = f'{beam_type}보 중앙부 단면 (M⁺)'
    else:
        title = f'{beam_type}방향 보 단면'

    # --- 위치별 철근 선택 -----------------------------------------------
    # support  : 상부 = M_neg 주근 / 하부 = 최소배근(통일직경 2가닥)
    # midspan  : 상부 = 최소배근(통일직경 2가닥) / 하부 = M_pos 주근
    # combined : 기존 동작 유지 (상부=M_neg, 하부=M_pos 모두 표시)
    if section_location == 'support' and rebar_string_min is not None:
        _str_bot,  _steps_bot,  _lyr_bot  = rebar_string_min, rebar_steps_min, layer_min
        _str_top,  _steps_top,  _lyr_top  = rebar_string_top, rebar_steps_top, layer_top
    elif section_location == 'midspan' and rebar_string_min is not None:
        _str_bot,  _steps_bot,  _lyr_bot  = rebar_string_bot, rebar_steps_bot, layer_bot
        _str_top,  _steps_top,  _lyr_top  = rebar_string_min, rebar_steps_min, layer_min
    else:
        _str_bot,  _steps_bot,  _lyr_bot  = rebar_string_bot, rebar_steps_bot, layer_bot
        _str_top,  _steps_top,  _lyr_top  = rebar_string_top, rebar_steps_top, layer_top

    # --- 1. 콘크리트 단면 (회색 배경 + 두꺼운 외곽선) ---
    fig.add_shape(type="rect", x0=0, y0=0, x1=b_beam, y1=h_beam,
                  line=dict(color="#333333", width=3), fillcolor="#E0E0E0", opacity=0.8)

    # --- 2. 늑근 (면 채우기 - 기둥 단면과 동일 스타일) ---
    fig.add_shape(type="rect", x0=cover, y0=cover, x1=b_beam-cover, y1=cover+stirrup_d, fillcolor="DarkGreen", line=dict(width=0))
    fig.add_shape(type="rect", x0=cover, y0=h_beam-cover-stirrup_d, x1=b_beam-cover, y1=h_beam-cover, fillcolor="DarkGreen", line=dict(width=0))
    fig.add_shape(type="rect", x0=cover, y0=cover, x1=cover+stirrup_d, y1=h_beam-cover, fillcolor="DarkGreen", line=dict(width=0))
    fig.add_shape(type="rect", x0=b_beam-cover-stirrup_d, y0=cover, x1=b_beam-cover, y1=h_beam-cover, fillcolor="DarkGreen", line=dict(width=0))

    # --- 3. 하부근 ---
    rebar_type_bot     = _str_bot.split('-')[1] if _lyr_bot == 1 else "D25"
    rebar_diameter_bot = _steps_bot['rebar_specs'][rebar_type_bot]['diameter']
    y_bot = cover + stirrup_d + rebar_diameter_bot / 2
    _draw_rebar_row(fig, b_beam, h_beam, y_bot, _str_bot, _steps_bot, _lyr_bot, color=color_bar, border_color=border_bar)

    # --- 4. 상부근 ---
    rebar_type_top     = _str_top.split('-')[1] if _lyr_top == 1 else "D25"
    rebar_diameter_top = _steps_top['rebar_specs'][rebar_type_top]['diameter']
    y_top = h_beam - cover - stirrup_d - rebar_diameter_top / 2
    _draw_rebar_row(fig, b_beam, h_beam, y_top, _str_top, _steps_top, _lyr_top, color=color_bar, border_color=border_bar)

    # --- 5. 치수선 (Engineering Style) ---
    # 폭(b) 치수선 — 하단
    dim_y = -30
    tick_len = 8
    fig.add_shape(type="line", x0=0, y0=dim_y, x1=b_beam, y1=dim_y, line=dict(color="black", width=1.5))
    fig.add_shape(type="line", x0=0, y0=dim_y-tick_len, x1=0, y1=dim_y+tick_len, line=dict(color="black", width=1.5))
    fig.add_shape(type="line", x0=b_beam, y0=dim_y-tick_len, x1=b_beam, y1=dim_y+tick_len, line=dict(color="black", width=1.5))
    fig.add_annotation(x=b_beam/2, y=dim_y-18, text=f"b = {b_beam:.0f}", showarrow=False,
                       font=dict(size=12, color="black"))

    # 춤(h) 치수선 — 좌측
    dim_x = -30
    fig.add_shape(type="line", x0=dim_x, y0=0, x1=dim_x, y1=h_beam, line=dict(color="black", width=1.5))
    fig.add_shape(type="line", x0=dim_x-tick_len, y0=0, x1=dim_x+tick_len, y1=0, line=dict(color="black", width=1.5))
    fig.add_shape(type="line", x0=dim_x-tick_len, y0=h_beam, x1=dim_x+tick_len, y1=h_beam, line=dict(color="black", width=1.5))
    fig.add_annotation(x=dim_x-20, y=h_beam/2, text=f"h = {h_beam:.0f}", showarrow=False, textangle=-90,
                       font=dict(size=12, color="black"))

    # --- 6. 지시선 (Annotations) ---
    n_bot_info = _steps_bot[f'n_final_{rebar_type_bot}'] if _lyr_bot == 1 else _steps_bot['fallback_n']
    n_top_info = _steps_top[f'n_final_{rebar_type_top}'] if _lyr_top == 1 else _steps_top['fallback_n']

    # 하부근 레이블
    bot_label = f"{n_bot_info}-{rebar_type_bot}"
    if   section_location == 'midspan': bot_label += " (주근)"
    elif section_location == 'support': bot_label += " (최소)"
    fig.add_annotation(x=b_beam + 10, y=y_bot, text=bot_label,
                       showarrow=True, arrowhead=2, ax=60, ay=0,
                       font=dict(size=11, color=border_bar))

    # 상부근 레이블
    top_label = f"{n_top_info}-{rebar_type_top}"
    if   section_location == 'support':  top_label += " (주근)"
    elif section_location == 'midspan':  top_label += " (최소)"
    fig.add_annotation(x=b_beam + 10, y=y_top, text=top_label,
                       showarrow=True, arrowhead=2, ax=60, ay=0,
                       font=dict(size=11, color=border_bar))

    # 늑근 레이블
    fig.add_annotation(x=cover, y=h_beam-cover, text=f"D10@{s_final:.0f}",
                       showarrow=True, arrowhead=2, ax=-55, ay=-25,
                       font=dict(size=10, color="#2E7D32"))

    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        xaxis=dict(visible=False, range=[-80, b_beam + 160]),
        yaxis=dict(visible=False, range=[-70, h_beam + 40], scaleanchor="x"),
        width=420, height=420,
        plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

def plot_beam_side_view(L_beam, h_beam, rebar_string_top, rebar_steps_top, layer_top,
                        rebar_string_bot, rebar_steps_bot, layer_bot, s_final, beam_type,
                        rebar_string_min=None, rebar_steps_min=None, layer_min=1,
                        dev_top=None, dev_bot=None, stirrup_zones=None):
    """보 측면도.

    rebar_string_min 전달 시 지점부/중앙부를 구간별 색상으로 구분:
      상부 — 지점부 (0~L/4, 3L/4~L): OrangeRed  (M⁻ 주근)
              중앙부 (L/4~3L/4)      : #FFCCAA   (최소근)
      하부 — 중앙부 (L/4~3L/4)      : Red        (M⁺ 주근)
              지점부 (0~L/4, 3L/4~L): #FFAAAA   (최소근)

    dev_top/dev_bot: 정착길이 dict (ld, ls_B 등) — 이음 구간 표시용
    stirrup_zones: 늑근 구간 분할 리스트 — 구간별 간격 표시용
    """
    fig = go.Figure()
    # 1. 콘크리트
    fig.add_shape(type="rect", x0=0, y0=0, x1=L_beam, y1=h_beam,
                  line=dict(color="#333333", width=3), fillcolor="#E0E0E0", opacity=0.8)

    cover = rebar_steps_bot['cover']
    stirrup_diameter = rebar_steps_bot['rebar_specs']['D10']['diameter']

    # 지점부 구간 길이 (경간의 1/4)
    L_zone = L_beam / 4

    # 2. 하부근 (M⁺ 저항)
    rebar_type_bot = rebar_string_bot.split('-')[1] if layer_bot == 1 else "D25"
    rebar_diameter_bot = rebar_steps_bot['rebar_specs'][rebar_type_bot]['diameter']
    y_bot = cover + stirrup_diameter + rebar_diameter_bot / 2

    if rebar_string_min is not None:
        # 중앙부(L/4~3L/4): M_pos 주근 — Red
        fig.add_shape(type="rect", x0=L_zone, y0=y_bot - rebar_diameter_bot/2,
                      x1=L_beam - L_zone, y1=y_bot + rebar_diameter_bot/2,
                      fillcolor="Red", line=dict(width=0))
        # 지점부(0~L/4, 3L/4~L): 최소근 — 연한 빨강
        for x0, x1 in [(0, L_zone), (L_beam - L_zone, L_beam)]:
            fig.add_shape(type="rect", x0=x0, y0=y_bot - rebar_diameter_bot/2,
                          x1=x1, y1=y_bot + rebar_diameter_bot/2,
                          fillcolor="#FFAAAA", line=dict(width=0))
    else:
        fig.add_shape(type="rect", x0=0, y0=y_bot - rebar_diameter_bot/2,
                      x1=L_beam, y1=y_bot + rebar_diameter_bot/2,
                      fillcolor="Red", line=dict(width=0))
        if layer_bot == 2:
            y_bot2 = y_bot + rebar_diameter_bot + 25
            fig.add_shape(type="rect", x0=0, y0=y_bot2 - rebar_diameter_bot/2,
                          x1=L_beam, y1=y_bot2 + rebar_diameter_bot/2,
                          fillcolor="Red", line=dict(width=0))

    # 3. 상부근 (M⁻ 저항)
    rebar_type_top = rebar_string_top.split('-')[1] if layer_top == 1 else "D25"
    rebar_diameter_top = rebar_steps_top['rebar_specs'][rebar_type_top]['diameter']
    y_top = h_beam - cover - stirrup_diameter - rebar_diameter_top / 2

    if rebar_string_min is not None:
        # 지점부(0~L/4, 3L/4~L): M_neg 주근 — OrangeRed
        for x0, x1 in [(0, L_zone), (L_beam - L_zone, L_beam)]:
            fig.add_shape(type="rect", x0=x0, y0=y_top - rebar_diameter_top/2,
                          x1=x1, y1=y_top + rebar_diameter_top/2,
                          fillcolor="OrangeRed", line=dict(width=0))
        # 중앙부(L/4~3L/4): 최소근 — 연한 주황
        fig.add_shape(type="rect", x0=L_zone, y0=y_top - rebar_diameter_top/2,
                      x1=L_beam - L_zone, y1=y_top + rebar_diameter_top/2,
                      fillcolor="#FFCCAA", line=dict(width=0))
    else:
        fig.add_shape(type="rect", x0=0, y0=y_top - rebar_diameter_top/2,
                      x1=L_beam, y1=y_top + rebar_diameter_top/2,
                      fillcolor="OrangeRed", line=dict(width=0))
        if layer_top == 2:
            y_top2 = y_top - rebar_diameter_top - 25
            fig.add_shape(type="rect", x0=0, y0=y_top2 - rebar_diameter_top/2,
                          x1=L_beam, y1=y_top2 + rebar_diameter_top/2,
                          fillcolor="OrangeRed", line=dict(width=0))

    # 4. 늑근 — stirrup_zones가 있으면 구간별 간격, 없으면 s_final 균일
    if stirrup_zones and len(stirrup_zones) > 1:
        for _sz in stirrup_zones:
            _sx0 = _sz['x_start'] * 1000  # m → mm
            _sx1 = _sz['x_end'] * 1000
            _s_z = _sz['s']
            x_pos = _sx0 + 50
            while x_pos < _sx1 - 10:
                if 50 <= x_pos <= L_beam - 50:
                    fig.add_shape(type="rect", x0=x_pos-stirrup_diameter/2, y0=cover,
                                  x1=x_pos+stirrup_diameter/2, y1=h_beam-cover,
                                  fillcolor="DarkGreen", line=dict(width=0))
                x_pos += _s_z
    else:
        num_stirrups = int(L_beam / s_final)
        for i in range(num_stirrups + 1):
            x_pos = 50 + i * s_final
            if x_pos > L_beam - 50: break
            fig.add_shape(type="rect", x0=x_pos-stirrup_diameter/2, y0=cover,
                          x1=x_pos+stirrup_diameter/2, y1=h_beam-cover,
                          fillcolor="DarkGreen", line=dict(width=0))

    # 5. 구간 경계선 (rebar_string_min 있을 때만)
    if rebar_string_min is not None:
        for x_div in [L_zone, L_beam - L_zone]:
            fig.add_shape(type="line", x0=x_div, y0=0, x1=x_div, y1=h_beam,
                          line=dict(color="#888888", width=1, dash="dot"))

    # 6. 이음 구간 표시 (정착길이/겹이음)
    if dev_top is not None and dev_top.get('ls_B'):
        _ls_top = dev_top['ls_B']
        # 상부근 이음: 지점부 끝에서 중앙부 방향으로 ls_B 구간
        for _x_sp in [L_zone, L_beam - L_zone]:
            _x0_sp = _x_sp - _ls_top / 2
            _x1_sp = _x_sp + _ls_top / 2
            fig.add_shape(type="rect", x0=_x0_sp, y0=y_top - rebar_diameter_top,
                          x1=_x1_sp, y1=y_top + rebar_diameter_top,
                          fillcolor="rgba(128,0,255,0.2)", line=dict(color="purple", width=1, dash="dot"))
        fig.add_annotation(x=L_zone, y=y_top + rebar_diameter_top + 15,
                           text=f"이음 {_ls_top:.0f}", showarrow=False,
                           font=dict(size=8, color="purple"))

    if dev_bot is not None and dev_bot.get('ls_B'):
        _ls_bot = dev_bot['ls_B']
        for _x_sp in [L_zone, L_beam - L_zone]:
            _x0_sp = _x_sp - _ls_bot / 2
            _x1_sp = _x_sp + _ls_bot / 2
            fig.add_shape(type="rect", x0=_x0_sp, y0=y_bot - rebar_diameter_bot,
                          x1=_x1_sp, y1=y_bot + rebar_diameter_bot,
                          fillcolor="rgba(255,0,128,0.2)", line=dict(color="deeppink", width=1, dash="dot"))
        fig.add_annotation(x=L_zone, y=y_bot - rebar_diameter_bot - 15,
                           text=f"이음 {_ls_bot:.0f}", showarrow=False,
                           font=dict(size=8, color="deeppink"))

    # 7. 늑근 구간 표시 (stirrup_zones 전달 시)
    if stirrup_zones and len(stirrup_zones) > 1:
        _sz_y = h_beam + 30
        for _sz in stirrup_zones:
            _sx0 = _sz['x_start'] * 1000  # m → mm
            _sx1 = _sz['x_end'] * 1000
            fig.add_shape(type="line", x0=_sx0, y0=_sz_y, x1=_sx1, y1=_sz_y,
                          line=dict(color="green", width=2))
            fig.add_annotation(
                x=(_sx0 + _sx1) / 2, y=_sz_y + 20,
                text=f"D10@{_sz['s']:.0f}", showarrow=False,
                font=dict(size=7, color="green"))

    # 치수선
    _y_dim = -190 if not stirrup_zones else -190
    fig.add_annotation(x=L_beam/2, y=-190, text=f"L = {L_beam:.0f}", showarrow=False, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=0, y0=-150, x1=L_beam, y1=-150, line=dict(color="black", width=1))
    fig.add_annotation(x=-250, y=h_beam/2, text=f"h = {h_beam:.0f}", showarrow=False, textangle=-90, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=-200, y0=0, x1=-200, y1=h_beam, line=dict(color="black", width=1))

    _y_range_max = h_beam + 100 if not stirrup_zones else h_beam + 80 + len(stirrup_zones) * 20
    fig.update_layout(title=f'{beam_type}방향 보 측면', xaxis=dict(visible=False, range=[-400, L_beam+200]), yaxis=dict(visible=False, range=[-300, _y_range_max]), width=700, height=350)
    return fig

def plot_rebar_3d(L_beam, b_beam, h_beam, rebar_string, s_final, rebar_steps, beam_type):
    fig = go.Figure()

    # 1. 콘크리트 (투명)
    x_c = [0, L_beam, L_beam, 0, 0, L_beam, L_beam, 0]
    y_c = [0, 0, b_beam, b_beam, 0, 0, b_beam, b_beam]
    z_c = [0, 0, 0, 0, h_beam, h_beam, h_beam, h_beam]
    i_c = [7, 0, 0, 0, 4, 4, 2, 6, 2, 1, 1, 6]
    j_c = [3, 4, 1, 2, 5, 6, 1, 1, 0, 0, 5, 5]
    k_c = [0, 7, 2, 3, 6, 7, 4, 5, 7, 2, 6, 4]
    fig.add_trace(go.Mesh3d(x=x_c, y=y_c, z=z_c, i=i_c, j=j_c, k=k_c, color='LightBlue', opacity=0.2, name='콘크리트'))

    # 2. 주철근 (Cylinder Helper)
    def create_cylinder(x_s, x_e, y_c, z_c, r, color):
        theta = np.linspace(0, 2*np.pi, 12)
        x_cyl = np.array([x_s, x_e])
        y_cyl = y_c + r * np.cos(theta)
        z_cyl = z_c + r * np.sin(theta)
        pts = []
        for x_val in x_cyl:
            for j in range(12): pts.append([x_val, y_cyl[j], z_cyl[j]])
        pts = np.array(pts)
        i_idx, j_idx, k_idx = [], [], []
        for i in range(12):
            p1, p2 = i, (i+1)%12
            p3, p4 = 12+i, 12+(i+1)%12
            i_idx.extend([p1, p2])
            j_idx.extend([p2, p4])
            k_idx.extend([p3, p3])
        return go.Mesh3d(x=pts[:,0], y=pts[:,1], z=pts[:,2], i=i_idx, j=j_idx, k=k_idx, color=color, opacity=1.0)

    cover = rebar_steps['cover']
    stirrup_d = rebar_steps['rebar_specs']['D10']['diameter']
    layer = rebar_steps['layer']
    rebar_type = rebar_string.split('-')[1] if layer == 1 else "D25"
    rebar_d = rebar_steps['rebar_specs'][rebar_type]['diameter']
    n_total = rebar_steps[f'n_final_{rebar_type}'] if layer == 1 else rebar_steps['fallback_n']

    y_base = cover + stirrup_d + rebar_d/2
    z_base = y_base
    avail_w = b_beam - 2*y_base

    if layer == 1:
        sp = avail_w / (n_total - 1) if n_total > 1 else 0
        for i in range(n_total):
            y = y_base + i*sp if n_total > 1 else b_beam/2
            fig.add_trace(create_cylinder(0, L_beam, y, z_base, rebar_d/2, 'Red'))
    else:
        n1 = n_total // 2 + (n_total % 2)
        n2 = n_total - n1
        sp1 = avail_w / (n1 - 1) if n1 > 1 else 0
        for i in range(n1):
            y = y_base + i*sp1 if n1 > 1 else b_beam/2
            fig.add_trace(create_cylinder(0, L_beam, y, z_base, rebar_d/2, 'Red'))
        sp2 = avail_w / (n2 - 1) if n2 > 1 else 0
        for i in range(n2):
            y = y_base + i*sp2 if n2 > 1 else b_beam/2
            fig.add_trace(create_cylinder(0, L_beam, y, z_base + rebar_d + 25, rebar_d/2, 'Red'))

    # 3. 늑근 (Hollow Box)
    def add_box(x0, x1, y0, y1, z0, z1, vx, vy, vz, ii, jj, kk):
        off = len(vx)
        vx.extend([x0, x1, x1, x0, x0, x1, x1, x0])
        vy.extend([y0, y0, y1, y1, y0, y0, y1, y1])
        vz.extend([z0, z0, z0, z0, z1, z1, z1, z1])
        faces_i = [0, 0, 4, 4, 0, 0, 3, 3, 0, 0, 1, 1]
        faces_j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 2, 6]
        faces_k = [2, 3, 6, 7, 5, 4, 6, 7, 7, 4, 6, 5]
        ii.extend([off+v for v in faces_i])
        jj.extend([off+v for v in faces_j])
        kk.extend([off+v for v in faces_k])

    num_s = int(L_beam / s_final)
    for i in range(num_s + 1):
        x = 50 + i * s_final
        if x > L_beam - 50: break
        xf, xb = x - stirrup_d/2, x + stirrup_d/2
        y0, y1 = cover, b_beam - cover
        z0, z1 = cover, h_beam - cover
        y0i, y1i = y0 + stirrup_d, y1 - stirrup_d
        z0i, z1i = z0 + stirrup_d, z1 - stirrup_d

        vx, vy, vz, ii, jj, kk = [], [], [], [], [], []
        add_box(xf, xb, y0, y1, z0, z0i, vx, vy, vz, ii, jj, kk) # Bottom
        add_box(xf, xb, y0, y1, z1i, z1, vx, vy, vz, ii, jj, kk) # Top
        add_box(xf, xb, y0, y0i, z0i, z1i, vx, vy, vz, ii, jj, kk) # Left
        add_box(xf, xb, y1i, y1, z0i, z1i, vx, vy, vz, ii, jj, kk) # Right

        fig.add_trace(go.Mesh3d(x=vx, y=vy, z=vz, i=ii, j=jj, k=kk, color='DarkGreen', opacity=0.8))

    fig.update_layout(title=f'{beam_type}방향 3D 배근', scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), width=600, height=400)
    return fig

def plot_sfd_bmd(member_forces, beam_type):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=member_forces['x_steps'], y=member_forces['SFD'], mode='lines', name='SFD (kN)', line=dict(color='blue', width=2)))
    fig.add_trace(go.Scatter(x=member_forces['x_steps'], y=member_forces['BMD'], mode='lines', name='BMD (kN·m)', line=dict(color='red', width=2)))
    fig.update_layout(
        title=f'{beam_type}방향 보 SFD & BMD',
        xaxis_title='위치 (m)',
        yaxis_title='힘 (kN) / 모멘트 (kN·m)',
        height=400,
        hovermode='x unified'
    )
    return fig
