import plotly.graph_objects as go
import numpy as np

from .helpers import create_box, add_diagram_ribbon, add_vertical_diagram, add_cylinder_to_mesh

def plot_3d_frame_forces(results, inputs, vis_options):
    fig = go.Figure()

    # 1. 제원 데이터 추출
    Lx = inputs['L_x']
    Ly = inputs['L_y']
    H = inputs['h_column']

    # 다중 기둥 지원: columns 리스트에서 순환하여 각 코너에 매핑
    _all_cols = results.get('columns', [results['column']])
    c_w = max(c['dimensions']['c_column'] for c in _all_cols)  # 최대 단면으로 뼈대 표현
    # 상부보 치수
    bx_w = results['beam_x']['design_params']['b_beam']
    bx_h = results['beam_x']['design_params']['h_beam']
    by_w = results['beam_y']['design_params']['b_beam']
    by_h = results['beam_y']['design_params']['h_beam']
    # 바닥보 치수 (독립 설계 결과, 없으면 천장보와 동일)
    _gbx = results.get('ground_beam_x')
    _gby = results.get('ground_beam_y')
    gbx_w = _gbx['design_params']['b_beam'] if _gbx else bx_w
    gbx_h = _gbx['design_params']['h_beam'] if _gbx else bx_h
    gby_w = _gby['design_params']['b_beam'] if _gby else by_w
    gby_h = _gby['design_params']['h_beam'] if _gby else by_h

    # 2. 3D 콘크리트 뼈대 그리기 (4기둥, 8보: 상부 4 + 바닥 4)
    # 기둥 4개 (C1: 원점, C2: X축, C3: 대각, C4: Y축)
    col_coords = [(0,0), (Lx,0), (Lx,Ly), (0,Ly)]
    for _ci, (cx, cy) in enumerate(col_coords):
        _this_col = _all_cols[_ci % len(_all_cols)]
        _c_w_i = _this_col['dimensions']['c_column']
        fig.add_trace(create_box(cx - _c_w_i/2, cy - _c_w_i/2, 0, _c_w_i, _c_w_i, H, color='#A0A0A0'))

        # 기둥 꼭대기에 기둥명 + 설계 하중 텍스트 표시
        Pu = _this_col['axial_moment']['Pu']
        Mu = _this_col['axial_moment']['Mu']
        _col_name = _this_col.get('col_name', f'기둥 {_ci+1}')
        mb = _this_col.get('mu_breakdown', {})
        _mux = mb.get('Mux_total', Mu)
        _muy = mb.get('Muy_total', 0.0)
        txt = f"{_col_name}<br>Pu={Pu:.0f}kN<br>Mux={_mux:.0f} / Muy={_muy:.0f}kN·m"
        fig.add_trace(go.Scatter3d(x=[cx], y=[cy], z=[H + 500], mode='text+markers', text=[txt], textfont=dict(color='purple', size=11), marker=dict(size=4, color='purple'), showlegend=False, hoverinfo='skip'))

    # 상부 X방향 보 2개 (앞, 뒤)
    fig.add_trace(create_box(0, 0 - bx_w/2, H - bx_h, Lx, bx_w, bx_h, color='#C0C0C0'))
    fig.add_trace(create_box(0, Ly - bx_w/2, H - bx_h, Lx, bx_w, bx_h, color='#C0C0C0'))

    # 상부 Y방향 보 2개 (좌, 우)
    fig.add_trace(create_box(0 - by_w/2, 0, H - by_h, by_w, Ly, by_h, color='#B8B8B8'))
    fig.add_trace(create_box(Lx - by_w/2, 0, H - by_h, by_w, Ly, by_h, color='#B8B8B8'))

    # 바닥보 X방향 2개 (앞, 뒤) — 바닥보 독립 설계 치수 사용
    fig.add_trace(create_box(0, 0 - gbx_w/2, 0, Lx, gbx_w, gbx_h, color='#C0C0C0'))
    fig.add_trace(create_box(0, Ly - gbx_w/2, 0, Lx, gbx_w, gbx_h, color='#C0C0C0'))

    # 바닥보 Y방향 2개 (좌, 우) — 바닥보 독립 설계 치수 사용
    fig.add_trace(create_box(0 - gby_w/2, 0, 0, gby_w, Ly, gby_h, color='#B8B8B8'))
    fig.add_trace(create_box(Lx - gby_w/2, 0, 0, gby_w, Ly, gby_h, color='#B8B8B8'))

    # 3. 부재력도 (SFD/BMD) 그리기
    steps_x = results['beam_x']['member_forces']['x_steps']
    steps_y = results['beam_y']['member_forces']['x_steps']
    # 바닥보 부재력 x_steps (없으면 천장보 폴백)
    _gbx_mf = _gbx['member_forces'] if _gbx else results['beam_x']['member_forces']
    _gby_mf = _gby['member_forces'] if _gby else results['beam_y']['member_forces']
    gb_steps_x = _gbx_mf['x_steps']
    gb_steps_y = _gby_mf['x_steps']

    # 상부보 다이어그램의 Z 기준선: 보 중앙 높이 (보 상단이 아닌 도심)
    z_center_x_top = H - bx_h / 2.0  # X방향 상부보 중앙 높이
    z_center_y_top = H - by_h / 2.0  # Y방향 상부보 중앙 높이
    # 바닥보 다이어그램의 Z 기준선 — 바닥보 독립 설계 높이 사용
    z_center_x_bot = gbx_h / 2.0
    z_center_y_bot = gby_h / 2.0

    # 보 BMD 그리기
    if "보 BMD" in vis_options:
        x_vals = results['beam_x']['member_forces']['BMD']
        y_vals = results['beam_y']['member_forces']['BMD']
        # 바닥보 BMD (독립 하중/부재력 사용, 없으면 천장보 폴백)
        gx_vals = _gbx_mf['BMD']
        gy_vals = _gby_mf['BMD']
        all_vals = list(np.abs(x_vals)) + list(np.abs(y_vals)) + list(np.abs(gx_vals)) + list(np.abs(gy_vals))
        max_val = max(all_vals) if all_vals else 1.0
        scale = (H / 3.0) / max_val if max_val > 0 else 1.0

        x_plot  = [-v for v in x_vals]
        y_plot  = [-v for v in y_vals]
        gx_plot = [-v for v in gx_vals]
        gy_plot = [-v for v in gy_vals]

        # 상부보 BMD
        add_diagram_ribbon(fig, steps_x * 1000, np.full_like(steps_x, 0), np.full_like(steps_x, z_center_x_top), x_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, steps_x * 1000, np.full_like(steps_x, Ly), np.full_like(steps_x, z_center_x_top), x_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(steps_y, 0), steps_y * 1000, np.full_like(steps_y, z_center_y_top), y_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(steps_y, Lx), steps_y * 1000, np.full_like(steps_y, z_center_y_top), y_plot, 'red', scale, direction='Z')

        # 바닥보 BMD (독립 부재력 사용)
        add_diagram_ribbon(fig, gb_steps_x * 1000, np.full_like(gb_steps_x, 0), np.full_like(gb_steps_x, z_center_x_bot), gx_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, gb_steps_x * 1000, np.full_like(gb_steps_x, Ly), np.full_like(gb_steps_x, z_center_x_bot), gx_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(gb_steps_y, 0), gb_steps_y * 1000, np.full_like(gb_steps_y, z_center_y_bot), gy_plot, 'red', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(gb_steps_y, Lx), gb_steps_y * 1000, np.full_like(gb_steps_y, z_center_y_bot), gy_plot, 'red', scale, direction='Z')

    # 보 SFD 그리기
    if "보 SFD" in vis_options:
        x_vals = results['beam_x']['member_forces']['SFD']
        y_vals = results['beam_y']['member_forces']['SFD']
        gx_vals = _gbx_mf['SFD']
        gy_vals = _gby_mf['SFD']
        all_vals = list(np.abs(x_vals)) + list(np.abs(y_vals)) + list(np.abs(gx_vals)) + list(np.abs(gy_vals))
        max_val = max(all_vals) if all_vals else 1.0
        scale = (H / 3.0) / max_val if max_val > 0 else 1.0

        # 상부보 SFD
        add_diagram_ribbon(fig, steps_x * 1000, np.full_like(steps_x, 0), np.full_like(steps_x, z_center_x_top), x_vals, 'blue', scale, direction='Z')
        add_diagram_ribbon(fig, steps_x * 1000, np.full_like(steps_x, Ly), np.full_like(steps_x, z_center_x_top), x_vals, 'blue', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(steps_y, 0), steps_y * 1000, np.full_like(steps_y, z_center_y_top), y_vals, 'green', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(steps_y, Lx), steps_y * 1000, np.full_like(steps_y, z_center_y_top), y_vals, 'green', scale, direction='Z')

        # 바닥보 SFD (독립 부재력 사용)
        add_diagram_ribbon(fig, gb_steps_x * 1000, np.full_like(gb_steps_x, 0), np.full_like(gb_steps_x, z_center_x_bot), gx_vals, 'blue', scale, direction='Z')
        add_diagram_ribbon(fig, gb_steps_x * 1000, np.full_like(gb_steps_x, Ly), np.full_like(gb_steps_x, z_center_x_bot), gx_vals, 'blue', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(gb_steps_y, 0), gb_steps_y * 1000, np.full_like(gb_steps_y, z_center_y_bot), gy_vals, 'green', scale, direction='Z')
        add_diagram_ribbon(fig, np.full_like(gb_steps_y, Lx), gb_steps_y * 1000, np.full_like(gb_steps_y, z_center_y_bot), gy_vals, 'green', scale, direction='Z')

    # 기둥 AFD 그리기 — 각 코너별 해당 기둥 데이터 사용
    if "기둥 AFD" in vis_options:
        # 스케일은 전체 기둥 중 최대값 기준
        _all_afd = [v for c in _all_cols for v in np.abs(c['member_forces']['AFD'])]
        max_val = max(_all_afd) if _all_afd else 1.0
        scale = (Lx / 5.0) / max_val if max_val > 0 else 1.0
        for _ci, (cx, cy) in enumerate(col_coords):
            _this_col = _all_cols[_ci % len(_all_cols)]
            z_steps  = _this_col['member_forces']['z_steps'] * 1000
            afd_vals = _this_col['member_forces']['AFD']
            add_vertical_diagram(fig, cx, cy, z_steps, afd_vals, 'orange', scale, direction='X')

    # 기둥 BMD 그리기 — 각 코너별 해당 기둥 데이터 사용 (Muy→Y방향, Mux→X방향 분리)
    if "기둥 BMD" in vis_options:
        _all_bmd = [v for c in _all_cols for v in np.abs(c['member_forces']['BMD'])]
        max_val = max(_all_bmd) if _all_bmd else 1.0
        scale = (Lx / 5.0) / max_val if max_val > 0 else 1.0
        for _ci, (cx, cy) in enumerate(col_coords):
            _this_col = _all_cols[_ci % len(_all_cols)]
            z_steps  = _this_col['member_forces']['z_steps'] * 1000
            bmd_vals = np.array(_this_col['member_forces']['BMD'])
            _mb = _this_col.get('mu_breakdown', {})
            _mux_t = abs(float(_mb.get('Mux_total', 0.0)))
            _muy_t = abs(float(_mb.get('Muy_total', 0.0)))
            _mu_d  = abs(float(_mb.get('Mu_design', 0.0)))
            if _mux_t + _muy_t > 0 and _mu_d > 0:
                # 두 방향 BMD를 비율로 분리하여 각 방향으로 표시
                add_vertical_diagram(fig, cx, cy, z_steps, bmd_vals * (_muy_t / _mu_d), 'purple', scale, direction='Y')
                add_vertical_diagram(fig, cx, cy, z_steps, bmd_vals * (_mux_t / _mu_d), 'darkviolet', scale, direction='X')
            else:
                # 단축 모멘트: 기존 Y방향으로 표시
                add_vertical_diagram(fig, cx, cy, z_steps, bmd_vals, 'purple', scale, direction='Y')

    # 4. 치수 표기 (dimension lines) — 그리드 대신 사용
    _dim_off = min(Lx, Ly) * 0.18  # 치수선 오프셋 (프레임 바깥쪽)
    _tick_l  = min(Lx, Ly) * 0.04  # 끝 짧은 틱 길이
    _txt_col = '#555555'

    # Lx 치수선 (y = -_dim_off 위치, z = 0)
    fig.add_trace(go.Scatter3d(x=[0, Lx], y=[-_dim_off]*2, z=[0, 0],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[Lx/2], y=[-_dim_off], z=[0],
        mode='text', text=[f'Lx = {Lx/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _xx in [0, Lx]:  # 끝 틱
        fig.add_trace(go.Scatter3d(x=[_xx]*2, y=[-_dim_off-_tick_l, -_dim_off+_tick_l], z=[0, 0],
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # Ly 치수선 (x = -_dim_off 위치, z = 0)
    fig.add_trace(go.Scatter3d(x=[-_dim_off]*2, y=[0, Ly], z=[0, 0],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[-_dim_off], y=[Ly/2], z=[0],
        mode='text', text=[f'Ly = {Ly/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _yy in [0, Ly]:
        fig.add_trace(go.Scatter3d(x=[-_dim_off-_tick_l, -_dim_off+_tick_l], y=[_yy]*2, z=[0, 0],
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # H 치수선 (x = Lx + _dim_off 위치, y = 0)
    fig.add_trace(go.Scatter3d(x=[Lx+_dim_off]*2, y=[0, 0], z=[0, H],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[Lx+_dim_off], y=[0], z=[H/2],
        mode='text', text=[f'H = {H/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _zz in [0, H]:
        fig.add_trace(go.Scatter3d(x=[Lx+_dim_off-_tick_l, Lx+_dim_off+_tick_l], y=[0, 0], z=[_zz]*2,
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # 5. 범례 (선택된 부재력도에 대한 색상 설명)
    _legend_items = []
    if "보 BMD" in vis_options:
        _legend_items.append(('red', '보 BMD (kN·m)'))
    if "보 SFD" in vis_options:
        _legend_items.append(('blue', 'X보 SFD (kN)'))
        _legend_items.append(('green', 'Y보 SFD (kN)'))
    if "기둥 AFD" in vis_options:
        _legend_items.append(('orange', '기둥 AFD (kN)'))
    if "기둥 BMD" in vis_options:
        _legend_items.append(('purple', '기둥 BMD-Y (kN·m)'))
        _legend_items.append(('darkviolet', '기둥 BMD-X (kN·m)'))
    for _lc, _ln in _legend_items:
        fig.add_trace(go.Scatter3d(
            x=[None], y=[None], z=[None],
            mode='lines', name=_ln,
            line=dict(color=_lc, width=4),
            showlegend=True
        ))

    # 6. 레이아웃 — 그리드 제거 + 축 라벨 숨김
    _no_axis = dict(showgrid=False, showbackground=False, zeroline=False,
                    showticklabels=False, showline=False, title='')
    fig.update_layout(
        title='3D Modular Frame Forces',
        scene=dict(
            xaxis=_no_axis,
            yaxis=_no_axis,
            zaxis=_no_axis,
            aspectmode='data'
        ),
        margin=dict(l=0, r=0, b=0, t=40),
        height=700,
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.8)',
                    font=dict(size=11))
    )

    return fig

def plot_3d_frame_rebar(results, inputs):
    fig = go.Figure()

    # 1. 제원 및 데이터 추출
    Lx, Ly, H = inputs['L_x'], inputs['L_y'], inputs['h_column']
    cw = results['column']['dimensions']['c_column']
    bx_w, bx_h = results['beam_x']['design_params']['b_beam'], results['beam_x']['design_params']['h_beam']
    by_w, by_h = results['beam_y']['design_params']['b_beam'], results['beam_y']['design_params']['h_beam']
    # 바닥보 독립 설계 치수 (없으면 천장보 폴백)
    _gbx_r = results.get('ground_beam_x')
    _gby_r = results.get('ground_beam_y')
    gbx_w = _gbx_r['design_params']['b_beam'] if _gbx_r else bx_w
    gbx_h = _gbx_r['design_params']['h_beam'] if _gbx_r else bx_h
    gby_w = _gby_r['design_params']['b_beam'] if _gby_r else by_w
    gby_h = _gby_r['design_params']['h_beam'] if _gby_r else by_h

    # 2. 콘크리트 외형 (투명 렌더링) — 다중 기둥 지원
    _all_cols_r = results.get('columns', [results['column']])
    col_coords = [(0,0), (Lx,0), (Lx,Ly), (0,Ly)]
    for _ci, (cx, cy) in enumerate(col_coords):
        _cw_i = _all_cols_r[_ci % len(_all_cols_r)]['dimensions']['c_column']
        fig.add_trace(create_box(cx - _cw_i/2, cy - _cw_i/2, 0, _cw_i, _cw_i, H, color='rgba(200, 200, 200, 0.1)'))

    # 상부보
    fig.add_trace(create_box(0, -bx_w/2, H - bx_h, Lx, bx_w, bx_h, color='rgba(100, 149, 237, 0.05)')) # X보 앞
    fig.add_trace(create_box(0, Ly-bx_w/2, H - bx_h, Lx, bx_w, bx_h, color='rgba(100, 149, 237, 0.05)')) # X보 뒤
    fig.add_trace(create_box(-by_w/2, 0, H - by_h, by_w, Ly, by_h, color='rgba(60, 179, 113, 0.05)')) # Y보 좌
    fig.add_trace(create_box(Lx-by_w/2, 0, H - by_h, by_w, Ly, by_h, color='rgba(60, 179, 113, 0.05)')) # Y보 우
    # 바닥보 — 바닥보 독립 설계 치수 사용 (V1 수정)
    fig.add_trace(create_box(0, -gbx_w/2, 0, Lx, gbx_w, gbx_h, color='rgba(100, 149, 237, 0.05)')) # 바닥 X보 앞
    fig.add_trace(create_box(0, Ly-gbx_w/2, 0, Lx, gbx_w, gbx_h, color='rgba(100, 149, 237, 0.05)')) # 바닥 X보 뒤
    fig.add_trace(create_box(-gby_w/2, 0, 0, gby_w, Ly, gby_h, color='rgba(60, 179, 113, 0.05)')) # 바닥 Y보 좌
    fig.add_trace(create_box(Lx-gby_w/2, 0, 0, gby_w, Ly, gby_h, color='rgba(60, 179, 113, 0.05)')) # 바닥 Y보 우
    # 슬래브 (상부층 + 바닥층)
    _slab_data = results.get('slab')
    if _slab_data:
        _t_slab = _slab_data['design_params']['t_slab']
        fig.add_trace(create_box(0, 0, H - _t_slab, Lx, Ly, _t_slab, color='rgba(255, 200, 100, 0.04)'))
        _ground_slab_z = max(gbx_h, gby_h)
        fig.add_trace(create_box(0, 0, _ground_slab_z - _t_slab, Lx, Ly, _t_slab, color='rgba(255, 200, 100, 0.04)'))

    # 3. 철근 배치 로직 (Mesh3d로 통합하여 렌더링 성능 최적화)
    # cover: beam_engine / column_engine 실제 값과 일관성 유지
    cover = results['beam_x']['rebar_steps_bot']['cover']

    # 메쉬 데이터 저장소
    vx_main, vy_main, vz_main = [], [], []
    ii_main, jj_main, kk_main = [], [], []

    vx_tie, vy_tie, vz_tie = [], [], []
    ii_tie, jj_tie, kk_tie = [], [], []

    # --- 기둥 철근 --- 각 코너별 해당 기둥 데이터 사용
    for _ci, (cx, cy) in enumerate(col_coords):
        _this_col_r = _all_cols_r[_ci % len(_all_cols_r)]
        cw = _this_col_r['dimensions']['c_column']  # 해당 기둥 단면 크기
        c_design = _this_col_r['rebar_design']
        n_col = c_design.get('n_col', 8)
        r_dia = c_design.get('rebar_diameter_col', 22)
        tie_dia = _this_col_r['tie_rebar_design'].get('tie_rebar_diameter', 10)
        tie_spacing = _this_col_r['tie_rebar_design'].get('tie_rebar_spacing', 300)

        # 1. 기둥 주철근 (Main Bars) - 띠철근 안쪽에 배치
        main_bar_offset = cover + tie_dia + r_dia/2

        # Q5 수정: n_col이 4의 배수가 아닐 때(6, 10, 14…) 누락 철근 보정
        n_base = n_col // 4 + 1      # 기준 변 철근 수 (모서리 포함)
        n_extra = n_col % 4          # 추가 철근 수 (0 또는 2)
        n_long = n_base + (1 if n_extra >= 2 else 0)  # 좌/우 면에 배치될 철근 수
        limit = cw/2 - main_bar_offset
        pos_long = np.linspace(-limit, limit, n_long)  # x=±limit 면 (좌/우)
        pos_base = np.linspace(-limit, limit, n_base)  # y=±limit 면 (전/후)

        # 4면 테두리에 정확히 n_col개 배치
        main_bars_xy = []
        for px in [pos_long[0], pos_long[-1]]:   # 좌/우 면: n_long개씩
            for py in pos_long: main_bars_xy.append((px, py))
        for py in [pos_base[0], pos_base[-1]]:   # 전/후 면: 모서리 제외 내부만
            for px in pos_base[1:-1]: main_bars_xy.append((px, py))

        for px, py in main_bars_xy:
            add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                 (cx+px, cy+py, 0), (cx+px, cy+py, H), r_dia/2)

        # 2. 기둥 띠철근 (Ties) - 주철근을 감싸는 위치
        tie_offset = cover + tie_dia/2
        tie_z_locs = np.arange(100, H, tie_spacing)

        # 기둥 중심(cx, cy) 기준 사각형 오프셋
        half_w = cw/2 - tie_offset

        for tz in tie_z_locs:
            p1 = (cx-half_w, cy-half_w, tz)
            p2 = (cx+half_w, cy-half_w, tz)
            p3 = (cx+half_w, cy+half_w, tz)
            p4 = (cx-half_w, cy+half_w, tz)

            # 사각형 루프 (4개 실린더)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p1, p2, tie_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p2, p3, tie_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p3, p4, tie_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p4, p1, tie_dia/2)

    # --- 보 철근 배치 함수 (실제 설계 결과 반영) ---
    def get_bar_y_positions(b, rebar_str, rebar_steps, layer):
        """보 단면 내 철근 y 위치 목록(보 중심 기준 오프셋)과 직경을 반환"""
        stirrup_dia = rebar_steps['rebar_specs']['D10']['diameter']  # 실제 D10 직경 (9.53mm)
        if layer == 1:
            rebar_type = rebar_str.split('-')[1]
            r_dia = rebar_steps['rebar_specs'][rebar_type]['diameter']
            n = rebar_steps[f'n_final_{rebar_type}']
        else:
            rebar_type = "D25"
            r_dia = rebar_steps['rebar_specs'][rebar_type]['diameter']
            n = rebar_steps['fallback_n']
        edge = cover + stirrup_dia + r_dia / 2
        first = -b / 2 + edge
        avail = b - 2 * edge
        positions = [first + i * avail / (n - 1) for i in range(n)] if n > 1 else [0.0]
        return positions, r_dia

    def add_beam_rebar_mesh(axis, offset_val, length, b, h, s_spacing, z_base,
                             rebar_str_top, rebar_steps_top, layer_top,
                             rebar_str_bot, rebar_steps_bot, layer_bot,
                             rebar_str_min=None, rebar_steps_min=None, layer_min=1,
                             cw_start=None, cw_end=None,
                         dev_top=None, dev_bot=None, stirrup_zones=None):
        """cw_start: 시작 코너 기둥 단면, cw_end: 끝 코너 기둥 단면 (None이면 전역 cw 사용)"""
        _cw_s = cw_start if cw_start is not None else cw
        _cw_e = cw_end   if cw_end   is not None else cw
        stirrup_dia = rebar_steps_bot['rebar_specs']['D10']['diameter']

        # 실제 철근 직경으로 z 위치 산정
        y_positions_top, r_dia_top = get_bar_y_positions(b, rebar_str_top, rebar_steps_top, layer_top)
        y_positions_bot, r_dia_bot = get_bar_y_positions(b, rebar_str_bot, rebar_steps_bot, layer_bot)

        z_top = z_base - (cover + stirrup_dia + r_dia_top / 2)
        z_bot = z_base - h + (cover + stirrup_dia + r_dia_bot / 2)

        # ── 이음(겹이음) 및 갈고리 정착 ─────────────────────────────────
        L_zone = length / 4
        _sp_top = dev_top['ls_B'] / 2 if dev_top else 0   # 상부근 겹이음 반길이
        _sp_bot = dev_bot['ls_B'] / 2 if dev_bot else 0   # 하부근 겹이음 반길이

        # 갈고리 정착 (단일 프레임 — 보가 기둥에서 종단 → 90° hook)
        _col_cover = 40.0
        _anc_s = -(_cw_s / 2 - _col_cover)           # 시작 기둥 원면 안쪽
        _anc_e = length + (_cw_e / 2 - _col_cover)   # 끝 기둥 원면 안쪽
        _hook_top = 12 * r_dia_top                     # 상부근 갈고리 꼬리
        _hook_bot = 12 * r_dia_bot                     # 하부근 갈고리 꼬리

        def _add_hook(x_pos, yp, z_bar, hook_len, r_bar):
            """갈고리(90° 하향 절곡) 시각화"""
            if axis == 'X':
                add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                     (x_pos, offset_val+yp, z_bar), (x_pos, offset_val+yp, z_bar - hook_len), r_bar)
            else:
                add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                     (offset_val+yp, x_pos, z_bar), (offset_val+yp, x_pos, z_bar - hook_len), r_bar)

        if rebar_str_min is not None:
            # ── 구간별 배근 (겹이음 오버랩 + 갈고리 정착) ─────────────
            y_positions_min, r_dia_min = get_bar_y_positions(b, rebar_str_min, rebar_steps_min, layer_min)
            z_min_top = z_base - (cover + stirrup_dia + r_dia_min / 2)
            z_min_bot = z_base - h + (cover + stirrup_dia + r_dia_min / 2)

            # 상부 주근 — 지점부 (갈고리 + 겹이음)
            _top_pairs = [(_anc_s, L_zone + _sp_top),
                          (length - L_zone - _sp_top, _anc_e)]
            for yp in y_positions_top:
                if axis == 'X':
                    for x0e, x1e in _top_pairs:
                        add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                             (x0e, offset_val+yp, z_top), (x1e, offset_val+yp, z_top), r_dia_top/2)
                else:
                    for x0e, x1e in _top_pairs:
                        add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                             (offset_val+yp, x0e, z_top), (offset_val+yp, x1e, z_top), r_dia_top/2)
                # 갈고리: 양 기둥 끝에서 90° 하향
                _add_hook(_anc_s, yp, z_top, _hook_top, r_dia_top/2)
                _add_hook(_anc_e, yp, z_top, _hook_top, r_dia_top/2)

            # 상부 최소근 — 중앙부 (겹이음 오버랩)
            for yp in y_positions_min:
                if axis == 'X':
                    add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                         (L_zone - _sp_top, offset_val+yp, z_min_top), (length - L_zone + _sp_top, offset_val+yp, z_min_top), r_dia_min/2)
                else:
                    add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                         (offset_val+yp, L_zone - _sp_top, z_min_top), (offset_val+yp, length - L_zone + _sp_top, z_min_top), r_dia_min/2)

            # 하부 주근 — 중앙부 (겹이음 오버랩)
            for yp in y_positions_bot:
                if axis == 'X':
                    add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                         (L_zone - _sp_bot, offset_val+yp, z_bot), (length - L_zone + _sp_bot, offset_val+yp, z_bot), r_dia_bot/2)
                else:
                    add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                         (offset_val+yp, L_zone - _sp_bot, z_bot), (offset_val+yp, length - L_zone + _sp_bot, z_bot), r_dia_bot/2)

            # 하부 최소근 — 지점부 (겹이음 오버랩)
            _bot_pairs = [(-_cw_s/2, L_zone + _sp_bot),
                          (length - L_zone - _sp_bot, length + _cw_e/2)]
            for yp in y_positions_min:
                if axis == 'X':
                    for x0e, x1e in _bot_pairs:
                        add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                             (x0e, offset_val+yp, z_min_bot), (x1e, offset_val+yp, z_min_bot), r_dia_min/2)
                else:
                    for x0e, x1e in _bot_pairs:
                        add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main,
                                             (offset_val+yp, x0e, z_min_bot), (offset_val+yp, x1e, z_min_bot), r_dia_min/2)

        else:
            # ── 전체 길이에 상·하부근 배치 (갈고리 정착) ──────────────
            for yp in y_positions_top:
                if axis == 'X':
                    p1 = (_anc_s, offset_val + yp, z_top)
                    p2 = (_anc_e, offset_val + yp, z_top)
                else:
                    p1 = (offset_val + yp, _anc_s, z_top)
                    p2 = (offset_val + yp, _anc_e, z_top)
                add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main, p1, p2, r_dia_top / 2)
                _add_hook(_anc_s, yp, z_top, _hook_top, r_dia_top/2)
                _add_hook(_anc_e, yp, z_top, _hook_top, r_dia_top/2)
            for yp in y_positions_bot:
                if axis == 'X':
                    p1 = (_anc_s, offset_val + yp, z_bot)
                    p2 = (_anc_e, offset_val + yp, z_bot)
                else:
                    p1 = (offset_val + yp, _anc_s, z_bot)
                    p2 = (offset_val + yp, _anc_e, z_bot)
                add_cylinder_to_mesh(vx_main, vy_main, vz_main, ii_main, jj_main, kk_main, p1, p2, r_dia_bot / 2)
                _add_hook(_anc_s, yp, z_bot, _hook_bot, r_dia_bot/2)
                _add_hook(_anc_e, yp, z_bot, _hook_bot, r_dia_bot/2)

        # ── 스터럽 — 구간별 간격 (대칭 미러링 포함) ──────────────────
        stirrup_offset = cover + stirrup_dia / 2
        if stirrup_zones:
            _st_locs = []
            _next_pos = _cw_s/2 + 50   # 첫 스터럽 위치
            for _sz in stirrup_zones:
                _sz_e = _sz['x_end'] * 1000   # m → mm
                _sz_sp = _sz['s']
                _last = min(_sz_e, length - _cw_e/2)
                if _next_pos < _last:
                    locs = np.arange(_next_pos, _last, _sz_sp)
                    _st_locs.extend(locs.tolist())
                    if len(locs) > 0:
                        _next_pos = locs[-1] + _sz_sp
            # 대칭 미러링: zone이 절반까지만 정의된 경우 나머지 절반 추가
            _last_zone_end = stirrup_zones[-1]['x_end'] * 1000 if stirrup_zones else length
            if _last_zone_end < length * 0.75:  # 절반(대칭) 구간만 정의된 경우
                _mirror_locs = [length - sl for sl in _st_locs]
                _mirror_locs.reverse()
                # 중복 제거 (중앙부 겹침 방지)
                _all_locs = sorted(set(_st_locs + _mirror_locs))
                _st_locs = _all_locs
            stirrup_locs = np.array(_st_locs) if _st_locs else np.array([])
        else:
            stirrup_locs = np.arange(_cw_s/2 + 50, length - _cw_e/2, s_spacing)
        z_s_top = z_base - stirrup_offset
        z_s_bot = z_base - h + stirrup_offset
        y_s_left = -b/2 + stirrup_offset
        y_s_right = b/2 - stirrup_offset

        for sl in stirrup_locs:
            if axis == 'X':
                p1 = (sl, offset_val+y_s_left, z_s_bot)
                p2 = (sl, offset_val+y_s_right, z_s_bot)
                p3 = (sl, offset_val+y_s_right, z_s_top)
                p4 = (sl, offset_val+y_s_left, z_s_top)
            else:
                p1 = (offset_val+y_s_left, sl, z_s_bot)
                p2 = (offset_val+y_s_right, sl, z_s_bot)
                p3 = (offset_val+y_s_right, sl, z_s_top)
                p4 = (offset_val+y_s_left, sl, z_s_top)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p1, p2, stirrup_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p2, p3, stirrup_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p3, p4, stirrup_dia/2)
            add_cylinder_to_mesh(vx_tie, vy_tie, vz_tie, ii_tie, jj_tie, kk_tie, p4, p1, stirrup_dia/2)

    # 코너별 기둥 단면 크기 (보 주근 경계 결정용)
    _N_c = len(_all_cols_r)
    _cw_00 = _all_cols_r[0 % _N_c]['dimensions']['c_column']  # (0,  0 )
    _cw_10 = _all_cols_r[1 % _N_c]['dimensions']['c_column']  # (Lx, 0 )
    _cw_11 = _all_cols_r[2 % _N_c]['dimensions']['c_column']  # (Lx, Ly)
    _cw_01 = _all_cols_r[3 % _N_c]['dimensions']['c_column']  # (0,  Ly)

    # 보 철근 추가 (실제 설계 결과 반영)
    bx  = results['beam_x']
    by  = results['beam_y']
    gbx = results.get('ground_beam_x', bx)   # 없으면 천장보 폴백
    gby = results.get('ground_beam_y', by)
    # 상부보 (z_base = H)
    add_beam_rebar_mesh('X', 0,  Lx, bx_w, bx_h, bx['s'], H,
                        bx['rebar_string_top'], bx['rebar_steps_top'], bx['layer_top'],
                        bx['rebar_string_bot'], bx['rebar_steps_bot'], bx['layer_bot'],
                        bx['rebar_string_min'], bx['rebar_steps_min'], bx['layer_min'],
                        cw_start=_cw_00, cw_end=_cw_10,
                        dev_top=bx.get('dev_top'), dev_bot=bx.get('dev_bot'),
                        stirrup_zones=bx.get('stirrup_zones'))
    add_beam_rebar_mesh('X', Ly, Lx, bx_w, bx_h, bx['s'], H,
                        bx['rebar_string_top'], bx['rebar_steps_top'], bx['layer_top'],
                        bx['rebar_string_bot'], bx['rebar_steps_bot'], bx['layer_bot'],
                        bx['rebar_string_min'], bx['rebar_steps_min'], bx['layer_min'],
                        cw_start=_cw_01, cw_end=_cw_11,
                        dev_top=bx.get('dev_top'), dev_bot=bx.get('dev_bot'),
                        stirrup_zones=bx.get('stirrup_zones'))
    add_beam_rebar_mesh('Y', 0,  Ly, by_w, by_h, by['s'], H,
                        by['rebar_string_top'], by['rebar_steps_top'], by['layer_top'],
                        by['rebar_string_bot'], by['rebar_steps_bot'], by['layer_bot'],
                        by['rebar_string_min'], by['rebar_steps_min'], by['layer_min'],
                        cw_start=_cw_00, cw_end=_cw_01,
                        dev_top=by.get('dev_top'), dev_bot=by.get('dev_bot'),
                        stirrup_zones=by.get('stirrup_zones'))
    add_beam_rebar_mesh('Y', Lx, Ly, by_w, by_h, by['s'], H,
                        by['rebar_string_top'], by['rebar_steps_top'], by['layer_top'],
                        by['rebar_string_bot'], by['rebar_steps_bot'], by['layer_bot'],
                        by['rebar_string_min'], by['rebar_steps_min'], by['layer_min'],
                        cw_start=_cw_10, cw_end=_cw_11,
                        dev_top=by.get('dev_top'), dev_bot=by.get('dev_bot'),
                        stirrup_zones=by.get('stirrup_zones'))
    # 바닥보 — 바닥보 독립 설계 결과 사용 (V1 수정)
    add_beam_rebar_mesh('X', 0,  Lx, gbx_w, gbx_h, gbx['s'], gbx_h,
                        gbx['rebar_string_top'], gbx['rebar_steps_top'], gbx['layer_top'],
                        gbx['rebar_string_bot'], gbx['rebar_steps_bot'], gbx['layer_bot'],
                        gbx['rebar_string_min'], gbx['rebar_steps_min'], gbx['layer_min'],
                        cw_start=_cw_00, cw_end=_cw_10,
                        dev_top=gbx.get('dev_top'), dev_bot=gbx.get('dev_bot'),
                        stirrup_zones=gbx.get('stirrup_zones'))
    add_beam_rebar_mesh('X', Ly, Lx, gbx_w, gbx_h, gbx['s'], gbx_h,
                        gbx['rebar_string_top'], gbx['rebar_steps_top'], gbx['layer_top'],
                        gbx['rebar_string_bot'], gbx['rebar_steps_bot'], gbx['layer_bot'],
                        gbx['rebar_string_min'], gbx['rebar_steps_min'], gbx['layer_min'],
                        cw_start=_cw_01, cw_end=_cw_11,
                        dev_top=gbx.get('dev_top'), dev_bot=gbx.get('dev_bot'),
                        stirrup_zones=gbx.get('stirrup_zones'))
    add_beam_rebar_mesh('Y', 0,  Ly, gby_w, gby_h, gby['s'], gby_h,
                        gby['rebar_string_top'], gby['rebar_steps_top'], gby['layer_top'],
                        gby['rebar_string_bot'], gby['rebar_steps_bot'], gby['layer_bot'],
                        gby['rebar_string_min'], gby['rebar_steps_min'], gby['layer_min'],
                        cw_start=_cw_00, cw_end=_cw_01,
                        dev_top=gby.get('dev_top'), dev_bot=gby.get('dev_bot'),
                        stirrup_zones=gby.get('stirrup_zones'))
    add_beam_rebar_mesh('Y', Lx, Ly, gby_w, gby_h, gby['s'], gby_h,
                        gby['rebar_string_top'], gby['rebar_steps_top'], gby['layer_top'],
                        gby['rebar_string_bot'], gby['rebar_steps_bot'], gby['layer_bot'],
                        gby['rebar_string_min'], gby['rebar_steps_min'], gby['layer_min'],
                        cw_start=_cw_10, cw_end=_cw_11,
                        dev_top=gby.get('dev_top'), dev_bot=gby.get('dev_bot'),
                        stirrup_zones=gby.get('stirrup_zones'))

    # --- 슬래브 철근 배치 (상부층 + 바닥층 공통 루프) ---
    vx_slab, vy_slab, vz_slab = [], [], []
    ii_slab, jj_slab, kk_slab = [], [], []

    slab_data = results.get('slab')
    if slab_data:
        t_slab = slab_data['design_params']['t_slab']
        slab_cover = 20.0  # 슬래브 피복두께 (mm)

        # 슬래브 배근 문자열 파싱 ("D13@125" → diameter, spacing)
        def _parse_slab_rebar(rb_str):
            if not rb_str or '@' not in rb_str:
                return 0, 0, 0
            parts = rb_str.split('@')
            size_name = parts[0]
            spacing = float(parts[1])
            _specs = {"D10": 9.53, "D13": 12.7, "D16": 15.9}
            diameter = _specs.get(size_name, 10.0)
            return diameter, spacing, size_name

        db_top, s_top, _ = _parse_slab_rebar(slab_data['rebar_string_top'])
        db_bot, s_bot, _ = _parse_slab_rebar(slab_data['rebar_string_bot'])
        db_dist, s_dist, _ = _parse_slab_rebar(slab_data['rebar_string_dist'])

        # 1방향 슬래브: L_short 방향으로 주근 배치, L_long 방향으로 배력근 배치
        L_short = min(Lx, Ly)
        # 슬래브 이음길이 (겹이음 반길이)
        _slab_dev_top = slab_data.get('dev_top')
        _slab_dev_bot = slab_data.get('dev_bot')
        _ssp_top = _slab_dev_top['ls_B'] / 2 if _slab_dev_top else 0
        _ssp_bot = _slab_dev_bot['ls_B'] / 2 if _slab_dev_bot else 0

        if Lx <= Ly:
            main_axis = 'X'
            main_span = Lx
            dist_span = Ly
        else:
            main_axis = 'Y'
            main_span = Ly
            dist_span = Lx

        _L4 = main_span / 4
        _3L4 = 3 * main_span / 4

        _beam_cover = 40.0
        _hook_slab_top = 12 * db_top
        _hook_slab_bot = 12 * db_bot

        # 두 레벨 반복: (z기준높이, 주근방향 지지보폭, 배력근방향 지지보폭)
        _ground_slab_z = max(gbx_h, gby_h)
        if main_axis == 'X':
            _slab_levels = [
                (H,              by_w,  bx_w),    # 상부 슬래브
                (_ground_slab_z, gby_w, gbx_w),   # 바닥 슬래브
            ]
        else:
            _slab_levels = [
                (H,              bx_w,  by_w),    # 상부 슬래브
                (_ground_slab_z, gbx_w, gby_w),   # 바닥 슬래브
            ]

        for _z_ref, _main_bw, _dist_bw in _slab_levels:
            z_slab_top_bar = _z_ref - slab_cover - db_top / 2.0
            z_slab_bot_bar = _z_ref - t_slab + slab_cover + db_bot / 2.0
            z_slab_dist = z_slab_bot_bar + db_bot / 2.0 + db_dist / 2.0 + 2.0

            if main_axis == 'X':
                _anc_xs = -(_main_bw / 2 - _beam_cover)
                _anc_xe = Lx + (_main_bw / 2 - _beam_cover)
                y_start = _dist_bw / 2.0
                y_end = Ly - _dist_bw / 2.0

                # 상부근 (지점부 + 갈고리 + 겹이음 오버랩)
                if s_top > 0:
                    n_top = int(np.floor((y_end - y_start) / s_top)) + 1
                    for i in range(n_top):
                        yp = y_start + i * s_top
                        if yp > y_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_xs, yp, z_slab_top_bar), (_L4 + _ssp_top, yp, z_slab_top_bar), db_top / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_3L4 - _ssp_top, yp, z_slab_top_bar), (_anc_xe, yp, z_slab_top_bar), db_top / 2, 6)
                        # 90° 갈고리 (하향)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_xs, yp, z_slab_top_bar), (_anc_xs, yp, z_slab_top_bar - _hook_slab_top), db_top / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_xe, yp, z_slab_top_bar), (_anc_xe, yp, z_slab_top_bar - _hook_slab_top), db_top / 2, 6)

                # 하부근 (중앙부 + 겹이음 오버랩)
                if s_bot > 0:
                    n_bot = int(np.floor((y_end - y_start) / s_bot)) + 1
                    for i in range(n_bot):
                        yp = y_start + i * s_bot
                        if yp > y_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_L4 - _ssp_bot, yp, z_slab_bot_bar), (_3L4 + _ssp_bot, yp, z_slab_bot_bar), db_bot / 2, 6)

                # 배력근: Y방향 배치
                if s_dist > 0:
                    _anc_dy_s = -(_dist_bw / 2 - _beam_cover)
                    _anc_dy_e = Ly + (_dist_bw / 2 - _beam_cover)
                    x_dist_start = _main_bw / 2.0
                    x_dist_end = Lx - _main_bw / 2.0
                    n_dist = int(np.floor((x_dist_end - x_dist_start) / s_dist)) + 1
                    for i in range(n_dist):
                        xp = x_dist_start + i * s_dist
                        if xp > x_dist_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_dy_s, z_slab_dist), (xp, _anc_dy_e, z_slab_dist), db_dist / 2, 6)
                        _hook_dist = 12 * db_dist
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_dy_s, z_slab_dist), (xp, _anc_dy_s, z_slab_dist - _hook_dist), db_dist / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_dy_e, z_slab_dist), (xp, _anc_dy_e, z_slab_dist - _hook_dist), db_dist / 2, 6)

            else:  # main_axis == 'Y'
                _anc_ys = -(_main_bw / 2 - _beam_cover)
                _anc_ye = Ly + (_main_bw / 2 - _beam_cover)
                x_start = _dist_bw / 2.0
                x_end = Lx - _dist_bw / 2.0

                # 상부근 (지점부 + 갈고리 + 겹이음 오버랩)
                if s_top > 0:
                    n_top = int(np.floor((x_end - x_start) / s_top)) + 1
                    for i in range(n_top):
                        xp = x_start + i * s_top
                        if xp > x_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_ys, z_slab_top_bar), (xp, _L4 + _ssp_top, z_slab_top_bar), db_top / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _3L4 - _ssp_top, z_slab_top_bar), (xp, _anc_ye, z_slab_top_bar), db_top / 2, 6)
                        # 90° 갈고리 (하향)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_ys, z_slab_top_bar), (xp, _anc_ys, z_slab_top_bar - _hook_slab_top), db_top / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _anc_ye, z_slab_top_bar), (xp, _anc_ye, z_slab_top_bar - _hook_slab_top), db_top / 2, 6)

                # 하부근 (중앙부)
                if s_bot > 0:
                    n_bot = int(np.floor((x_end - x_start) / s_bot)) + 1
                    for i in range(n_bot):
                        xp = x_start + i * s_bot
                        if xp > x_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (xp, _L4 - _ssp_bot, z_slab_bot_bar), (xp, _3L4 + _ssp_bot, z_slab_bot_bar), db_bot / 2, 6)

                # 배력근: X방향 배치
                if s_dist > 0:
                    _anc_dx_s = -(_dist_bw / 2 - _beam_cover)
                    _anc_dx_e = Lx + (_dist_bw / 2 - _beam_cover)
                    y_dist_start = _main_bw / 2.0
                    y_dist_end = Ly - _main_bw / 2.0
                    n_dist = int(np.floor((y_dist_end - y_dist_start) / s_dist)) + 1
                    for i in range(n_dist):
                        yp = y_dist_start + i * s_dist
                        if yp > y_dist_end:
                            break
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_dx_s, yp, z_slab_dist), (_anc_dx_e, yp, z_slab_dist), db_dist / 2, 6)
                        _hook_dist = 12 * db_dist
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_dx_s, yp, z_slab_dist), (_anc_dx_s, yp, z_slab_dist - _hook_dist), db_dist / 2, 6)
                        add_cylinder_to_mesh(vx_slab, vy_slab, vz_slab, ii_slab, jj_slab, kk_slab,
                                             (_anc_dx_e, yp, z_slab_dist), (_anc_dx_e, yp, z_slab_dist - _hook_dist), db_dist / 2, 6)

    # 4. 최종 메쉬 트레이스 추가
    if vx_main:
        fig.add_trace(go.Mesh3d(x=vx_main, y=vy_main, z=vz_main, i=ii_main, j=jj_main, k=kk_main,
                                color='red', opacity=1.0, name='주철근', flatshading=True))
    if vx_tie:
        fig.add_trace(go.Mesh3d(x=vx_tie, y=vy_tie, z=vz_tie, i=ii_tie, j=jj_tie, k=kk_tie,
                                color='green', opacity=1.0, name='띠철근/늑근', flatshading=True))
    if vx_slab:
        fig.add_trace(go.Mesh3d(x=vx_slab, y=vy_slab, z=vz_slab, i=ii_slab, j=jj_slab, k=kk_slab,
                                color='orange', opacity=1.0, name='슬래브 철근', flatshading=True))

    # 5. 치수 표기 (dimension lines) — 그리드 대신 사용
    _dim_off = min(Lx, Ly) * 0.18
    _tick_l  = min(Lx, Ly) * 0.04
    _txt_col = '#555555'

    # Lx 치수선 (y = -_dim_off, z = 0)
    fig.add_trace(go.Scatter3d(x=[0, Lx], y=[-_dim_off]*2, z=[0, 0],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[Lx/2], y=[-_dim_off], z=[0],
        mode='text', text=[f'Lx = {Lx/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _xx in [0, Lx]:
        fig.add_trace(go.Scatter3d(x=[_xx]*2, y=[-_dim_off-_tick_l, -_dim_off+_tick_l], z=[0, 0],
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # Ly 치수선 (x = -_dim_off, z = 0)
    fig.add_trace(go.Scatter3d(x=[-_dim_off]*2, y=[0, Ly], z=[0, 0],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[-_dim_off], y=[Ly/2], z=[0],
        mode='text', text=[f'Ly = {Ly/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _yy in [0, Ly]:
        fig.add_trace(go.Scatter3d(x=[-_dim_off-_tick_l, -_dim_off+_tick_l], y=[_yy]*2, z=[0, 0],
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # H 치수선 (x = Lx + _dim_off, y = 0)
    fig.add_trace(go.Scatter3d(x=[Lx+_dim_off]*2, y=[0, 0], z=[0, H],
        mode='lines', line=dict(color=_txt_col, width=2), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter3d(x=[Lx+_dim_off], y=[0], z=[H/2],
        mode='text', text=[f'H = {H/1000:.2f} m'],
        textfont=dict(color=_txt_col, size=11), showlegend=False, hoverinfo='skip'))
    for _zz in [0, H]:
        fig.add_trace(go.Scatter3d(x=[Lx+_dim_off-_tick_l, Lx+_dim_off+_tick_l], y=[0, 0], z=[_zz]*2,
            mode='lines', line=dict(color=_txt_col, width=1.5), showlegend=False, hoverinfo='skip'))

    # 6. 레이아웃 — 그리드 제거 + 축 라벨 숨김
    _no_axis = dict(showgrid=False, showbackground=False, zeroline=False,
                    showticklabels=False, showline=False, title='')
    fig.update_layout(
        title="3D Frame Rebar Detail",
        scene=dict(
            xaxis=_no_axis,
            yaxis=_no_axis,
            zaxis=_no_axis,
            aspectmode='data'
        ),
        margin=dict(l=0, r=0, b=0, t=30),
        height=800
    )
    return fig
