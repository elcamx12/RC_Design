import plotly.graph_objects as go
import numpy as np

def plot_slab_section(t_slab, rebar_string_top, rebar_string_bot,
                      rebar_string_dist=None, cover=20.0):
    """
    1m 폭 슬래브 단면 (1000mm × t_slab) 렌더링.
    "D10@200" 형태의 배근 문자열에서 간격을 파싱하여 철근 위치 배치.
    """
    fig = go.Figure()
    b = 1000.0  # mm
    h = t_slab

    # 콘크리트 단면
    fig.add_shape(type='rect', x0=-b/2, y0=0, x1=b/2, y1=h,
                  fillcolor='rgba(200,200,200,0.3)', line=dict(color='gray', width=2))

    def _parse_rebar(rb_str):
        """'D10@200' → (diameter, spacing, n_bars_in_1m)"""
        if rb_str is None or '@' not in rb_str:
            return None, None, 0
        parts = rb_str.split('@')
        size_name = parts[0]
        spacing = float(parts[1])
        rebar_specs = {"D10": 9.53, "D13": 12.7, "D16": 15.9}
        diameter = rebar_specs.get(size_name, 10.0)
        n = int(np.floor(b / spacing))
        return diameter, spacing, n

    def _draw_bars(y_center, rb_str, color, label):
        d, s, n = _parse_rebar(rb_str)
        if n <= 0:
            return
        # 첫 철근 위치: -b/2 + s/2, 이후 s 간격
        x_start = -b/2 + s/2
        xs = [x_start + i * s for i in range(n)]
        ys = [y_center] * n
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='markers',
            marker=dict(size=max(d * 0.8, 6), color=color,
                        line=dict(color='black', width=1)),
            name=f'{label} ({rb_str})', hoverinfo='name'
        ))

    # 하부근 (M_pos)
    _db_bot = _parse_rebar(rebar_string_bot)[0] or 9.53
    y_bot = cover + _db_bot / 2.0
    _draw_bars(y_bot, rebar_string_bot, 'red', '하부근')

    # 상부근 (M_neg)
    _db_top = _parse_rebar(rebar_string_top)[0] or 9.53
    y_top = h - cover - _db_top / 2.0
    _draw_bars(y_top, rebar_string_top, 'blue', '상부근')

    # 배력근 (수축·온도 — 직교 방향, 수평선으로 표시)
    if rebar_string_dist and '@' in rebar_string_dist:
        _db_dist, _s_dist, _n_dist = _parse_rebar(rebar_string_dist)
        _db_dist = _db_dist or 9.53
        # 하부근 바로 위에 배력근 (직교 방향이므로 단면에서 수평선으로 보임)
        y_dist = y_bot + _db_bot / 2.0 + _db_dist / 2.0 + 2.0
        # 직교 방향 철근 → 단면에 수평 실선으로 표현 (단면을 관통)
        fig.add_trace(go.Scatter(
            x=[-b/2 + 15, b/2 - 15], y=[y_dist, y_dist],
            mode='lines',
            line=dict(color='green', width=max(_db_dist * 0.3, 2)),
            name=f'배력근 ({rebar_string_dist})', hoverinfo='name'
        ))
        # 양쪽 끝 표시 (단면 절단 표시)
        fig.add_trace(go.Scatter(
            x=[-b/2 + 15, b/2 - 15], y=[y_dist, y_dist],
            mode='markers',
            marker=dict(size=max(_db_dist * 0.6, 4), color='green',
                        symbol='line-ns', line=dict(width=1.5, color='green')),
            showlegend=False, hoverinfo='skip'
        ))

    # 치수선: t_slab 높이
    _dim_x = b/2 + 60
    fig.add_shape(type='line', x0=_dim_x, y0=0, x1=_dim_x, y1=h,
                  line=dict(color='gray', width=1.5))
    for _y in [0, h]:
        fig.add_shape(type='line', x0=_dim_x-15, y0=_y, x1=_dim_x+15, y1=_y,
                      line=dict(color='gray', width=1.5))
    fig.add_annotation(x=_dim_x+10, y=h/2, text=f"t={h:.0f}",
                       showarrow=False, font=dict(size=11, color='gray'))

    # 치수선: 피복두께
    _cv_x = -b/2 - 40
    fig.add_shape(type='line', x0=_cv_x, y0=0, x1=_cv_x, y1=cover,
                  line=dict(color='orange', width=1, dash='dot'))
    fig.add_annotation(x=_cv_x-5, y=cover/2, text=f"c={cover:.0f}",
                       showarrow=False, font=dict(size=9, color='orange'))

    fig.update_layout(
        title="슬래브 단면도 (1m 스트립)",
        xaxis=dict(title='폭 (mm)', scaleanchor='y', scaleratio=1,
                   showgrid=False, zeroline=False),
        yaxis=dict(title='높이 (mm)', showgrid=False, zeroline=False),
        height=300, margin=dict(l=40, r=60, t=40, b=40),
        showlegend=True, legend=dict(x=0.01, y=0.99, font=dict(size=10))
    )
    return fig
