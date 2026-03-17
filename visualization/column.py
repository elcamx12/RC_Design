import plotly.graph_objects as go
import numpy as np

def plot_pm_diagram(rebar_design, axial_moment):
    """기둥 P-M 상관도 — 공칭강도 vs 설계강도 비교

    Parameters
    ----------
    rebar_design : dict
        column_engine.calculate_rebar_design() 반환 dict.
    axial_moment : dict
        column_engine.calculate_axial_load_and_moment() 반환 dict.
    """
    phi_Pn_max = rebar_design['phi_Pn_max']   # φPn,max (kN)
    phi_Pn_b   = rebar_design['phi_Pn_b']     # 균형파괴 φPu (kN)
    phi_Mn_b   = rebar_design['phi_Mn_b']     # 균형파괴 φMu (kN·m)
    phi_Mn_o   = rebar_design['phi_Mn_o']     # 순수휨 φMu (kN·m)
    Mu_d       = rebar_design['Mu_design']
    Pu_d       = axial_moment['Pu']
    rebar_str  = rebar_design.get('rebar_string_col', '')

    # 곡선 데이터
    pm_curve_P   = rebar_design.get('pm_curve_P')
    pm_curve_M   = rebar_design.get('pm_curve_M')
    pm_nominal_P = rebar_design.get('pm_nominal_P')
    pm_nominal_M = rebar_design.get('pm_nominal_M')
    Pn_max       = rebar_design.get('Pn_max', phi_Pn_max / 0.65)

    fig = go.Figure()

    if pm_curve_P is not None and pm_curve_M is not None:
        # ── P ≥ 0 영역만 필터 (압축 영역) ───────────────────────────────
        def _filter_compression(M_list, P_list, P_cap):
            """P ≥ 0 포인트만 추출하고 상단 캡 포인트로 닫기"""
            ms, ps = [], []
            for m, p in zip(M_list, P_list):
                if p >= 0:
                    ms.append(m)
                    ps.append(min(p, P_cap))
            # 폐곡선: (0, P_cap) → 곡선 → (Mn_o, 0) → (0, 0) → (0, P_cap)
            closed_M = [0.0] + ms + [ms[-1] if ms else 0.0, 0.0, 0.0]
            closed_P = [P_cap] + ps + [0.0, 0.0, P_cap]
            return closed_M, closed_P

        # ── 공칭강도 곡선 (Pn, Mn) — 파랑 실선 ──────────────────────────
        if pm_nominal_P is not None and pm_nominal_M is not None:
            nom_M, nom_P = _filter_compression(pm_nominal_M, pm_nominal_P, Pn_max)
            fig.add_trace(go.Scatter(
                x=nom_M, y=nom_P,
                mode='lines',
                name='공칭 강도',
                line=dict(color='blue', width=2),
                hovertemplate='Mn = %{x:.1f} kN·m<br>Pn = %{y:.1f} kN<extra></extra>'
            ))

        # ── 설계강도 곡선 (φPn, φMn) — 빨강 실선 ────────────────────────
        des_M, des_P = _filter_compression(pm_curve_M, pm_curve_P, phi_Pn_max)
        fig.add_trace(go.Scatter(
            x=des_M, y=des_P,
            mode='lines',
            name='설계 강도',
            line=dict(color='red', width=2),
            hovertemplate='φMn = %{x:.1f} kN·m<br>φPn = %{y:.1f} kN<extra></extra>'
        ))

        # ── 주요 점 마커 (공칭 곡선 위) ──────────────────────────────────
        key_M = [0.0, phi_Mn_b, phi_Mn_o]
        key_P = [phi_Pn_max, phi_Pn_b, 0.0]
        key_labels = [
            f'A: φPn,max (0, {phi_Pn_max:.1f})',
            f'B: 균형점 ({phi_Mn_b:.1f}, {phi_Pn_b:.1f})',
            f'C: φMn,o ({phi_Mn_o:.1f}, 0)'
        ]
        fig.add_trace(go.Scatter(
            x=key_M, y=key_P,
            mode='markers+text',
            name='주요 점',
            marker=dict(size=8, symbol='circle-open', color='black',
                        line=dict(color='black', width=2)),
            text=key_labels,
            textposition=['top right', 'top right', 'top right'],
            textfont=dict(size=9),
            hovertemplate='%{text}<extra></extra>'
        ))

    else:
        # ── 폴백: 3점 포락선 ─────────────────────────────────────────────
        env_M = [0.0, phi_Mn_b, phi_Mn_o, 0.0]
        env_P = [phi_Pn_max, phi_Pn_b, 0.0, 0.0]
        fig.add_trace(go.Scatter(
            x=env_M, y=env_P,
            mode='lines+markers',
            name='P-M 포락선 (3점 근사)',
            line=dict(color='blue', width=2),
            marker=dict(size=8, symbol='circle', color='blue'),
        ))

    # ── 설계 하중점 ★ ────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=[Mu_d], y=[Pu_d],
        mode='markers',
        name=f'설계점 ({rebar_str})',
        marker=dict(size=14, symbol='star', color='red',
                    line=dict(color='darkred', width=1)),
        hovertemplate=f'설계점<br>Mu = {Mu_d:.2f} kN·m<br>Pu = {Pu_d:.2f} kN<extra></extra>'
    ))

    # ── 판정 텍스트 ──────────────────────────────────────────────────────
    _pm_safe = rebar_design.get('pm_safe', True)
    _ann_x = max(phi_Mn_o * 0.55, Mu_d * 0.5, 10.0)
    _ann_y = (Pn_max if pm_nominal_P else phi_Pn_max) * 0.9
    if _pm_safe:
        _ann_text = f"✅ P-M 검토 OK  {rebar_str}"
        _ann_color = 'green'
    else:
        _ann_text = f"❌ P-M 검토 NG  {rebar_str}"
        _ann_color = 'red'
    fig.add_annotation(
        x=_ann_x, y=_ann_y,
        text=_ann_text,
        showarrow=False,
        font=dict(size=11, color=_ann_color),
        bgcolor='rgba(255,255,255,0.85)',
        bordercolor=_ann_color, borderwidth=1
    )

    # ── 축 참조선 (점선) ─────────────────────────────────────────────────
    _y_top = (Pn_max if pm_nominal_P else phi_Pn_max) * 1.05
    _x_right = max(phi_Mn_o * 1.2, phi_Mn_b * 1.2, Mu_d * 1.15, 10.0)
    fig.add_shape(type='line', x0=0, y0=0, x1=0, y1=_y_top,
                  line=dict(color='gray', dash='dash', width=1))
    fig.add_shape(type='line', x0=0, y0=0, x1=_x_right, y1=0,
                  line=dict(color='gray', dash='dash', width=1))

    fig.update_layout(
        title='기둥 P-M 상관도 (KDS 41 20 20)',
        xaxis_title='Mn (kN·m)',
        yaxis_title='P (kN)',
        height=500,
        legend=dict(x=0.65, y=0.95, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=60, r=20, t=40, b=50),
        hovermode='closest',
        xaxis=dict(rangemode='tozero'),
        yaxis=dict(rangemode='tozero'),
    )
    return fig


