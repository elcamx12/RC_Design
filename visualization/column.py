import plotly.graph_objects as go  # P-M, 3D용 유지
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
matplotlib.rcParams['font.family'] = ['NanumGothic', 'Malgun Gothic', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False

def plot_pm_diagram(rebar_design, axial_moment):
    """BeST.RC 스타일 P-M 상관도 — 공칭강도(빨강) vs 설계강도(파랑)

    Parameters
    ----------
    rebar_design : dict
        column_engine.calculate_rebar_design() 반환 dict.
    axial_moment : dict
        column_engine.calculate_axial_load_and_moment() 반환 dict.
    """
    phi_Pn_max = rebar_design['phi_Pn_max']
    phi_Pn_b   = rebar_design['phi_Pn_b']
    phi_Mn_b   = rebar_design['phi_Mn_b']
    phi_Mn_o   = rebar_design['phi_Mn_o']
    Mu_d       = rebar_design['Mu_design']
    Pu_d       = axial_moment['Pu']
    rebar_str  = rebar_design.get('rebar_string_col', '')

    pm_curve_P   = rebar_design.get('pm_curve_P')
    pm_curve_M   = rebar_design.get('pm_curve_M')
    pm_nominal_P = rebar_design.get('pm_nominal_P')
    pm_nominal_M = rebar_design.get('pm_nominal_M')
    Pn_max       = rebar_design.get('Pn_max', phi_Pn_max / 0.65)

    fig = go.Figure()

    if pm_curve_P is not None and pm_curve_M is not None:
        # ── 공칭강도 곡선 (Pn, Mn) — 빨강 실선 (BeST 스타일) ────────
        if pm_nominal_P is not None and pm_nominal_M is not None:
            nom_M = list(pm_nominal_M)
            nom_P = list(pm_nominal_P)
            # 상단 캡: (0, Pn_max)으로 시작 — 첫 점의 M > 0이면 삽입
            if nom_M and nom_M[0] > 0.1:
                nom_M.insert(0, 0.0)
                nom_P.insert(0, Pn_max)
            fig.add_trace(go.Scatter(
                x=nom_M, y=nom_P,
                mode='lines',
                name='Nominal (Pn, Mn)',
                line=dict(color='red', width=2),
                hovertemplate='Mn = %{x:.1f} kN·m<br>Pn = %{y:.1f} kN<extra></extra>'
            ))

        # ── 설계강도 곡선 (φPn, φMn) — 파랑 실선 (BeST 스타일) ──────
        des_M = list(pm_curve_M)
        des_P = list(pm_curve_P)
        # 상단 캡: (0, φPn_max)으로 시작 — 첫 점의 M > 0이면 삽입
        if des_M and des_M[0] > 0.1:
            des_M.insert(0, 0.0)
            des_P.insert(0, phi_Pn_max)
        fig.add_trace(go.Scatter(
            x=des_M, y=des_P,
            mode='lines',
            name='Design (φPn, φMn)',
            line=dict(color='blue', width=2),
            hovertemplate='φMn = %{x:.1f} kN·m<br>φPn = %{y:.1f} kN<extra></extra>'
        ))

    else:
        # ── 폴백: 3점 포락선 ─────────────────────────────────────────────
        env_M = [0.0, phi_Mn_b, phi_Mn_o, 0.0]
        env_P = [phi_Pn_max, phi_Pn_b, 0.0, 0.0]
        fig.add_trace(go.Scatter(
            x=env_M, y=env_P,
            mode='lines+markers',
            name='P-M Envelope (3-point)',
            line=dict(color='blue', width=2),
            marker=dict(size=8, symbol='circle', color='blue'),
        ))

    # ── 설계점 — 빨간 십자(+) + 중앙 점 + 좌표 텍스트 (BeST 스타일) ──
    fig.add_trace(go.Scatter(
        x=[Mu_d], y=[Pu_d],
        mode='markers+text',
        name=f'Design Point ({rebar_str})',
        marker=dict(size=12, symbol='cross-thin', color='red',
                    line=dict(color='red', width=2)),
        text=[f'({Mu_d:.0f}, {Pu_d:.0f})'],
        textposition='bottom right',
        textfont=dict(size=10, color='#008080'),
        hovertemplate=f'Design Point<br>Mu = {Mu_d:.2f} kN·m<br>Pu = {Pu_d:.2f} kN<extra></extra>'
    ))
    # 중앙 빨간 점
    fig.add_trace(go.Scatter(
        x=[Mu_d], y=[Pu_d],
        mode='markers',
        name='',
        marker=dict(size=5, color='red'),
        showlegend=False,
        hoverinfo='skip'
    ))

    # (판정 텍스트 제거 — BeST 스타일에 없음)

    # ── 레이아웃 — 초록 격자 (BeST 스타일) ───────────────────────────────
    fig.update_layout(
        title='Column P-M Diagram (KDS 41 20 20)',
        xaxis_title='Mu (kN·m)',
        yaxis_title='Pu (kN)',
        height=500,
        legend=dict(x=0.60, y=0.98, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=60, r=20, t=40, b=50),
        hovermode='closest',
        plot_bgcolor='white',
        xaxis=dict(
            showgrid=True, gridcolor='rgba(0,180,0,0.25)', gridwidth=1,
            zeroline=True, zerolinecolor='gray', zerolinewidth=1,
            rangemode='tozero',
        ),
        yaxis=dict(
            showgrid=True, gridcolor='rgba(0,180,0,0.25)', gridwidth=1,
            zeroline=True, zerolinecolor='gray', zerolinewidth=1,
        ),
    )
    return fig


def plot_column_section(c_column, n_col, rebar_type_col, rebar_dia, tie_type, tie_dia, tie_spacing):
    """기둥 단면 — Matplotlib 렌더링"""
    fig, ax = plt.subplots(1, 1, figsize=(5, 5), dpi=150)
    ax.set_aspect('equal')
    ax.set_axis_off()

    # 1. 콘크리트 (연한 파랑 MIDAS 스타일)
    ax.add_patch(mpatches.Rectangle((0, 0), c_column, c_column,
                 facecolor='#D6EAF8', edgecolor='#2255CC', linewidth=2.5))

    # 2. 띠철근 (주근 외경 감싸는 사각형)
    cover = 40
    off = cover + tie_dia + rebar_dia / 2
    ax.add_patch(mpatches.Rectangle((off - rebar_dia/2, off - rebar_dia/2),
                 c_column - 2*(off - rebar_dia/2), c_column - 2*(off - rebar_dia/2),
                 facecolor='none', edgecolor='#CC6600', linewidth=1.5))

    # 3. 주철근 배치 (Q5 수정 포함)
    n_base = n_col // 4 + 1
    n_extra = n_col % 4
    n_long = n_base + (1 if n_extra >= 2 else 0)
    pos_long = np.linspace(off, c_column - off, n_long)
    pos_base = np.linspace(off, c_column - off, n_base)

    rebar_coords = []
    for px in pos_long:
        rebar_coords.append((px, off))
        rebar_coords.append((px, c_column - off))
    if n_base > 2:
        for py in pos_base[1:-1]:
            rebar_coords.append((off, py))
            rebar_coords.append((c_column - off, py))

    for x, y in set(rebar_coords):
        ax.add_patch(mpatches.Circle((x, y), rebar_dia / 2,
                     facecolor='#CC0000', edgecolor='#990000', linewidth=1))

    # 4. 치수선
    _dot_r = 2.0
    _dx = -30
    ax.plot([_dx, _dx], [0, c_column], color='#444444', linewidth=1)
    for _yt in [0, c_column]:
        ax.plot([_dx-5, _dx+5], [_yt, _yt], color='#444444', linewidth=1)
        ax.add_patch(mpatches.Circle((_dx, _yt), _dot_r, facecolor='#444444', edgecolor='none'))
    ax.text(_dx-14, c_column/2, f"{c_column/1000:.2f}", fontsize=8, color='#444444',
            ha='center', va='center', rotation=90)

    _dy = -20
    ax.plot([0, c_column], [_dy, _dy], color='#444444', linewidth=1)
    for _xt in [0, c_column]:
        ax.plot([_xt, _xt], [_dy-5, _dy+5], color='#444444', linewidth=1)
        ax.add_patch(mpatches.Circle((_xt, _dy), _dot_r, facecolor='#444444', edgecolor='none'))
    ax.text(c_column/2, _dy-14, f"{c_column/1000:.2f}", fontsize=8, color='#444444',
            ha='center', va='center')

    # 5. 하단 텍스트 (보 스타일: MAIN / TIE)
    _info = [f"MAIN   {n_col}-{rebar_type_col}",
             f"TIE    {tie_type} @{tie_spacing:.0f}"]
    for _li, _lt in enumerate(_info):
        ax.text(c_column / 2, _dy - 35 - _li * 18, _lt,
                fontsize=7, color='black', ha='center', va='top', family='monospace',
                fontweight='bold')

    ax.set_xlim(-80, c_column + 80)
    ax.set_ylim(-90, c_column + 50)
    ax.set_title('Column Section', fontsize=10, family='monospace')
    fig.tight_layout()
    return fig

def plot_column_side_view(h_column, c_column, tie_spacing, tie_dia, rebar_dia):
    """기둥 측면 — Matplotlib 렌더링"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 7), dpi=150)
    ax.set_aspect('equal')
    ax.set_axis_off()

    # 1. 콘크리트
    ax.add_patch(mpatches.Rectangle((0, 0), c_column, h_column,
                 facecolor='#D6EAF8', edgecolor='#222222', linewidth=2.5))

    # 2. 주철근 (좌/우 외곽)
    cover = 40
    off = cover + tie_dia + rebar_dia / 2
    ax.add_patch(mpatches.Rectangle((off - rebar_dia/2, 0), rebar_dia, h_column,
                 facecolor='#333333', edgecolor='none'))
    ax.add_patch(mpatches.Rectangle((c_column - off - rebar_dia/2, 0), rebar_dia, h_column,
                 facecolor='#333333', edgecolor='none'))

    # 3. 띠철근
    num_ties = int(h_column / tie_spacing) if tie_spacing > 0 else 0
    for i in range(num_ties + 1):
        y_pos = 50 + i * tie_spacing
        if y_pos > h_column - 50:
            break
        ax.add_patch(mpatches.Rectangle((cover, y_pos - tie_dia/2),
                     c_column - 2*cover, tie_dia,
                     facecolor='#555555', edgecolor='none'))

    # 4. 치수선
    _dx = -30
    ax.plot([_dx, _dx], [0, h_column], color='#444444', linewidth=1)
    for _yt in [0, h_column]:
        ax.plot([_dx-5, _dx+5], [_yt, _yt], color='#444444', linewidth=1)
    ax.text(_dx-14, h_column/2, f"H={h_column:.0f}", fontsize=8, color='#444444',
            ha='center', va='center', rotation=90)

    _dy = -40
    ax.plot([0, c_column], [_dy, _dy], color='#444444', linewidth=1)
    for _xt in [0, c_column]:
        ax.plot([_xt, _xt], [_dy-5, _dy+5], color='#444444', linewidth=1)
    ax.text(c_column/2, _dy-14, f"c={c_column:.0f}", fontsize=8, color='#444444',
            ha='center', va='center')

    ax.set_xlim(-80, c_column + 50)
    ax.set_ylim(-80, h_column + 50)
    ax.set_title('Column Side View', fontsize=10, family='monospace')
    fig.tight_layout()
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
    fig.add_trace(go.Mesh3d(x=x_c, y=y_c, z=z_c, i=i_c, j=j_c, k=k_c, color='#D0D0D0', opacity=0.15, name='콘크리트', hoverinfo='skip'))

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
        fig.add_trace(create_vertical_cylinder(x, y, 0, h_column, rebar_dia/2, '#333333'))

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
    num_ties = int(h_column / tie_spacing) if tie_spacing > 0 else 0
    for i in range(num_ties + 1):
        z_pos = 50 + i * tie_spacing
        if z_pos > h_column - 50: break
        add_horizontal_box(cover, c_column-cover, cover, c_column-cover, z_pos, tie_dia, vx, vy, vz, ii, jj, kk)

    if len(vx) > 0:
        fig.add_trace(go.Mesh3d(x=vx, y=vy, z=vz, i=ii, j=jj, k=kk, color='#555555', opacity=0.8, hoverinfo='skip'))

    fig.update_layout(title='Column 3D Rebar', scene=dict(aspectmode='data', xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False)), width=400, height=600)
    return fig
