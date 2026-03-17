import plotly.graph_objects as go
import numpy as np

def add_vertical_diagram(fig, x_pos, y_pos, z_array, val_array, color, scale, direction='X'):
    """수직 부재(기둥)의 다이어그램을 면 채우기 없이 선(Line) 형태로만 그리는 함수"""
    x_base = np.full_like(z_array, x_pos)
    y_base = np.full_like(z_array, y_pos)

    # 방향에 따라 돌출
    if direction == 'X':
        x_val = x_base + val_array * scale
        y_val = y_base
    else: # 'Y'
        x_val = x_base
        y_val = y_base + val_array * scale

    # 1. 외곽선(아웃라인) 그리기: 기둥 중심선 -> 위쪽 닫기 -> 다이어그램 외곽선 -> 아래쪽 닫기
    outline_x = np.concatenate([x_base, [x_val[-1]], x_val[::-1], [x_base[0]]])
    outline_y = np.concatenate([y_base, [y_val[-1]], y_val[::-1], [y_base[0]]])
    outline_z = np.concatenate([z_array, [z_array[-1]], z_array[::-1], [z_array[0]]])

    fig.add_trace(go.Scatter3d(
        x=outline_x, y=outline_y, z=outline_z,
        mode='lines',
        line=dict(color=color, width=2.5), # 테두리는 약간 굵게
        showlegend=False
    ))

    # 2. 얇은 수직선(해치선) 그리기 — 보 SFD/BMD와 동일한 밀도 (약 30개 간격)
    hatch_x = []
    hatch_y = []
    hatch_z = []
    _n_z = len(z_array)
    _hz_step = max(1, _n_z // 30)

    # 각 Z 높이마다 기준선과 값 선을 연결하는 얇은 선의 좌표 생성
    for i in range(0, _n_z, _hz_step):
        hatch_x.extend([x_base[i], x_val[i], None]) # None은 선을 끊어서 그리라는 의미
        hatch_y.extend([y_base[i], y_val[i], None])
        hatch_z.extend([z_array[i], z_array[i], None])

    fig.add_trace(go.Scatter3d(
        x=hatch_x, y=hatch_y, z=hatch_z,
        mode='lines',
        line=dict(color=color, width=1), # 내부는 얇은 선으로
        opacity=0.6, # 살짝 투명하게 해서 보기 편하게
        showlegend=False
    ))

def create_box(x0, y0, z0, dx, dy, dz, color='lightgray'):
    """3D 직육면체(콘크리트 기둥/보)를 그리는 함수"""
    x = [x0, x0+dx, x0+dx, x0, x0, x0+dx, x0+dx, x0]
    y = [y0, y0, y0+dy, y0+dy, y0, y0, y0+dy, y0+dy]
    z = [z0, z0, z0, z0, z0+dz, z0+dz, z0+dz, z0+dz]

    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]

    return go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, color=color, opacity=0.7, flatshading=True, hoverinfo='skip')

def add_diagram_ribbon(fig, x_coords, y_coords, z_coords, vals, color, scale_factor, direction='Z'):
    """부재력(SFD/BMD) 데이터를 3D 빗금(Hatch) 형태의 다이어그램으로 그려주는 함수"""
    env_x, env_y, env_z = [], [], []
    hatch_x, hatch_y, hatch_z = [], [], []

    for i in range(len(vals)):
        bx, by, bz = x_coords[i], y_coords[i], z_coords[i]

        # 방향에 따라 다이어그램이 솟아오르는 축 결정
        if direction == 'Z':
            ex, ey, ez = bx, by, bz + vals[i] * scale_factor
        elif direction == 'Y':
            ex, ey, ez = bx, by + vals[i] * scale_factor, bz
        else:
            ex, ey, ez = bx + vals[i] * scale_factor, by, bz

        env_x.append(ex); env_y.append(ey); env_z.append(ez)

        # 너무 빽빽하지 않게 빗금(수직선) 추가 (약 30개 간격)
        if i % max(1, len(vals)//30) == 0:
            hatch_x.extend([bx, ex, None])
            hatch_y.extend([by, ey, None])
            hatch_z.extend([bz, ez, None])

    # 외곽선 (Envelope)
    fig.add_trace(go.Scatter3d(x=env_x, y=env_y, z=env_z, mode='lines', line=dict(color=color, width=4), showlegend=False, hoverinfo='skip'))
    # 빗금 (Hatching)
    fig.add_trace(go.Scatter3d(x=hatch_x, y=hatch_y, z=hatch_z, mode='lines', line=dict(color=color, width=1, dash='solid'), showlegend=False, hoverinfo='skip'))

def add_cylinder_to_mesh(vx, vy, vz, ii, jj, kk, p1, p2, r, n_sides=12):
    """3D Mesh 리스트에 실린더 데이터를 추가하는 함수"""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    offset = len(vx)

    theta = np.linspace(0, 2*np.pi, n_sides, endpoint=False)

    # 축 방향 판별 및 원형 단면 좌표 생성
    if abs(x2 - x1) > 0.1: # X축
        y = r * np.cos(theta)
        z = r * np.sin(theta)
        for i in range(n_sides):
            vx.append(x1); vy.append(y1 + y[i]); vz.append(z1 + z[i])
        for i in range(n_sides):
            vx.append(x2); vy.append(y1 + y[i]); vz.append(z1 + z[i])

    elif abs(y2 - y1) > 0.1: # Y축
        x = r * np.cos(theta)
        z = r * np.sin(theta)
        for i in range(n_sides):
            vx.append(x1 + x[i]); vy.append(y1); vz.append(z1 + z[i])
        for i in range(n_sides):
            vx.append(x1 + x[i]); vy.append(y2); vz.append(z1 + z[i])

    else: # Z축 (또는 아주 짧은 구간)
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        for i in range(n_sides):
            vx.append(x1 + x[i]); vy.append(y1 + y[i]); vz.append(z1)
        for i in range(n_sides):
            vx.append(x1 + x[i]); vy.append(y1 + y[i]); vz.append(z2)

    # 측면 메쉬 인덱스 생성 (Triangle Strip)
    for i in range(n_sides):
        p1_idx = offset + i
        p2_idx = offset + (i + 1) % n_sides
        p3_idx = offset + n_sides + (i + 1) % n_sides
        p4_idx = offset + n_sides + i

        # Triangle 1 (p1-p2-p3)
        ii.append(p1_idx); jj.append(p2_idx); kk.append(p3_idx)
        # Triangle 2 (p1-p3-p4)
        ii.append(p1_idx); jj.append(p3_idx); kk.append(p4_idx)
