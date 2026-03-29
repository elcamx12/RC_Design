import plotly.graph_objects as go  # 3D용 유지
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
matplotlib.rcParams['font.family'] = ['Malgun Gothic', 'NanumGothic', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False

def _draw_rebar_row(ax, b_beam, h_beam, y_center, rebar_string, rebar_steps, layer,
                    color="#CC0000", border_color="#990000", x_offset=0):
    """보 단면도에서 한 줄의 철근을 그리는 내부 함수 (Matplotlib 버전)"""
    cover = rebar_steps['cover']
    stirrup_diameter = rebar_steps['rebar_specs']['D10']['diameter']

    if layer == 1:
        rebar_type = rebar_string.split('-')[1]
        n = rebar_steps['n_final_' + rebar_type]
        rebar_diameter = rebar_steps['rebar_specs'][rebar_type]['diameter']
        available_width = b_beam - 2 * (cover + stirrup_diameter + rebar_diameter / 2)
        spacing = available_width / (n - 1) if n > 1 else 0
        for i in range(n):
            x_pos = x_offset + (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing if n > 1 else x_offset + b_beam / 2
            ax.add_patch(mpatches.Circle((x_pos, y_center), rebar_diameter / 2,
                         facecolor=color, edgecolor=border_color, linewidth=1))
    else:
        rebar_type = "D25"
        n = rebar_steps['fallback_n']
        rebar_diameter = rebar_steps['rebar_specs'][rebar_type]['diameter']
        available_width = b_beam - 2 * (cover + stirrup_diameter + rebar_diameter / 2)
        n1 = n // 2 + (n % 2)
        n2 = n - n1
        spacing1 = available_width / (n1 - 1) if n1 > 1 else 0
        for i in range(n1):
            x_pos = x_offset + (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing1 if n1 > 1 else x_offset + b_beam / 2
            ax.add_patch(mpatches.Circle((x_pos, y_center), rebar_diameter / 2,
                         facecolor=color, edgecolor=border_color, linewidth=1))
        if n2 > 0:
            spacing2 = available_width / (n2 - 1) if n2 > 1 else 0
            y_offset = y_center + (25 + rebar_diameter) if y_center < h_beam / 2 else y_center - (25 + rebar_diameter)
            for i in range(n2):
                x_pos = x_offset + (cover + stirrup_diameter + rebar_diameter / 2) + i * spacing2 if n2 > 1 else x_offset + b_beam / 2
                ax.add_patch(mpatches.Circle((x_pos, y_offset), rebar_diameter / 2,
                             facecolor=color, edgecolor=border_color, linewidth=1))

def _draw_one_section(ax, x_off, b_beam, h_beam, rebar_str_top, rebar_str_bot,
                      s_final_str, cover=40.0, stirrup_d=9.53, title='[END-I]'):
    """단일 단면 1개를 ax 위에 그리는 공용 함수 (설계/검토 모드 모두 사용)."""
    import re as _re
    CLR_CONCRETE = '#D4F1F9'  # MIDAS 스타일 밝은 민트색
    CLR_OUTLINE  = '#2255CC'
    CLR_STIRRUP  = '#CC6600'
    CLR_REBAR    = '#CC0000'
    CLR_REBAR_BD = '#990000'
    CLR_DIM      = '#444444'

    _dia_map = {'D10': 9.53, 'D13': 12.7, 'D16': 15.9, 'D19': 19.1,
                'D22': 22.2, 'D25': 25.4, 'D29': 28.6, 'D32': 31.8, 'D35': 35.8}

    def _parse(rstr):
        m = _re.match(r'(\d+)-D(\d+)', str(rstr or '2-D13').strip())
        if not m: return 2, 'D13', 12.7
        n, dkey = int(m.group(1)), f'D{m.group(2)}'
        return n, dkey, _dia_map.get(dkey, 12.7)

    n_bot, rtype_b, rdia_b = _parse(rebar_str_bot)
    n_top, rtype_t, rdia_t = _parse(rebar_str_top)

    loc_b = cover + stirrup_d + rdia_b / 2
    loc_t = cover + stirrup_d + rdia_t / 2
    y_t = h_beam - loc_t

    # 1. 콘크리트
    ax.add_patch(mpatches.Rectangle((x_off, 0), b_beam, h_beam,
                 facecolor=CLR_CONCRETE, edgecolor=CLR_OUTLINE, linewidth=2.5))

    # 2. 늑근 (주근 시각적 외경 감싸는 사각형)
    _rv_b = rdia_b / 2.0 * 1.5  # 시각적 반지름 (1.5배)
    _rv_t = rdia_t / 2.0 * 1.5
    _stir_margin = 1.5  # 늑근과 철근 사이 여유
    _stir_x0 = x_off + loc_b - _rv_b - _stir_margin
    _stir_y0 = loc_b - _rv_b - _stir_margin
    _stir_x1 = x_off + b_beam - loc_b + _rv_b + _stir_margin
    _stir_y1 = h_beam - loc_t + _rv_t + _stir_margin
    _stir_w = _stir_x1 - _stir_x0
    _stir_h = _stir_y1 - _stir_y0
    ax.add_patch(mpatches.Rectangle((_stir_x0, _stir_y0), _stir_w, _stir_h,
                 facecolor='none', edgecolor=CLR_STIRRUP, linewidth=1.5))

    # 3. 철근 그리기 (원형) — 실제 직경의 1.5배, 늑근 안쪽 배치
    b_net = b_beam - 2 * loc_b
    for _n, _y, _rdia in [(n_bot, loc_b, rdia_b), (n_top, y_t, rdia_t)]:
        _r_visual = _rdia / 2.0 * 1.5  # 실제 반지름 × 1.5배
        if _n <= 0: continue
        # 철근 간격: 늑근 안쪽 기준
        _inner_w = b_net  # 양쪽 loc 사이 거리
        spacing = _inner_w / (_n - 1) if _n > 1 else 0
        for _i in range(_n):
            cx = x_off + loc_b + (_i * spacing if _n > 1 else _inner_w / 2)
            ax.add_patch(mpatches.Circle((cx, _y), _r_visual,
                         facecolor=CLR_REBAR, edgecolor=CLR_REBAR_BD, linewidth=0.8))

    # 4. 치수선
    _b_m = b_beam / 1000.0
    _h_m = h_beam / 1000.0
    _loc_b_m = loc_b / 1000.0
    _loc_t_m = loc_t / 1000.0
    _dot_r = 2.0
    _dy = -20

    # 하단 — 폭
    ax.plot([x_off, x_off + b_beam], [_dy, _dy], color=CLR_DIM, linewidth=1)
    for _xt in [x_off, x_off + b_beam]:
        ax.plot([_xt, _xt], [_dy - 5, _dy + 5], color=CLR_DIM, linewidth=1)
        ax.add_patch(mpatches.Circle((_xt, _dy), _dot_r, facecolor=CLR_DIM, edgecolor='none'))
    ax.text(x_off + b_beam / 2, _dy - 12, f"{_b_m:.2f}",
            fontsize=8, color=CLR_DIM, ha='center', va='top')

    # 좌측 — Loc + 춤
    _dx1 = x_off - 12
    _dx2 = x_off - 40
    _txt_gap = 14

    ax.plot([_dx1, _dx1], [h_beam, y_t], color=CLR_DIM, linewidth=0.8)
    for _yt in [h_beam, y_t]:
        ax.plot([_dx1 - 3, _dx1 + 3], [_yt, _yt], color=CLR_DIM, linewidth=0.8)
        ax.add_patch(mpatches.Circle((_dx1, _yt), _dot_r, facecolor=CLR_DIM, edgecolor='none'))
    ax.text(_dx1 - _txt_gap, (h_beam + y_t) / 2, f"{_loc_t_m:.3f}",
            fontsize=6, color=CLR_DIM, ha='center', va='center', rotation=90)

    ax.plot([_dx2, _dx2], [0, h_beam], color=CLR_DIM, linewidth=1)
    for _yt in [0, h_beam]:
        ax.plot([_dx2 - 5, _dx2 + 5], [_yt, _yt], color=CLR_DIM, linewidth=1)
        ax.add_patch(mpatches.Circle((_dx2, _yt), _dot_r, facecolor=CLR_DIM, edgecolor='none'))
    ax.text(_dx2 - _txt_gap, h_beam / 2, f"{_h_m:.2f}",
            fontsize=8, color=CLR_DIM, ha='center', va='center', rotation=90)

    ax.plot([_dx1, _dx1], [0, loc_b], color=CLR_DIM, linewidth=0.8)
    for _yt in [0, loc_b]:
        ax.plot([_dx1 - 3, _dx1 + 3], [_yt, _yt], color=CLR_DIM, linewidth=0.8)
        ax.add_patch(mpatches.Circle((_dx1, _yt), _dot_r, facecolor=CLR_DIM, edgecolor='none'))
    ax.text(_dx1 - _txt_gap, loc_b / 2, f"{_loc_b_m:.3f}",
            fontsize=6, color=CLR_DIM, ha='center', va='center', rotation=90)

    # 5. 단면 제목
    ax.text(x_off + b_beam / 2, h_beam + 20, title,
            fontsize=10, color='black', ha='center', va='bottom', family='monospace')

    # 6. 하단 텍스트 (배근 + 스터럽)
    _info = [f"TOP   {n_top}-{rtype_t}", f"BOT   {n_bot}-{rtype_b}",
             f"STIRRUPS  {s_final_str}"]
    for _li, _lt in enumerate(_info):
        ax.text(x_off + b_beam / 2, -55 - _li * 18, _lt,
                fontsize=7, color='black', ha='center', va='top', family='monospace',
                fontweight='bold')


def plot_rebar_section(b_beam, h_beam, rebar_string_top, rebar_steps_top, layer_top,
                       rebar_string_bot, rebar_steps_bot, layer_bot, beam_type, s_final,
                       section_location='combined',
                       rebar_string_min=None, rebar_steps_min=None, layer_min=1):
    """MIDAS Gen 스타일 보 단면도 — 설계 모드 (기존 호환)."""
    cover     = rebar_steps_bot['cover']
    stirrup_d = rebar_steps_bot['rebar_specs']['D10']['diameter']

    # 3단면 설정
    if section_location == 'combined' and rebar_string_min is not None:
        sections = [('support', '[END-I]'), ('midspan', '[MID]'), ('support', '[END-J]')]
    elif section_location == 'combined':
        sections = [('combined', f'{beam_type}-Direction')]
    else:
        sections = [(section_location, '[END-I]' if section_location == 'support' else '[MID]')]

    n_sec = len(sections)
    gap = b_beam * 0.5
    total_w = n_sec * b_beam + (n_sec - 1) * gap

    fig, ax = plt.subplots(1, 1, figsize=(max(6, 3 * n_sec), 5), dpi=200)
    ax.set_aspect('equal')
    ax.set_axis_off()

    for _si, (_loc, _title) in enumerate(sections):
        x_off = _si * (b_beam + gap)
        if _loc == 'support' and rebar_string_min is not None:
            _str_t, _str_b = rebar_string_top, rebar_string_min
        elif _loc == 'midspan' and rebar_string_min is not None:
            _str_t, _str_b = rebar_string_min, rebar_string_bot
        else:
            _str_t, _str_b = rebar_string_top, rebar_string_bot

        _draw_one_section(ax, x_off, b_beam, h_beam, _str_t, _str_b,
                          f"2-D10 @{s_final:.0f}", cover=cover, stirrup_d=stirrup_d,
                          title=_title)

    ax.set_xlim(-80, total_w + 50)
    ax.set_ylim(-120, h_beam + 40)
    ax.set_title(f'midas Gen RC Beam Section  [{beam_type}-Dir]',
                 fontsize=10, family='monospace', pad=10)
    fig.tight_layout()
    return fig


def plot_rebar_section_review(b_beam, h_beam, sections_data, cover=40.0, stirrup_d=9.53,
                               title_prefix='RC Beam Section'):
    """검토 모드 보 단면도 — END-I/MID/END-J 각각 독립 배근.

    Args:
        sections_data: [
            {'title': '[END-I]', 'top': '3-D19', 'bot': '3-D19', 'stirrup': '2-D10@125'},
            {'title': '[MID]',   'top': '3-D19', 'bot': '3-D19', 'stirrup': '2-D10@125'},
            {'title': '[END-J]', 'top': '3-D19', 'bot': '3-D19', 'stirrup': '2-D10@125'},
        ]
    """
    n_sec = len(sections_data)
    gap = b_beam * 0.5
    total_w = n_sec * b_beam + (n_sec - 1) * gap

    fig, ax = plt.subplots(1, 1, figsize=(max(6, 3 * n_sec), 5), dpi=200)
    ax.set_aspect('equal')
    ax.set_axis_off()

    for _si, sec in enumerate(sections_data):
        x_off = _si * (b_beam + gap)
        _draw_one_section(ax, x_off, b_beam, h_beam,
                          sec.get('top', '2-D13'), sec.get('bot', '2-D13'),
                          sec.get('stirrup', '-'),
                          cover=cover, stirrup_d=stirrup_d,
                          title=sec.get('title', f'[{_si}]'))

    ax.set_xlim(-80, total_w + 50)
    ax.set_ylim(-120, h_beam + 40)
    ax.set_title(title_prefix, fontsize=10, family='monospace', pad=10)
    fig.tight_layout()
    return fig

def plot_best_section(b, h, rebar_top_str, rebar_bot_str, skin_str='',
                      cover=40.0, stirrup_d=9.53, b_top=0, h_top=0):
    """BeST.RC 스타일 단면도 (직사각/T형보).
    - 연노랑 배경 + 파란 외곽선
    - 작은 빨간 점 (철근)
    - Skin 철근 (양 측면)
    - 외부 치수선 (mm 단위)
    - T형보 지원
    """
    import re as _re

    CLR_BG = '#FFFFCC'       # BeST 연노랑
    CLR_OUTLINE = '#2255CC'  # 파란 외곽선
    CLR_STIRRUP = '#CC6600'  # 주황 스터럽
    CLR_REBAR = '#CC0000'    # 빨간 철근
    CLR_DIM = '#333333'      # 치수선

    _dia_map = {'D10': 9.53, 'D13': 12.7, 'D16': 15.9, 'D19': 19.1,
                'D22': 22.2, 'D25': 25.4, 'D29': 28.6, 'D32': 31.8}

    def _parse(rstr):
        if not rstr:
            return 0, 0.0
        m = _re.match(r'(\d+)-D(\d+)', str(rstr).strip())
        if not m:
            return 0, 0.0
        return int(m.group(1)), _dia_map.get(f"D{m.group(2)}", 19.1)

    def _parse_skin(sstr):
        if not sstr:
            return 0, 0.0
        m = _re.match(r'(\d+)/(\d+)\s*-?\s*D(\d+)', str(sstr).strip())
        if not m:
            return 0, 0.0
        return int(m.group(1)) + int(m.group(2)), _dia_map.get(f"D{m.group(3)}", 12.7)

    n_top, dia_top = _parse(rebar_top_str)
    n_bot, dia_bot = _parse(rebar_bot_str)
    n_skin, dia_skin = _parse_skin(skin_str)

    is_t = b_top > 0 and h_top > 0
    h_bot = h - h_top if is_t else h
    bw = b  # 웹 폭

    # figure 크기: xlim/ylim 비율에 맞춤
    _draw_w = (max(b_top, b) + 75) if is_t else (b + 50)
    _draw_h = h + 44  # ylim 여백 포함
    _fig_base = 2.5  # inch 기준
    if _draw_w >= _draw_h:
        _fig_w = _fig_base
        _fig_h = _fig_base * _draw_h / _draw_w
    else:
        _fig_h = _fig_base
        _fig_w = _fig_base * _draw_w / _draw_h
    fig, ax = plt.subplots(1, 1, figsize=(_fig_w, _fig_h), dpi=100)
    ax.set_aspect('equal')
    ax.axis('off')

    # 원점: 단면 좌하단 = (0, 0)
    margin = 50

    if is_t:
        # T형보: Polygon (6개 꼭짓점, 좌하단 시작 반시계)
        x_flange_left = -(b_top - bw) / 2  # 플랜지 좌측 시작 (웹 중심 기준)
        pts = [
            (0, 0),                          # 웹 좌하단
            (bw, 0),                         # 웹 우하단
            (bw, h_bot),                     # 웹 우상단 → 플랜지 전환
            (bw + (b_top - bw) / 2, h_bot),  # 플랜지 우하단
            (bw + (b_top - bw) / 2, h),      # 플랜지 우상단
            (-(b_top - bw) / 2, h),           # 플랜지 좌상단
            (-(b_top - bw) / 2, h_bot),       # 플랜지 좌하단
            (0, h_bot),                       # 웹 좌상단
        ]
        poly = mpatches.Polygon(pts, closed=True,
                                facecolor=CLR_BG, edgecolor=CLR_OUTLINE, linewidth=2.5)
        ax.add_patch(poly)
    else:
        # 직사각형
        ax.add_patch(mpatches.Rectangle((0, 0), b, h,
                     facecolor=CLR_BG, edgecolor=CLR_OUTLINE, linewidth=2.5))

    # 스터럽 (웹 내부)
    loc_b = cover + stirrup_d
    loc_t = cover + stirrup_d
    stir_x0 = loc_b
    stir_y0 = loc_b
    stir_w = bw - 2 * loc_b
    stir_h = h - loc_b - loc_t
    if stir_w > 0 and stir_h > 0:
        ax.add_patch(mpatches.Rectangle((stir_x0, stir_y0), stir_w, stir_h,
                     facecolor='none', edgecolor=CLR_STIRRUP, linewidth=1.2))

    # 철근 배치
    r_vis = 4.0  # BeST 스타일: 고정 크기 작은 점

    def _draw_rebar_row(n, y, x_start, x_end):
        if n <= 0:
            return
        if n == 1:
            ax.add_patch(mpatches.Circle(((x_start + x_end) / 2, y), r_vis,
                         facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))
        else:
            spacing = (x_end - x_start) / (n - 1)
            for i in range(n):
                cx = x_start + i * spacing
                ax.add_patch(mpatches.Circle((cx, y), r_vis,
                             facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))

    x_inner_l = loc_b + dia_bot / 2 if dia_bot > 0 else loc_b + 10
    x_inner_r = bw - loc_b - dia_bot / 2 if dia_bot > 0 else bw - loc_b - 10
    y_bot = loc_b + dia_bot / 2 if dia_bot > 0 else loc_b + 10
    y_top = h - loc_t - dia_top / 2 if dia_top > 0 else h - loc_t - 10

    # 상부근
    _draw_rebar_row(n_top, y_top, x_inner_l, x_inner_r)
    # 하부근
    _draw_rebar_row(n_bot, y_bot, x_inner_l, x_inner_r)

    # Skin 철근 (양 측면, 중간 높이)
    if n_skin > 0:
        n_each = n_skin // 2
        if n_each > 0:
            y_mid = (y_bot + y_top) / 2
            if n_each == 1:
                # 1개씩: 정중앙
                ax.add_patch(mpatches.Circle((x_inner_l, y_mid), r_vis,
                             facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))
                ax.add_patch(mpatches.Circle((x_inner_r, y_mid), r_vis,
                             facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))
            else:
                # 여러 개: 균등 배치
                for i in range(n_each):
                    yy = y_bot + (y_top - y_bot) * (i + 1) / (n_each + 1)
                    ax.add_patch(mpatches.Circle((x_inner_l, yy), r_vis,
                                 facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))
                    ax.add_patch(mpatches.Circle((x_inner_r, yy), r_vis,
                                 facecolor=CLR_REBAR, edgecolor=CLR_REBAR, linewidth=0.5))

    # 치수선
    _tick = 5
    _dim_off = 15

    if is_t:
        # T형보 치수 (BeST 스타일)
        _flange_l = -(b_top - bw) / 2  # 플랜지 좌측 x
        _flange_r = bw + (b_top - bw) / 2  # 플랜지 우측 x

        # 상단: Btop (플랜지 폭)
        _y_top_dim = h + _dim_off
        ax.plot([_flange_l, _flange_r], [_y_top_dim, _y_top_dim], color=CLR_DIM, linewidth=0.8)
        for _x in [_flange_l, _flange_r]:
            ax.plot([_x, _x], [_y_top_dim - _tick, _y_top_dim + _tick], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x, _y_top_dim, 'o', color=CLR_DIM, markersize=2)
        ax.text(bw / 2, _y_top_dim + 8, f'{int(b_top)}', fontsize=7, ha='center', va='bottom', color=CLR_DIM)

        # 하단: Bbot (웹 폭)
        _y_bot_dim = -_dim_off
        ax.plot([0, bw], [_y_bot_dim, _y_bot_dim], color=CLR_DIM, linewidth=0.8)
        for _x in [0, bw]:
            ax.plot([_x, _x], [_y_bot_dim - _tick, _y_bot_dim + _tick], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x, _y_bot_dim, 'o', color=CLR_DIM, markersize=2)
        ax.text(bw / 2, _y_bot_dim - 8, f'{int(bw)}', fontsize=7, ha='center', va='top', color=CLR_DIM)

        # 왼쪽: Hbot (웹 높이) — 웹 좌측에서 약간 왼쪽
        _x_hbot_dim = -_dim_off - 5
        ax.plot([_x_hbot_dim, _x_hbot_dim], [0, h_bot], color=CLR_DIM, linewidth=0.8)
        for _y in [0, h_bot]:
            ax.plot([_x_hbot_dim - _tick, _x_hbot_dim + _tick], [_y, _y], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x_hbot_dim, _y, 'o', color=CLR_DIM, markersize=2)
        ax.text(_x_hbot_dim - 8, h_bot / 2, f'{int(h_bot)}', fontsize=7, ha='right', va='center',
                rotation=90, color=CLR_DIM)

        # 왼쪽: Htop (플랜지 높이) — 플랜지 좌측 기준
        _x_htop_dim = _flange_l - _dim_off
        ax.plot([_x_htop_dim, _x_htop_dim], [h_bot, h], color=CLR_DIM, linewidth=0.8)
        for _y in [h_bot, h]:
            ax.plot([_x_htop_dim - _tick, _x_htop_dim + _tick], [_y, _y], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x_htop_dim, _y, 'o', color=CLR_DIM, markersize=2)
        ax.text(_x_htop_dim - 8, (h_bot + h) / 2, f'{int(h_top)}', fontsize=7, ha='right', va='center',
                rotation=90, color=CLR_DIM)
    else:
        # 직사각형 치수
        # 하단: 폭
        _y_bot_dim = -_dim_off
        ax.plot([0, b], [_y_bot_dim, _y_bot_dim], color=CLR_DIM, linewidth=0.8)
        for _x in [0, b]:
            ax.plot([_x, _x], [_y_bot_dim - _tick, _y_bot_dim + _tick], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x, _y_bot_dim, 'o', color=CLR_DIM, markersize=2)
        ax.text(b / 2, _y_bot_dim - 8, f'{int(b)}', fontsize=7, ha='center', va='top', color=CLR_DIM)

        # 왼쪽: 높이
        _x_left_dim = -_dim_off
        ax.plot([_x_left_dim, _x_left_dim], [0, h], color=CLR_DIM, linewidth=0.8)
        for _y in [0, h]:
            ax.plot([_x_left_dim - _tick, _x_left_dim + _tick], [_y, _y], color=CLR_DIM, linewidth=0.8)
            ax.plot(_x_left_dim, _y, 'o', color=CLR_DIM, markersize=2)
        ax.text(_x_left_dim - 8, h / 2, f'{int(h)}', fontsize=7, ha='right', va='center',
                rotation=90, color=CLR_DIM)

    # 범위 설정 (상하 여백 최소화)
    x_min = -(b_top - bw) / 2 - 55 if is_t else -35
    x_max = bw + (b_top - bw) / 2 + 20 if is_t else b + 15
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(-22, h + 22)
    fig.tight_layout(pad=0.1)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
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
    fig, ax = plt.subplots(1, 1, figsize=(10, 4), dpi=200)
    ax.set_aspect('equal')
    ax.set_axis_off()

    # 1. 콘크리트
    ax.add_patch(mpatches.Rectangle((0, 0), L_beam, h_beam,
                 facecolor='#D6EAF8', edgecolor='#222222', linewidth=2.5))

    cover = rebar_steps_bot['cover']
    stirrup_diameter = rebar_steps_bot['rebar_specs']['D10']['diameter']
    L_zone = L_beam / 4

    # 2. 하부근
    rebar_type_bot = rebar_string_bot.split('-')[1] if layer_bot == 1 else "D25"
    rebar_diameter_bot = rebar_steps_bot['rebar_specs'][rebar_type_bot]['diameter']
    y_bot = cover + stirrup_diameter + rebar_diameter_bot / 2

    if rebar_string_min is not None:
        ax.add_patch(mpatches.Rectangle((L_zone, y_bot - rebar_diameter_bot/2), L_beam - 2*L_zone, rebar_diameter_bot,
                     facecolor='#333333', edgecolor='none'))
        for x0, x1 in [(0, L_zone), (L_beam - L_zone, L_beam)]:
            ax.add_patch(mpatches.Rectangle((x0, y_bot - rebar_diameter_bot/2), x1-x0, rebar_diameter_bot,
                         facecolor='#888888', edgecolor='none'))
    else:
        ax.add_patch(mpatches.Rectangle((0, y_bot - rebar_diameter_bot/2), L_beam, rebar_diameter_bot,
                     facecolor='#333333', edgecolor='none'))
        if layer_bot == 2:
            y_bot2 = y_bot + rebar_diameter_bot + 25
            ax.add_patch(mpatches.Rectangle((0, y_bot2 - rebar_diameter_bot/2), L_beam, rebar_diameter_bot,
                         facecolor='#333333', edgecolor='none'))

    # 3. 상부근
    rebar_type_top = rebar_string_top.split('-')[1] if layer_top == 1 else "D25"
    rebar_diameter_top = rebar_steps_top['rebar_specs'][rebar_type_top]['diameter']
    y_top = h_beam - cover - stirrup_diameter - rebar_diameter_top / 2

    if rebar_string_min is not None:
        for x0, x1 in [(0, L_zone), (L_beam - L_zone, L_beam)]:
            ax.add_patch(mpatches.Rectangle((x0, y_top - rebar_diameter_top/2), x1-x0, rebar_diameter_top,
                         facecolor='#333333', edgecolor='none'))
        ax.add_patch(mpatches.Rectangle((L_zone, y_top - rebar_diameter_top/2), L_beam - 2*L_zone, rebar_diameter_top,
                     facecolor='#888888', edgecolor='none'))
    else:
        ax.add_patch(mpatches.Rectangle((0, y_top - rebar_diameter_top/2), L_beam, rebar_diameter_top,
                     facecolor='#333333', edgecolor='none'))
        if layer_top == 2:
            y_top2 = y_top - rebar_diameter_top - 25
            ax.add_patch(mpatches.Rectangle((0, y_top2 - rebar_diameter_top/2), L_beam, rebar_diameter_top,
                         facecolor='#333333', edgecolor='none'))

    # 4. 늑근
    if stirrup_zones and len(stirrup_zones) > 1:
        _L_m = L_beam / 1000.0
        _all_zones = list(stirrup_zones)
        _last_end = max(z['x_end'] for z in stirrup_zones)
        if _last_end < _L_m * 0.9:
            for _sz in reversed(stirrup_zones):
                _all_zones.append({'x_start': _L_m - _sz['x_end'], 'x_end': _L_m - _sz['x_start'], 's': _sz['s']})
        for _sz in _all_zones:
            _sx0 = _sz['x_start'] * 1000
            _sx1 = _sz['x_end'] * 1000
            x_pos = _sx0 + 50
            while x_pos < _sx1 - 10:
                if 50 <= x_pos <= L_beam - 50:
                    ax.add_patch(mpatches.Rectangle((x_pos - stirrup_diameter/2, cover), stirrup_diameter, h_beam - 2*cover,
                                 facecolor='#555555', edgecolor='none'))
                x_pos += _sz['s']
    else:
        num_stirrups = int(L_beam / s_final) if s_final > 0 else 0
        for i in range(num_stirrups + 1):
            x_pos = 50 + i * s_final
            if x_pos > L_beam - 50:
                break
            ax.add_patch(mpatches.Rectangle((x_pos - stirrup_diameter/2, cover), stirrup_diameter, h_beam - 2*cover,
                         facecolor='#555555', edgecolor='none'))

    # 5. 구간 경계선
    if rebar_string_min is not None:
        for x_div in [L_zone, L_beam - L_zone]:
            ax.plot([x_div, x_div], [0, h_beam], color='#888888', linewidth=0.8, linestyle=':')

    # 6. 이음 구간
    if dev_top is not None and dev_top.get('ls_B'):
        _ls_top = dev_top['ls_B']
        for _x_sp in [L_zone, L_beam - L_zone]:
            _x0_ext = _x_sp if _x_sp == L_zone else _x_sp - _ls_top
            _x1_ext = _x_sp + _ls_top if _x_sp == L_zone else _x_sp
            ax.add_patch(mpatches.Rectangle((_x0_ext, y_top - rebar_diameter_top/2 - 1), _x1_ext - _x0_ext, rebar_diameter_top + 2,
                         facecolor='#333333', edgecolor='none', alpha=0.7))
        ax.text(L_zone + _ls_top/2, y_top + rebar_diameter_top + 12, f"ls={_ls_top:.0f}",
                fontsize=6, color='#666666', ha='center', va='center')

    if dev_bot is not None and dev_bot.get('ls_B'):
        _ls_bot = dev_bot['ls_B']
        for _x_sp in [L_zone, L_beam - L_zone]:
            _x0_ext = _x_sp - _ls_bot if _x_sp == L_zone else _x_sp
            _x1_ext = _x_sp if _x_sp == L_zone else _x_sp + _ls_bot
            ax.add_patch(mpatches.Rectangle((_x0_ext, y_bot - rebar_diameter_bot/2 - 1), _x1_ext - _x0_ext, rebar_diameter_bot + 2,
                         facecolor='#333333', edgecolor='none', alpha=0.7))
        ax.text(L_zone - _ls_bot/2, y_bot - rebar_diameter_bot - 12, f"ls={_ls_bot:.0f}",
                fontsize=6, color='#666666', ha='center', va='center')

    # 7. 늑근 구간 표시
    if stirrup_zones and len(stirrup_zones) > 1:
        _sz_y = h_beam + 30
        _L_m = L_beam / 1000.0
        _disp_zones = list(stirrup_zones)
        _last_end = max(z['x_end'] for z in stirrup_zones)
        if _last_end < _L_m * 0.9:
            for _sz in reversed(stirrup_zones):
                _disp_zones.append({'x_start': _L_m - _sz['x_end'], 'x_end': _L_m - _sz['x_start'], 's': _sz['s']})
        for _sz in _disp_zones:
            _sx0 = _sz['x_start'] * 1000
            _sx1 = _sz['x_end'] * 1000
            ax.plot([_sx0, _sx1], [_sz_y, _sz_y], color='#555555', linewidth=2)
            ax.text((_sx0 + _sx1)/2, _sz_y + 20, f"D10@{_sz['s']:.0f}",
                    fontsize=5, color='#555555', ha='center', va='center')

    # 8. 지점 삼각형
    tri_h = 80
    tri_w = 60
    for x_support in [0, L_beam]:
        tri = plt.Polygon([[x_support, 0], [x_support - tri_w, -tri_h], [x_support + tri_w, -tri_h]],
                          facecolor='#cccccc', edgecolor='#333333', linewidth=1.5, alpha=0.5)
        ax.add_patch(tri)
        for _hi in range(4):
            _hx0 = x_support - tri_w - 10 + _hi * 20
            ax.plot([_hx0, _hx0 - 15], [-tri_h, -tri_h - 15], color='#666666', linewidth=0.8)

    # 9. 치수선
    ax.text(L_beam/2, -190, f"L = {L_beam:.0f}", fontsize=10, color='black', ha='center', va='center')
    ax.plot([0, L_beam], [-150, -150], color='black', linewidth=1)
    ax.text(-250, h_beam/2, f"h = {h_beam:.0f}", fontsize=10, color='black', ha='center', va='center', rotation=90)
    ax.plot([-200, -200], [0, h_beam], color='black', linewidth=1)

    _y_max = h_beam + 100 if not stirrup_zones else h_beam + 80 + len(stirrup_zones) * 20
    ax.set_xlim(-400, L_beam + 200)
    ax.set_ylim(-300, _y_max)
    ax.set_title(f'Beam Side View  [{beam_type}-Dir]', fontsize=10, family='monospace')
    fig.tight_layout()
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
            fig.add_trace(create_cylinder(0, L_beam, y, z_base, rebar_d/2, '#333333'))
    else:
        n1 = n_total // 2 + (n_total % 2)
        n2 = n_total - n1
        sp1 = avail_w / (n1 - 1) if n1 > 1 else 0
        for i in range(n1):
            y = y_base + i*sp1 if n1 > 1 else b_beam/2
            fig.add_trace(create_cylinder(0, L_beam, y, z_base, rebar_d/2, '#333333'))
        sp2 = avail_w / (n2 - 1) if n2 > 1 else 0
        for i in range(n2):
            y = y_base + i*sp2 if n2 > 1 else b_beam/2
            fig.add_trace(create_cylinder(0, L_beam, y, z_base + rebar_d + 25, rebar_d/2, '#333333'))

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

    num_s = int(L_beam / s_final) if s_final > 0 else 0
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

    fig.update_layout(title=f'Beam 3D Rebar [{beam_type}-Dir]', scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), width=600, height=400)
    return fig

def plot_sfd_bmd(member_forces, beam_type):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=member_forces['x_steps'], y=member_forces['SFD'], mode='lines', name='SFD (kN)', line=dict(color='blue', width=2)))
    fig.add_trace(go.Scatter(x=member_forces['x_steps'], y=member_forces['BMD'], mode='lines', name='BMD (kN·m)', line=dict(color='red', width=2)))
    fig.update_layout(
        title=f'Beam SFD & BMD [{beam_type}-Dir]',
        xaxis_title='위치 (m)',
        yaxis_title='힘 (kN) / 모멘트 (kN·m)',
        height=400,
        hovermode='x unified'
    )
    return fig