def plot_column_section(c_column, n_col, rebar_type_col, rebar_dia, tie_type, tie_dia, tie_spacing):
    """기둥 단면을 그리는 함수"""
    fig = go.Figure()

    # 1. 콘크리트 기둥 (정방형)
    fig.add_shape(type="rect", x0=0, y0=0, x1=c_column, y1=c_column, line=dict(color="#333333", width=3), fillcolor="#E0E0E0", opacity=0.8)

    # 2. 띠철근 (피복두께 40mm 가정)
    cover = 40
    fig.add_shape(type="rect", x0=cover, y0=cover, x1=c_column-cover, y1=cover+tie_dia, fillcolor="DarkGreen", line=dict(width=0)) # 하
    fig.add_shape(type="rect", x0=cover, y0=c_column-cover-tie_dia, x1=c_column-cover, y1=c_column-cover, fillcolor="DarkGreen", line=dict(width=0)) # 상
    fig.add_shape(type="rect", x0=cover, y0=cover, x1=cover+tie_dia, y1=c_column-cover, fillcolor="DarkGreen", line=dict(width=0)) # 좌
    fig.add_shape(type="rect", x0=c_column-cover-tie_dia, y0=cover, x1=c_column-cover, y1=c_column-cover, fillcolor="DarkGreen", line=dict(width=0)) # 우

    # 3. 주철근 배치 (둘레를 따라 균등하게 배치) - 3D 배근 로직과 통일
    off = cover + tie_dia + rebar_dia / 2
    w_inner = c_column - 2 * off

    # Q5 수정: n_col이 4의 배수가 아닐 때(6, 10, 14…) 누락 철근 보정
    n_base = n_col // 4 + 1      # 기준 변 철근 수 (모서리 포함)
    n_extra = n_col % 4          # 추가 철근 수 (0 또는 2)
    n_long = n_base + (1 if n_extra >= 2 else 0)  # 상/하단 행 철근 수

    pos_long = np.linspace(off, c_column - off, n_long)  # 상/하단 행
    pos_base = np.linspace(off, c_column - off, n_base)  # 좌/우단 열

    rebar_coords = []

    # 상단 (Top) & 하단 (Bottom) - n_long개
    for px in pos_long:
        rebar_coords.append((px, off))              # 하단
        rebar_coords.append((px, c_column - off))   # 상단

    # 좌측 (Left) & 우측 (Right) - 모서리 제외 내부만 (n_base - 2개)
    if n_base > 2:
        for py in pos_base[1:-1]:
            rebar_coords.append((off, py))              # 좌측
            rebar_coords.append((c_column - off, py))   # 우측

    # 중복 좌표 제거 (모서리 부분) 및 그리기
    unique_coords = set(rebar_coords)

    for x, y in unique_coords:
        fig.add_shape(type="circle", x0=x-rebar_dia/2, y0=y-rebar_dia/2, x1=x+rebar_dia/2, y1=y+rebar_dia/2, fillcolor="Red", line=dict(color="DarkRed", width=1))

    # 4. 치수선 및 지시선
    fig.add_annotation(x=c_column/2, y=-40, text=f"c = {c_column:.0f}", showarrow=False, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=0, y0=-20, x1=c_column, y1=-20, line=dict(color="black", width=1))
    fig.add_annotation(x=-50, y=c_column/2, text=f"c = {c_column:.0f}", showarrow=False, textangle=-90, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=-30, y0=0, x1=-30, y1=c_column, line=dict(color="black", width=1))

    # 철근 정보
    fig.add_annotation(x=cover, y=c_column-cover, text=f"띠철근 {tie_type} @ {tie_spacing:.0f}", showarrow=True, arrowhead=2, ax=-60, ay=-40)
    fig.add_annotation(x=c_column/2, y=cover+tie_dia+10, text=f"주근 {n_col}-{rebar_type_col}", showarrow=True, arrowhead=2, ax=20, ay=50)

    fig.update_layout(title='기둥 단면', xaxis=dict(visible=False, range=[-150, c_column+100]), yaxis=dict(visible=False, range=[-150, c_column+100], scaleanchor="x"), width=400, height=400)
    return fig

