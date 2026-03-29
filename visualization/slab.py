import matplotlib
matplotlib.use('Agg')  # Streamlit 호환 백엔드
import matplotlib.pyplot as plt
import matplotlib.patches as patches
matplotlib.rcParams['font.family'] = ['Malgun Gothic', 'NanumGothic', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np

def plot_slab_section(t_slab, rebar_string_top, rebar_string_bot,
                      rebar_string_dist=None, cover=20.0,
                      fck=24.0, fy=400.0):
    """
    1m 폭 슬래브 단면 (1000mm × t_slab) — Matplotlib PNG 렌더링.
    비율 완벽 유지, 브라우저 리사이즈 영향 없음.
    """
    b = 1000.0  # mm
    h = t_slab

    # ── 색상 팔레트 ──
    CLR_OUTLINE = '#222222'
    CLR_CONCRETE = '#E8E8E8'
    CLR_HATCH = '#CCCCCC'
    CLR_REBAR = '#1a1a1a'
    CLR_REBAR_LINE = '#000000'
    CLR_DIM = '#444444'
    CLR_DIM_D = '#888888'
    CLR_DIST = '#555555'
    CLR_LABEL = '#333333'

    REBAR_SCALE = 3.5

    def _parse_rebar(rb_str):
        if rb_str is None or '@' not in rb_str:
            return None, None, 0
        parts = rb_str.split('@')
        size_name = parts[0]
        spacing = float(parts[1])
        rebar_specs = {"D10": 9.53, "D13": 12.7, "D16": 15.9}
        diameter = rebar_specs.get(size_name, 10.0)
        n = int(np.floor(b / spacing))
        return diameter, spacing, n

    # ── Figure 생성 ──
    fig, ax = plt.subplots(1, 1, figsize=(10, 5), dpi=150)
    ax.set_aspect('equal')
    ax.set_axis_off()

    # --- 1. 콘크리트 단면 ---
    ax.add_patch(patches.Rectangle((0, 0), b, h,
                 facecolor=CLR_CONCRETE, edgecolor=CLR_OUTLINE, linewidth=2.5))

    # 사선 해칭 (45도)
    _hatch_sp = max(12, h / 10)
    for _hi in np.arange(-b - h, b + h, _hatch_sp):
        _x0 = max(0, _hi)
        _y0 = max(0, -_hi)
        _x1 = min(b, _hi + h)
        _y1 = min(h, h - _hi)
        if _x0 < b and _x1 > 0 and _y0 < h and _y1 > 0:
            ax.plot([_x0, _x1], [_y0, _y1], color=CLR_HATCH, linewidth=0.4)

    # --- 2. 하부근 (B1) ---
    _db_bot, _s_bot, _n_bot = _parse_rebar(rebar_string_bot)
    _db_bot = _db_bot or 9.53
    _draw_bot = _db_bot * REBAR_SCALE
    y_bot = cover + _db_bot / 2.0
    if _n_bot > 0:
        x_start = _s_bot / 2.0
        for i in range(_n_bot):
            x_pos = x_start + i * _s_bot
            ax.add_patch(patches.Circle((x_pos, y_bot), _draw_bot / 2,
                         facecolor=CLR_REBAR, edgecolor=CLR_REBAR_LINE, linewidth=1.5))

    # --- 3. 상부근 (T1) ---
    _db_top, _s_top, _n_top = _parse_rebar(rebar_string_top)
    _db_top = _db_top or 9.53
    _draw_top = _db_top * REBAR_SCALE
    y_top = h - cover - _db_top / 2.0
    if _n_top > 0:
        x_start = _s_top / 2.0
        for i in range(_n_top):
            x_pos = x_start + i * _s_top
            ax.add_patch(patches.Circle((x_pos, y_top), _draw_top / 2,
                         facecolor=CLR_REBAR, edgecolor=CLR_REBAR_LINE, linewidth=1.5))

    # --- 4. 배력근 (직교 방향 — 수평 실선) ---
    _db_dist_val = 9.53
    y_dist = y_bot
    if rebar_string_dist and '@' in rebar_string_dist:
        _db_dist, _s_dist, _n_dist = _parse_rebar(rebar_string_dist)
        _db_dist_val = _db_dist or 9.53
        _draw_dist = _db_dist_val * REBAR_SCALE
        y_dist = y_bot + _db_bot / 2.0 + _db_dist_val / 2.0 + 2.0
        ax.add_patch(patches.Rectangle((cover, y_dist - _draw_dist / 2),
                     b - 2 * cover, _draw_dist,
                     facecolor=CLR_DIST, edgecolor='none', alpha=0.7))

    # --- 5. 유효깊이(d) 치수선 — 좌측 ---
    d_eff = h - cover - _db_bot / 2.0
    d_x = -35
    ax.plot([d_x, d_x], [h, h - d_eff], color=CLR_DIM_D, linewidth=1)
    for _dy in [h, h - d_eff]:
        ax.plot([d_x - 5, d_x + 5], [_dy, _dy], color=CLR_DIM_D, linewidth=1)
    ax.text(d_x - 16, h - d_eff / 2, f"d={d_eff:.0f}",
            fontsize=7, color=CLR_DIM_D, ha='center', va='center', rotation=90)
    # d 보조 점선
    ax.plot([0, d_x + 5], [h - d_eff, h - d_eff],
            color=CLR_DIM_D, linewidth=0.5, linestyle=':')

    # --- 6. 피복두께 — 상/하 ---
    cv_x = -12
    for (_y0, _y1) in [(0, cover), (h - cover, h)]:
        ax.plot([cv_x, cv_x], [_y0, _y1], color=CLR_DIM_D, linewidth=0.7, linestyle=':')
        for _yt in [_y0, _y1]:
            ax.plot([cv_x - 3, cv_x + 3], [_yt, _yt], color=CLR_DIM_D, linewidth=0.7)

    # --- 7. 두께(t) 치수선 — 우측 ---
    dim_x = b + 35
    tick = 6
    ax.plot([dim_x, dim_x], [0, h], color=CLR_DIM, linewidth=1.2)
    for _yt in [0, h]:
        ax.plot([dim_x - tick, dim_x + tick], [_yt, _yt], color=CLR_DIM, linewidth=1.2)
    ax.text(dim_x + 18, h / 2, f"t={h:.0f}",
            fontsize=8, color=CLR_DIM, ha='center', va='center', rotation=-90)

    # 폭(b) 치수선 — 하단
    dim_y = -18
    ax.plot([0, b], [dim_y, dim_y], color=CLR_DIM, linewidth=1.2)
    for _xt in [0, b]:
        ax.plot([_xt, _xt], [dim_y - tick, dim_y + tick], color=CLR_DIM, linewidth=1.2)
    ax.text(b / 2, dim_y - 12, "b = 1000 (1m strip)",
            fontsize=7, color=CLR_DIM, ha='center', va='center')

    # --- 8. 지시선 (annotate) ---
    _ann_x = b + 60
    _arrow_props = dict(arrowstyle='->', color=CLR_LABEL, lw=1)
    if _n_top > 0:
        ax.annotate(f"T1: {rebar_string_top}",
                    xy=(b - 50, y_top), xytext=(_ann_x + 50, y_top),
                    fontsize=7, color=CLR_LABEL, family='monospace',
                    arrowprops=_arrow_props, va='center')
    if _n_bot > 0:
        ax.annotate(f"B1: {rebar_string_bot}",
                    xy=(b - 50, y_bot), xytext=(_ann_x + 50, y_bot + 12),
                    fontsize=7, color=CLR_LABEL, family='monospace',
                    arrowprops=_arrow_props, va='center')
    if rebar_string_dist and '@' in rebar_string_dist:
        ax.annotate(f"Dist: {rebar_string_dist}",
                    xy=(b - 50, y_dist), xytext=(_ann_x + 50, y_dist - 12),
                    fontsize=7, color=CLR_LABEL, family='monospace',
                    arrowprops=_arrow_props, va='center')

    # --- 9. 재료 정보 ---
    _info = f"fck={fck:.0f}MPa  fy={fy:.0f}MPa  c={cover:.0f}mm  d={d_eff:.0f}mm"
    ax.text(b / 2, h + 12, _info,
            fontsize=6, color='#666666', ha='center', va='bottom', family='monospace')

    # --- 제목 ---
    ax.set_title("SLAB SECTION (1m STRIP)", fontsize=10, family='monospace', pad=20)

    # --- 범위 ---
    ax.set_xlim(-60, b + 160)
    ax.set_ylim(-45, h + 25)

    fig.tight_layout()
    return fig