def plot_column_side_view(h_column, c_column, tie_spacing, tie_dia, rebar_dia):
    """기둥 측면을 세로로 그리는 함수"""
    fig = go.Figure()

    # 1. 콘크리트 기둥 (세로형, x축: 폭, y축: 높이)
    fig.add_shape(type="rect", x0=0, y0=0, x1=c_column, y1=h_column, line=dict(color="#333333", width=3), fillcolor="#E0E0E0", opacity=0.8)

    # 2. 주철근 (측면에서 보이는 좌/우 외곽 철근만 붉은 선으로 표현)
    cover = 40
    off = cover + tie_dia + rebar_dia / 2
    fig.add_shape(type="rect", x0=off-rebar_dia/2, y0=0, x1=off+rebar_dia/2, y1=h_column, fillcolor="Red", line=dict(width=0))
    fig.add_shape(type="rect", x0=c_column-off-rebar_dia/2, y0=0, x1=c_column-off+rebar_dia/2, y1=h_column, fillcolor="Red", line=dict(width=0))

    # 3. 띠철근 (가로선으로 높이를 따라 반복)
    num_ties = int(h_column / tie_spacing)
    for i in range(num_ties + 1):
        y_pos = 50 + i * tie_spacing
        if y_pos > h_column - 50: break
        fig.add_shape(type="rect", x0=cover, y0=y_pos-tie_dia/2, x1=c_column-cover, y1=y_pos+tie_dia/2, fillcolor="DarkGreen", line=dict(width=0))

    # 4. 치수선
    fig.add_annotation(x=c_column/2, y=-100, text=f"c = {c_column:.0f}", showarrow=False, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=0, y0=-60, x1=c_column, y1=-60, line=dict(color="black", width=1))

    fig.add_annotation(x=-150, y=h_column/2, text=f"H = {h_column:.0f}", showarrow=False, textangle=-90, font=dict(size=14, color="black"))
    fig.add_shape(type="line", x0=-100, y0=0, x1=-100, y1=h_column, line=dict(color="black", width=1))

    fig.update_layout(title='기둥 측면', xaxis=dict(visible=False, range=[-200, c_column+150]), yaxis=dict(visible=False, range=[-150, h_column+150]), width=300, height=600)
    return fig



def plot_column_3d(h_column, c_column, col_steps):
    """기둥 엔진의 실제 데이터를 받아 3D 배근도를 그리는 함수"""
    fig = go.Figure()

    # 데이터 추출
    n_col = col_steps['n_col']
    rebar_dia = col_steps['rebar_diameter_col']
    tie_dia = col_steps['tie_rebar_diameter']
    tie_spacing = col_steps['tie_rebar_spacing']
    cover = 40

    # 1. 콘크리트 기둥 (투명하게)
    x_c = [0, c_column, c_column, 0, 0, c_column, c_column, 0]
    y_c = [0, 0, c_column, c_column, 0, 0, c_column, c_column]
    z_c = [0, 0, 0, 0, h_column, h_column, h_column, h_column]
    i_c = [7, 0, 0, 0, 4, 4, 2, 6, 2, 1, 1, 6]
    j_c = [3, 4, 1, 2, 5, 6, 1, 1, 0, 0, 5, 5]
    k_c = [0, 7, 2, 3, 6, 7, 4, 5, 7, 2, 6, 4]
    fig.add_trace(go.Mesh3d(x=x_c, y=y_c, z=z_c, i=i_c, j=j_c, k=k_c, color='LightBlue', opacity=0.15, name='콘크리트', hoverinfo='skip'))

    # Helper: 원기둥 그리기 (수직 철근용)
    def create_vertical_cylinder(x_c, y_c, z_start, z_end, r, color):
        theta = np.linspace(0, 2*np.pi, 12)
        z_cyl = np.array([z_start, z_end])
        x_cyl = x_c + r * np.cos(theta)
        y_cyl = y_c + r * np.sin(theta)
        pts = []
        for z_val in z_cyl:
            for j in range(12): pts.append([x_cyl[j], y_cyl[j], z_val])
        pts = np.array(pts)
        i_idx, j_idx, k_idx = [], [], []
        for i in range(12):
            p1, p2 = i, (i+1)%12
            p3, p4 = 12+i, 12+(i+1)%12
            i_idx.extend([p1, p2]); j_idx.extend([p2, p4]); k_idx.extend([p3, p3])
        return go.Mesh3d(x=pts[:,0], y=pts[:,1], z=pts[:,2], i=i_idx, j=j_idx, k=k_idx, color=color, opacity=1.0, hoverinfo='skip')

    # 2. 주철근 (수직 배열) - Q5 수정: n_col이 4의 배수 아닐 때 누락 보정
    off = cover + tie_dia + rebar_dia / 2

    n_base = n_col // 4 + 1      # 기준 변 철근 수 (모서리 포함)
    n_extra = n_col % 4          # 추가 철근 수 (0 또는 2)
    n_long = n_base + (1 if n_extra >= 2 else 0)  # 상/하단 행 철근 수

    pos_long = np.linspace(off, c_column - off, n_long)  # 상/하단 행
    pos_base = np.linspace(off, c_column - off, n_base)  # 좌/우단 열

    rebar_coords = []

    # 상단 (Top) & 하단 (Bottom) - n_long개
    for px in pos_long:
        rebar_coords.append((px, off))              # 하단
        rebar_coords.append((px, c_column - off))   # 상단

    # 좌측 (Left) & 우측 (Right) - 모서리 제외 내부만
    if n_base > 2:
        for py in pos_base[1:-1]:
            rebar_coords.append((off, py))              # 좌측
            rebar_coords.append((c_column - off, py))   # 우측

    unique_coords = set(rebar_coords)

    for x, y in unique_coords:
        fig.add_trace(create_vertical_cylinder(x, y, 0, h_column, rebar_dia/2, 'Red'))

    # 3. 띠철근 (Hollow Box 형태)
    def add_horizontal_box(x0, x1, y0, y1, z_center, t, vx, vy, vz, ii, jj, kk):
        z0, z1 = z_center - t/2, z_center + t/2
        x0i, x1i = x0 + t, x1 - t
        y0i, y1i = y0 + t, y1 - t

        def add_segment(sx0, sx1, sy0, sy1):
            off = len(vx)
            vx.extend([sx0, sx1, sx1, sx0, sx0, sx1, sx1, sx0])
            vy.extend([sy0, sy0, sy1, sy1, sy0, sy0, sy1, sy1])
            vz.extend([z0, z0, z0, z0, z1, z1, z1, z1])
            faces_i = [0, 0, 4, 4, 0, 0, 3, 3, 0, 0, 1, 1]
            faces_j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 2, 6]
            faces_k = [2, 3, 6, 7, 5, 4, 6, 7, 7, 4, 6, 5]
            ii.extend([off+v for v in faces_i])
            jj.extend([off+v for v in faces_j])
            kk.extend([off+v for v in faces_k])

        add_segment(x0, x1, y0, y0i) # Bottom edge
        add_segment(x0, x1, y1i, y1) # Top edge
        add_segment(x0, x0i, y0i, y1i) # Left edge
        add_segment(x1i, x1, y0i, y1i) # Right edge

    vx, vy, vz, ii, jj, kk = [], [], [], [], [], []
    num_ties = int(h_column / tie_spacing)
    for i in range(num_ties + 1):
        z_pos = 50 + i * tie_spacing
        if z_pos > h_column - 50: break
        add_horizontal_box(cover, c_column-cover, cover, c_column-cover, z_pos, tie_dia, vx, vy, vz, ii, jj, kk)

    if len(vx) > 0:
        fig.add_trace(go.Mesh3d(x=vx, y=vy, z=vz, i=ii, j=jj, k=kk, color='DarkGreen', opacity=0.8, hoverinfo='skip'))

    fig.update_layout(title='기둥 3D 배근', scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), width=400, height=600)
    return fig
