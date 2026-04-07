import streamlit as st
import numpy as np
import os
import re
import pandas as pd
import matplotlib.pyplot as plt
from visualization import (plot_rebar_section, plot_rebar_section_review, plot_beam_side_view,
                           plot_column_section, plot_column_side_view,
                           plot_3d_frame_rebar, plot_pm_diagram, plot_slab_section)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════
# Module-level helper functions (used across multiple render sections)
# ═══════════════════════════════════════════════════════════════════════════

def _render_flexural_expander(expander_title, Mu_kNm, fs, b, h, As_req, fc_k, fy):
    with st.expander(expander_title):
        st.markdown("**① 설계 모멘트**")
        st.write(f"$M_u$ = {Mu_kNm:.2f} kN·m = {Mu_kNm*1e6:.4e} N·mm")

        st.markdown("**② 등가응력블록 계수 β₁ (KDS 41 20 20 4.1.1)**")
        st.latex(r"\beta_1 = \begin{cases}0.85 & f_{ck}\le28\,\mathrm{MPa}\\\max\!\left(0.65,\ 0.85-\frac{0.05}{7}(f_{ck}-28)\right) & f_{ck}>28\end{cases}")
        st.write(f"→ $f_{{ck}}$ = {fc_k:.0f} MPa   →   **β₁ = {fs['beta1']:.4f}**")

        st.markdown("**③ 피복두께 및 유효깊이 d 산정 (2-패스 추정법)**")
        st.latex(r"d_c = c_{cover}(40) + d_{stirrup}(10) + d_b/2,\quad d = h - d_c")
        _db_mm = fs.get('d_c_db_est', 25.4)
        _db_name = {9.53:'D10', 12.7:'D13', 15.9:'D16', 19.1:'D19',
                    22.2:'D22', 25.4:'D25', 28.6:'D29', 31.8:'D32'}.get(_db_mm, f'{_db_mm:.1f}mm')
        st.write(f"- 추정 주근 직경: **{_db_name}** (d_b = {_db_mm:.2f} mm)")
        st.write(f"- $d_c$ = 40 + 10 + {_db_mm/2:.2f} = **{fs['d_c']:.2f} mm**")
        st.write(f"- $d$ = {h:.0f} − {fs['d_c']:.2f} = **{fs['d']:.2f} mm**")

        st.markdown("**④ 강도감소계수 φ 수렴 및 공칭저항계수 Rn**")
        st.latex(r"R_n = \frac{M_u/\phi}{b\cdot d^2}")
        st.write(f"- φ 수렴 결과: **φ = {fs['phi']:.3f}** ({fs['phi_iters']}회 반복)")
        st.write(f"- $R_n$ = {Mu_kNm*1e6:.2e} / ({fs['phi']:.3f} × {b:.0f} × {fs['d']:.2f}²) = **{fs['Rn']:.4f} MPa**")

        st.markdown("**⑤ 판별식 Δ (단면 적합성)**")
        st.latex(r"\Delta = 1 - \frac{2\,R_n}{0.85\,f_{ck}}")
        disc = fs.get('discriminant', 0.0)
        disc_icon = "✅ > 0 (단면 적합)" if disc > 0 else "❌ < 0 (단면 부족 — h 또는 b 증가 필요)"
        rn_val = fs.get('Rn', 0.0)
        st.write(f"- Δ = 1 − 2×{rn_val:.4f} / (0.85×{fc_k:.0f}) = **{disc:.4f}**   →   {disc_icon}")

        if disc <= 0:
            st.error("단면이 부족하여 이하 계산을 수행할 수 없습니다. 단면 치수를 확인하세요.")
            return

        st.markdown("**⑥ 필요 철근비 ρ_req 및 최소 철근비 ρ_min (KDS 41 20 20 4.3)**")
        st.latex(r"\rho_{req} = \frac{0.85\,f_{ck}}{f_y}\left(1-\sqrt{\Delta}\right)")
        st.write(f"- ρ_req (강도) = {fs.get('rho_req_calculated', 0.0):.4f}")
        st.latex(r"\rho_{min} = \max\!\left(\frac{0.25\sqrt{f_{ck}}}{f_y},\; \frac{1.4}{f_y}\right)")
        st.write(f"- ρ_min,1 = 0.25√{fc_k:.0f} / {fy:.0f} = {fs.get('rho_min1', 0.0):.4f}")
        st.write(f"- ρ_min,2 = 1.4 / {fy:.0f} = {fs.get('rho_min2', 0.0):.4f}")
        rho_fin = fs.get('rho_req_final', 0.0)
        rho_min = fs.get('rho_min', 0.0)
        rho_gov = "⬆ 최소 철근비 지배" if abs(rho_fin - rho_min) < 1e-6 else "강도 지배"
        rho_max = fs.get('rho_max', 0.0)
        rho_max_ok = fs.get('rho_max_ok', True)
        st.write(f"- **ρ_min = {rho_min:.4f}**,   **ρ_req (최종) = {rho_fin:.4f}**  ({rho_gov})")
        st.latex(r"\rho_{max} = \frac{0.85\,\beta_1\,f_{ck}}{f_y}\cdot\frac{0.003}{0.003+0.004} \quad(\varepsilon_t \ge 0.004\text{ 보장})")
        rho_max_icon = "✅ OK" if rho_max_ok else "❌ 초과 — 단면 증가 필요"
        st.write(f"- **ρ_max = {rho_max:.4f}**   →   {rho_max_icon}")

        st.markdown("**⑦ 소요 철근면적 As**")
        st.latex(r"A_s = \rho_{req}\cdot b\cdot d")
        st.write(f"- $A_s$ = {rho_fin:.4f} × {b:.0f} × {fs['d']:.2f} = **{As_req:.2f} mm²**")

        st.markdown("**⑧ 등가응력블록 깊이 및 인장변형률 εt 검토**")
        st.latex(r"a = \frac{A_s\,f_y}{0.85\,f_{ck}\,b},\quad c = \frac{a}{\beta_1},\quad \varepsilon_t = \varepsilon_{cu}\frac{d-c}{c}\ (\varepsilon_{cu}=0.003)")
        a_val  = fs.get('a', 0.0)
        c_val  = fs.get('c', 0.0)
        et     = fs.get('epsilon_t', 0.005)
        st.write(f"- a = {a_val:.2f} mm,   c = {c_val:.2f} mm")
        if et >= 0.005:
            et_icon = "✅ ≥ 0.005 → 인장지배 (φ = 0.85)"
        elif et >= 0.002:
            et_icon = "⚠️ 0.002–0.005 → 전이구간 (φ 보간)"
        else:
            et_icon = "❌ < 0.002 → 압축지배 (φ = 0.65)"
        d_val = fs.get('d', 0.0)
        st.write(f"- ε_t = 0.003 × ({d_val:.2f}−{c_val:.2f}) / {c_val:.2f} = **{et:.4f}**   →   {et_icon}")
        st.write(f"- **최종 φ = {fs['phi']:.3f}**")


def _render_shear_expander(expander_title, Vu_kN, ss, b, fc_k):
    with st.expander(expander_title):
        phi  = ss['phi']
        A_v  = ss['A_v']
        fy_t = ss['fy_t']
        d    = ss['d']

        if 'V_at_d' in ss:
            st.markdown("**⓪ 위험단면 전단력 (KDS 41 20 22)**")
            st.latex(r"V_u(d) = V_{max} - w_u \cdot d")
            _V_face = ss.get('V_max_face', Vu_kN)
            _V_atd = ss['V_at_d']
            _d_cr = ss.get('d_critical_m', d / 1000.0)
            st.write(f"- $V_{{max}}$ (지점면) = {_V_face:.2f} kN")
            st.write(f"- $d$ = {_d_cr*1000:.1f} mm = {_d_cr:.4f} m")
            st.write(f"- $V_u(d)$ = {_V_face:.2f} − w_u × {_d_cr:.4f} = **{_V_atd:.2f} kN**")
            st.write("---")

        st.markdown("**① 소요 공칭전단강도 Vn**")
        st.latex(r"V_n = \frac{V_u}{\phi} \quad (\phi = 0.75\text{, 전단 강도감소계수})")
        st.write(f"- $V_u$ = {Vu_kN:.2f} kN = {ss['Vu_N']:.0f} N")
        st.write(f"- $V_n$ = {ss['Vu_N']:.0f} / {phi:.2f} = **{ss['Vn_N']:.0f} N  ({ss['Vn_N']/1000:.2f} kN)**")

        st.markdown("**② 콘크리트 전단강도 Vc (KDS 41 20 22 식 4.1-2)**")
        st.latex(r"V_c = \frac{1}{6}\,\lambda\sqrt{f_{ck}}\cdot b_w\cdot d \quad (\lambda=1.0)")
        st.write(f"- $V_c$ = (1/6) × 1.0 × √{fc_k:.0f} × {b:.0f} × {d:.1f} = **{ss['Vc_N']/1000:.2f} kN**")

        st.markdown("**③ 전단철근 부담 강도 Vs**")
        st.latex(r"V_s = V_n - V_c \quad\left[\text{상한: }V_{s,max}=\frac{2}{3}\sqrt{f_{ck}}\cdot b_w\cdot d\right]")
        st.write(f"- $V_s$ = {ss['Vn_N']/1000:.2f} − {ss['Vc_N']/1000:.2f} = **{ss['Vs_N']/1000:.2f} kN**")
        vs_ok = ss['Vs_N'] <= ss['Vs_max_N']
        st.write(f"- $V_{{s,max}}$ = {ss['Vs_max_N']/1000:.2f} kN   →   {'✅ 단면 OK' if vs_ok else '❌ 단면 부족'}")

        st.markdown("**④ 이론적 소요 늑근 간격 s_req**")
        st.latex(r"s_{req} = \frac{A_v\,f_{yt}\,d}{V_s}")
        st.write(f"- $A_v$ = 2 × {A_v/2:.2f} = {A_v:.2f} mm²  (D10 U형 2지),   $f_{{yt}}$ = {fy_t:.0f} MPa")
        if ss['s_req'] < 1e5:
            st.write(f"- $s_{{req}}$ = {A_v:.2f} × {fy_t:.0f} × {d:.1f} / {ss['Vs_N']:.0f} = **{ss['s_req']:.1f} mm**")
        else:
            st.write("- $V_s$ ≤ 0 → 콘크리트만으로 전단 충분. 최소 전단철근 규정으로 결정됨.")

        st.markdown("**⑤ 최소전단철근 규정에 의한 최대 간격 s_max,Av**")
        st.latex(r"s_{max,Av} = \frac{A_v\,f_{yt}}{\max(0.0625\sqrt{f_{ck}},\;0.35)\cdot b_w}")
        st.write(f"- $s_{{max,Av}}$ = **{ss['s_max_Av']:.1f} mm**")

        st.markdown("**⑥ 기하학적 최대 간격 s_max,geom (KDS 41 20 22 8.1)**")
        vc_lim = ss['Vc_limit_N']
        vs_cur = ss['Vs_N']
        st.write(f"- $V_{{c,limit}}$ = (1/3)√{fc_k:.0f}·{b:.0f}·{d:.1f} = {vc_lim/1000:.2f} kN")
        if vs_cur <= vc_lim:
            st.write(f"- $V_s$ ≤ $V_{{c,limit}}$   →   s_max,geom = min(d/2, 600) = **{ss['s_max_geom']:.0f} mm**")
        else:
            st.write(f"- $V_s$ > $V_{{c,limit}}$   →   s_max,geom = min(d/4, 300) = **{ss['s_max_geom']:.0f} mm**")

        st.markdown("**⑦ 최종 늑근 간격 결정**")
        s_req_disp = f"{ss['s_req']:.0f}" if ss['s_req'] < 1e5 else "∞"
        st.write(f"- $s_{{raw}}$ = min({s_req_disp}, {ss['s_max_Av']:.0f}, {ss['s_max_geom']:.0f}) = {ss['s_raw']:.1f} mm")
        st.write(f"- 50 mm 단위 내림   →   **s = {ss['s_final']:.0f} mm**")


def _render_rebar_expander(expander_title, rs, As_req, b_beam):
    with st.expander(expander_title):
        cover = rs['cover']
        d_bst = rs['d_b_stirrup']
        b_net = rs['b_net']
        agg   = rs['max_agg_size']

        st.markdown("**① 배근 유효 폭 b_net**")
        st.latex(r"b_{net} = b - 2\cdot c_{cover} - 2\cdot d_{b,stirrup}")
        st.write(f"- $b_{{net}}$ = {b_beam:.0f} − 2×{cover:.0f} − 2×{d_bst:.0f} = **{b_net:.0f} mm**")

        st.markdown("**② 최소 순간격 S_min (KDS 41 20 52 5.3)**")
        st.latex(r"S_{min} = \max\!\left(\tfrac{4}{3}d_{agg},\; d_b\right)")
        st.write(f"- 굵은골재 최대치수 $d_{{agg}}$ = {agg:.0f} mm   →   (4/3)×{agg:.0f} = {4/3*agg:.1f} mm")

        st.markdown("**③ 철근 규격별 1단 배근 검토**")
        st.caption("소요폭 = n·d_b + (n−1)·S_min  ≤  b_net 이면 ✅ 배근 가능")
        rebar_sizes = ["D13", "D16", "D19", "D22", "D25", "D29", "D32"]
        row_data = {"규격": [], "S_min (mm)": [], "가닥수 n": [],
                    "소요폭 (mm)": [], "유효폭 (mm)": [], "가능": []}
        for size in rebar_sizes:
            if f'S_min_{size}' not in rs:
                continue
            rw_s = rs.get(f'req_width_{size}', None)
            if rw_s is None:
                continue
            row_data["규격"].append(size)
            row_data["S_min (mm)"].append(f"{rs[f'S_min_{size}']:.1f}")
            row_data["가닥수 n"].append(str(rs.get(f'n_final_{size}', '-')))
            row_data["소요폭 (mm)"].append(f"{rw_s:.1f}")
            row_data["유효폭 (mm)"].append(f"{b_net:.0f}")
            row_data["가능"].append("✅" if rw_s <= b_net else "❌")
        if row_data["규격"]:
            st.table(row_data)

        st.markdown("**④ 최종 선택 결과**")
        sel_str   = rs.get('rebar_string', 'N/A')
        sel_As    = rs.get('As_provided', 0.0)
        sel_layer = rs.get('layer', 1)
        st.write(f"- 소요 $A_s$ = {As_req:.2f} mm²")
        st.write(f"- 선택: **{sel_str}** ({sel_layer}단 배근,  제공 $A_s$ = {sel_As:.2f} mm²)")
        if sel_As > 0 and As_req > 0:
            st.write(f"- 제공/소요 비 = {sel_As/As_req:.3f}  ({'✅ OK' if sel_As >= As_req else '❌ 부족'})")

        # v0.6.3: 2단 배근 시 유효깊이 보정 수식 표시
        _d_c_2 = rs.get('d_c_2layer')
        if _d_c_2 and sel_layer == 2:
            st.markdown("**⑤ 2단 배근 유효깊이 보정 (v0.6.3)**")
            st.latex(r"d_{c,2layer} = cover + d_{stirrup} + d_b + \max(25, d_b) + d_b / 2")
            st.write(f"$d_{{c,2layer}}$ = {_d_c_2:.2f} mm  →  유효깊이 감소로 As 재산정됨")


def _render_slab_flexural_expander(title, fs, b, fck, fy):
    """슬래브 휨 설계 상세 expander (보 _render_flexural_expander 패턴)"""
    with st.expander(title, expanded=False):
        st.write("**Step 1.** 설계 모멘트")
        _Mu_kNm = fs['Mu_Nmm'] / 1e6
        st.write(f"$M_u$ = {_Mu_kNm:.2f} kN·m/m  →  {fs['Mu_Nmm']:.0f} N·mm")

        st.write("**Step 2.** 등가응력블록 깊이 계수 (KDS 41 20 20 4.1.1)")
        st.latex(r"\beta_1 = 0.85 - \frac{0.05}{7}(f_{ck} - 28) \quad (0.65 \leq \beta_1 \leq 0.85)")
        st.write(f"$\\beta_1 = {fs['beta1']:.4f}$  (fck = {fck} MPa)")

        st.write("**Step 3.** 유효깊이 (슬래브: 스터럽 없음)")
        st.latex(r"d_c = cover + d_b/2, \quad d = h - d_c")
        st.write(f"$d_c = {fs['d_c']:.2f}$ mm,  $d = {fs['d']:.2f}$ mm")

        st.write("**Step 4.** 강도감소계수 φ 수렴")
        _Rn = fs['Mu_Nmm'] / (fs['phi'] * b * fs['d'] ** 2) if fs['d'] > 0 else 0
        st.latex(r"R_n = \frac{M_u}{\phi \cdot b \cdot d^2}")
        st.write(f"$R_n = {_Rn:.4f}$ MPa,  $\\phi = {fs['phi']:.4f}$  ({fs['phi_iters']}회 수렴)")

        st.write("**Step 5.** 철근비 산정")
        st.latex(r"\rho_{req} = \frac{0.85 f_{ck}}{f_y}\left(1 - \sqrt{1 - \frac{2R_n}{0.85 f_{ck}}}\right)")
        st.write(f"$\\rho_{{req}}$ = {fs['rho_req_calculated']:.6f}")
        st.write(f"$\\rho_{{min}}$ = {fs['rho_min']:.4f}  (수축·온도 철근비, KDS 41 20 20)")
        st.write(f"$\\rho_{{final}}$ = {fs['rho_req_final']:.6f}")

        st.write("**Step 6.** 소요 철근량")
        st.latex(r"A_s = \rho \cdot b \cdot d")
        st.write(f"$A_s$ = {fs['As_calculated']:.2f} mm²/m")

        st.write("**Step 7.** 순인장변형률 검토")
        st.write(f"- $a = {fs['a']:.2f}$ mm,  $c = {fs['c']:.2f}$ mm")
        st.write(f"- $\\varepsilon_t = 0.003 \\times (d-c)/c = {fs['epsilon_t']:.5f}$"
                 f"  {'✅ ≥ 0.005 (인장지배)' if fs['epsilon_t'] >= 0.005 else '⚠️ < 0.005'}")


def _render_slab_shear_expander(ss, fck):
    """슬래브 전단 검토 상세 expander"""
    with st.expander("슬래브 전단 설계 상세 (KDS 41 20 22)", expanded=False):
        st.write("**Step 1.** 위험단면 전단력 (면에서 d 떨어진 위치)")
        st.latex(r"V_{u}(d) = V_{max,face} - w_u \cdot d")
        st.write(f"$V_{{max,face}}$ = {ss.get('V_max_face', 0):.1f} kN,  "
                 f"$d$ = {ss.get('d', 0):.1f} mm  →  "
                 f"$V_u(d)$ = {ss.get('V_at_d', ss.get('Vu_kN', 0)):.1f} kN")

        st.write("**Step 2.** 콘크리트 전단강도")
        st.latex(r"V_c = \frac{1}{6}\sqrt{f_{ck}} \cdot b \cdot d")
        st.write(f"$V_c$ = {ss.get('Vc_kN', 0):.1f} kN  ($f_{{ck}}$ = {fck} MPa, b = 1000 mm)")

        st.write("**Step 3.** 설계 전단강도")
        st.latex(r"\phi V_c = 0.75 \times V_c")
        st.write(f"$\\phi V_c$ = {ss.get('phi_Vc_kN', 0):.1f} kN  vs  $V_u$ = {ss.get('Vu_kN', 0):.1f} kN")

        st.write("**Step 4.** 판정")
        _ok = ss.get('ok', True)
        _ratio = ss.get('ratio', 0)
        st.write(f"$V_u / \\phi V_c$ = {_ratio:.3f}  →  {'✅ OK (전단철근 불필요)' if _ok else '❌ NG'}")


def _render_slab_deflection_expander(s_defl, slab_dp):
    """슬래브 처짐 계산 상세 expander"""
    with st.expander("슬래브 처짐 계산 상세 (수식 전개)", expanded=False):
        st.write("**1. 재료 특성**")
        st.write(f"- $E_c$ = {s_defl.get('Ec', 0):.0f} MPa,  $f_r$ = {s_defl.get('fr', 0):.2f} MPa,  $n$ = {s_defl.get('n', 0):.2f}")

        st.write("**2. 총단면 특성 (Ig, M_cr)**")
        _Ig = s_defl.get('Ig', 0)
        _M_cr = s_defl.get('M_cr_Nmm', s_defl.get('M_cr_kNm', 0) * 1e6 if s_defl.get('M_cr_kNm') else 0)
        st.latex(r"I_g = \frac{b h^3}{12}, \quad M_{cr} = \frac{f_r \cdot I_g}{y_t}")
        st.write(f"$I_g$ = {_Ig:.0f} mm⁴,  $M_{{cr}}$ = {_M_cr/1e6:.2f} kN·m/m")

        st.write("**3. 균열단면 특성**")
        _Icr = s_defl.get('Icr', 0)
        _Icr_sup = s_defl.get('Icr_sup', _Icr)
        st.write(f"- $I_{{cr,mid}}$ (하부근 인장) = {_Icr:,.0f} mm⁴")
        if _Icr_sup != _Icr:
            st.write(f"- $I_{{cr,sup}}$ (상부근 인장) = {_Icr_sup:,.0f} mm⁴")
        st.write(f"- 중립축 깊이 $x_{{cr}}$ = {s_defl.get('x_cr', 0):.2f} mm")
        _cracked = s_defl.get('cracked', False)
        st.write(f"- 균열 여부: {'균열 발생 (Ma > Mcr)' if _cracked else '비균열 (Ma ≤ Mcr)'}")

        st.write("**4. Branson 유효 단면2차모멘트 (Ie)**")
        st.latex(r"I_e = \left(\frac{M_{cr}}{M_a}\right)^3 I_g + \left[1-\left(\frac{M_{cr}}{M_a}\right)^3\right] I_{cr}")
        st.latex(r"I_{e,avg} = 0.70 \cdot I_{e,mid} + 0.30 \cdot I_{e,sup}")
        st.write(f"$I_{{e,total}}$ = {s_defl.get('Ie_total', 0):,.0f} mm⁴,  "
                 f"$I_{{e,DL}}$ = {s_defl.get('Ie_DL', 0):,.0f} mm⁴")

        st.write("**5. 즉시 처짐 (양단 고정보)**")
        st.latex(r"\delta = \frac{w L^4}{384 E_c I_e}")
        st.write(f"- $\\delta_{{DL}}$ = {s_defl.get('delta_DL_i', 0):.2f} mm")
        st.write(f"- $\\delta_{{LL}}$ = {s_defl.get('delta_LL_i', 0):.2f} mm")
        st.write(f"- $\\delta_{{total,i}}$ = {s_defl.get('delta_total_i', 0):.2f} mm")

        st.write("**6. 장기 처짐**")
        _xi = s_defl.get('xi', 2.0)
        _lam = s_defl.get('lambda_delta', 0)
        st.latex(r"\lambda_\Delta = \frac{\xi}{1 + 50 \rho'}")
        st.write(f"$\\xi$ = {_xi:.1f},  $\\lambda_\\Delta$ = {_lam:.2f}")
        st.write(f"$\\delta_{{long}}$ = {s_defl.get('delta_long', 0):.2f} mm")
        st.write(f"**검토 처짐** = $\\delta_{{long}} + \\delta_{{LL}}$ = {s_defl.get('delta_check', 0):.2f} mm")

        st.write("**7. 허용 처짐**")
        st.write(f"- 활하중: L/360 = {s_defl.get('delta_allow_LL', 0):.2f} mm  →  "
                 f"{'✅' if s_defl.get('check_LL', True) else '❌'}")
        st.write(f"- 총처짐: L/240 = {s_defl.get('delta_allow_total', 0):.2f} mm  →  "
                 f"{'✅' if s_defl.get('check_total', True) else '❌'}")

        # v0.6.3: 최소두께 면제 기준
        if s_defl.get('h_min_exempt'):
            st.write("**8. 최소두께 면제 검토 (KDS 41 20 30)**")
            st.write(f"$h_{{min}}$ = L / {slab_dp.get('L', 0)/s_defl['h_min_exempt']:.0f} = {s_defl['h_min_exempt']:.0f} mm  "
                     f"(t_slab = {slab_dp.get('t_slab', 0):.0f} mm)  →  "
                     f"{'면제 가능' if s_defl.get('min_thickness_exempt', False) else '면제 불가'}")


def _render_slab_rebar_expander(title, rs):
    """슬래브 배근 상세 expander"""
    with st.expander(title, expanded=False):
        st.write("**Step 1.** 소요 철근량")
        st.write(f"$A_s$ = {rs.get('As_req', 0):.2f} mm²/m")

        st.write("**Step 2.** 최대 간격 제한 (KDS 41 20 20)")
        st.write(f"$s_{{max}}$ = {rs.get('s_max', 450):.0f} mm  (min(3·t, 450))")

        st.write("**Step 3.** 규격별 소요 간격")
        _rebar_sizes = ['D10', 'D13', 'D16']
        _rows = []
        for _sz in _rebar_sizes:
            _s_req = rs.get(f's_req_{_sz}')
            _s_rnd = rs.get(f's_rounded_{_sz}')
            if _s_req is not None:
                _rows.append(f"| {_sz} | {_s_req:.0f} | {_s_rnd:.0f} |")
        if _rows:
            st.markdown("| 규격 | 소요간격 (mm) | 조정간격 (mm) |\n|------|------:|------:|\n" + '\n'.join(_rows))

        st.write("**Step 4.** 최종 선택")
        st.write(f"**{rs.get('rebar_string', '-')}** — As_provided = {rs.get('As_provided', 0):.0f} mm²/m")


def _render_stirrup_zones_table(beam_result, L_m, direction_label, fc_k):
    zones = beam_result.get('stirrup_zones', [])
    if not zones:
        return
    n = len(zones)
    st.markdown(f"**{direction_label} 보 늑근 — {n}구간 배치 (D10 U형 2지)**")
    rows = {"구간": [], "범위 (m)": [], "설계 Vu (kN)": [], "늑근 간격 (mm)": []}
    for z in zones:
        rows["구간"].append(f"구간 {z['zone_idx']}")
        rows["범위 (m)"].append(f"{z['x_start']:.2f} ~ {z['x_end']:.2f}")
        rows["설계 Vu (kN)"].append(f"{z['Vu_kN']:.1f}")
        rows["늑근 간격 (mm)"].append(f"**D10 @ {z['s']:.0f}**")
    st.table(pd.DataFrame(rows))
    with st.expander(f"{direction_label} 보 구간별 전단 설계 상세"):
        for z in zones:
            st.markdown(f"##### 구간 {z['zone_idx']}  ({z['x_start']:.2f} ~ {z['x_end']:.2f} m,  Vu = {z['Vu_kN']:.1f} kN)")
            _render_shear_expander(
                f"구간 {z['zone_idx']} 전단 설계", z['Vu_kN'], z['shear_steps'],
                beam_result['design_params']['b_beam'], fc_k)
            for warning in z['shear_warnings']:
                st.warning(warning)



def _render_deflection(results, beam_key, beam_label):
    df = results[beam_key]['deflection']
    dp = results[beam_key]['design_params']
    ok_icon = lambda v: "✅" if v else "❌"

    with st.expander(f"**{beam_label}  |  처짐 검토 {'✅ OK' if df['ok'] else '❌ NG'}**", expanded=not df['ok']):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ec (MPa)", f"{df['Ec']:.0f}")
        c2.metric("n (탄성계수비)", f"{df['n']}")
        c3.metric("Ig (mm⁴ × 10⁶)", f"{df['Ig']/1e6:.2f}")
        c4.metric("Icr (mm⁴ × 10⁶)", f"{df['Icr']/1e6:.2f}")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("균열모멘트 Mcr", f"{df['M_cr_kNm']:.2f} kN·m")
        c6.metric("서비스모멘트 Ma", f"{df['M_a_kNm']:.2f} kN·m")
        c7.metric("Ie / Ig", f"{df['Ie_total']/df['Ig']:.3f}")
        c8.metric("균열 여부", "균열" if df['cracked'] else "비균열")

        st.markdown("---")
        c9, c10, c11 = st.columns(3)
        c9.metric("사하중 즉시처짐 δ_DL", f"{df['delta_DL_i']:.2f} mm")
        c10.metric("활하중 즉시처짐 δ_LL", f"{df['delta_LL_i']:.2f} mm")
        L_mm_label = results[beam_key]['analyzer'].L_beam * 1000
        c11.metric(f"허용 δ_LL (L/360 = {L_mm_label:.0f}/360)", f"{df['delta_allow_LL']:.2f} mm")

        c12, c13, c14 = st.columns(3)
        c12.metric("장기처짐 계수 λ_Δ", f"{df['lambda_delta']:.3f}",
                   help=f"ξ={df['xi']:.1f}, ρ'={df['rho_prime']*100:.3f}%")
        c13.metric("추가 장기처짐 δ_long", f"{df['delta_long']:.2f} mm")
        c14.metric("검토 총처짐 δ_long+δ_LL", f"{df['delta_check']:.2f} mm")

        st.markdown("**처짐 판정**")
        L_mm = results[beam_key]['analyzer'].L_beam * 1000
        data = {
            "검토 항목": [
                f"① 활하중 즉시처짐 ≤ L/360 ({L_mm:.0f}/360 = {df['delta_allow_LL']:.1f} mm)",
                f"② 장기+활 처짐 ≤ L/240 ({L_mm:.0f}/240 = {df['delta_allow_total']:.1f} mm)",
                f"③ 장기+활 처짐 ≤ L/480 ({L_mm:.0f}/480 = {df['delta_allow_strict']:.1f} mm) [비구조부재]",
            ],
            "계산값 (mm)": [f"{df['delta_LL_i']:.2f}", f"{df['delta_check']:.2f}", f"{df['delta_check']:.2f}"],
            "허용값 (mm)": [f"{df['delta_allow_LL']:.2f}", f"{df['delta_allow_total']:.2f}", f"{df['delta_allow_strict']:.2f}"],
            "비율": [f"{df['ratio_LL']:.3f}", f"{df['ratio_total']:.3f}", f"{df['delta_check']/df['delta_allow_strict']:.3f}"],
            "판정": [
                ok_icon(df['check_LL'])    + (" OK" if df['check_LL']    else " NG"),
                ok_icon(df['check_total']) + (" OK" if df['check_total'] else " NG"),
                ok_icon(df['check_strict'])+ (" OK" if df['check_strict'] else " NG"),
            ],
        }
        st.table(data)

        with st.expander("처짐 계산 상세 (수식 전개)"):
            st.markdown("**재료 및 단면 특성**")
            st.latex(r"E_c = 8500\cdot(f_{ck}+4)^{1/3}\ \mathrm{[MPa]},\quad f_r = 0.63\sqrt{f_{ck}},\quad n = E_s/E_c")
            st.write(f"- Ec = **{df['Ec']:.0f} MPa**,   fr = **{df['fr']:.3f} MPa**,   n = **{df['n']:.3f}**")
            st.write(f"- 서비스 하중: w_DL = {df['w_DL']:.4f} N/mm,   w_LL = {df['w_LL']:.4f} N/mm")

            st.markdown("**균열 중립축 x_cr (탄성계수비법)**")
            st.latex(r"k = \sqrt{2n\rho+(n\rho)^2}-n\rho,\quad x_{cr}=k\cdot d")
            st.write(f"- ρ = As_bot/(b·d) = **{df['rho']*100:.4f}%**")
            st.write(f"- x_cr = **{df['x_cr']:.1f} mm**")

            st.markdown("**균열단면 2차모멘트 Icr**")
            st.latex(r"I_{cr} = \frac{b\,x_{cr}^3}{3} + n\,A_s(d-x_{cr})^2 + (n-1)\,A_s'(x_{cr}-d')^2")
            st.write(f"- Icr = **{df['Icr']/1e6:.2f} × 10⁶ mm⁴**")

            st.markdown("**유효 2차모멘트 Ie — Branson 공식 + 가중평균 (KDS 41 20 30)**")
            st.latex(r"I_e = \left(\frac{M_{cr}}{M_a}\right)^{\!3}I_g+\left[1-\left(\frac{M_{cr}}{M_a}\right)^{\!3}\right]I_{cr}\le I_g")
            st.latex(r"I_{e,avg} = 0.70\,I_{e,mid} + 0.30\,I_{e,sup} \quad\text{(양단 고정보)}")
            st.write(f"- Mcr = **{df['M_cr_kNm']:.2f} kN·m**")
            st.write(f"- Ma(지점부) = **{df['M_a_kNm']:.2f} kN·m**,   Ma(중앙부) = **{df.get('M_a_mid_kNm', df['M_a_kNm']/2):.2f} kN·m**")
            cracked_str = "**균열 발생** (Ma > Mcr — Branson Ie 적용)" if df['cracked'] else "**비균열** (Ma ≤ Mcr — Ie = Ig)"
            st.write(f"- 상태: {cracked_str}")
            _Ie_sup = df.get('Ie_sup', df['Ie_total'])
            _Ie_mid = df.get('Ie_mid', df['Ie_total'])
            st.write(f"- Ie(지점부) = **{_Ie_sup/1e6:.2f} × 10⁶ mm⁴**,   Ie(중앙부) = **{_Ie_mid/1e6:.2f} × 10⁶ mm⁴**")
            st.write(f"- **Ie(가중평균) = 0.70×{_Ie_mid/1e6:.2f} + 0.30×{_Ie_sup/1e6:.2f} = {df['Ie_total']/1e6:.2f} × 10⁶ mm⁴**   (Ig = {df['Ig']/1e6:.2f} × 10⁶)")

            st.markdown("**즉시처짐 δ (고정-고정 등분포하중)**")
            st.latex(r"\delta = \frac{w\,L^4}{384\,E_c\,I_e}")
            st.write(f"- δ_DL = {df['delta_DL_i']:.2f} mm,   δ_LL = {df['delta_LL_i']:.2f} mm")

            st.markdown("**장기처짐 λ_Δ (KDS 41 20 30 4.3.4)**")
            _alpha_sus = df.get('alpha_sus', 0.25)
            st.latex(r"\lambda_\Delta = \frac{\xi}{1+50\rho'},\quad \delta_{long}=\lambda_\Delta\cdot(\delta_{DL}+\alpha\cdot\delta_{LL})")
            st.write(f"- ξ = {df['xi']:.1f} (5년 이상 지속하중),   ρ' = {df['rho_prime']*100:.4f}%")
            st.write(f"- α = {_alpha_sus:.2f} (활하중 지속비율: 주거/사무)")
            st.write(f"- λ_Δ = {df['xi']:.1f} / (1 + 50×{df['rho_prime']:.4f}) = **{df['lambda_delta']:.3f}**")
            _delta_sus = df['delta_DL_i'] + _alpha_sus * df['delta_LL_i']
            st.write(f"- δ_long = {df['lambda_delta']:.3f} × ({df['delta_DL_i']:.2f} + {_alpha_sus:.2f}×{df['delta_LL_i']:.2f}) = {df['lambda_delta']:.3f} × {_delta_sus:.2f} = **{df['delta_long']:.2f} mm**")


def render_output_section(results, inputs):
    # Unpack results
    common   = results['common']
    beam_x   = results['beam_x']
    beam_y   = results['beam_y']
    columns  = results.get('columns', [results['column']])
    column   = columns[0]

    # === 메인 영역 탭 구조 (맨 위) ===
    _args = (results, inputs, common, beam_x, beam_y, columns, column)
    _slab_type_label = common.get('slab_type', '1방향')

    tab_result, tab_vis, tab_report = st.tabs(["📋 설계 결과", "📊 시각화", "📄 보고서"])

    with tab_vis:
        _render_visualization(*_args)

    with tab_report:
        _render_report_download(results, inputs)
        _render_todo(*_args)

    with tab_result:
        _render_design_result_tab(results, inputs, common, beam_x, beam_y, columns, column, _slab_type_label, _args)

    # (설계 결과 탭 내용은 _render_design_result_tab으로 분리)


def _render_design_result_tab(results, inputs, common, beam_x, beam_y, columns, column, _slab_type_label, _args):
    # --------------------------------------------------------------------------
    # 3.1 단면 결정 결과
    # --------------------------------------------------------------------------
    # ── 자동결정된 단면 + 사이즈 override ────────────────────────────
    st.subheader("1. 자동 결정된 단면")

    # 자동 수렴설계 값 (현재 결과에서)
    _auto_vals = {
        't_slab': int(common['t_slab']),
        'h_beam_x': int(beam_x['design_params']['h_beam']),
        'b_beam_x': int(beam_x['design_params']['b_beam']),
        'h_beam_y': int(beam_y['design_params']['h_beam']),
        'b_beam_y': int(beam_y['design_params']['b_beam']),
        'c_column': int(columns[0]['dimensions']['c_column']),
    }

    # modified_sizes: 사용자가 명시적으로 수정한 부재 키 집합
    if 'modified_sizes' not in st.session_state:
        st.session_state['modified_sizes'] = set()

    # 첫 실행 시 override를 수렴설계 값으로 초기화 + 기준값 저장
    if 'auto_ref_vals' not in st.session_state:
        st.session_state['auto_ref_vals'] = _auto_vals.copy()
    for _k, _v in _auto_vals.items():
        if f'override_{_k}' not in st.session_state:
            st.session_state[f'override_{_k}'] = _v

    # 부재별 사이즈 변경 콜백
    def _on_size_change(member_key):
        ref_vals = st.session_state.get('auto_ref_vals', {})
        override_val = st.session_state.get(f'override_{member_key}', 0)
        modified = st.session_state.get('modified_sizes', set())
        if override_val == ref_vals.get(member_key, 0):
            modified.discard(member_key)  # 자동값과 같으면 수정 해제
        else:
            modified.add(member_key)  # 다르면 수정 표시
        st.session_state['modified_sizes'] = modified
        # 전부 자동값이면 toggle ON
        st.session_state['size_auto_mode'] = len(modified) == 0

    # 자동 (수렴설계) 토글
    _auto_mode = st.toggle("🔄 자동 (수렴설계)", value=True, key="size_auto_mode")

    # 자동 모드 ON → 기준값 갱신 + override 리셋 + modified 초기화
    if _auto_mode:
        st.session_state['auto_ref_vals'] = _auto_vals.copy()
        st.session_state['modified_sizes'] = set()
        for _k, _v in _auto_vals.items():
            st.session_state[f'override_{_k}'] = _v
        st.info(
            "**🔄 단면 자동 최적화 로직**  \n"
            "· 보 춤 **h**: L/28 시작 → 처짐 NG 또는 배근 불가 시 +50mm 반복  \n"
            "· 보 폭 **b**: h×0.5 시작 → 1단 배근에 폭이 모자라면 +50mm 반복  \n"
            "· 기둥 **c**: max(b_x, b_y)+100mm 시작 → 세장비 λ>100이면 +50mm 반복"
        )
    else:
        # 비수정 부재: override 값 + 기준값을 현재 자동값으로 갱신
        _modified = st.session_state.get('modified_sizes', set())
        for _k, _v in _auto_vals.items():
            if _k not in _modified:
                st.session_state[f'override_{_k}'] = _v
                st.session_state.setdefault('auto_ref_vals', {})[_k] = _v
        st.caption("💡 수정한 부재만 고정되고 나머지는 자동 수렴설계됩니다.")
        # 강도/처짐 부족 경고 (h 또는 b 부분 고정 포함)
        _warnings = []
        _x_any_fixed = beam_x.get('size_fixed') or beam_x.get('h_fixed') or beam_x.get('b_fixed')
        if _x_any_fixed and (beam_x.get('As_top', 0) == 0.0 or beam_x.get('As_bot', 0) == 0.0):
            _warnings.append("X보: 휨 강도 부족 (단면 증가 필요)")
        elif _x_any_fixed and not beam_x.get('deflection', {}).get('ok', True):
            _warnings.append("X보: 처짐 기준 불만족 (보 춤 증가 권장)")
        _y_any_fixed = beam_y.get('size_fixed') or beam_y.get('h_fixed') or beam_y.get('b_fixed')
        if _y_any_fixed and (beam_y.get('As_top', 0) == 0.0 or beam_y.get('As_bot', 0) == 0.0):
            _warnings.append("Y보: 휨 강도 부족 (단면 증가 필요)")
        elif _y_any_fixed and not beam_y.get('deflection', {}).get('ok', True):
            _warnings.append("Y보: 처짐 기준 불만족 (보 춤 증가 권장)")
        _col_slend = column.get('slenderness') or {}
        if column.get('size_fixed') and not _col_slend.get('ok', True):
            _warnings.append("기둥: 세장비 초과 (단면 증가 필요)")
        for w in _warnings:
            st.warning(f"⚠️ {w}")

    # 수정 여부 판별
    def _is_modified(key):
        return key in st.session_state.get('modified_sizes', set())

    # 슬래브
    col_t_metric, col_t_override, col_t_detail = st.columns([2, 1, 3])
    with col_t_metric:
        st.metric("슬래브 두께 (t)", f"{common['t_slab']:.0f} mm")
    with col_t_override:
        _lbl_t = "🟡 슬래브 두께 [mm]" if _is_modified('t_slab') else "슬래브 두께 [mm]"
        st.number_input(_lbl_t, min_value=120, max_value=500,
                         step=10, key="override_t_slab",
                         on_change=_on_size_change, args=('t_slab',))
    with col_t_detail:
        with st.expander("슬래브 두께 상세"):
            st.markdown("#### 슬래브 두께 ($t$)")
            st.latex(r"L_{short} = \min(L_x, L_y)")
            st.write(f"짧은 변 길이 ($L_{{short}}$): {common['L_short']:.0f} mm")
            st.latex(r"t_{slab, raw} = L_{short} / 20")
            st.write(f"최소 두께 기준 ($t_{{slab, raw}}$): {common['t_slab_raw']:.2f} mm")
            st.latex(r"t_{slab} = \max(\text{round\_up\_to\_50}(t_{slab, raw}), 150)")
            st.write(f"최종 슬래브 두께 ($t_{{slab}}$): {common['t_slab']:.0f} mm")
            _slab_r = results.get('slab')
            if _slab_r:
                st.write(f"**슬래브 배근**: 상부근 {_slab_r['rebar_string_top']} / "
                         f"하부근 {_slab_r['rebar_string_bot']} / "
                         f"배력근 {_slab_r['rebar_string_dist']}")

    # X보
    _x_defl_gov = beam_x.get('deflection_governed', False)
    _x_h_start = beam_x['design_params']['h_beam_start']
    _x_h_L21   = beam_x['design_params']['h_beam_L21']
    _x_h_final = beam_x['design_params']['h_beam']
    _x_saved   = _x_h_L21 - _x_h_final
    col_hx_metric, col_hx_override, col_hx_detail = st.columns([2, 1, 3])
    with col_hx_metric:
        if _x_saved > 0:
            st.metric("X보 춤 (h_x)", f"{_x_h_final:.0f} mm",
                      delta=f"-{_x_saved:.0f} mm (L/21 대비 절감)")
        elif _x_defl_gov:
            st.metric("X보 춤 (h_x)", f"{_x_h_final:.0f} mm",
                      delta=f"+{_x_h_final - _x_h_start:.0f} mm (처짐 증가)",
                      delta_color="inverse")
        else:
            st.metric("X보 춤 (h_x)", f"{_x_h_final:.0f} mm")
    with col_hx_override:
        _lbl_hx = "🟡 X보 춤 [mm]" if _is_modified('h_beam_x') else "X보 춤 [mm]"
        st.number_input(_lbl_hx, min_value=200, max_value=2000,
                         step=50, key="override_h_beam_x",
                         on_change=_on_size_change, args=('h_beam_x',))
    with col_hx_detail:
        if _x_saved > 0 and not _x_defl_gov:
            st.success(f"최적화: L/21={_x_h_L21:.0f}mm → 처짐 검토 결과 {_x_h_final:.0f}mm ({_x_saved:.0f}mm 절감)")
        elif _x_defl_gov:
            st.warning(f"처짐 검토 지배: 시작점 {_x_h_start:.0f}mm (L/28) → {_x_h_final:.0f}mm로 증가 "
                       f"({beam_x.get('deflection_n_iter', 0)}회 반복)")
        with st.expander("X보 춤 상세"):
            st.write(f"KDS L/21 참조 (처짐 면제 최소 깊이): {_x_h_L21:.0f} mm")
            st.write(f"최적화 시작점 (L/28): {_x_h_start:.0f} mm")
            st.write(f"처짐 검토 후 최종 춤: **{_x_h_final:.0f} mm**")
            if _x_saved > 0:
                st.write(f"L/21 대비 절감량: **{_x_saved:.0f} mm ({_x_saved/_x_h_L21*100:.1f}%)**")

    _x_b_start  = beam_x['design_params']['b_beam_start']
    _x_b_final  = beam_x['design_params']['b_beam']
    _x_w_gov    = beam_x.get('width_governed', False)
    col_bx_metric, col_bx_override, col_bx_detail = st.columns([2, 1, 3])
    with col_bx_metric:
        if _x_w_gov:
            st.metric("X보 폭 (b_x)", f"{_x_b_final:.0f} mm",
                      delta=f"+{_x_b_final - _x_b_start:.0f} mm (배근 증가)",
                      delta_color="inverse")
        else:
            st.metric("X보 폭 (b_x)", f"{_x_b_final:.0f} mm")
    with col_bx_override:
        _lbl_bx = "🟡 X보 폭 [mm]" if _is_modified('b_beam_x') else "X보 폭 [mm]"
        st.number_input(_lbl_bx, min_value=200, max_value=1500,
                         step=50, key="override_b_beam_x",
                         on_change=_on_size_change, args=('b_beam_x',))
    with col_bx_detail:
        if _x_w_gov:
            st.info(f"폭 배근 지배: 시작 {_x_b_start:.0f}mm → {_x_b_final:.0f}mm로 증가")
        with st.expander("X보 폭 상세"):
            st.latex(r"b_{beam, raw, x} = h_{beam, x} \times 0.5")
            st.write(f"X보 최소 폭 기준 ($b_{{beam, raw, x}}$): {beam_x['analyzer'].b_beam_raw:.2f} mm")
            st.latex(r"b_{beam, start, x} = \min(\text{round\_up\_to\_50}(b_{beam, raw, x}),\ h_{beam, x})")
            st.write(f"X보 시작 폭 ($b_{{beam, start, x}}$): {_x_b_start:.0f} mm")
            st.write(f"X보 최종 폭 ($b_{{beam, x}}$): **{_x_b_final:.0f} mm**")

    # Y보
    _y_defl_gov = beam_y.get('deflection_governed', False)
    _y_h_start = beam_y['design_params']['h_beam_start']
    _y_h_L21   = beam_y['design_params']['h_beam_L21']
    _y_h_final = beam_y['design_params']['h_beam']
    _y_saved   = _y_h_L21 - _y_h_final
    col_hy_metric, col_hy_override, col_hy_detail = st.columns([2, 1, 3])
    with col_hy_metric:
        if _y_saved > 0:
            st.metric("Y보 춤 (h_y)", f"{_y_h_final:.0f} mm",
                      delta=f"-{_y_saved:.0f} mm (L/21 대비 절감)")
        elif _y_defl_gov:
            st.metric("Y보 춤 (h_y)", f"{_y_h_final:.0f} mm",
                      delta=f"+{_y_h_final - _y_h_start:.0f} mm (처짐 증가)",
                      delta_color="inverse")
        else:
            st.metric("Y보 춤 (h_y)", f"{_y_h_final:.0f} mm")
    with col_hy_override:
        _lbl_hy = "🟡 Y보 춤 [mm]" if _is_modified('h_beam_y') else "Y보 춤 [mm]"
        st.number_input(_lbl_hy, min_value=200, max_value=2000,
                         step=50, key="override_h_beam_y",
                         on_change=_on_size_change, args=('h_beam_y',))
    with col_hy_detail:
        if _y_saved > 0 and not _y_defl_gov:
            st.success(f"최적화: L/21={_y_h_L21:.0f}mm → 처짐 검토 결과 {_y_h_final:.0f}mm ({_y_saved:.0f}mm 절감)")
        elif _y_defl_gov:
            st.warning(f"처짐 검토 지배: 시작점 {_y_h_start:.0f}mm (L/28) → {_y_h_final:.0f}mm로 증가 "
                       f"({beam_y.get('deflection_n_iter', 0)}회 반복)")
        with st.expander("Y보 춤 상세"):
            st.write(f"KDS L/21 참조 (처짐 면제 최소 깊이): {_y_h_L21:.0f} mm")
            st.write(f"최적화 시작점 (L/28): {_y_h_start:.0f} mm")
            st.write(f"처짐 검토 후 최종 춤: **{_y_h_final:.0f} mm**")
            if _y_saved > 0:
                st.write(f"L/21 대비 절감량: **{_y_saved:.0f} mm ({_y_saved/_y_h_L21*100:.1f}%)**")

    _y_b_start  = beam_y['design_params']['b_beam_start']
    _y_b_final  = beam_y['design_params']['b_beam']
    _y_w_gov    = beam_y.get('width_governed', False)
    col_by_metric, col_by_override, col_by_detail = st.columns([2, 1, 3])
    with col_by_metric:
        if _y_w_gov:
            st.metric("Y보 폭 (b_y)", f"{_y_b_final:.0f} mm",
                      delta=f"+{_y_b_final - _y_b_start:.0f} mm (배근 증가)",
                      delta_color="inverse")
        else:
            st.metric("Y보 폭 (b_y)", f"{_y_b_final:.0f} mm")
    with col_by_override:
        _lbl_by = "🟡 Y보 폭 [mm]" if _is_modified('b_beam_y') else "Y보 폭 [mm]"
        st.number_input(_lbl_by, min_value=200, max_value=1500,
                         step=50, key="override_b_beam_y",
                         on_change=_on_size_change, args=('b_beam_y',))
    with col_by_detail:
        if _y_w_gov:
            st.info(f"폭 배근 지배: 시작 {_y_b_start:.0f}mm → {_y_b_final:.0f}mm로 증가")
        with st.expander("Y보 폭 상세"):
            st.latex(r"b_{beam, raw, y} = h_{beam, y} \times 0.5")
            st.write(f"Y보 최소 폭 기준 ($b_{{beam, raw, y}}$): {beam_y['analyzer'].b_beam_raw:.2f} mm")
            st.latex(r"b_{beam, start, y} = \min(\text{round\_up\_to\_50}(b_{beam, raw, y}),\ h_{beam, y})")
            st.write(f"Y보 시작 폭 ($b_{{beam, start, y}}$): {_y_b_start:.0f} mm")
            st.write(f"Y보 최종 폭 ($b_{{beam, y}}$): **{_y_b_final:.0f} mm**")

    # 기둥 단면
    st.markdown("---")
    st.markdown("#### 기둥 단면")
    # 기둥 사이즈 override (모든 기둥 공통)
    _first_col = columns[0]
    _col_c_first = _first_col['dimensions']['c_column']
    col_c_metric_g, col_c_override_g, col_c_spacer_g = st.columns([2, 1, 3])
    with col_c_metric_g:
        st.metric("기둥 단면 (c)", f"{_col_c_first:.0f} mm")
    with col_c_override_g:
        _lbl_c = "🟡 기둥 c [mm]" if _is_modified('c_column') else "기둥 c [mm]"
        st.number_input(_lbl_c, min_value=300, max_value=1500,
                         step=50, key="override_c_column",
                         on_change=_on_size_change, args=('c_column',))

    _col_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _col_tabs = [st.container()]
    else:
        _col_tabs = st.tabs(_col_tab_labels)
    for _tab_ctx, col_r in zip(_col_tabs, columns):
        with _tab_ctx:
            _col_slend_gov = col_r.get('slenderness_governed', False)
            _col_c_beam    = col_r['dimensions'].get('c_column_from_beam', col_r['dimensions']['c_column'])
            _col_c_final   = col_r['dimensions']['c_column']
            _col_delta_c   = _col_c_final - _col_c_beam
            if _col_slend_gov and _col_delta_c > 0:
                st.warning(f"세장비 검토 지배: 보 폭 기반 {_col_c_beam:.0f}mm → {_col_c_final:.0f}mm로 증가 "
                           f"({col_r.get('slenderness_n_iter', 0)}회 반복)")
            with st.expander(f"기둥 단면 상세 — {col_r.get('col_name', '')}"):
                st.latex(r"c_{raw} = \max(b_x, b_y) + 100")
                st.write(f"기둥 원시 단면 ($c_{{raw}}$): {col_r['dimensions']['c_column_raw']:.0f} mm")
                st.latex(r"c = \text{round\_up\_to\_50}(c_{raw})")
                st.write(f"보 폭 기반 기둥 단면 ($c_{{beam}}$): {_col_c_beam:.0f} mm")
                st.write(f"최종 기둥 단면 ($c$): {_col_c_final:.0f} mm")

    # === 설계 결과 탭 계속 (Override 이후) ===
    _render_sections_2_to_4(*_args)
    with st.expander(f"5. 슬래브 설계 ({_slab_type_label} 슬래브)", expanded=False):
        _render_slab_design(*_args)
    with st.expander("6. 보 설계", expanded=False):
        _render_beam_design(*_args)
    with st.expander("7. 기둥 설계", expanded=False):
        _render_column_design(*_args)
    _render_joint_seismic(*_args)
    _render_crack_development(*_args)


# === STUB 함수들 — '계속해' 시 순차적으로 내용 채움 ===

def _render_sections_2_to_4(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 2(하중), 3(부재력), 4(3D 프레임)"""

    # --------------------------------------------------------------------------
    # 3.2 하중 집계표 (Loads)
    # --------------------------------------------------------------------------
    st.subheader("2. 하중 집계표")
    st.info(
        "**⚖️ 하중 집계 로직 (KDS 41 10 15: 1.2D + 1.6L)**  \n"
        "슬래브 하중은 **단변 방향 보**에만 전달됩니다 (단변 지배, S_slab = L_short/2).  \n"
        "w_u = 1.2·(슬래브자중+마감하중)·S_slab + 1.2·보자중 + 1.6·활하중·S_slab  \n"
        "※ 보 자중은 슬래브와 겹치는 부분(b×t_slab)을 제외하여 이중 계산 방지: b×(h−t_slab)×24"
    )
    col_slab_self_metric, col_slab_self_detail = st.columns([1, 3])
    with col_slab_self_metric:
        st.write(f"슬래브 자중: {beam_x['design_params']['w_slab_self']:.2f} kN/m²")
    with col_slab_self_detail:
        with st.expander("슬래브 자중 상세"):
            st.latex(r"w_{slab, self} = (t_{slab} / 1000) \times 24 \text{ kN/m}^2")
            st.write(f"슬래브 자중 ($w_{{slab, self}}$): {beam_x['design_params']['w_slab_self']:.2f} kN/m²")

    # 슬래브 하중 분배 유형 표시
    _slab_type = common.get('slab_type', '1방향')
    _aspect_r  = common.get('aspect_ratio', 0.0)
    if _slab_type == '2방향':
        st.info(
            f"**슬래브 하중 분배: {_slab_type} 슬래브** (변장비 α = {_aspect_r:.2f} < 2.0)  \n"
            f"장변보: 사다리꼴 하중 → 등가 분담폭 $S = L_{{short}}(3-r^2)/6$  \n"
            f"단변보: 삼각형 하중 → 등가 분담폭 $S = L_{{short}}/3$"
        )
    else:
        st.info(
            f"**슬래브 하중 분배: {_slab_type} 슬래브** (변장비 α = {_aspect_r:.2f} ≥ 2.0)  \n"
            f"단변 방향 보만 하중 부담: $S = L_{{short}}/2$"
        )

    # X보 하중
    col_x_wu_metric, col_x_wu_detail = st.columns([1, 3])
    with col_x_wu_metric:
        st.write(f"X보 계수 등분포 하중 (w_u_x): {beam_x['design_params']['w_u']:.2f} kN/m")
    with col_x_wu_detail:
        with st.expander("X보 하중 상세"):
            if _slab_type == '2방향':
                _x_role = '장변(사다리꼴)' if inputs['L_x'] >= inputs['L_y'] else '단변(삼각형)'
                st.write(f"X보 역할: **{_x_role}**")
            st.write(f"X보 슬래브 분담폭 ($S_{{slab, x}}$): {common['S_slab_x'] / 1000.0:.3f} m")
            st.latex(r"w_{DL, factored, x} = 1.2 \times [(w_{slab, self} + DL_{area}) \times (S_{slab, x} / 1000) + w_{beam, self, x}]")
            st.write(f"X보 계수 고정하중 ($w_{{DL, factored, x}}$): {beam_x['design_params']['w_DL_factored']:.2f} kN/m")
            st.latex(r"w_{LL, factored, x} = 1.6 \times [LL_{area} \times (S_{slab, x} / 1000)]")
            st.write(f"X보 계수 활하중 ($w_{{LL, factored, x}}$): {beam_x['design_params']['w_LL_factored']:.2f} kN/m")
            st.latex(r"w_{u, x} = w_{DL, factored} + w_{LL, factored}")
            st.write(f"X보 최종 계수하중 ($w_{{u, x}}$): {beam_x['design_params']['w_u']:.2f} kN/m")

    # Y보 하중
    col_y_wu_metric, col_y_wu_detail = st.columns([1, 3])
    with col_y_wu_metric:
        st.write(f"Y보 계수 등분포 하중 (w_u_y): {beam_y['design_params']['w_u']:.2f} kN/m")
    with col_y_wu_detail:
        with st.expander("Y보 하중 상세"):
            if _slab_type == '2방향':
                _y_role = '장변(사다리꼴)' if inputs['L_y'] > inputs['L_x'] else '단변(삼각형)'
                st.write(f"Y보 역할: **{_y_role}**")
            st.write(f"Y보 슬래브 분담폭 ($S_{{slab, y}}$): {common['S_slab_y'] / 1000.0:.3f} m")
            st.latex(r"w_{DL, factored, y} = 1.2 \times [(w_{slab, self} + DL_{area}) \times (S_{slab, y} / 1000) + w_{beam, self, y}]")
            st.write(f"Y보 계수 고정하중 ($w_{{DL, factored, y}}$): {beam_y['design_params']['w_DL_factored']:.2f} kN/m")
            st.latex(r"w_{LL, factored, y} = 1.6 \times [LL_{area} \times (S_{slab, y} / 1000)]")
            st.write(f"Y보 계수 활하중 ($w_{{LL, factored, y}}$): {beam_y['design_params']['w_LL_factored']:.2f} kN/m")
            st.latex(r"w_{u, y} = w_{DL, factored} + w_{LL, factored}")
            st.write(f"Y보 최종 계수하중 ($w_{{u, y}}$): {beam_y['design_params']['w_u']:.2f} kN/m")

    # --------------------------------------------------------------------------
    # 3.3 부재력 결과 (Forces)
    # --------------------------------------------------------------------------
    st.subheader("3. 부재력 결과 (강접합 고정단 보)")
    st.info(
        "**📊 부재력 산정 로직 — 고정단 보 (Fixed-End Beam)**  \n"
        "양단 고정 강접합 보에 등분포하중 w_u 작용 시:  \n"
        "· 지점부 부(−)모멘트: **M_neg = w·L²/12** (상부 인장 → 상부근 배근)  \n"
        "· 중앙부 정(+)모멘트: **M_pos = w·L²/24** (하부 인장 → 하부근 배근)  \n"
        "· 최대 전단력: **V_max = w·L/2** (지점부 발생)  \n"
        "기둥 축력·모멘트는 보 단부 반력(강접합 전달)과 기둥 자중을 합산합니다."
    )

    # X보
    col_mx_neg_metric, col_mx_neg_detail = st.columns([1, 3])
    with col_mx_neg_metric:
        st.metric("X보 지점부 부모멘트 (M_neg_x)", f"{beam_x['member_forces']['M_neg']:.2f} kN·m")
    with col_mx_neg_detail:
        with st.expander("X보 지점부 모멘트 상세"):
            st.latex(r"M_{neg, x} = w_{u, x} \times L_x^2 / 12 \text{ (고정단)}")
            st.write(f"X보 지점부 부모멘트 ($M_{{neg, x}}$): {beam_x['member_forces']['M_neg']:.2f} kN·m")

    col_mx_pos_metric, col_mx_pos_detail = st.columns([1, 3])
    with col_mx_pos_metric:
        st.metric("X보 중앙부 정모멘트 (M_pos_x)", f"{beam_x['member_forces']['M_pos']:.2f} kN·m")
    with col_mx_pos_detail:
        with st.expander("X보 중앙부 모멘트 상세"):
            st.latex(r"M_{pos, x} = w_{u, x} \times L_x^2 / 24 \text{ (고정단)}")
            st.write(f"X보 중앙부 정모멘트 ($M_{{pos, x}}$): {beam_x['member_forces']['M_pos']:.2f} kN·m")

    col_vx_metric, col_vx_detail = st.columns([1, 3])
    with col_vx_metric:
        st.metric("X보 최대 전단력 (V_max_x)", f"{beam_x['member_forces']['V_max']:.2f} kN")
    with col_vx_detail:
        with st.expander("X보 전단력 상세"):
            st.latex(r"V_{max, x} = w_{u, x} \times L_x / 2")
            st.write(f"X보 최대 전단력 ($V_{{max, x}}$): {beam_x['member_forces']['V_max']:.2f} kN")

    # Y보
    col_my_neg_metric, col_my_neg_detail = st.columns([1, 3])
    with col_my_neg_metric:
        st.metric("Y보 지점부 부모멘트 (M_neg_y)", f"{beam_y['member_forces']['M_neg']:.2f} kN·m")
    with col_my_neg_detail:
        with st.expander("Y보 지점부 모멘트 상세"):
            st.latex(r"M_{neg, y} = w_{u, y} \times L_y^2 / 12 \text{ (고정단)}")
            st.write(f"Y보 지점부 부모멘트 ($M_{{neg, y}}$): {beam_y['member_forces']['M_neg']:.2f} kN·m")

    col_my_pos_metric, col_my_pos_detail = st.columns([1, 3])
    with col_my_pos_metric:
        st.metric("Y보 중앙부 정모멘트 (M_pos_y)", f"{beam_y['member_forces']['M_pos']:.2f} kN·m")
    with col_my_pos_detail:
        with st.expander("Y보 중앙부 모멘트 상세"):
            st.latex(r"M_{pos, y} = w_{u, y} \times L_y^2 / 24 \text{ (고정단)}")
            st.write(f"Y보 중앙부 정모멘트 ($M_{{pos, y}}$): {beam_y['member_forces']['M_pos']:.2f} kN·m")

    col_vy_metric, col_vy_detail = st.columns([1, 3])
    with col_vy_metric:
        st.metric("Y보 최대 전단력 (V_max_y)", f"{beam_y['member_forces']['V_max']:.2f} kN")
    with col_vy_detail:
        with st.expander("Y보 전단력 상세"):
            st.latex(r"V_{max, y} = w_{u, y} \times L_y / 2")
            st.write(f"Y보 최대 전단력 ($V_{{max, y}}$): {beam_y['member_forces']['V_max']:.2f} kN")

    # 기둥 부재력
    st.markdown("---")
    st.markdown("#### 기둥 부재력 결과")
    _col_force_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _col_force_tabs = [st.container()]
    else:
        _col_force_tabs = st.tabs(_col_force_tab_labels)
    for _ftab, col_r in zip(_col_force_tabs, columns):
        with _ftab:
            col_pu_metric, col_pu_detail = st.columns([1, 3])
            with col_pu_metric:
                st.metric(f"기둥 축력 Pu — {col_r.get('col_name','')}", f"{col_r['axial_moment']['Pu']:.2f} kN")
            with col_pu_detail:
                with st.expander("기둥 축력 상세"):
                    st.markdown("**입력 추가 축하중 + 보 단부 반력 + 기둥 자중**")
                    pb = col_r['pu_breakdown']
                    st.write(f"- 입력 추가 축하중 ($P_{{u,add}}$): **{pb['Pu_input']:.2f} kN**")
                    st.write(f"- X방향 보 단부 반력 ($V_{{max,x}}$): **{pb['V_beam_x']:.2f} kN**")
                    st.write(f"- Y방향 보 단부 반력 ($V_{{max,y}}$): **{pb['V_beam_y']:.2f} kN**")
                    st.write(f"- 기둥 자중 ($P_{{self}}$): **{pb['P_self']:.2f} kN**")
                    st.markdown(f"**합계 ($P_u$): {pb['Pu_total']:.2f} kN**")

            col_mu_metric, col_mu_detail = st.columns([1, 3])
            mb = col_r['mu_breakdown']
            _mu_design = mb.get('Mu_design', col_r['axial_moment']['Mu'])
            with col_mu_metric:
                st.metric(f"기둥 설계 휨모멘트 (SRSS) — {col_r.get('col_name','')}", f"{_mu_design:.2f} kN·m")
            with col_mu_detail:
                with st.expander("기둥 휨모멘트 상세 (강접합 + SRSS 조합)"):
                    st.markdown("**X·Y 방향 각각 산정 후 SRSS 조합: $M_u = \\sqrt{M_{ux}^2 + M_{uy}^2}$**")
                    _col_mx, _col_my = st.columns(2)
                    with _col_mx:
                        st.markdown("**X방향 (Mux)**")
                        st.write(f"- 입력 추가 ($M_{{ux,add}}$): **{mb['Mux_add']:.2f} kN·m**")
                        st.write(f"- 보 단부 부모멘트 ($M_{{neg,x}}$): **{mb['M_neg_x']:.2f} kN·m**")
                        st.write(f"- **합계 $M_{{ux}}$: {mb['Mux_total']:.2f} kN·m**")
                    with _col_my:
                        st.markdown("**Y방향 (Muy)**")
                        st.write(f"- 입력 추가 ($M_{{uy,add}}$): **{mb['Muy_add']:.2f} kN·m**")
                        st.write(f"- 보 단부 부모멘트 ($M_{{neg,y}}$): **{mb['M_neg_y']:.2f} kN·m**")
                        st.write(f"- **합계 $M_{{uy}}$: {mb['Muy_total']:.2f} kN·m**")
                    st.markdown(f"**SRSS 설계 모멘트 ($M_u$): {_mu_design:.2f} kN·m**")

            # 하중조합 테이블
            _combos = col_r.get('load_combos', [])
            if len(_combos) > 1:
                with st.expander(f"하중조합 상세 — 지배 조합: **{col_r.get('governing_combo', '')}**"):
                    _combo_rows = []
                    for _lc in _combos:
                        _combo_rows.append({
                            '하중조합': _lc['name'],
                            'Pu [kN]': f"{_lc['Pu']:.1f}",
                            'Mux [kN·m]': f"{_lc['Mux']:.1f}",
                            'Muy [kN·m]': f"{_lc['Muy']:.1f}",
                        })
                    st.table(pd.DataFrame(_combo_rows))
    st.markdown("---")

    # --------------------------------------------------------------------------
    # 3.4 3D 프레임 부재력도 (SFD & BMD)
    # --------------------------------------------------------------------------
    st.subheader("4. 3D 프레임 부재력도 (SFD & BMD)")
    st.info("💡 3D 구조물 프레임 상에서 부재력을 직관적으로 확인합니다. 시스템 부하를 방지하기 위해 버튼 클릭 시에만 렌더링됩니다.")

    col_vis_opt, col_vis_btn = st.columns([2, 1])
    with col_vis_opt:
        vis_options = st.multiselect(
            "표시할 부재력 다이어그램 선택 (다중 선택 가능)",
            ["보 SFD", "보 BMD", "기둥 AFD", "기둥 BMD"],
            default=["보 BMD"]
        )
    with col_vis_btn:
        st.write("")
        render_btn = st.button("📊 3D 프레임 렌더링 실행", use_container_width=True, type="primary")

    if render_btn:
        with st.spinner("3D 프레임을 렌더링 중입니다... (잠시만 기다려주세요)"):
            from visualization import plot_3d_frame_forces
            fig_3d_forces = plot_3d_frame_forces(results, inputs, vis_options)
            st.plotly_chart(fig_3d_forces, width='stretch', key="chart_3d_forces")

    st.divider()


def _render_beam_design(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 5: 보 설계 (휨 + 전단 + 처짐 + 배근 + 단면도)"""

    # --------------------------------------------------------------------------
    # 5. 보 설계
    # --------------------------------------------------------------------------
    st.markdown("#### 6-1. 휨 설계 (강접합 이중 배근)")
    st.info(
        "**📐 휨 설계 로직 (KDS 41 20 20)**  \n"
        "강접합 고정단 보이므로 **지점부(M_neg)** 와 **중앙부(M_pos)** 에 각각 설계합니다.  \n"
        "M_neg = wL²/12 로 M_pos(=wL²/24)의 **2배** → 상부근이 더 굵어지는 원인.  \n\n"
        "① fck에 따라 **β₁** 결정 (등가응력블록 깊이 계수)  \n"
        "② **유효깊이 d 산정 — 2-패스법**: 철근 직경을 알아야 d를 계산하고, d를 알아야 철근 직경을 정할 수 있는 닭-달걀 문제를 해결하기 위해 두 번 계산합니다.  \n"
        "   · 1패스: D25 철근이라고 임시 가정 → As 어림산정  \n"
        "   · 2패스: 어림 As에 맞는 실제 최적 직경 추정 → d_c = 피복(40)+늑근(10)+d_b/2 로 정밀화  \n"
        "③ **φ–εt 수렴 루프**: 강도감소계수 φ는 철근 변형률 εt에 따라 달라지고, εt는 다시 φ로 산정된 As에 달라지는 순환 참조 문제가 있습니다.  \n"
        "   → φ=0.85 초기 가정 → As 계산 → εt 재계산 → φ 갱신 → 변화량 < 0.0001 이면 수렴 (≤10회)  \n"
        "④ 공칭저항계수 Rn으로 **ρ_req 역산** → ρ_min 미달 시 상향  \n"
        "⑤ 등가응력블록 a·c 계산 → **εt 판정**: ≥0.005 인장지배(φ=0.85), 0.002~0.005 전이구간(φ 보간)"
    )

    # X보 상부근 (M_neg)
    col_as_xt_metric, col_as_xt_detail = st.columns([1, 3])
    with col_as_xt_metric:
        st.write(f"**X보 상부근 (지점부 M_neg): {beam_x['As_top']:.2f} mm²**")
        for warning in beam_x['warnings_top']: st.warning(warning)
    with col_as_xt_detail:
        _render_flexural_expander(
            "X보 상부근 휨 설계 상세",
            beam_x['member_forces']['M_neg'], beam_x['flexural_steps_top'],
            beam_x['design_params']['b_beam'], beam_x['design_params']['h_beam'],
            beam_x['As_top'], inputs['fc_k'], inputs['fy'])

    # X보 하부근 (M_pos)
    col_as_xb_metric, col_as_xb_detail = st.columns([1, 3])
    with col_as_xb_metric:
        st.write(f"**X보 하부근 (중앙부 M_pos): {beam_x['As_bot']:.2f} mm²**")
        for warning in beam_x['warnings_bot']: st.warning(warning)
    with col_as_xb_detail:
        _render_flexural_expander(
            "X보 하부근 휨 설계 상세",
            beam_x['member_forces']['M_pos'], beam_x['flexural_steps_bot'],
            beam_x['design_params']['b_beam'], beam_x['design_params']['h_beam'],
            beam_x['As_bot'], inputs['fc_k'], inputs['fy'])

    # Y보 상부근 (M_neg)
    col_as_yt_metric, col_as_yt_detail = st.columns([1, 3])
    with col_as_yt_metric:
        st.write(f"**Y보 상부근 (지점부 M_neg): {beam_y['As_top']:.2f} mm²**")
        for warning in beam_y['warnings_top']: st.warning(warning)
    with col_as_yt_detail:
        _render_flexural_expander(
            "Y보 상부근 휨 설계 상세",
            beam_y['member_forces']['M_neg'], beam_y['flexural_steps_top'],
            beam_y['design_params']['b_beam'], beam_y['design_params']['h_beam'],
            beam_y['As_top'], inputs['fc_k'], inputs['fy'])

    # Y보 하부근 (M_pos)
    col_as_yb_metric, col_as_yb_detail = st.columns([1, 3])
    with col_as_yb_metric:
        st.write(f"**Y보 하부근 (중앙부 M_pos): {beam_y['As_bot']:.2f} mm²**")
        for warning in beam_y['warnings_bot']: st.warning(warning)
    with col_as_yb_detail:
        _render_flexural_expander(
            "Y보 하부근 휨 설계 상세",
            beam_y['member_forces']['M_pos'], beam_y['flexural_steps_bot'],
            beam_y['design_params']['b_beam'], beam_y['design_params']['h_beam'],
            beam_y['As_bot'], inputs['fc_k'], inputs['fy'])

    st.divider()

    # --------------------------------------------------------------------------
    # 3.6 전단 설계 결과
    # --------------------------------------------------------------------------
    st.markdown("#### 6-2. 전단 설계")
    st.info(
        "**✂️ 전단 설계 로직 (KDS 41 20 22)**  \n"
        "D10 U형 늑근 2지(Av = 142.7 mm²)를 가정하고 늑근 간격을 결정합니다.  \n\n"
        "① Vn = Vu/φ (φ=0.75)  \n"
        "② **Vc** = (1/6)·√fck·bw·d  — 콘크리트가 부담하는 전단강도  \n"
        "③ **Vs** = Vn − Vc  — 전단철근이 추가로 부담해야 할 강도  \n"
        "④ **s_req** = Av·fyt·d / Vs  — 이론적 소요 간격  \n"
        "⑤ **s_max,Av**: 최소전단철근 규정에 의한 상한  \n"
        "⑥ **s_max,geom**: Vs 크기에 따라 d/2(≤600) 또는 d/4(≤300)  \n"
        "⑦ 세 값 중 최솟값 → **50mm 단위 내림** 적용"
    )

    # X보
    col_shear_x_metric, col_shear_x_detail = st.columns([1, 3])
    with col_shear_x_metric:
        st.write(f"**X방향 보 지점부 늑근 간격: {beam_x['s']:.0f} mm**")
        for warning in beam_x['shear_warnings']: st.warning(warning)
    with col_shear_x_detail:
        _Vu_x = beam_x['shear_steps'].get('V_at_d', beam_x['member_forces']['V_max'])
        _render_shear_expander("X방향 보 전단 설계 상세 (위험단면 전단력 기준)",
                               _Vu_x, beam_x['shear_steps'],
                               beam_x['design_params']['b_beam'], inputs['fc_k'])
    _render_stirrup_zones_table(beam_x, inputs['L_x'] / 1000.0, "X방향", inputs['fc_k'])

    # Y보
    col_shear_y_metric, col_shear_y_detail = st.columns([1, 3])
    with col_shear_y_metric:
        st.write(f"**Y방향 보 지점부 늑근 간격: {beam_y['s']:.0f} mm**")
        for warning in beam_y['shear_warnings']: st.warning(warning)
    with col_shear_y_detail:
        _Vu_y = beam_y['shear_steps'].get('V_at_d', beam_y['member_forces']['V_max'])
        _render_shear_expander("Y방향 보 전단 설계 상세 (위험단면 전단력 기준)",
                               _Vu_y, beam_y['shear_steps'],
                               beam_y['design_params']['b_beam'], inputs['fc_k'])
    _render_stirrup_zones_table(beam_y, inputs['L_y'] / 1000.0, "Y방향", inputs['fc_k'])

    st.divider()

    # --------------------------------------------------------------------------
    # 7.5 처짐 검토
    # --------------------------------------------------------------------------
    st.markdown("#### 6-3. 처짐 검토 (KDS 41 20 30 4.3)")
    st.caption("고정단 보 δ = wL⁴/(384·Ec·Ie)  |  허용: 활하중 L/360, 장기+활 L/240 (비구조부재 미고려) / L/480 (고려)")
    st.info(
        "**📏 처짐 계산 로직 — Branson 유효단면법 (KDS 41 20 30)**  \n"
        "콘크리트 보는 균열이 생기면 단면 강성이 크게 떨어집니다. 하지만 균열 구간과 비균열 구간이 섞여 있어서  \n"
        "'완전 균열 단면(Icr)'과 '균열 없는 단면(Ig)' 사이의 **유효값 Ie를 보간**하는 방식을 사용합니다.  \n\n"
        "① **x_cr** 산정: 균열이 생겼을 때 중립축 위치 (탄성계수비 n=Es/Ec로 철근을 콘크리트로 환산)  \n"
        "② **Icr**: 균열 단면의 2차모멘트 (중립축 위 콘크리트 + 환산 철근 기여)  \n"
        "③ **Ie (Branson)**: 실제 모멘트 Ma가 클수록 Icr에 가까워지고, Mcr보다 작으면 Ie = Ig 그대로 사용  \n"
        "④ **즉시처짐** δ = wL⁴/(384·Ec·Ie) — 고정단 보 공식 (단순보의 5/384 계수와 다름에 주의)  \n"
        "⑤ **장기처짐**: 콘크리트 크리프로 인해 시간이 지날수록 처짐이 추가됩니다.  \n"
        "   λ_Δ = ξ/(1+50ρ')로 증폭 — ρ'(압축철근비)가 클수록 장기처짐 억제 효과  \n"
        "⑥ 판정: ① 활하중 처짐 ≤ L/360, ② 장기+활 처짐 ≤ L/240 (또는 비구조부재 손상 고려 시 L/480)"
    )


    _render_deflection(results, 'beam_x', 'X방향 보')
    _render_deflection(results, 'beam_y', 'Y방향 보')

    st.divider()

    st.markdown("#### 6-4. 보 배근 결과")
    st.info(
        "**🔩 배근 탐색 로직 (KDS 41 20 52)**  \n"
        "소요 As를 만족하는 **최소 규격**을 자동 탐색합니다.  \n\n"
        "D13 → D16 → D19 → D22 → D25 → D29 → D32 순서로 검토:  \n"
        "각 규격마다 ① **S_min** = max(4/3·dagg, db) 산정  \n"
        "② 필요 가닥수 n 계산 → ③ **소요폭** = n·db + (n−1)·S_min ≤ b_net 이면 채택  \n"
        "모든 규격 불가 시 → **D25 2단 배근** 폴백"
    )

    # X보
    st.markdown("#### X방향 보 배근")
    col_rebar_xt_metric, col_rebar_xt_detail = st.columns([1, 3])
    with col_rebar_xt_metric:
        st.write(f"**상부근: {beam_x['rebar_string_top']}** (As={beam_x['As_provided_top']:.0f} mm², {beam_x['layer_top']}단)")
        for warning in beam_x['rebar_warnings_top']: st.warning(warning)
    with col_rebar_xt_detail:
        _render_rebar_expander("X보 상부근 배근 상세", beam_x['rebar_steps_top'],
                               beam_x['As_top'], beam_x['design_params']['b_beam'])

    col_rebar_xb_metric, col_rebar_xb_detail = st.columns([1, 3])
    with col_rebar_xb_metric:
        st.write(f"**하부근: {beam_x['rebar_string_bot']}** (As={beam_x['As_provided_bot']:.0f} mm², {beam_x['layer_bot']}단)")
        for warning in beam_x['rebar_warnings_bot']: st.warning(warning)
    with col_rebar_xb_detail:
        _render_rebar_expander("X보 하부근 배근 상세", beam_x['rebar_steps_bot'],
                               beam_x['As_bot'], beam_x['design_params']['b_beam'])

    # Y보
    st.markdown("#### Y방향 보 배근")
    col_rebar_yt_metric, col_rebar_yt_detail = st.columns([1, 3])
    with col_rebar_yt_metric:
        st.write(f"**상부근: {beam_y['rebar_string_top']}** (As={beam_y['As_provided_top']:.0f} mm², {beam_y['layer_top']}단)")
        for warning in beam_y['rebar_warnings_top']: st.warning(warning)
    with col_rebar_yt_detail:
        _render_rebar_expander("Y보 상부근 배근 상세", beam_y['rebar_steps_top'],
                               beam_y['As_top'], beam_y['design_params']['b_beam'])

    col_rebar_yb_metric, col_rebar_yb_detail = st.columns([1, 3])
    with col_rebar_yb_metric:
        st.write(f"**하부근: {beam_y['rebar_string_bot']}** (As={beam_y['As_provided_bot']:.0f} mm², {beam_y['layer_bot']}단)")
        for warning in beam_y['rebar_warnings_bot']: st.warning(warning)
    with col_rebar_yb_detail:
        _render_rebar_expander("Y보 하부근 배근 상세", beam_y['rebar_steps_bot'],
                               beam_y['As_bot'], beam_y['design_params']['b_beam'])

    # ── 보 단면도 & 측면도 (MIDAS 스타일: X방향 → Y방향 순서) ──
    st.markdown("---")
    st.markdown("##### X방향 보 단면도 (END-I / MID / END-J)")
    fig_x_combined = plot_rebar_section(
        beam_x['design_params']['b_beam'], beam_x['design_params']['h_beam'],
        beam_x['rebar_string_top'], beam_x['rebar_steps_top'], beam_x['layer_top'],
        beam_x['rebar_string_bot'], beam_x['rebar_steps_bot'], beam_x['layer_bot'],
        'X', beam_x['s'], section_location='combined',
        rebar_string_min=beam_x['rebar_string_min'],
        rebar_steps_min=beam_x['rebar_steps_min'],
        layer_min=beam_x['layer_min'])
    st.pyplot(fig_x_combined); plt.close(fig_x_combined)

    st.markdown("##### Y방향 보 단면도 (END-I / MID / END-J)")
    fig_y_combined = plot_rebar_section(
        beam_y['design_params']['b_beam'], beam_y['design_params']['h_beam'],
        beam_y['rebar_string_top'], beam_y['rebar_steps_top'], beam_y['layer_top'],
        beam_y['rebar_string_bot'], beam_y['rebar_steps_bot'], beam_y['layer_bot'],
        'Y', beam_y['s'], section_location='combined',
        rebar_string_min=beam_y['rebar_string_min'],
        rebar_steps_min=beam_y['rebar_steps_min'],
        layer_min=beam_y['layer_min'])
    st.pyplot(fig_y_combined); plt.close(fig_y_combined)

    with st.expander("Beam Side View (Debugging)", expanded=False):
        fig2 = plot_beam_side_view(
            inputs['L_x'], beam_x['design_params']['h_beam'],
            beam_x['rebar_string_top'], beam_x['rebar_steps_top'], beam_x['layer_top'],
            beam_x['rebar_string_bot'], beam_x['rebar_steps_bot'], beam_x['layer_bot'],
            beam_x['s'], 'X',
            rebar_string_min=beam_x['rebar_string_min'],
            rebar_steps_min=beam_x['rebar_steps_min'],
            layer_min=beam_x['layer_min'],
            dev_top=beam_x.get('dev_top'), dev_bot=beam_x.get('dev_bot'),
            stirrup_zones=beam_x.get('stirrup_zones'))
        st.pyplot(fig2); plt.close(fig2)
        fig5 = plot_beam_side_view(
            inputs['L_y'], beam_y['design_params']['h_beam'],
            beam_y['rebar_string_top'], beam_y['rebar_steps_top'], beam_y['layer_top'],
            beam_y['rebar_string_bot'], beam_y['rebar_steps_bot'], beam_y['layer_bot'],
            beam_y['s'], 'Y',
            rebar_string_min=beam_y['rebar_string_min'],
            rebar_steps_min=beam_y['rebar_steps_min'],
            layer_min=beam_y['layer_min'],
            dev_top=beam_y.get('dev_top'), dev_bot=beam_y.get('dev_bot'),
            stirrup_zones=beam_y.get('stirrup_zones'))
        st.pyplot(fig5); plt.close(fig5)

    # ── 바닥보 (보 설계 하위) ──
    _render_ground_beam(results, inputs, common, beam_x, beam_y, columns, column)

def _render_column_design(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 6: 기둥 설계 (세장비 + P-M + 배근 + 단면도)"""

    # --------------------------------------------------------------------------
    # 7.6 기둥 세장비 검토
    # --------------------------------------------------------------------------
    st.markdown("#### 7-1. 세장비 검토 (KDS 41 20 40)")
    st.caption("λ = k·l_u / r  |  λ ≤ 22: 단주  |  22 < λ ≤ 100: 세장주 (δ_ns 증폭)  |  λ > 100: 설계 불가")
    st.info(
        "**🏗️ 세장비 검토 로직 — 비횡이동 골조 (Non-sway, KDS 41 20 40)**  \n"
        "기둥이 가늘고 길면(세장하면) 좌굴 때문에 실제 버티는 모멘트가 처음 계산값보다 **커질 수** 있습니다.  \n"
        "이를 '2차 모멘트 효과'라고 하며, 세장비 λ로 그 위험도를 판단합니다.  \n\n"
        "① **λ** = k·lu / r 산정 (r = 0.3c: 정사각형 단면 회전반경, k = 1.0: 핀-핀 보수적 가정)  \n"
        "② 구간 판정:  \n"
        "   · λ ≤ 22 → **단주**: 2차 효과 무시 가능, P-M 그대로 설계  \n"
        "   · 22 < λ ≤ 100 → **세장주**: 모멘트를 증폭계수 δ_ns 배 키운 후 P-M 재설계  \n"
        "   · λ > 100 → **설계 불가**: 단면 증가 필요  \n"
        "③ **모멘트 증폭 계산**: EI(유효강성) → Pc(임계좌굴하중) →  \n"
        "   δ_ns = Cm/(1 − Pu/0.75Pc): Pu가 Pc의 75%에 근접할수록 폭발적으로 커짐  \n"
        "※ βd = 0.6 (지속하중 60% 가정), Cm = 1.0 (보수적 가정)")

    _slend_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _slend_tabs = [st.container()]
    else:
        _slend_tabs = st.tabs(_slend_tab_labels)

    for _stab, col_r in zip(_slend_tabs, columns):
        with _stab:
            _slend = col_r.get('slenderness', {})
            if not _slend:
                continue
            _cat_label = {'short': '단주 (Short Column)', 'slender': '세장주 (Slender Column)',
                          'prohibited': '설계불가 (Prohibited)'}.get(_slend.get('category',''), '-')
            _cat_ok    = _slend.get('category') in ('short', 'slender') and _slend.get('ok', False)
            _ok_icon   = "✅" if _cat_ok else "❌"

            with st.expander(f"**{col_r.get('col_name','')} 세장비 검토  |  λ = {_slend.get('lambda_ratio', 0):.1f}  →  {_cat_label}  {_ok_icon}**",
                             expanded=_slend.get('category') != 'short'):
                cs1, cs2, cs3, cs4 = st.columns(4)
                cs1.metric("비지지 길이 l_u", f"{_slend.get('l_u', 0):.0f} mm")
                cs2.metric("회전반경 r = 0.3c", f"{_slend.get('r', 0):.1f} mm")
                cs3.metric("유효길이계수 k", f"{_slend.get('k', 1.0):.1f}")
                cs4.metric("세장비 λ", f"{_slend.get('lambda_ratio', 0):.1f}")
                st.markdown("---")

                if _slend.get('category') == 'short':
                    st.success(f"✅ **단주 (λ = {_slend['lambda_ratio']:.1f} ≤ 22)**: 모멘트 증폭 없음.")
                elif _slend.get('category') == 'slender':
                    cs5, cs6, cs7, cs8 = st.columns(4)
                    cs5.metric("Ec (MPa)", f"{_slend.get('Ec', 0):.0f}")
                    cs6.metric("Ig (mm⁴ × 10⁶)", f"{_slend.get('Ig', 0)/1e6:.2f}")
                    cs7.metric("임계좌굴하중 Pc", f"{_slend.get('Pc_kN', 0):.2f} kN")
                    cs8.metric("Cm", f"{_slend.get('Cm', 1.0):.2f}")
                    if _slend.get('stable', True):
                        cs9, cs10, cs11 = st.columns(3)
                        cs9.metric("증폭계수 δ_ns", f"{_slend.get('delta_ns', 1.0):.3f}")
                        cs10.metric("원래 Mu", f"{_slend.get('Mu_original', 0):.2f} kN·m")
                        cs11.metric("증폭 후 Mu", f"{_slend.get('Mu_magnified', 0):.2f} kN·m")
                        if _slend.get('delta_ns', 1.0) > 1.0:
                            st.warning(f"⚠️ 세장주: Mu를 δ_ns = {_slend['delta_ns']:.3f}배 증폭하여 P-M 설계 적용")
                        else:
                            st.success("✅ 세장주이나 모멘트 증폭계수 δ_ns = 1.0 (증폭 없음)")
                    else:
                        st.error(f"❌ 좌굴 불안정: Pu ({col_r['axial_moment']['Pu']:.2f} kN) ≥ 0.75·Pc ({0.75*_slend['Pc_kN']:.2f} kN) — 단면 증가 필요")
                else:
                    st.error(f"❌ 설계 불가 (λ = {_slend['lambda_ratio']:.1f} > 100) — 단면을 증가하여야 합니다.")

                with st.expander("세장비 계산 상세"):
                    st.write(f"- k = {_slend.get('k', 1.0):.1f} (핀-핀 보수적 가정)")
                    st.write(f"- l_u = {_slend.get('l_u', 0):.0f} mm (기둥 높이 = 비지지 길이)")
                    st.write(f"- r = 0.3 × c = 0.3 × {col_r['dimensions']['c_column']:.0f} = {_slend.get('r', 0):.1f} mm")
                    st.write(f"- λ = k·l_u/r = {_slend.get('lambda_ratio', 0):.2f}")
                    if _slend.get('category') == 'slender':
                        st.write(f"- β_d = {_slend.get('beta_d', 0.6):.2f} (지속하중 비율 = 1.2D/(1.2D+1.6L))")
                        st.write(f"- EI = 0.4·Ec·Ig/(1+β_d) = {_slend.get('EI', 0):.3e} N·mm²")
                        st.write(f"- Pc = π²·EI/(k·l_u)² = {_slend.get('Pc_kN', 0):.2f} kN")
                        if _slend.get('stable', True):
                            Pu_N = col_r['axial_moment']['Pu'] * 1000
                            Pc_N = _slend.get('Pc_kN', 0) * 1000
                            denom = 1.0 - Pu_N / (0.75 * Pc_N) if Pc_N > 0 else 1.0
                            st.write(f"- δ_ns = Cm / (1 - Pu/0.75Pc) = {_slend.get('Cm',1.0):.1f} / {denom:.4f} = {_slend.get('delta_ns', 1.0):.3f}")

            if col_r.get('convergence_failed', False):
                st.error(f"⚠️ [{col_r.get('col_name','')}] 세장비-P/M 수렴 루프가 최대 반복 횟수를 초과하여 강제 종료되었습니다.")

    st.divider()

    # 기둥 하중조합 상세
    st.markdown("---")
    st.markdown("#### 7-2. 기둥 하중 분해 및 하중조합")
    _lc_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _lc_tabs = [st.container()]
    else:
        _lc_tabs = st.tabs(_lc_tab_labels)

    for _lctab, col_r in zip(_lc_tabs, columns):
        with _lctab:
            _pu_bd = col_r.get('pu_breakdown', {})
            _mu_bd = col_r.get('mu_breakdown', {})
            if _pu_bd or _mu_bd:
                with st.expander("축력·모멘트 분해 + 하중조합 상세", expanded=False):
                    if _pu_bd:
                        st.markdown("**축력 분해 (Pu)**")
                        st.write(f"- 상부층 전달 축력 (Pu_add): {_pu_bd.get('Pu_input', 0):.1f} kN")
                        st.write(f"- X보 반력 (V_beam_x): {_pu_bd.get('V_beam_x', 0):.1f} kN")
                        st.write(f"- Y보 반력 (V_beam_y): {_pu_bd.get('V_beam_y', 0):.1f} kN")
                        st.write(f"- 기둥 자중 (P_self): {_pu_bd.get('P_self', 0):.1f} kN")
                        st.write(f"- **Pu_total = {_pu_bd.get('Pu_total', 0):.1f} kN**")

                    if _mu_bd:
                        st.markdown("**모멘트 분해 (Mu)**")
                        st.write(f"- X방향: Mux_add = {_mu_bd.get('Mux_add', 0):.2f} + M_neg_x = {_mu_bd.get('M_neg_x', 0):.2f}  →  **Mux = {_mu_bd.get('Mux_total', 0):.2f} kN·m**")
                        st.write(f"- Y방향: Muy_add = {_mu_bd.get('Muy_add', 0):.2f} + M_neg_y = {_mu_bd.get('M_neg_y', 0):.2f}  →  **Muy = {_mu_bd.get('Muy_total', 0):.2f} kN·m**")
                        st.latex(r"M_u = \sqrt{M_{ux}^2 + M_{uy}^2}")
                        st.write(f"**Mu_design (SRSS) = {_mu_bd.get('Mu_design', 0):.2f} kN·m**")

                    # 하중 조합 표
                    _combos = col_r.get('load_combos', [])
                    _gov = col_r.get('governing_combo', '')
                    if _combos:
                        st.markdown("**하중 조합 비교 (KDS 41 10 15)**")
                        _combo_rows = []
                        for _c in _combos:
                            _mark = " **◀ 지배**" if _c.get('name', '') == _gov else ""
                            _combo_rows.append(f"| {_c['name']}{_mark} | {_c['Pu']:.1f} | {_c.get('Mux', 0):.2f} | {_c.get('Muy', 0):.2f} |")
                        st.markdown("| 조합 | Pu (kN) | Mux (kN·m) | Muy (kN·m) |\n|------|------:|------:|------:|\n" + '\n'.join(_combo_rows))

    st.divider()

    # 기둥 주철근 + 띠철근
    st.markdown("---")
    st.markdown("#### 7-3. 기둥 배근 결과")
    _col_rebar_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _col_rebar_tabs = [st.container()]
    else:
        _col_rebar_tabs = st.tabs(_col_rebar_tab_labels)

    for _rtab, col_r in zip(_col_rebar_tabs, columns):
        with _rtab:
            col_col_rebar_metric, col_col_rebar_detail = st.columns([1, 3])
            with col_col_rebar_metric:
                st.write(f"**기둥 주철근: {col_r['rebar_design']['rebar_string_col']}**")
                st.write(f"제공 철근 면적: {col_r['rebar_design']['As_provided_col']:.2f} mm²")
            with col_col_rebar_detail:
                with st.expander("기둥 주철근 설계 상세"):
                    st.write("---")
                    st.markdown("#### 기둥 P-M 상관도 검토 (KDS 41 20)")
                    st.info(
                        "**🏛️ P-M 상관도 검토 로직 (3점 포락선, 단순화)**  \n"
                        "기둥 단면에 작용하는 **(Pu, Mu)** 가 P-M 포락선 **내부**에 있으면 안전합니다.  \n\n"
                        "**3점 계산:**  \n"
                        "· **점 A** (순수 압축): Pn,max = 0.80[0.85·fck·(Ag−Ast) + fy·Ast]  \n"
                        "· **점 B** (균형파괴): cb = 600d/(600+fy) → Pn,b / Mn,b 동시 계산  \n"
                        "· **점 C** (순수 휨): Pn=0이 되는 c₀를 이분법으로 산정 → Mn,o 계산  \n\n"
                        "세 점을 직선으로 연결한 포락선 내부이면 OK.  \n"
                        "※ 최소 편심 e_min = max(15, 0.03·h) mm 적용으로 보수적 설계  \n"
                        "※ 양방향 모멘트 Mux, Muy는 SRSS 조합 후 단축 P-M 검토"
                    )

                    st.markdown("**1) 설계 하중 및 편심 검토**")
                    mb_r = col_r['mu_breakdown']
                    _mux_t = mb_r.get('Mux_total', col_r['axial_moment']['Mu'])
                    _muy_t = mb_r.get('Muy_total', 0.0)
                    _mu_d  = mb_r.get('Mu_design', col_r['axial_moment']['Mu'])
                    _mu_c1, _mu_c2 = st.columns(2)
                    with _mu_c1:
                        st.write(f"- $M_{{ux,total}}$ (X방향): **{_mux_t:.2f} kN·m**")
                        st.write(f"- $M_{{uy,total}}$ (Y방향): **{_muy_t:.2f} kN·m**")
                    with _mu_c2:
                        st.write(f"- SRSS 설계 모멘트 ($M_u$): **{_mu_d:.2f} kN·m**")
                        st.write(f"- 설계 축하중 ($P_u$): **{col_r['rebar_design']['Pu']:.2f} kN**")
                    e_actual_val = col_r['rebar_design']['e_actual']
                    if e_actual_val is None:
                        st.write(f"- 실제 편심: 해당없음 (Pu≈0, 순수 휨 상태)")
                    else:
                        st.write(f"- 실제 편심 ($e_{{actual}}$): {e_actual_val:.2f} mm")
                    st.write(f"- 최소 편심 ($e_{{min}}$): {col_r['rebar_design']['e_min']:.2f} mm")

                    if e_actual_val is None:
                        st.info("ℹ️ Pu=0(순수 휨)이므로 최소편심 보정을 적용하지 않습니다.")
                    elif col_r['rebar_design']['is_min_ecc_applied']:
                        st.warning(f"⚠️ 실제 편심이 최소 편심보다 작아 최소 편심을 적용합니다. (최종 $M_u = {col_r['rebar_design']['Mu_design']:.2f}$ kN·m)")
                    else:
                        st.success(f"✅ 실제 편심이 최소 편심보다 커서 입력 모멘트를 그대로 적용합니다.")

                    st.markdown("**2) P-M 상관도 주요 검토점 ($\\phi=0.65$ 반영)**")
                    col_pts1, col_pts2 = st.columns(2)
                    with col_pts1:
                        st.write(f"- 점 A (순수압축): $\\phi P_{{n,max}} = {col_r['rebar_design']['phi_Pn_max']:.2f}$ kN")
                        st.write(f"- 점 B (균형파괴 $P$): $\\phi P_{{n,b}} = {col_r['rebar_design']['phi_Pn_b']:.2f}$ kN")
                    with col_pts2:
                        st.write(f"- 점 B (균형파괴 $M$): $\\phi M_{{n,b}} = {col_r['rebar_design']['phi_Mn_b']:.2f}$ kN·m")
                        st.write(f"- 점 C (순수휨): $\\phi M_{{n,o}} = {col_r['rebar_design']['phi_Mn_o']:.2f}$ kN·m")

                    st.markdown("**3) 최종 설계 결과 및 판정**")
                    st.write(f"- 적용 철근비 ($\\rho$): {col_r['rebar_design']['rho']*100:.2f}% (기준: 1% ~ 8%)")
                    st.write(f"- 배근 결과: {col_r['rebar_design']['rebar_string_col']} (제공 $A_s = {col_r['rebar_design']['As_provided_col']:.2f}$ mm²)")
                    if col_r['rebar_design'].get('pm_safe', True):
                        st.success("✅ 판정: OK (설계 하중이 P-M 상관도 포락선 내부에 위치함)")
                    else:
                        st.error("❌ 판정: NG (설계 하중이 P-M 상관도 포락선을 초과함 — 단면 또는 철근량 증가 필요)")

            # 기둥 띠철근
            st.markdown(f"##### {col_r.get('col_name','')} 띠철근 설계")
            col_col_tie_rebar_metric, col_col_tie_rebar_detail = st.columns([1, 3])
            with col_col_tie_rebar_metric:
                st.write(f"**기둥 띠철근: {col_r['tie_rebar_design']['tie_rebar_type']} @ {col_r['tie_rebar_design']['tie_rebar_spacing']:.0f}**")
            with col_col_tie_rebar_detail:
                with st.expander("기둥 띠철근 설계 상세"):
                    st.write("---")
                    st.markdown("#### 기둥 띠철근 설계 (KDS 41 20)")
                    st.write(f"띠철근 직경: {col_r['tie_rebar_design']['tie_rebar_type']} (d_t = {col_r['tie_rebar_design']['tie_rebar_diameter']:.2f} mm)")
                    st.markdown("**간격 결정 조건 (Min값 적용):**")
                    st.write(f"1) 16 x 주철근 지름: {16 * col_r['rebar_design']['rebar_diameter_col']:.1f} mm")
                    st.write(f"2) 48 x 띠철근 지름: {48 * col_r['tie_rebar_design']['tie_rebar_diameter']:.1f} mm")
                    st.write(f"3) 기둥 단면 최소 치수: {col_r['dimensions']['c_column']:.0f} mm")
                    st.write(f"최종 띠철근 간격: {col_r['tie_rebar_design']['tie_rebar_spacing']:.0f} mm (50mm 단위 내림)")


    # ── 기둥 단면도 & 측면도 (같은 줄에 배치) ──
    st.markdown("---")
    st.markdown("##### 기둥 단면도 & 측면도")
    _col_vis_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _col_vis_tabs = [st.container()]
    else:
        _col_vis_tabs = st.tabs(_col_vis_labels)
    for _vi, (_cvtab, col_r) in enumerate(zip(_col_vis_tabs, columns)):
        with _cvtab:
            _col_dim_v = col_r['dimensions']
            _col_ds_v  = col_r['tie_rebar_design']
            col_fig1 = plot_column_section(
                c_column=_col_dim_v['c_column'],
                n_col=_col_ds_v['n_col'],
                rebar_type_col=_col_ds_v['rebar_type_col'],
                rebar_dia=_col_ds_v['rebar_diameter_col'],
                tie_type=_col_ds_v['tie_rebar_type'],
                tie_dia=_col_ds_v['tie_rebar_diameter'],
                tie_spacing=_col_ds_v['tie_rebar_spacing'])
            st.pyplot(col_fig1); plt.close(col_fig1)
            with st.expander("Column Side View (Debugging)", expanded=False):
                col_fig2 = plot_column_side_view(
                    h_column=inputs['h_column'],
                    c_column=_col_dim_v['c_column'],
                    tie_spacing=_col_ds_v['tie_rebar_spacing'],
                    tie_dia=_col_ds_v['tie_rebar_diameter'],
                    rebar_dia=_col_ds_v['rebar_diameter_col'])
                st.pyplot(col_fig2); plt.close(col_fig2)

def _render_slab_design(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 7: 슬래브 설계"""
    # --------------------------------------------------------------------------
    slab = results.get('slab')
    if slab:
        _slab_type_label = common.get('slab_type', '1방향')
        if _slab_type_label == '2방향':
            st.info(
                f"**📐 {_slab_type_label} 슬래브 (변장비 α = {common.get('aspect_ratio', 0):.2f} < 2.0)**  \n"
                "양방향 하중 분배 적용. 슬래브 자체 구조 설계는 **단변 방향(1m 스트립 고정단 모델)**로 수행합니다.  \n\n"
                "· 경간: L_short (단변 방향)  \n"
                "· 보 하중 분배: 사다리꼴(장변보) + 삼각형(단변보)  \n"
                "· 배근: D10~D16, 간격 표기 (예: D10@200)")
        else:
            st.info(
                f"**📐 {_slab_type_label} 슬래브 설계 (KDS 41 20 20)**  \n"
                "슬래브를 **1m 폭 고정단 보**로 모델링하여 설계합니다.  \n\n"
                "· 경간: L_short (단변 방향)  \n"
                "· 부재력: M_neg = w_u·L²/12, M_pos = w_u·L²/24  \n"
                "· 배근: D10~D16, 간격 표기 (예: D10@200)  \n"
                "· 최소 철근비: ρ_min = max(수축온도 0.0018, 휨최소)  \n"
                "· 전단: φVc 검토 (통상 콘크리트만으로 충분)  \n"
                "· 처짐: Branson Ie, L/240 기준")

        slab_dp = slab['design_params']
        slab_mf = slab['member_forces']

        _sc1, _sc2, _sc3, _sc4 = st.columns(4)
        _sc1.metric("슬래브 자중", f"{slab_dp['w_slab_self']:.2f} kN/m²")
        _sc2.metric("비계수 DL", f"{slab_dp['w_DL_unfactored']:.2f} kN/m")
        _sc3.metric("비계수 LL", f"{slab_dp['w_LL_unfactored']:.2f} kN/m")
        _sc4.metric("계수하중 w_u", f"{slab_dp['w_u']:.2f} kN/m")

        _sm1, _sm2, _sm3 = st.columns(3)
        _sm1.metric("M_neg (지점부)", f"{slab_mf['M_neg']:.2f} kN·m/m")
        _sm2.metric("M_pos (중앙부)", f"{slab_mf['M_pos']:.2f} kN·m/m")
        _sm3.metric("V_max", f"{slab_mf['V_max']:.2f} kN/m")

        st.markdown("---")

        st.markdown("#### 슬래브 휨 설계")
        _sf1, _sf2, _sf3 = st.columns(3)
        _sf1.metric("지점부 상부근", slab['rebar_string_top'], delta=f"As={slab['As_provided_top']:.0f} mm²/m")
        _sf2.metric("중앙부 하부근", slab['rebar_string_bot'], delta=f"As={slab['As_provided_bot']:.0f} mm²/m")
        _sf3.metric("배력근 (수축·온도)", slab['rebar_string_dist'], delta=f"As={slab['As_provided_dist']:.0f} mm²/m")

        _slab_fck = slab_dp.get('fc_k', inputs.get('fc_k', 24))
        _slab_fy = slab_dp.get('fy', inputs.get('fy', 400))
        _slab_b = 1000  # 1m 스트립

        # 휨 설계 상세 expander
        _fs_top = slab.get('flexural_steps_top', {})
        _fs_bot = slab.get('flexural_steps_bot', {})
        if _fs_top:
            _render_slab_flexural_expander("지점부 상부근 휨 설계 상세 (7단계)", _fs_top, _slab_b, _slab_fck, _slab_fy)
        if _fs_bot:
            _render_slab_flexural_expander("중앙부 하부근 휨 설계 상세 (7단계)", _fs_bot, _slab_b, _slab_fck, _slab_fy)

        # 배근 상세 expander
        _rs_top = slab.get('rebar_steps_top', {})
        _rs_bot = slab.get('rebar_steps_bot', {})
        _rs_dist = slab.get('rebar_steps_dist', {})
        if _rs_top:
            _render_slab_rebar_expander("지점부 상부근 배근 상세", _rs_top)
        if _rs_bot:
            _render_slab_rebar_expander("중앙부 하부근 배근 상세", _rs_bot)
        if _rs_dist:
            _render_slab_rebar_expander("배력근 배근 상세", _rs_dist)

        for w in slab.get('warnings_top', []) + slab.get('rebar_warnings_top', []):
            st.warning(w)
        for w in slab.get('warnings_bot', []) + slab.get('rebar_warnings_bot', []):
            st.warning(w)

        st.markdown("#### 슬래브 전단 검토")
        ss = slab['shear_steps']
        _shear_icon = "✅ OK" if slab['shear_ok'] else "❌ NG"
        if 'V_at_d' in ss:
            st.write(f"**위험단면 전단력 (KDS 41 20 22)**: "
                     f"V_max(지점면) = {ss.get('V_max_face', 0):.1f} kN → "
                     f"V_u(d) = {ss.get('V_at_d', 0):.1f} kN  "
                     f"(d = {ss.get('d_critical_m', 0)*1000:.1f} mm)")
        st.write(f"**전단 판정: {_shear_icon}** — "
                 f"φVc = {ss.get('phi_Vc_kN', 0):.1f} kN  vs  Vu = {ss.get('Vu_kN', 0):.1f} kN")
        if not slab['shear_ok']:
            st.error("슬래브 전단강도 부족 — t_slab을 증가시키세요.")
        for w in slab.get('shear_warnings', []):
            st.warning(w)
        _render_slab_shear_expander(ss, _slab_fck)

        st.markdown("#### 슬래브 처짐 검토")
        s_defl = slab['deflection']
        if s_defl.get('min_thickness_exempt', False):
            st.success(f"✅ 최소두께 충족 (t_slab={slab_dp['t_slab']:.0f}mm ≥ L/28={s_defl.get('h_min_exempt', 0):.0f}mm) → 처짐 검토 면제 가능")
        _defl_ok = s_defl.get('ok', True)
        _defl_icon = "✅ OK" if _defl_ok else "❌ NG"
        _dc1, _dc2, _dc3 = st.columns(3)
        _dc1.metric("즉시처짐 (DL)", f"{s_defl.get('delta_DL_i', 0):.2f} mm")
        _dc2.metric("즉시처짐 (LL)", f"{s_defl.get('delta_LL_i', 0):.2f} mm",
                    delta=f"허용 L/360 = {s_defl.get('delta_allow_LL', 0):.2f} mm")
        _dc3.metric("장기+LL 총처짐", f"{s_defl.get('delta_check', 0):.2f} mm",
                    delta=f"허용 L/240 = {s_defl.get('delta_allow_total', 0):.2f} mm")
        st.write(f"**처짐 판정: {_defl_icon}**")
        if not _defl_ok:
            st.error("슬래브 처짐 초과 — t_slab을 증가시키세요.")
        _render_slab_deflection_expander(s_defl, slab_dp)

        st.markdown("#### 슬래브 단면도")
        _slab_fig = plot_slab_section(
            slab_dp['t_slab'], slab['rebar_string_top'], slab['rebar_string_bot'],
            rebar_string_dist=slab['rebar_string_dist'], cover=slab_dp.get('cover', 20.0),
            fck=inputs.get('fc_k', 24.0), fy=inputs.get('fy', 400.0))
        st.pyplot(_slab_fig)
        plt.close(_slab_fig)

def _render_ground_beam(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 8: 바닥보 설계"""
    # ── 바닥보 설계 ────────────────────────────────────────
    if inputs.get('show_ground_beam', True):
        ground_x = results.get('ground_beam_x')
        ground_y = results.get('ground_beam_y')
        if ground_x and ground_y:
            st.markdown("#### 6-5. 바닥보 설계")
            _dl_g  = inputs.get('DL_area_ground', inputs['DL_area'])
            _ll_g  = inputs.get('LL_area_ground', inputs['LL_area'])
            _loads_same = (_dl_g == inputs['DL_area'] and _ll_g == inputs['LL_area'])
            if _loads_same:
                st.caption(f"천장보와 동일 하중 적용 (DL={_dl_g:.1f}, LL={_ll_g:.1f} kN/m²) — 독립 단면으로 설계됨")
            else:
                st.caption(f"별도 하중 적용 (DL={_dl_g:.1f}, LL={_ll_g:.1f} kN/m²) — 독립 설계")

            _gx_h = ground_x['design_params']['h_beam']
            _gx_b = ground_x['design_params']['b_beam']
            _gy_h = ground_y['design_params']['h_beam']
            _gy_b = ground_y['design_params']['b_beam']

            _gb_m1, _gb_m2, _gb_m3, _gb_m4 = st.columns(4)
            _gb_m1.metric("X바닥보 춤 h", f"{_gx_h:.0f} mm",
                          delta=f"{_gx_h - beam_x['design_params']['h_beam']:+.0f} mm"
                          if _gx_h != beam_x['design_params']['h_beam'] else None)
            _gb_m2.metric("X바닥보 폭 b", f"{_gx_b:.0f} mm",
                          delta=f"{_gx_b - beam_x['design_params']['b_beam']:+.0f} mm"
                          if _gx_b != beam_x['design_params']['b_beam'] else None)
            _gb_m3.metric("Y바닥보 춤 h", f"{_gy_h:.0f} mm",
                          delta=f"{_gy_h - beam_y['design_params']['h_beam']:+.0f} mm"
                          if _gy_h != beam_y['design_params']['h_beam'] else None)
            _gb_m4.metric("Y바닥보 폭 b", f"{_gy_b:.0f} mm",
                          delta=f"{_gy_b - beam_y['design_params']['b_beam']:+.0f} mm"
                          if _gy_b != beam_y['design_params']['b_beam'] else None)

            with st.expander("바닥보 배근 상세"):
                _gb_dc1, _gb_dc2 = st.columns(2)
                with _gb_dc1:
                    st.markdown("**X방향 바닥보**")
                    st.write(f"- 상부근: **{ground_x['rebar_string_top']}** (As={ground_x['As_provided_top']:.0f} mm², {ground_x['layer_top']}단)")
                    st.write(f"- 하부근: **{ground_x['rebar_string_bot']}** (As={ground_x['As_provided_bot']:.0f} mm², {ground_x['layer_bot']}단)")
                    st.write(f"- 늑근: D10 @ {ground_x['s']:.0f} mm")
                with _gb_dc2:
                    st.markdown("**Y방향 바닥보**")
                    st.write(f"- 상부근: **{ground_y['rebar_string_top']}** (As={ground_y['As_provided_top']:.0f} mm², {ground_y['layer_top']}단)")
                    st.write(f"- 하부근: **{ground_y['rebar_string_bot']}** (As={ground_y['As_provided_bot']:.0f} mm², {ground_y['layer_bot']}단)")
                    st.write(f"- 늑근: D10 @ {ground_y['s']:.0f} mm")

                st.markdown("---")
                st.markdown("##### 지중보 X방향 단면도 (END-I / MID / END-J)")
                _fig_gb_x = plot_rebar_section(
                    ground_x['design_params']['b_beam'], ground_x['design_params']['h_beam'],
                    ground_x['rebar_string_top'], ground_x['rebar_steps_top'], ground_x['layer_top'],
                    ground_x['rebar_string_bot'], ground_x['rebar_steps_bot'], ground_x['layer_bot'],
                    'X', ground_x['s'], section_location='combined',
                    rebar_string_min=ground_x['rebar_string_min'],
                    rebar_steps_min=ground_x['rebar_steps_min'],
                    layer_min=ground_x['layer_min'])
                st.pyplot(_fig_gb_x); plt.close(_fig_gb_x)

                st.markdown("##### 지중보 Y방향 단면도 (END-I / MID / END-J)")
                _fig_gb_y = plot_rebar_section(
                    ground_y['design_params']['b_beam'], ground_y['design_params']['h_beam'],
                    ground_y['rebar_string_top'], ground_y['rebar_steps_top'], ground_y['layer_top'],
                    ground_y['rebar_string_bot'], ground_y['rebar_steps_bot'], ground_y['layer_bot'],
                    'Y', ground_y['s'], section_location='combined',
                    rebar_string_min=ground_y['rebar_string_min'],
                    rebar_steps_min=ground_y['rebar_steps_min'],
                    layer_min=ground_y['layer_min'])
                st.pyplot(_fig_gb_y); plt.close(_fig_gb_y)

                with st.expander("Ground Beam Side View (Debugging)", expanded=False):
                    _fig_gb_side_x = plot_beam_side_view(
                        inputs['L_x'], ground_x['design_params']['h_beam'],
                        ground_x['rebar_string_top'], ground_x['rebar_steps_top'], ground_x['layer_top'],
                        ground_x['rebar_string_bot'], ground_x['rebar_steps_bot'], ground_x['layer_bot'],
                        ground_x['s'], 'X',
                        rebar_string_min=ground_x['rebar_string_min'],
                        rebar_steps_min=ground_x['rebar_steps_min'],
                        layer_min=ground_x['layer_min'],
                        dev_top=ground_x.get('dev_top'), dev_bot=ground_x.get('dev_bot'),
                        stirrup_zones=ground_x.get('stirrup_zones'))
                    st.pyplot(_fig_gb_side_x); plt.close(_fig_gb_side_x)
                    _fig_gb_side_y = plot_beam_side_view(
                        inputs['L_y'], ground_y['design_params']['h_beam'],
                        ground_y['rebar_string_top'], ground_y['rebar_steps_top'], ground_y['layer_top'],
                        ground_y['rebar_string_bot'], ground_y['rebar_steps_bot'], ground_y['layer_bot'],
                        ground_y['s'], 'Y',
                        rebar_string_min=ground_y['rebar_string_min'],
                        rebar_steps_min=ground_y['rebar_steps_min'],
                        layer_min=ground_y['layer_min'],
                        dev_top=ground_y.get('dev_top'), dev_bot=ground_y.get('dev_bot'),
                        stirrup_zones=ground_y.get('stirrup_zones'))
                    st.pyplot(_fig_gb_side_y); plt.close(_fig_gb_side_y)

            st.divider()


def _render_joint_seismic(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 9: 접합부/내진 설계"""
    # ── 접합부 전단 검토 ────────────────────────────────────────────
    st.markdown("---")
    st.subheader("8. 접합부/내진 설계")
    st.markdown("#### 8-1. 보-기둥 접합부 전단 검토 (KDS 41 17)")
    _jt_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _jt_tabs = [st.container()]
    else:
        _jt_tabs = st.tabs(_jt_tab_labels)
    for _jtab, col_r in zip(_jt_tabs, columns):
        with _jtab:
            _jx = col_r.get('joint_shear_x', {})
            _jy = col_r.get('joint_shear_y', {})
            if _jx and _jy:
                _jx_icon = "✅ OK" if _jx['ok'] else "❌ NG"
                _jy_icon = "✅ OK" if _jy['ok'] else "❌ NG"
                _jc1, _jc2 = st.columns(2)
                with _jc1:
                    st.markdown(f"**X방향 접합부: {_jx_icon}**")
                    st.write(f"Vj = {abs(_jx['Vj']):.1f} kN  vs  φVn = {_jx['phi_Vn']:.1f} kN  "
                             f"(비율: {_jx['ratio']:.2f})")
                with _jc2:
                    st.markdown(f"**Y방향 접합부: {_jy_icon}**")
                    st.write(f"Vj = {abs(_jy['Vj']):.1f} kN  vs  φVn = {_jy['phi_Vn']:.1f} kN  "
                             f"(비율: {_jy['ratio']:.2f})")
                for w in _jx.get('warnings', []) + _jy.get('warnings', []):
                    st.warning(w)
                with st.expander("접합부 전단 계산 상세"):
                    _ft = col_r.get('frame_type', 'OMF')
                    st.write(f"골조 유형: **{_ft}** (α_o = {1.25 if _ft=='IMF' else 1.0})")
                    for _dir, _j in [("X", _jx), ("Y", _jy)]:
                        _js = _j['steps']
                        st.markdown(f"**{_dir}방향**")
                        st.write(f"- T = As×α_o×fy = {_js['T_kN']:.1f} kN")
                        st.write(f"- V_col = 2·M_neg/h_col = {_js['V_col_kN']:.1f} kN")
                        st.write(f"- Vj = T − V_col = {_js['Vj_kN']:.1f} kN")
                        st.write(f"- Aj = {_js['Aj']:.0f} mm² (b_eff={_js['b_eff']:.0f})")
                        st.write(f"- γ = {_js['gamma']:.2f}")
                        st.write(f"- φVn = {_js['phi_Vn_kN']:.1f} kN")

    # ── IMF 내진 상세 검토 ──────────────────────────────────────────
    if inputs.get('frame_type') == 'IMF':
        st.markdown("---")
        st.markdown("#### 8-2. IMF 내진 상세 검토 (KDS 41 17)")

        st.markdown("#### 보 소성힌지 구간")
        for key, label in [('beam_x', 'X방향'), ('beam_y', 'Y방향')]:
            _imf_b = results[key].get('imf')
            if _imf_b:
                _s = _imf_b['steps']
                _icon_h = "✅" if _imf_b['s_hinge_ok'] else "❌"
                _icon_r = "✅" if _imf_b['bot_ratio_ok'] else "❌"
                st.write(f"**{label} 보**: l_ph = {_imf_b['l_ph']:.0f} mm (2h),  "
                         f"s_max = {_imf_b['s_max_hinge']:.0f} mm,  "
                         f"현재 s = {_s['s_stirrup']:.0f} mm  {_icon_h}  |  "
                         f"하부/상부근 비율 = {_s['bot_ratio']:.2f}  {_icon_r}")
                for w in _imf_b.get('warnings', []):
                    st.warning(w)
                with st.expander(f"{label} 보 소성힌지 계산 상세 (KDS 41 17 4.4)"):
                    st.write("**Step 1.** 소성힌지 구간 길이")
                    st.latex(r"l_{ph} = 2h")
                    st.write(f"$l_{{ph}}$ = 2 × {_s.get('h_beam', 0):.0f} = {_imf_b['l_ph']:.0f} mm")
                    st.write("**Step 2.** 힌지구간 늑근 최대간격")
                    st.latex(r"s_{max} = \min(d/4,\ 8 d_b,\ 24 d_{bt},\ 300)")
                    st.write(f"$s_{{max}}$ = {_imf_b['s_max_hinge']:.0f} mm")
                    st.write(f"현재 늑근 간격 = {_s['s_stirrup']:.0f} mm  →  "
                             f"{'✅ OK' if _imf_b['s_hinge_ok'] else '❌ NG'}")
                    st.write("**Step 3.** 하부근/상부근 비율 ≥ 0.5")
                    st.write(f"비율 = {_s['bot_ratio']:.3f}  →  "
                             f"{'✅ OK' if _imf_b['bot_ratio_ok'] else '❌ NG'}")

        st.markdown("#### 기둥 구속구간 / 강기둥-약보")
        _imf_col_tabs = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
        if len(columns) == 1:
            _imf_ctabs = [st.container()]
        else:
            _imf_ctabs = st.tabs(_imf_col_tabs)
        for _ictab, col_r in zip(_imf_ctabs, columns):
            with _ictab:
                _imf_c = col_r.get('imf')
                _scwb = col_r.get('scwb')
                if _imf_c:
                    _cs = _imf_c['steps']
                    _icon_c = "✅" if _imf_c['s_confine_ok'] else "❌"
                    st.write(f"**구속구간**: l_o = {_imf_c['l_o']:.0f} mm,  "
                             f"s_max = {_imf_c['s_max_confine']:.0f} mm,  "
                             f"현재 s = {_cs['s_tie_normal']:.0f} mm  {_icon_c}")
                    for w in _imf_c.get('warnings', []):
                        st.warning(w)
                    with st.expander("기둥 구속구간 계산 상세 (KDS 41 17 4.5)"):
                        st.write("**Step 1.** 구속구간 길이")
                        st.latex(r"l_o = \max(c_{col},\ h_{col}/6,\ 450)")
                        st.write(f"$l_o$ = {_imf_c['l_o']:.0f} mm")
                        st.write("**Step 2.** 구속구간 띠철근 최대간격")
                        st.latex(r"s_{max} = \min(c_{col}/4,\ 6 d_b,\ s_x)")
                        st.write(f"$s_{{max}}$ = {_imf_c['s_max_confine']:.0f} mm")
                        st.write(f"현재 띠철근 간격 = {_cs['s_tie_normal']:.0f} mm  →  "
                                 f"{'✅ OK' if _imf_c['s_confine_ok'] else '❌ NG'}")
                if _scwb:
                    _ss = _scwb['steps']
                    _icon_sc = "✅" if _scwb['ok'] else "❌"
                    st.write(f"**강기둥-약보**: ΣMn_col = {_scwb['Mn_col_sum']:.1f} kN·m,  "
                             f"1.2×ΣMn_beam = {1.2*_scwb['Mn_beam_sum']:.1f} kN·m,  "
                             f"비율 = {_scwb['ratio']:.2f}  {_icon_sc}")
                    if not _scwb['ok']:
                        st.error("강기둥-약보 조건 불만족 — 기둥 단면 또는 배근 증가 필요")
                    with st.expander("강기둥-약보 검토 상세 (KDS 41 17 4.5.2)"):
                        st.latex(r"\sum M_{n,col} \geq 1.2 \sum M_{n,beam}")
                        st.write(f"$\\sum M_{{n,col}}$ = {_scwb['Mn_col_sum']:.1f} kN·m")
                        st.write(f"$\\sum M_{{n,beam}}$ = {_scwb['Mn_beam_sum']:.1f} kN·m")
                        st.write(f"$1.2 \\times \\sum M_{{n,beam}}$ = {1.2*_scwb['Mn_beam_sum']:.1f} kN·m")
                        st.write(f"비율 = {_scwb['ratio']:.2f}  →  "
                                 f"{'✅ OK' if _scwb['ok'] else '❌ NG'}")


def _render_crack_development(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 10: 균열/정착"""
    # --------------------------------------------------------------------------
    # 6-1. 균열 제어 검토
    # --------------------------------------------------------------------------
    st.subheader("9. 균열/정착")
    st.markdown("#### 9-1. 균열 제어 검토 (KDS 14 20 50)")
    st.info(
        "**균열 제어 — 철근 최대 간격 제한 (간접균열제어)**  \n"
        "① $s \\leq 380 \\cdot (k_{cr} / f_s) - 2.5 \\cdot c_c$  \n"
        "② $s \\leq 300 \\cdot (k_{cr} / f_s)$  \n"
        "두 식 중 작은 값 이하로 배근. $k_{cr}$=280(건조), $f_s \\approx \\frac{2}{3} f_y$"
    )

    def _render_crack_row(label, crack_result):
        if not crack_result or not crack_result.get('steps'):
            return
        _cs = crack_result['steps']
        ok_str = "**OK**" if crack_result['ok'] else "**NG**"
        return f"| {label} | {_cs.get('s_actual', 0):.0f} | {_cs.get('s_limit_1', 0):.0f} | {_cs.get('s_limit_2', 0):.0f} | {crack_result['s_max']:.0f} | {ok_str} |"

    _crack_header = "| 부재 | 실제 간격 (mm) | 제한①  (mm) | 제한② (mm) | s_max (mm) | 판정 |\n|------|------:|------:|------:|------:|:----:|"
    _crack_rows = []
    for _bkey, _blabel in [('beam_x', 'X보'), ('beam_y', 'Y보')]:
        _br = results[_bkey]
        _r_top = _render_crack_row(f'{_blabel} 상부근', _br.get('crack_top'))
        _r_bot = _render_crack_row(f'{_blabel} 하부근', _br.get('crack_bot'))
        if _r_top: _crack_rows.append(_r_top)
        if _r_bot: _crack_rows.append(_r_bot)

    _slab_r = results.get('slab')
    if _slab_r:
        _r_st = _render_crack_row('슬래브 상부근', _slab_r.get('crack_top'))
        _r_sb = _render_crack_row('슬래브 하부근', _slab_r.get('crack_bot'))
        if _r_st: _crack_rows.append(_r_st)
        if _r_sb: _crack_rows.append(_r_sb)

    if _crack_rows:
        st.markdown(_crack_header + '\n' + '\n'.join(_crack_rows))
    else:
        st.caption("균열 제어 검토 결과 없음 — 엔진에서 균열 데이터가 산출되지 않았습니다.")

    # 균열 제어 계산 상세 expander
    _all_crack = []
    for _bkey, _blabel in [('beam_x', 'X보'), ('beam_y', 'Y보')]:
        _br = results[_bkey]
        for _pos, _pk in [('상부근', 'crack_top'), ('하부근', 'crack_bot')]:
            _cr = _br.get(_pk)
            if _cr and _cr.get('steps'):
                _all_crack.append((f'{_blabel} {_pos}', _cr))
    _slab_r = results.get('slab')
    if _slab_r:
        for _pos, _pk in [('상부근', 'crack_top'), ('하부근', 'crack_bot')]:
            _cr = _slab_r.get(_pk)
            if _cr and _cr.get('steps'):
                _all_crack.append((f'슬래브 {_pos}', _cr))
    if _all_crack:
        with st.expander("균열 제어 계산 상세"):
            for _label, _cr in _all_crack:
                _cs = _cr['steps']
                st.markdown(f"**{_label}**")
                st.write(f"- $c_c$ (인장근 외면~표면) = {_cs.get('cc', 0):.1f} mm")
                st.write(f"- $f_s = (2/3) \\times f_y$ = {_cs.get('fs', 0):.1f} MPa")
                st.write(f"- $k_{{cr}}$ = {_cs.get('k_cr', 280):.0f}")
                st.write(f"- 제한① = 380·(k/fs) - 2.5·cc = {_cs.get('s_limit_1', 0):.0f} mm")
                st.write(f"- 제한② = 300·(k/fs) = {_cs.get('s_limit_2', 0):.0f} mm")
                st.write(f"- $s_{{max}}$ = min(①, ②) = {_cr['s_max']:.0f} mm")
                st.write(f"- 실제 간격 = {_cs.get('s_actual', 0):.0f} mm  →  "
                         f"{'✅ OK' if _cr['ok'] else '❌ NG'}")
                st.markdown("---")

    st.divider()

    # --------------------------------------------------------------------------
    # 6-2. 정착길이 / 이음길이
    # --------------------------------------------------------------------------
    st.markdown("#### 9-2. 정착길이 / 이음길이 (KDS 14 20 52)")
    st.info(
        "**정착 및 이음 설계 (KDS 14 20 52)**  \n"
        "$\\ell_d = \\ell_{db} \\cdot \\frac{\\alpha \\cdot \\beta \\cdot \\gamma}{(c_b+K_{tr})/d_b}$  \n"
        "$\\ell_{db} = 0.9 \\cdot d_b \\cdot f_y / \\sqrt{f_{ck}}$  \n"
        "$\\alpha$=1.3(상부근)/1.0(하부근),  $\\gamma$=0.8(≤D19)/1.0(≥D22)  \n"
        "겹이음(B급) = 1.3·$\\ell_d$,  표준갈고리 $\\ell_{dh}$ = 0.24·$d_b$·$f_y$/$\\sqrt{f_{ck}}$"
    )

    _dev_header = "| 부재 | 철근 | ℓd (mm) | 겹이음 B급 (mm) | 갈고리 ℓdh (mm) | 압축 ℓdc (mm) |\n|------|------|------:|------:|------:|------:|"
    _dev_rows = []

    def _dev_row(label, rebar_str, dev_result):
        if not dev_result:
            return None
        return f"| {label} | {rebar_str} | {dev_result['ld']:.0f} | {dev_result['ls_B']:.0f} | {dev_result['ldh']:.0f} | {dev_result['ldc']:.0f} |"

    for _bkey, _blabel in [('beam_x', 'X보'), ('beam_y', 'Y보')]:
        _br = results[_bkey]
        _r = _dev_row(f'{_blabel} 상부근', _br['rebar_string_top'], _br.get('dev_top'))
        if _r: _dev_rows.append(_r)
        _r = _dev_row(f'{_blabel} 하부근', _br['rebar_string_bot'], _br.get('dev_bot'))
        if _r: _dev_rows.append(_r)

    _slab_r = results.get('slab')
    if _slab_r:
        _r = _dev_row('슬래브 상부근', _slab_r.get('rebar_string_top', ''), _slab_r.get('dev_top'))
        if _r: _dev_rows.append(_r)
        _r = _dev_row('슬래브 하부근', _slab_r.get('rebar_string_bot', ''), _slab_r.get('dev_bot'))
        if _r: _dev_rows.append(_r)

    if _dev_rows:
        st.markdown(_dev_header + '\n' + '\n'.join(_dev_rows))
    else:
        st.caption("정착길이 검토 결과 없음 — 엔진에서 정착 데이터가 산출되지 않았습니다.")

    # 정착길이 계산 상세 expander
    _all_dev = []
    for _bkey, _blabel in [('beam_x', 'X보'), ('beam_y', 'Y보')]:
        _br = results[_bkey]
        for _pos, _pk in [('상부근', 'dev_top'), ('하부근', 'dev_bot')]:
            _dr = _br.get(_pk)
            if _dr and _dr.get('steps'):
                _all_dev.append((f'{_blabel} {_pos}', _dr))
    _slab_r = results.get('slab')
    if _slab_r:
        for _pos, _pk in [('상부근', 'dev_top'), ('하부근', 'dev_bot')]:
            _dr = _slab_r.get(_pk)
            if _dr and _dr.get('steps'):
                _all_dev.append((f'슬래브 {_pos}', _dr))
    if _all_dev:
        with st.expander("정착길이 계산 상세 (KDS 41 20 52)"):
            for _label, _dr in _all_dev:
                _ds = _dr['steps']
                st.markdown(f"**{_label}** ({_dr.get('rebar_str', '')})")
                st.write(f"- 기본정착길이 $\\ell_{{db}}$ = 0.9·d_b·fy/√fck = {_ds.get('ldb', 0):.0f} mm")
                st.write(f"- α = {_ds.get('alpha', 1.0):.1f} (상부근 1.3 / 하부근 1.0)")
                st.write(f"- β = {_ds.get('beta', 1.0):.1f},  γ = {_ds.get('gamma', 1.0):.1f}")
                st.write(f"- cb = {_ds.get('cb', 0):.1f} mm,  Ktr = {_ds.get('Ktr', 0):.1f}")
                _cb_ktr = _ds.get('cb_ktr_ratio', _ds.get('cb_ktr', 0))
                st.write(f"- (cb+Ktr)/db = {_cb_ktr:.2f}  (상한 2.5)")
                st.write(f"- $\\ell_d$ = {_dr['ld']:.0f} mm")
                st.write(f"- 겹이음 B급 = 1.3·ℓd = {_dr['ls_B']:.0f} mm")
                st.write(f"- 갈고리 $\\ell_{{dh}}$ = {_dr['ldh']:.0f} mm,  압축 $\\ell_{{dc}}$ = {_dr['ldc']:.0f} mm")
                st.markdown("---")

    st.divider()

def _render_visualization(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 11: 3D 배근도 + P-M 다이어그램"""

    st.subheader("10. 3D 배근도 + P-M 다이어그램")
    st.markdown("#### 10-1. 기둥 P-M 상관도 (KDS 41 20 20)")
    _pm_tab_labels = [col_r.get('col_name', f'기둥 {i+1}') for i, col_r in enumerate(columns)]
    if len(columns) == 1:
        _pm_tabs = [st.container()]
    else:
        _pm_tabs = st.tabs(_pm_tab_labels)
    for _pm_tab_idx, (_pm_tab, col_r) in enumerate(zip(_pm_tabs, columns)):
        with _pm_tab:
            _col_pm1, _col_pm2 = st.columns([2, 1])
            with _col_pm1:
                _fig_pm = plot_pm_diagram(
                    rebar_design=col_r['rebar_design'],
                    axial_moment=col_r['axial_moment'])
                st.plotly_chart(_fig_pm, width='stretch', key=f"chart_pm_{_pm_tab_idx}")
            with _col_pm2:
                _rd = col_r['rebar_design']
                _am = col_r['axial_moment']
                _mb = col_r['mu_breakdown']
                st.markdown("**포락선 주요 점**")
                st.write(f"- **A (순수압축)**: φPn = {_rd['phi_Pn_max']:.1f} kN")
                st.write(f"- **B (균형파괴)**: φPn = {_rd['phi_Pn_b']:.1f} kN, φMn = {_rd['phi_Mn_b']:.1f} kN·m")
                st.write(f"- **C (순수휨)**: φMn = {_rd['phi_Mn_o']:.1f} kN·m")
                st.markdown("---")
                st.write(f"- **설계 축력 Pu**: {_am['Pu']:.1f} kN")
                _mu_d = _mb.get('Mu_design', _am['Mu'])
                st.write(f"- **Mux** : {_mb.get('Mux_total', _am['Mu']):.2f} kN·m")
                st.write(f"- **Muy** : {_mb.get('Muy_total', 0.0):.2f} kN·m")
                st.write(f"- **SRSS Mu**: {_mu_d:.2f} kN·m")
                if _rd.get('is_min_ecc_applied'):
                    st.caption(f"※ 최소편심 적용: e_min={15 + 0.03*col_r['dimensions']['c_column']:.1f} mm → Mu 보정됨")
                st.success(f"✅ P-M 검토 OK ({_rd['rebar_string_col']})")

                _bresler = _rd.get('bresler')
                if _bresler is not None:
                    st.markdown("---")
                    st.markdown("**Bresler 이축 휨 검토**")
                    _br_icon = "✅ OK" if _bresler['safe'] else "❌ NG"
                    st.write(f"- Pnx = {_bresler['Pnx']:.1f} kN  (X단축)")
                    st.write(f"- Pny = {_bresler['Pny']:.1f} kN  (Y단축)")
                    st.write(f"- Pno = {_bresler['Pno']:.1f} kN  (순수압축)")
                    st.write(f"- **Pn(Bresler) = {_bresler['Pn_bresler']:.1f} kN**")
                    st.write(f"- φPn = {_bresler['phi_Pn']:.1f} kN  vs  Pu = {_am['Pu']:.1f} kN")
                    st.write(f"- **비율 = {_bresler['ratio']:.3f}  →  {_br_icon}**")


    st.markdown("---")
    st.markdown("#### 10-2. 3D 통합 프레임 배근도")
    st.info("💡 전체 구조물 프레임 상에서 보와 기둥의 철근 배근 상태를 직관적으로 확인합니다. 상부보 + 바닥보 + 기둥이 모두 표시됩니다.")

    rebar_render_btn = st.button("🏗️ 3D 통합 배근도 렌더링 실행", use_container_width=True)

    if rebar_render_btn:
        with st.spinner("3D 통합 배근도를 렌더링 중입니다... (잠시만 기다려주세요)"):
            fig_3d_rebar = plot_3d_frame_rebar(results, inputs)
            st.plotly_chart(fig_3d_rebar, width='stretch', key="chart_3d_rebar")


def _render_report_download(results, inputs):
    """구조계산서 보고서 — 새 창에서 열고 바로 PDF 인쇄 다이얼로그."""
    import base64
    import streamlit.components.v1 as components

    st.divider()
    st.subheader("📄 구조계산서 보고서 출력")

    try:
        from report_generator import generate_html_report
        _html = generate_html_report(results, inputs)
    except Exception as _e:
        st.error(f"보고서 생성 오류: {_e}")
        return

    # 인쇄용 HTML: 보고서 끝에 자동 print() 스크립트 삽입
    _html_print = _html.replace(
        '</body>',
        '<script>window.onload=function(){setTimeout(function(){window.print();},300);}</script>\n</body>'
    )
    _b64 = base64.b64encode(_html_print.encode('utf-8')).decode()

    col_desc, col_btn = st.columns([3, 1])
    with col_desc:
        st.caption(
            "버튼을 누르면 새 창에서 구조계산서가 열리고 PDF 저장 다이얼로그가 자동으로 표시됩니다."
        )
    with col_btn:
        # Blob URL → 새 탭에서 열기 (parent window에서 실행)
        components.html(f"""
        <button id="printBtn"
                style="background:#FF4B4B; color:white; border:none; border-radius:8px;
                       padding:10px 20px; font-size:14px; cursor:pointer; width:100%;">
          🖨️ 보고서 출력 (PDF)
        </button>
        <script>
        document.getElementById('printBtn').addEventListener('click', function() {{
            var bin = atob("{_b64}");
            var bytes = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            var blob = new Blob([bytes], {{type: 'text/html;charset=utf-8'}});
            var url = URL.createObjectURL(blob);
            window.parent.open(url, '_blank');
        }});
        </script>
        """, height=50)


def _render_todo(results, inputs, common, beam_x, beam_y, columns, column):
    """섹션 12: 미구현 항목"""
    # 9. 미구현 항목 및 개선 예정 사항
    # --------------------------------------------------------------------------
    st.divider()
    st.subheader("📋 11. 미구현 항목 및 개선 예정 사항")
    st.info("💡 아래 목록은 `계획 및 수정사항.md` 파일에서 자동으로 읽어옵니다.")

    _plan_path = os.path.join(BASE_PATH, '계획 및 수정사항.md')
    if os.path.exists(_plan_path):
        with open(_plan_path, 'r', encoding='utf-8') as _f:
            _plan_content = _f.read()
        _match = re.search(
            r'(## 🔧 5\. 수정해야 하는 것들.*?)(?=\n---\s*\n|\Z)',
            _plan_content, re.DOTALL)
        if _match:
            st.markdown(_match.group(1))
        else:
            st.warning("'계획 및 수정사항.md'에서 '수정사항' 섹션을 찾을 수 없습니다.")
    else:
        st.warning(f"'계획 및 수정사항.md' 파일을 찾을 수 없습니다: `{_plan_path}`")


# ═══════════════════════════════════════════════════════════════════════════
# 검토 모드 결과 렌더링
# ═══════════════════════════════════════════════════════════════════════════

def _render_review_slab_detail(sl):
    """BeST.RC 1방향 슬래브 검토 결과 상세 — BeST 구조계산서 양식."""
    st.markdown(
        '<style>'
        '.best-tbl table, .best-tbl th, .best-tbl td, .best-tbl tr '
        '{border:none !important; border-width:0 !important;}'
        '</style>',
        unsafe_allow_html=True)

    _n = 'border:none !important; padding:3px 8px; font-size:13px;'
    _ok_ng = lambda ok: '<span style="color:blue;">O.K.</span>' if ok else '<span style="color:red; font-weight:bold;">N.G.</span>'

    _name = sl.get('name', '')
    _clean_name = _name.split('[')[0].strip() if '[' in _name else _name
    _fck = sl['fc_k']
    _fy = sl['fy']
    _Lx = sl['Lx']
    _Ly = sl['Ly']
    _H = sl['H']
    _cover = sl['cover']
    _beta1 = sl['beta1']
    _d = sl['d']
    _overall_icon = '✅ O.K.' if sl['ok_overall'] else '❌ N.G.'

    # 헤더
    st.markdown(
        f'<div style="border-bottom:2px solid #333; padding-bottom:4px; margin-bottom:12px;">'
        f'<span style="font-size:13px; color:#888;">BeST.RC</span>'
        f'&nbsp;&nbsp;&nbsp;<b style="font-size:16px;">MEMBER : {_clean_name}</b>'
        f'&nbsp;&nbsp;&nbsp;<span style="font-size:14px;">{_overall_icon}</span></div>',
        unsafe_allow_html=True)

    # ── 1. Design Conditions ──
    with st.container(border=True):
        st.markdown(f"""<div class="best-tbl">
<table style="width:100%; border-collapse:collapse;">
<tr><td style="{_n}"><b>Design Conditions</b></td><td style="{_n}"></td></tr>
<tr><td style="{_n}">Material Data</td><td style="{_n}">f_ck = {int(_fck)} N/mm² (β₁ = {_beta1:.3f})</td></tr>
<tr><td style="{_n}"></td><td style="{_n}">fy = {int(_fy)} MPa</td></tr>
<tr><td style="{_n}">Slab Dim</td><td style="{_n}">{int(_Lx)} × {int(_Ly)} × {int(_H)} (mm)&emsp;cc = {_cover:.0f} mm</td></tr>
<tr><td style="{_n}">Edge Beams</td><td style="{_n}">UP: {sl['edge_UP']}&emsp;DN: {sl['edge_DN']}&emsp;LT: {sl['edge_LT']}&emsp;RT: {sl['edge_RT']}</td></tr>
<tr><td style="{_n}">Boundary</td><td style="{_n}">{sl['boundary']}</td></tr>
<tr><td style="{_n}">Effective d</td><td style="{_n}">{_d:.1f} mm (H - cover - D10/2)</td></tr>
</table></div>""", unsafe_allow_html=True)

    # ── 2. Applied Loads ──
    with st.container(border=True):
        _Wd = sl['Wd']; _Wl = sl['Wl']; _Wu = sl['Wu']
        st.markdown(f"""<div class="best-tbl">
<table style="width:100%; border-collapse:collapse;">
<tr><td style="{_n}"><b>Applied Loads</b></td><td style="{_n}"></td></tr>
<tr><td style="{_n}">Dead Load (Wd)</td><td style="{_n}">{_Wd:.2f} kN/m²</td></tr>
<tr><td style="{_n}">Live Load (Wl)</td><td style="{_n}">{_Wl:.2f} kN/m²</td></tr>
<tr><td style="{_n}">Factored Load (Wu)</td><td style="{_n}">1.2×{_Wd:.2f} + 1.6×{_Wl:.2f} = <b>{_Wu:.2f} kN/m²</b></td></tr>
</table></div>""", unsafe_allow_html=True)

    # ── 3. Check Minimum Slab Thickness ──
    with st.container(border=True):
        _beta_r = sl['beta']
        _h_min = sl['h_min']
        st.markdown(f"""<div class="best-tbl">
<table style="width:100%; border-collapse:collapse;">
<tr><td style="{_n}"><b>Check Minimum Slab Thickness</b> (KDS 14 20 22)</td><td style="{_n}"></td></tr>
<tr><td style="{_n}">β = Ly/Lx</td><td style="{_n}">{int(_Ly)}/{int(_Lx)} = {_beta_r:.4f} {'→ 1방향 슬래브' if _beta_r >= 2.0 else ''}</td></tr>
<tr><td style="{_n}">Ln (Short)</td><td style="{_n}">{sl['Ln_x']:.1f} mm</td></tr>
<tr><td style="{_n}">h_req</td><td style="{_n}">{_h_min:.1f} mm</td></tr>
<tr><td style="{_n}">H = {int(_H)} mm</td><td style="{_n}">{_ok_ng(sl['thk_ok'])}</td></tr>
</table></div>""", unsafe_allow_html=True)

    # ── 4. Flexure Reinforcement Table ──
    with st.container(border=True):
        st.markdown(f'<div class="best-tbl"><b>Flexure Reinforcement</b> (KDS 14 20 22 — 모멘트 계수법)</div>', unsafe_allow_html=True)

        # 테이블 헤더
        _th = 'border:1px solid #ccc !important; padding:4px 6px; font-size:12px; text-align:center; background:#f0f0f0;'
        _td = 'border:1px solid #ccc !important; padding:4px 6px; font-size:12px; text-align:center;'
        _td_ok = lambda ok: f'{_td} color:blue;' if ok else f'{_td} color:red; font-weight:bold;'

        tbl = f"""<table style="width:100%; border-collapse:collapse; margin-top:4px;">
<tr>
<th style="{_th}">방향</th><th style="{_th}">위치</th>
<th style="{_th}">Mu(BeST)</th><th style="{_th}">Mu(독립)</th><th style="{_th}">차이%</th>
<th style="{_th}">Ast,req</th><th style="{_th}">배근</th><th style="{_th}">As,prov</th>
<th style="{_th}">φMn</th><th style="{_th}">판정</th>
</tr>"""

        for pos_key in ['short_cont', 'short_pos', 'long_cont', 'long_pos']:
            fr = sl['flexure'][pos_key]
            _mu_b = fr['Mu_best']
            _mu_i = fr['Mu_independent']
            _diff = fr['Mu_diff_pct']
            _ast_req = fr['Ast_req']
            _combo = fr['combo']
            _sp = int(fr['spacing'])
            _as_prov = fr['As_provided']
            _phi_mn = fr['phi_Mn']
            _ok = fr['ok']
            _ok_str = 'O.K.' if _ok else 'N.G.'
            _ok_color = 'color:blue;' if _ok else 'color:red; font-weight:bold;'

            tbl += f"""<tr>
<td style="{_td}">{fr['direction']}</td><td style="{_td}">{fr['location']}</td>
<td style="{_td}">{_mu_b:.2f}</td><td style="{_td}">{_mu_i:.2f}</td>
<td style="{_td}">{_diff:+.1f}%</td>
<td style="{_td}">{_ast_req:.0f}</td>
<td style="{_td}">{_combo}@{_sp}</td>
<td style="{_td}">{_as_prov:.0f}</td>
<td style="{_td}">{_phi_mn:.2f}</td>
<td style="{_td} {_ok_color}">{_ok_str}</td>
</tr>"""

        # Min Bar 행
        _rho_min = sl['rho_min']
        _Ast_min = sl['Ast_min']
        tbl += f"""<tr>
<td colspan="5" style="{_td}"><b>Min Bar</b>: ρ_min = {_rho_min:.4f}, Ast_min = {_Ast_min:.0f} mm²/m</td>
<td colspan="5" style="{_td}">Ast_min = ρ_min × 1000 × H = {_rho_min:.4f} × 1000 × {int(sl['H'])} = {_Ast_min:.0f}</td>
</tr>"""
        tbl += "</table>"
        st.markdown(tbl, unsafe_allow_html=True)

    # ── 5. Check Shear ──
    with st.container(border=True):
        sh = sl['shear']
        st.markdown(f"""<div class="best-tbl">
<table style="width:100%; border-collapse:collapse;">
<tr><td style="{_n}"><b>Check Shear</b> (KDS 14 20 22)</td><td style="{_n}"></td></tr>
<tr><td style="{_n}">Vu,x = Wu×Ln,x/2</td><td style="{_n}">{sl['Wu']:.2f} × {sl['Ln_x']/1000:.3f} / 2 = <b>{sh['Vu_x']:.1f} kN/m</b></td></tr>
<tr><td style="{_n}">φVc,x = φ(1/6)√fck·b·d</td><td style="{_n}">0.75 × (1/6)√{int(_fck)} × 1000 × {_d:.1f} / 1000 = <b>{sh['phi_Vc_x']:.1f} kN/m</b>&emsp;{_ok_ng(sh['ok_x'])}</td></tr>
<tr><td style="{_n}">Vu,y = Wu×Ln,y/2</td><td style="{_n}">{sl['Wu']:.2f} × {sl['Ln_y']/1000:.3f} / 2 = <b>{sh['Vu_y']:.1f} kN/m</b></td></tr>
<tr><td style="{_n}">φVc,y = φ(1/6)√fck·b·d</td><td style="{_n}">0.75 × (1/6)√{int(_fck)} × 1000 × {_d:.1f} / 1000 = <b>{sh['phi_Vc_y']:.1f} kN/m</b>&emsp;{_ok_ng(sh['ok_y'])}</td></tr>
</table></div>""", unsafe_allow_html=True)


def render_review_output_section(results):
    """구조계산서 검토 모드 결과 표시."""
    if not results or results.get('mode') != 'review':
        return

    st.header("📄 구조계산서 검토 결과")

    fc_k = results.get('fc_k', 24.0)
    fy = results.get('fy', 400.0)
    st.caption(f"fck = {fc_k} MPa | fy = {fy} MPa")

    # ── 전체 요약 테이블 ──
    st.subheader("1. 검토 요약")
    summary_rows = []
    for bm in results.get('review_beams', []):
        status = "✅ OK" if bm['ok_overall'] else "❌ NG"
        # 대표 배근 (END-I 기준)
        end_i = bm['locations'].get('END_I', {})
        top = end_i.get('flexural_neg', {}).get('rebar_string', '-')
        bot = end_i.get('flexural_pos', {}).get('rebar_string', '-')
        s = end_i.get('shear', {}).get('s', '-')
        summary_rows.append({
            '부재': f"보 {bm['name']}",
            '단면': f"{int(bm['b_beam'])}×{int(bm['h_beam'])}",
            'TOP': top, 'BOT': bot, 'Stirrup': f"D10@{int(s)}" if isinstance(s, (int, float)) and s > 0 else '-',
            '판정': status,
        })
    for sl in results.get('review_slabs', []):
        status = "✅ OK" if sl['ok_overall'] else "❌ NG"
        # 대표 배근: Short Cont
        _sc = sl['flexure'].get('short_cont', {})
        summary_rows.append({
            '부재': f"��래브 {sl['name']}",
            '단면': f"{int(sl['Lx'])}×{int(sl['Ly'])}×{int(sl['H'])}",
            'TOP': f"{_sc.get('combo','D10')}@{int(_sc.get('spacing',300))}", 'BOT': '-',
            'Stirrup': '-',
            '판정': status,
        })
    for col in results.get('review_columns', []):
        status = "✅ OK" if col['ok_overall'] else "❌ NG"
        rd = col.get('rebar_design', {})
        summary_rows.append({
            '부재': f"기둥 {col['name']}",
            '단면': f"{int(col['c_column'])}×{int(col['c_column'])}",
            'TOP': rd.get('rebar_string_col', '-'), 'BOT': '-',
            'Stirrup': f"{col['tie_rebar_design']['tie_rebar_type']}@{col['tie_rebar_design']['tie_rebar_spacing']}" if 'tie_rebar_design' in col else '-',
            '판정': status,
        })

    if summary_rows:
        import pandas as _pd
        st.dataframe(_pd.DataFrame(summary_rows), hide_index=True, width='stretch')

    # ── 2. 검토 상세 (탭: 슬래브 / 보 / 기둥) ──
    review_slabs = results.get('review_slabs', [])
    review_beams = results.get('review_beams', [])
    review_columns = results.get('review_columns', [])

    if review_slabs or review_beams or review_columns:
        st.subheader("2. 검토 상세")

        # 탭 라벨 생성
        _detail_tab_labels = []
        _detail_tab_types = []  # ('slab'/'beam'/'col', index)
        for sl in review_slabs:
            _detail_tab_labels.append(f"🟢 슬래브 {sl['name']}")
            _detail_tab_types.append(('slab', sl))
        for bm in review_beams:
            _detail_tab_labels.append(f"🔵 보 {bm['name']}")
            _detail_tab_types.append(('beam', bm))
        for col_data in review_columns:
            _detail_tab_labels.append(f"🟠 기둥 {col_data['name']}")
            _detail_tab_types.append(('col', col_data))

        _detail_tabs = st.tabs(_detail_tab_labels)
        for _dt, (_dtype, _ddata) in zip(_detail_tabs, _detail_tab_types):
            with _dt:
                if _dtype == 'slab':
                    _render_review_slab_detail(_ddata)
                elif _dtype == 'beam':
                    _render_review_beam_detail(_ddata)
                elif _dtype == 'col':
                    _render_review_column_detail(_ddata)

    # ── 3D 배근도 ──
    frame_3d_data = results.get('frame_3d')
    if frame_3d_data:
        st.subheader("3. 3D 골조 배근도")
        _missing_reasons = frame_3d_data.get('missing_reasons', [])
        try:
            from visualization import plot_3d_frame_rebar
            _compat_results = frame_3d_data['results']
            _compat_inputs = frame_3d_data['inputs']
            # beam_x, beam_y, column + 경간/높이 모두 있어야 렌더링 가능
            _can_render = (
                'beam_x' in _compat_results
                and 'beam_y' in _compat_results
                and 'column' in _compat_results
                and _compat_inputs.get('L_x', 0) > 0
                and _compat_inputs.get('L_y', 0) > 0
                and _compat_inputs.get('h_column', 0) > 0
            )
            if _can_render:
                fig_3d = plot_3d_frame_rebar(_compat_results, _compat_inputs)
                st.plotly_chart(fig_3d, use_container_width=True, key="review_3d_rebar")
            else:
                st.info("3D 배근도를 표시할 수 없습니다. 아래 항목을 확인하세요:")
                for _reason in _missing_reasons:
                    st.markdown(f"- {_reason}")
                if not _missing_reasons:
                    st.markdown("- 장변보, 단변보, 기둥이 모두 매핑되고, 치수/배근이 입력되어야 합니다.")
        except Exception as e:
            st.warning(f"⚠️ 3D 배근도 렌더링 실패: {e}")


def _render_best_beam_detail(bm):
    """BeST.RC 보 검토 결과 상세 — 수식 전개 형식."""
    # Streamlit CSS 오버라이드
    st.markdown(
        '<style>'
        '.best-tbl table, .best-tbl th, .best-tbl td, .best-tbl tr '
        '{border:none !important; border-width:0 !important;}'
        '</style>',
        unsafe_allow_html=True)

    _n = 'border:none !important; padding:3px 8px; font-size:13px;'
    _nl = f'{_n} width:45%;'
    # BeST 섹션 박스: st.container(border=True) 사용
    _ok_ng = lambda ok: '<span style="color:blue;">O.K.</span>' if ok else '<span style="color:red; font-weight:bold;">N.G.</span>'

    _name = bm.get('name', '')
    _clean_name = _name.split('[')[0].strip() if '[' in _name else _name
    _fck = bm.get('fc_k', 0)
    _fy = bm.get('fy', 0)
    _fys = bm.get('fys', 0)
    _b = bm.get('b_beam', 0)
    _h = bm.get('h_beam', 0)
    _b_top = bm.get('b_top', 0)
    _h_top = bm.get('h_top', 0)
    from review.calculation_review import _get_alpha1_beta1
    _alpha1_disp, _beta1 = _get_alpha1_beta1(_fck)
    _overall_icon = '✅ O.K.' if bm['ok_overall'] else '❌ N.G.'

    # BeST는 END_I에 단일값으로 저장됨
    end_i = bm['locations'].get('END_I', {})
    neg = end_i.get('flexural_neg', {})
    pos = end_i.get('flexural_pos', {})
    sh = end_i.get('shear', {})

    # 헤더
    st.markdown(
        f'<div style="border-bottom:2px solid #333; padding-bottom:4px; margin-bottom:12px;">'
        f'<span style="font-size:13px; color:#888;">BeST.RC</span>'
        f'&nbsp;&nbsp;&nbsp;<b style="font-size:16px;">MEMBER : {_clean_name}</b>'
        f'&nbsp;&nbsp;&nbsp;<span style="font-size:14px;">{_overall_icon}</span></div>',
        unsafe_allow_html=True)

    # ── Design Conditions (변수 준비) ──
    _fys_line = f"<tr><td style='{_n}'></td><td style='{_n}'>fy = {int(_fy)},&emsp;fys = {int(_fys)} MPa</td></tr>" if _fys > 0 else ""
    if _b_top > 0 and _h_top > 0:
        _sec_line = (f"<tr><td style='{_n}'>Section Data</td><td style='{_n}'>"
                     f"B_top = {int(_b_top)} mm&emsp;H_top = {int(_h_top)} mm</td></tr>"
                     f"<tr><td style='{_n}'></td><td style='{_n}'>"
                     f"B_bot = {int(_b)} mm&emsp;H_bot = {int(_h - _h_top)} mm</td></tr>")
    else:
        _sec_line = f"<tr><td style='{_n}'>Section Data</td><td style='{_n}'>B = {int(_b)} mm&emsp;H = {int(_h)} mm</td></tr>"

    _rebar_top = bm.get('rebar_top', '-')
    _rebar_bot = bm.get('rebar_bot', '-')
    _skin = bm.get('skin_rebar', '')
    _skin_line = f"<tr><td style='{_n}'></td><td style='{_n}'>Skin : {_skin}</td></tr>" if _skin else ""
    _loc_top = neg.get('flexural_steps', {}).get('Loc', 0)
    _loc_bot = pos.get('flexural_steps', {}).get('Loc', 0)
    _loc_top_str = f" (Loc. = {_loc_top:.0f} mm)" if _loc_top > 0 else ""
    _loc_bot_str = f" (Loc. = {_loc_bot:.0f} mm)" if _loc_bot > 0 else ""

    from review.calculation_review import _parse_rebar_string, _parse_skin_rebar
    _, _, _As_top_only = _parse_rebar_string(_rebar_top)
    _, _, _As_bot_only = _parse_rebar_string(_rebar_bot)
    _, _, _As_skin_only = _parse_skin_rebar(_skin)
    _As_total = _As_top_only + _As_bot_only + _As_skin_only
    if _b_top > 0 and _h_top > 0:
        _Ag = _b_top * _h_top + _b * (_h - _h_top)
    else:
        _Ag = _b * _h
    _rho_st = _As_total / _Ag if _Ag > 0 else 0

    _dc_html = f"""
    <div class="best-tbl">
    <table style="width:100%; border-collapse:collapse;">
    <tr><td style="{_n}">Material Data</td><td style="{_n}">f_ck = {int(_fck)} N/mm² (β₁ = {_beta1:.3f})</td></tr>
    {_fys_line}
    {_sec_line}
    <tr><td style="{_n}">Rebar Data</td><td style="{_n}">Upper : {_rebar_top}{_loc_top_str}</td></tr>
    <tr><td style="{_n}"></td><td style="{_n}">Lower : {_rebar_bot}{_loc_bot_str}</td></tr>
    {_skin_line}
    <tr><td style="{_n}"></td><td style="{_n}">Total Rebar Area = {_As_total:.0f} mm² (ρ_st = {_rho_st:.4f})</td></tr>
    </table>
    </div>
    """
    # ── Design Conditions(왼쪽 박스) + 단면도(오른쪽 박스) ──
    # 왼쪽 텍스트 줄 수로 높이 계산
    _dc_lines = 5
    if _fys > 0:
        _dc_lines += 1
    if _b_top > 0 and _h_top > 0:
        _dc_lines += 1
    if _skin:
        _dc_lines += 1
    _dc_lines += 1
    _dc_box_h = 70 + _dc_lines * 28

    # 오른쪽 박스 스크롤 제거 CSS
    st.markdown(
        '<style>'
        '.best-sec-box [data-testid="stVerticalBlockBorderWrapper"] > div[style*="overflow"] '
        '{overflow:hidden !important;}'
        '</style>',
        unsafe_allow_html=True)

    _col_dc, _col_sec = st.columns([3, 2])
    with _col_dc:
        with st.container(border=True, height=_dc_box_h):
            st.markdown("#### ◆ Design Conditions ◆")
            st.markdown(_dc_html, unsafe_allow_html=True)
    with _col_sec:
        with st.container(border=True, height=_dc_box_h):
            try:
                from visualization import plot_best_section
                import io as _io, base64 as _b64
                _cover_sec = float(bm.get('cover', 40) or 40)
                fig_sec = plot_best_section(
                    _b, _h, _rebar_top, _rebar_bot, skin_str=_skin,
                    cover=_cover_sec, stirrup_d=9.53,
                    b_top=_b_top, h_top=_h_top)
                _buf = _io.BytesIO()
                fig_sec.savefig(_buf, format='png', bbox_inches='tight', pad_inches=0.02, dpi=150)
                plt.close(fig_sec)
                _buf.seek(0)
                _img_b64 = _b64.b64encode(_buf.read()).decode()
                # HTML img 태그로 직접 삽입 (Streamlit 마진 없음, 100% 폭, 높이 자동)
                _avail_h = _dc_box_h - 34  # border+padding
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:center;height:{_avail_h}px;">'
                    f'<img src="data:image/png;base64,{_img_b64}" '
                    f'style="max-width:100%;max-height:{_avail_h}px;object-fit:contain;">'
                    f'</div>',
                    unsafe_allow_html=True)
            except Exception as _e_best_sec:
                st.caption(f"⚠️ 단면도: {_e_best_sec}")

    # ── Design Force and Moment ──
    _Mu = neg.get('Mu', 0)
    _Vu = sh.get('Vu', 0)
    with st.container(border=True):
        st.markdown("#### ◆ Design Force and Moment ◆")
        st.markdown(f"""
        <div class="best-tbl">
        <table style="width:100%; border-collapse:collapse;">
        <tr><td style="{_n}">M_u = {_Mu:.1f} kN·m,&emsp;T_u = 0.0 kN·m</td></tr>
        <tr><td style="{_n}">V_u = {_Vu:.1f} kN</td></tr>
        </table>
        </div>
        """, unsafe_allow_html=True)

    # ── Check Crack Width ──
    _crack = end_i.get('crack', {})
    with st.container(border=True):
        st.markdown("#### ◆ Check Crack Width ◆")
        if _crack:
            _smax_cr = _crack.get('smax', 0)
            _s_cr = _crack.get('s_rebar', 0)
            _crack_ok_val = _crack.get('ok', True)
            st.markdown(
                f'<div class="best-tbl"><table style="width:100%; border-collapse:collapse;">'
                f'<tr><td style="{_n}">s_max = Min[380(280/f_s)-2.5c_c, 300(280/f_s)]</td>'
                f'<td style="{_n}">= {_smax_cr:.0f} &nbsp;{">" if _smax_cr >= _s_cr else "<"}&nbsp; '
                f's = {_s_cr:.0f} mm &nbsp;--->&nbsp; {_ok_ng(_crack_ok_val)}</td></tr>'
                f'</table></div>', unsafe_allow_html=True)
        else:
            st.caption("균열 검사 데이터 없음")

    # ── Check Bending Moment Capacity ──
    _phi = neg.get('phi', 0.85)
    _cb = neg.get('cb', 0)
    _c = neg.get('c', 0)
    _et = neg.get('epsilon_t', 0)
    _Ts = neg.get('Ts_kN', 0)
    _Cs = neg.get('Cs_kN', 0)
    _Cc = neg.get('Cc_kN', 0)
    _phiMn = neg.get('phi_Mn', 0)
    _ratio = neg.get('check_ratio', 0)
    _ok_flex = neg.get('ok', True)
    _et_ok = _et >= 0.005
    _12Mcr = neg.get('1.2Mcr', 0)

    _flex_html = f"""
    <div class="best-tbl">
    <table style="width:100%; border-collapse:collapse;">
    <tr><td style="{_nl}">Strength Reduction Factor</td><td style="{_n}">Φ = {_phi:.3f}</td></tr>
    <tr><td style="{_nl}">Balanced Axis Depth</td><td style="{_n}">c_b = {_cb:.0f} mm</td></tr>
    <tr><td style="{_nl}">Neutral Axis Depth</td><td style="{_n}">c = {_c:.0f} mm</td></tr>
    <tr><td style="{_nl}">Max. Tensile strain</td><td style="{_n}">ε_t = {_et:.4f} {'>' if _et_ok else '<'} 0.0050 &nbsp;--->&nbsp; {_ok_ng(_et_ok)}</td></tr>
    <tr><td style="{_nl}">Tension : Rebar</td><td style="{_n}">T_s = {-abs(_Ts):.1f} kN</td></tr>
    <tr><td style="{_nl}">Compression : Rebar</td><td style="{_n}">C_s = {abs(_Cs):.1f} kN</td></tr>
    <tr><td style="{_nl}">Compression : Concrete</td><td style="{_n}">C_c = {abs(_Cc):.1f} kN</td></tr>
    <tr><td style="{_nl}">Design Moment Capacity</td><td style="{_n}">ΦM_n = {abs(_phiMn):.1f} kN·m {'>' if abs(_phiMn) >= _12Mcr else '<'} 1.2M_cr = {_12Mcr:.1f} &nbsp;--->&nbsp; {_ok_ng(abs(_phiMn) >= _12Mcr)}</td></tr>
    <tr><td style="{_nl}">M_u/ΦM_n = {_ratio:.3f}</td><td style="{_n}">{'<' if _ratio <= 1.0 else '>'} 1.000 &nbsp;--->&nbsp; {_ok_ng(_ok_flex)}</td></tr>
    </table>
    </div>
    """
    with st.container(border=True):
        st.markdown("#### ◆ Check Bending Moment Capacity ◆")
        st.markdown(_flex_html, unsafe_allow_html=True)

    # ── Calculate Shear Reinf. (변수 준비) ──
    _phi_sh = 0.75
    _phiVc = sh.get('phi_Vc', 0)
    _phiVs_req = sh.get('phi_Vs_req', 0)
    _stir_str = bm.get('stirrup', '-')
    _s_val = sh.get('s', 0)
    _stir_display = _stir_str if _stir_str else f"2-D10 @{int(_s_val)}" if _s_val > 0 else "-"

    _sh_steps = sh.get('shear_steps', {})
    _sh_formula = _sh_steps.get('shear_formula', 'simplified')
    if _sh_formula == 'detailed':
        _vc_formula_line = (f'<tr><td style="{_nl}">ΦV_c = (0.16√f_ck + 17.6ρ_w·V_u·d/M_u)b_w·d</td>'
                           f'<td style="{_n}">= {_phiVc:.1f} kN</td></tr>')
    else:
        _vc_formula_line = f'<tr><td style="{_nl}">ΦV_c</td><td style="{_n}">= {_phiVc:.1f} kN</td></tr>'

    _shear_html = f"""
    <div class="best-tbl">
    <table style="width:100%; border-collapse:collapse;">
    <tr><td style="{_nl}">Strength Reduction Factor</td><td style="{_n}">Φ = {_phi_sh:.3f}</td></tr>
    {_vc_formula_line}
    <tr><td style="{_nl}">ΦV_s,req = V_u - ΦV_c</td><td style="{_n}">= {_phiVs_req:.1f} kN</td></tr>
    <tr><td style="{_nl}">ΦV_c + ΦV_s,req</td><td style="{_n}">= {_phiVc:.1f} + {_phiVs_req:.1f} = {_phiVc + _phiVs_req:.1f} kN</td></tr>
    <tr><td style="{_nl}">Required Stirrup Reinf.</td><td style="{_n}">{_stir_display}</td></tr>
    </table>
    </div>
    """
    with st.container(border=True):
        st.markdown("#### ◆ Calculate Shear Reinf. ◆")
        st.markdown(_shear_html, unsafe_allow_html=True)

    # 경고
    all_warnings = []
    for sub in ['flexural_neg', 'flexural_pos', 'shear']:
        all_warnings.extend(end_i.get(sub, {}).get('warnings', []))
    for w in set(all_warnings):
        if '오류' in w or 'NG' in w:
            st.error(w)
        elif '경고' in w:
            st.warning(w)

    na = bm.get('not_available', {})
    if na:
        _na_text = "\n".join([f"- **{key}**: {msg}" for key, msg in na.items()])
        st.warning(f"**검토 불가 항목**\n\n{_na_text}")


def _render_review_beam_detail(bm):
    """보 1개의 검토 결과 상세 (MIDAS/BeST 분기)."""
    # Streamlit 기본 테이블 CSS 오버라이드 (선 제거)
    st.markdown(
        '<style>.midas-tbl table, .midas-tbl th, .midas-tbl td, .midas-tbl tr '
        '{border:none !important; border-width:0 !important;}</style>',
        unsafe_allow_html=True)

    software = bm.get('software', '')
    is_midas = 'MIDAS' in software.upper() or not software  # 기본값도 MIDAS 형식

    if not is_midas:
        _render_best_beam_detail(bm)
        return

    # ── 헤더 (MIDAS) ──
    if is_midas:
        _overall_icon = '✅ OK' if bm['ok_overall'] else '❌ NG'
        st.markdown(
            f'<div style="border-bottom:2px solid #333; padding-bottom:4px; margin-bottom:12px;">'
            f'<span style="font-size:13px; color:#888;">midas Gen</span>'
            f'&nbsp;&nbsp;&nbsp;<b style="font-size:16px;">RC Beam Strength Checking Result</b>'
            f'&nbsp;&nbsp;&nbsp;<span style="font-size:14px;">{_overall_icon}</span></div>',
            unsafe_allow_html=True)
    else:
        st.markdown(f"**{bm['name']}** — {int(bm['b_beam'])}×{int(bm['h_beam'])}mm | "
                    f"판정: {'✅ OK' if bm['ok_overall'] else '❌ NG'}")

    # ── 1. Design Information ──
    if is_midas:
        _fck = bm.get('fc_k', 0)
        _fy = bm.get('fy', 0)
        _fys = bm.get('fys', 0)
        _span = bm.get('span_m', 0)
        _name = bm.get('name', '')
        # 부재명에서 [MIDAS Gen] 등 제거
        _clean_name = _name.split('[')[0].strip() if '[' in _name else _name
        _fys_str = f"&emsp;&emsp;fys = {int(_fys)}" if _fys > 0 else ""
        _span_str = f"{_span:.2f}m" if _span > 0 else "-"
        st.markdown("#### 1. Design Information")
        _info_html = f"""
        <div class="midas-tbl">
        <table style="width:100%; border-collapse:collapse; font-size:13px; margin-bottom:12px;">
        <tr><td style="padding:4px 8px; width:20%;">Design Code</td><td style="padding:4px 8px;">KDS 41 30 : 2018</td>
            <td style="padding:4px 8px; width:15%;">Unit System</td><td style="padding:4px 8px;">kN, m</td></tr>
        <tr><td style="padding:4px 8px;">Material Data</td><td colspan="3" style="padding:4px 8px;">fck = {int(_fck)}&emsp;&emsp;fy = {int(_fy)}{_fys_str} MPa</td></tr>
        <tr><td style="padding:4px 8px;">Section Property</td><td style="padding:4px 8px;">{_clean_name} — {int(bm['b_beam'])}×{int(bm['h_beam'])}mm</td>
            <td style="padding:4px 8px;">Beam Span</td><td style="padding:4px 8px;">{_span_str}</td></tr>
        </table>
        </div>
        """
        st.markdown(_info_html, unsafe_allow_html=True)

    end_i = bm['locations'].get('END_I', {})
    mid = bm['locations'].get('MID', {})
    end_j = bm['locations'].get('END_J', {})

    def _get(loc, path, default=0):
        """loc 딕셔너리에서 중첩 키 접근."""
        parts = path.split('.')
        v = loc
        for p in parts:
            if isinstance(v, dict):
                v = v.get(p, {})
            else:
                return default
        return v if v != {} else default

    def _fmt(v, decimals=2):
        if isinstance(v, (int, float)):
            return f"{v:.{decimals}f}"
        return str(v) if v else '-'

    def _ratio_color(v):
        """검토비 색상: >1.0 빨강, ≤1.0 파랑."""
        try:
            fv = float(v)
            return 'color: red; font-weight: bold' if fv > 1.0 else 'color: blue'
        except (ValueError, TypeError):
            return ''

    # ── 1. 단면도 (맨 위) ──
    try:
        from visualization import plot_rebar_section
        top_i = _get(end_i, 'flexural_neg.rebar_string', '2-D13')
        bot_i = _get(end_i, 'flexural_pos.rebar_string', '2-D13')
        s_i = _get(end_i, 'shear.s', 200)
        top_m = _get(mid, 'flexural_neg.rebar_string', '2-D13')
        bot_m = _get(mid, 'flexural_pos.rebar_string', '2-D13')
        s_m = _get(mid, 'shear.s', 200)
        top_j = _get(end_j, 'flexural_neg.rebar_string', '2-D13')
        bot_j = _get(end_j, 'flexural_pos.rebar_string', '2-D13')
        s_j = _get(end_j, 'shear.s', 200)

        _cover = float(bm.get('cover', 40))
        _stir_str = bm.get('stirrup', '2-D10@125')
        _stir_d = 9.53  # D10 기본

        sections_data = [
            {'title': '[END-I]', 'top': top_i, 'bot': bot_i, 'stirrup': _stir_str},
            {'title': '[MID]',   'top': top_m, 'bot': bot_m, 'stirrup': _stir_str},
            {'title': '[END-J]', 'top': top_j, 'bot': bot_j, 'stirrup': _stir_str},
        ]
        fig = plot_rebar_section_review(
            bm['b_beam'], bm['h_beam'], sections_data,
            cover=_cover, stirrup_d=_stir_d,
            title_prefix=f"midas Gen RC Beam Section — {bm['name']}"
        )
        st.pyplot(fig); plt.close(fig)
    except Exception as _e_rv_beam:
        st.caption(f"⚠️ 보 단면도 렌더링 실패: {_e_rv_beam}")

    # ── 2. Bending Moment Capacity (가로 비교 테이블) ──
    st.markdown("#### 2. Bending Moment Capacity")

    neg_i = end_i.get('flexural_neg', {})
    neg_m = mid.get('flexural_neg', {})
    neg_j = end_j.get('flexural_neg', {})
    pos_i = end_i.get('flexural_pos', {})
    pos_m = mid.get('flexural_pos', {})
    pos_j = end_j.get('flexural_pos', {})

    # (-) 부모멘트
    neg_Mu_i = neg_i.get('Mu', 0)
    neg_Mu_m = neg_m.get('Mu', 0)
    neg_Mu_j = neg_j.get('Mu', 0)
    neg_phiMn_i = neg_i.get('phi_Mn', 0)
    neg_phiMn_m = neg_m.get('phi_Mn', 0)
    neg_phiMn_j = neg_j.get('phi_Mn', 0)
    neg_ratio_i = neg_Mu_i / neg_phiMn_i if neg_phiMn_i > 0 else 0
    neg_ratio_m = neg_Mu_m / neg_phiMn_m if neg_phiMn_m > 0 else 0
    neg_ratio_j = neg_Mu_j / neg_phiMn_j if neg_phiMn_j > 0 else 0

    # (+) 정모멘트
    pos_Mu_i = pos_i.get('Mu', 0)
    pos_Mu_m = pos_m.get('Mu', 0)
    pos_Mu_j = pos_j.get('Mu', 0)
    pos_phiMn_i = pos_i.get('phi_Mn', 0)
    pos_phiMn_m = pos_m.get('phi_Mn', 0)
    pos_phiMn_j = pos_j.get('phi_Mn', 0)
    pos_ratio_i = pos_Mu_i / pos_phiMn_i if pos_phiMn_i > 0 else 0
    pos_ratio_m = pos_Mu_m / pos_phiMn_m if pos_phiMn_m > 0 else 0
    pos_ratio_j = pos_Mu_j / pos_phiMn_j if pos_phiMn_j > 0 else 0

    # As 배근
    as_top_i = neg_i.get('rebar_string', '-')
    as_top_m = neg_m.get('rebar_string', '-')
    as_top_j = neg_j.get('rebar_string', '-')
    as_bot_i = pos_i.get('rebar_string', '-')
    as_bot_m = pos_m.get('rebar_string', '-')
    as_bot_j = pos_j.get('rebar_string', '-')

    # LC 번호 (있으면 표시)
    _lc = bm.get('load_combinations', {})
    _lc_neg = _lc.get('Mu_neg_lc')  # (I, MID, J) 튜플 또는 None
    _lc_pos = _lc.get('Mu_pos_lc')
    _lc_vu = _lc.get('Vu_lc')

    # 공통 테이블 스타일 (MIDAS: 선 없음, 헤더 회색 배경만)
    _tbl = 'width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px;'
    _th = 'padding:6px 8px; text-align:center; background:#e8e8e8; font-weight:bold;'
    _th_l = 'padding:6px 8px; text-align:left; background:#e8e8e8; font-weight:bold; width:40%;'
    _td = 'padding:4px 8px; text-align:center;'
    _td_l = 'padding:4px 8px; text-align:left;'
    _sec = 'padding:8px 8px 4px 0; font-weight:bold;'

    def _lc_row(label, lc_tuple):
        """LC No. 행 HTML. 데이터 없으면 빈 문자열."""
        if not lc_tuple or not isinstance(lc_tuple, (list, tuple)) or len(lc_tuple) < 3:
            return ''
        return (f'<tr><td style="{_td_l}">{label}</td>'
                f'<td style="{_td}">{lc_tuple[0]}</td>'
                f'<td style="{_td}">{lc_tuple[1]}</td>'
                f'<td style="{_td}">{lc_tuple[2]}</td></tr>')

    bending_html = f"""
    <div class="midas-tbl">
    <table style="{_tbl}">
    <thead>
    <tr><th style="{_th_l}"></th>
        <th style="{_th}">END-I</th><th style="{_th}">MID</th><th style="{_th}">END-J</th></tr>
    </thead>
    <tbody>
    {_lc_row('(-) Load Combination No.', _lc_neg)}
    <tr><td style="{_td_l}">Moment (Mu) [kN·m]</td>
        <td style="{_td}">{_fmt(neg_Mu_i)}</td><td style="{_td}">{_fmt(neg_Mu_m)}</td><td style="{_td}">{_fmt(neg_Mu_j)}</td></tr>
    <tr><td style="{_td_l}">Factored Strength (φMn) [kN·m]</td>
        <td style="{_td}">{_fmt(neg_phiMn_i)}</td><td style="{_td}">{_fmt(neg_phiMn_m)}</td><td style="{_td}">{_fmt(neg_phiMn_j)}</td></tr>
    <tr><td style="{_td_l}">Check Ratio (Mu/φMn)</td>
        <td style="{_td} {_ratio_color(neg_ratio_i)}">{_fmt(neg_ratio_i, 4)}</td>
        <td style="{_td} {_ratio_color(neg_ratio_m)}">{_fmt(neg_ratio_m, 4)}</td>
        <td style="{_td} {_ratio_color(neg_ratio_j)}">{_fmt(neg_ratio_j, 4)}</td></tr>

    <tr><td colspan="4" style="padding:6px 0;"></td></tr>
    {_lc_row('(+) Load Combination No.', _lc_pos)}
    <tr><td style="{_td_l}">Moment (Mu) [kN·m]</td>
        <td style="{_td}">{_fmt(pos_Mu_i)}</td><td style="{_td}">{_fmt(pos_Mu_m)}</td><td style="{_td}">{_fmt(pos_Mu_j)}</td></tr>
    <tr><td style="{_td_l}">Factored Strength (φMn) [kN·m]</td>
        <td style="{_td}">{_fmt(pos_phiMn_i)}</td><td style="{_td}">{_fmt(pos_phiMn_m)}</td><td style="{_td}">{_fmt(pos_phiMn_j)}</td></tr>
    <tr><td style="{_td_l}">Check Ratio (Mu/φMn)</td>
        <td style="{_td} {_ratio_color(pos_ratio_i)}">{_fmt(pos_ratio_i, 4)}</td>
        <td style="{_td} {_ratio_color(pos_ratio_m)}">{_fmt(pos_ratio_m, 4)}</td>
        <td style="{_td} {_ratio_color(pos_ratio_j)}">{_fmt(pos_ratio_j, 4)}</td></tr>

    <tr><td colspan="4" style="padding:6px 0;"></td></tr>
    <tr><td style="{_td_l}">Using Rebar Top (As.top) [m²]</td>
        <td style="{_td}">{_fmt(neg_i.get('As_provided', 0) / 1e6, 4)}</td>
        <td style="{_td}">{_fmt(neg_m.get('As_provided', 0) / 1e6, 4)}</td>
        <td style="{_td}">{_fmt(neg_j.get('As_provided', 0) / 1e6, 4)}</td></tr>
    <tr><td style="{_td_l}">Using Rebar Bot (As.bot) [m²]</td>
        <td style="{_td}">{_fmt(pos_i.get('As_provided', 0) / 1e6, 4)}</td>
        <td style="{_td}">{_fmt(pos_m.get('As_provided', 0) / 1e6, 4)}</td>
        <td style="{_td}">{_fmt(pos_j.get('As_provided', 0) / 1e6, 4)}</td></tr>
    </tbody>
    </table>
    </div>
    """
    st.markdown(bending_html, unsafe_allow_html=True)

    # ── 3. Shear Capacity (가로 비교 테이블) ──
    st.markdown("#### 3. Shear Capacity")

    sh_i = end_i.get('shear', {})
    sh_m = mid.get('shear', {})
    sh_j = end_j.get('shear', {})

    vu_i = sh_i.get('Vu', 0)
    vu_m = sh_m.get('Vu', 0)
    vu_j = sh_j.get('Vu', 0)
    phiVc_i = sh_i.get('phi_Vc', 0)
    phiVc_m = sh_m.get('phi_Vc', 0)
    phiVc_j = sh_j.get('phi_Vc', 0)
    phiVs_i = sh_i.get('phi_Vs', 0)
    phiVs_m = sh_m.get('phi_Vs', 0)
    phiVs_j = sh_j.get('phi_Vs', 0)
    s_i_val = sh_i.get('s', 0)
    s_m_val = sh_m.get('s', 0)
    s_j_val = sh_j.get('s', 0)
    stir_str = bm.get('stirrup', '2-D10@125')
    stir_i = stir_str if stir_str else '-'
    stir_m = stir_str if stir_str else '-'
    stir_j = stir_str if stir_str else '-'
    # 구조계산서 스터럽 기반 AsV (Av/s × 1000 = mm²/m → /1e6 = m²/m)
    # MIDAS는 AsV를 m²/m 단위로 표시 (1m당 전단철근 면적)
    import re as _re_stir
    _stir_m = _re_stir.match(r'(\d+)-D(\d+)\s*@\s*(\d+)', str(stir_str or ''))
    if _stir_m:
        _stir_n = int(_stir_m.group(1))
        _stir_dnum = int(_stir_m.group(2))
        _stir_s = float(_stir_m.group(3))
        _stir_dia_map = {10: 9.53, 13: 12.7, 16: 15.9}
        _stir_dia = _stir_dia_map.get(_stir_dnum, 9.53)
        _Av_one = _stir_n * 3.14159 / 4.0 * _stir_dia ** 2  # mm²
        _asv_per_m = _Av_one / _stir_s * 1000  # mm²/m
    else:
        _asv_per_m = 0.0
    asv_i = _asv_per_m
    asv_m = _asv_per_m
    asv_j = _asv_per_m
    vn_i = phiVc_i + phiVs_i
    vn_m = phiVc_m + phiVs_m
    vn_j = phiVc_j + phiVs_j
    sh_ratio_i = vu_i / vn_i if vn_i > 0 else 0
    sh_ratio_m = vu_m / vn_m if vn_m > 0 else 0
    sh_ratio_j = vu_j / vn_j if vn_j > 0 else 0

    shear_html = f"""
    <div class="midas-tbl">
    <table style="{_tbl}">
    <thead>
    <tr><th style="{_th_l}"></th>
        <th style="{_th}">END-I</th><th style="{_th}">MID</th><th style="{_th}">END-J</th></tr>
    </thead>
    <tbody>
    {_lc_row('Load Combination No.', _lc_vu)}
    <tr><td style="{_td_l}">Factored Shear Force (Vu) [kN]</td>
        <td style="{_td}">{_fmt(vu_i)}</td><td style="{_td}">{_fmt(vu_m)}</td><td style="{_td}">{_fmt(vu_j)}</td></tr>
    <tr><td style="{_td_l}">Shear Strength by Conc. (φVc) [kN]</td>
        <td style="{_td}">{_fmt(phiVc_i)}</td><td style="{_td}">{_fmt(phiVc_m)}</td><td style="{_td}">{_fmt(phiVc_j)}</td></tr>
    <tr><td style="{_td_l}">Shear Strength by Rebar (φVs) [kN]</td>
        <td style="{_td}">{_fmt(phiVs_i)}</td><td style="{_td}">{_fmt(phiVs_m)}</td><td style="{_td}">{_fmt(phiVs_j)}</td></tr>
    <tr><td style="{_td_l}">Using Shear Reinf. (AsV) [m²]</td>
        <td style="{_td}">{_fmt(asv_i / 1e6, 4)}</td><td style="{_td}">{_fmt(asv_m / 1e6, 4)}</td><td style="{_td}">{_fmt(asv_j / 1e6, 4)}</td></tr>
    <tr><td style="{_td_l}">Using Stirrups Spacing</td>
        <td style="{_td}">{stir_i}</td><td style="{_td}">{stir_m}</td><td style="{_td}">{stir_j}</td></tr>
    <tr><td style="{_td_l}">Check Ratio (Vu/(φVc+φVs))</td>
        <td style="{_td} {_ratio_color(sh_ratio_i)}">{_fmt(sh_ratio_i, 4)}</td>
        <td style="{_td} {_ratio_color(sh_ratio_m)}">{_fmt(sh_ratio_m, 4)}</td>
        <td style="{_td} {_ratio_color(sh_ratio_j)}">{_fmt(sh_ratio_j, 4)}</td></tr>
    </tbody>
    </table>
    </div>
    """
    st.markdown(shear_html, unsafe_allow_html=True)

    # ── 경고 메시지 취합 ──
    all_warnings = []
    for loc_name in ['END_I', 'MID', 'END_J']:
        loc = bm['locations'].get(loc_name, {})
        for sub in ['flexural_neg', 'flexural_pos', 'shear']:
            all_warnings.extend(loc.get(sub, {}).get('warnings', []))
    for w in set(all_warnings):
        if '오류' in w or 'NG' in w:
            st.error(w)
        elif '경고' in w:
            st.warning(w)

    # ── 검토 불가 항목 ──
    na = bm.get('not_available', {})
    if na:
        _na_text = "\n".join([f"• **{key}**: {msg}" for key, msg in na.items()])
        st.warning(f"**검토 불가 항목**\n\n{_na_text}")


def _render_best_column_detail(col_data):
    """BeST.Steel 기둥 검토 결과 상세 — 수식 전개 형식."""
    # CSS 오버라이드
    st.markdown(
        '<style>.best-tbl table, .best-tbl th, .best-tbl td, .best-tbl tr '
        '{border:none !important; border-width:0 !important;}</style>',
        unsafe_allow_html=True)

    _n = 'border:none !important; padding:3px 8px; font-size:13px;'
    _nl = f'{_n} width:45%;'
    _ok_ng = lambda ok: '<span style="color:blue;">O.K.</span>' if ok else '<span style="color:red; font-weight:bold;">N.G.</span>'

    rd = col_data.get('rebar_design', {})
    sl = col_data.get('slenderness', {})
    tie = col_data.get('tie_rebar_design', {})

    _name = col_data.get('name', '')
    _clean_name = _name.split('[')[0].strip() if '[' in _name else _name
    _c = col_data.get('c_column', 0)
    _h_col = col_data.get('h_column', 0)
    _fck = col_data.get('fc_k', 0) if 'fc_k' in col_data else 0
    _fy = col_data.get('fy', 0) if 'fy' in col_data else 0
    _Pu = col_data.get('Pu', 0)
    _Mux = col_data.get('Mux', 0)
    _Muy = col_data.get('Muy', 0)
    _overall = '✅ O.K.' if col_data['ok_overall'] else '❌ N.G.'

    # ── 헤더 ──
    st.markdown(
        f'<div style="border-bottom:2px solid #333; padding-bottom:4px; margin-bottom:12px;">'
        f'<span style="font-size:13px; color:#888;">BeST.Steel</span>'
        f'&nbsp;&nbsp;&nbsp;<b style="font-size:16px;">MEMBER : {_clean_name}</b>'
        f'&nbsp;&nbsp;&nbsp;<span style="font-size:14px;">{_overall}</span></div>',
        unsafe_allow_html=True)

    # ── Design Conditions ──
    _rebar_str = rd.get('rebar_vert_input', rd.get('rebar_string_col', '-'))
    _hoop_str = f"{tie.get('tie_rebar_type', 'D10')}@{int(tie.get('tie_rebar_spacing', 200))}"
    _rho = rd.get('rho', 0)
    _As = rd.get('As_provided_col', 0)
    _Ag = col_data.get('dimensions', {}).get('Ag', _c * _c)

    _dc_html = f"""
    <div class="best-tbl">
    <table style="width:100%; border-collapse:collapse;">
    <tr><td style="{_n}">Material Data</td><td style="{_n}">f_ck = {int(_fck)} N/mm²</td></tr>
    <tr><td style="{_n}"></td><td style="{_n}">F_y,Bar = {int(_fy)} N/mm²</td></tr>
    <tr><td style="{_n}">Section Data</td><td style="{_n}">C_x = {int(_c)} mm&emsp;C_y = {int(_c)} mm</td></tr>
    <tr><td style="{_n}"></td><td style="{_n}">KL_u = {_h_col/1000:.2f} m</td></tr>
    <tr><td style="{_n}">Rebar Data</td><td style="{_n}">Vert : {_rebar_str} (A_s = {_As:.0f} mm²)</td></tr>
    <tr><td style="{_n}"></td><td style="{_n}">Hoop : {_hoop_str}</td></tr>
    </table>
    </div>
    """

    # Design Conditions + 단면도
    _col_dc, _col_sec = st.columns([3, 2])
    with _col_dc:
        with st.container(border=True):
            st.markdown("#### ◆ Design Conditions ◆")
            st.markdown(_dc_html, unsafe_allow_html=True)
    with _col_sec:
        with st.container(border=True):
            try:
                from visualization import plot_best_column_section
                import io as _io, base64 as _b64
                _n_col = rd.get('n_col', 8)
                _main_dia = rd.get('rebar_diameter_col', 19.1)
                _tie_dia = tie.get('tie_rebar_diameter', 9.53)
                _steel_sec_str = col_data.get('src_data', {}).get('steel_section', '')
                _cover_val = col_data.get('cover', 40)
                fig_sec = plot_best_column_section(
                    _c, _n_col, _main_dia, _cover_val, _tie_dia, _steel_sec_str)
                _buf = _io.BytesIO()
                fig_sec.savefig(_buf, format='png', bbox_inches='tight', pad_inches=0.02, dpi=150)
                plt.close(fig_sec)
                _buf.seek(0)
                _img_b64 = _b64.b64encode(_buf.read()).decode()
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:center;">'
                    f'<img src="data:image/png;base64,{_img_b64}" style="max-width:100%;max-height:250px;object-fit:contain;">'
                    f'</div>', unsafe_allow_html=True)
            except Exception as _e:
                st.caption(f"⚠️ 단면도: {_e}")

    # ── Design Force and Moment ──
    _Mux_input = col_data.get('Mux_input', _Mux)
    _Muy_input = col_data.get('Muy_input', _Muy)
    _delta_ns = sl.get('delta_ns', 1.0)
    _is_amplified = _delta_ns > 1.0
    with st.container(border=True):
        st.markdown("#### ◆ Design Force and Moment ◆")
        _df_html = f"""
        <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
        <tr><td style="{_n}">P_u = {_Pu:.1f} kN</td></tr>
        <tr><td style="{_n}">M_ux = {_Mux_input:.1f},&emsp;M_uy = {_Muy_input:.1f} kN·m</td></tr>
        """
        if _is_amplified:
            _df_html += f"""
        <tr><td style="{_n}"><i>세장기둥 모멘트 확대 (δ_ns = {_delta_ns:.3f})</i></td></tr>
        <tr><td style="{_n}">M_ux,design = {_Mux:.1f},&emsp;M_uy,design = {_Muy:.1f} kN·m</td></tr>
            """
        _df_html += "</table></div>"
        st.markdown(_df_html, unsafe_allow_html=True)

    # ── Check Limitations ──
    with st.container(border=True):
        st.markdown("#### ◆ Check Limitations ◆")
        _fck_ok = _fck >= 21
        _rho_ok = 0.01 <= _rho <= 0.08 if _rho > 0 else False
        _lambda = sl.get('lambda_ratio', 0)
        _lambda_ok = sl.get('ok', True)
        st.markdown(f"""
        <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
        <tr><td style="{_nl}">Concrete Compressive Strength</td>
            <td style="{_n}">f_ck = {int(_fck)} N/mm² {'>' if _fck_ok else '<'} 21 N/mm² &nbsp;--->&nbsp; {_ok_ng(_fck_ok)}</td></tr>
        <tr><td style="{_nl}">Longitudinal Reinforcement Ratio</td>
            <td style="{_n}">ρ = {_rho:.4f} {'>' if _rho >= 0.01 else '<'} 0.01, {'<' if _rho <= 0.08 else '>'} 0.08 &nbsp;--->&nbsp; {_ok_ng(_rho_ok)}</td></tr>
        <tr><td style="{_nl}">Slenderness (λ = KLu/r)</td>
            <td style="{_n}">λ = {_lambda:.1f} {'≤' if _lambda <= 100 else '>'} 100 &nbsp;--->&nbsp; {_ok_ng(_lambda_ok)}</td></tr>
        </table></div>
        """, unsafe_allow_html=True)

    # ── Check Flexure Capacity ──
    _phi_Pn_max = rd.get('phi_Pn_max', 0)
    _phi_Mnx = rd.get('phi_Mnx', 0)
    _phi_Mny = rd.get('phi_Mny', 0)
    _Rcom = rd.get('Rcom', 0)
    _ok_Rcom = rd.get('ok_Rcom', True)
    _ok_pm = col_data.get('ok_pm', False)

    _src = col_data.get('src_data', {})
    with st.container(border=True):
        st.markdown("#### ◆ Check Flexure Capacity ◆")

        # SRC 추가 정보
        if _src.get('is_src'):
            st.markdown(f"""
            <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
            <tr><td style="{_nl}">C₁ = 0.1 + 2.0(A_s/(A_c+A_s))</td><td style="{_n}">= {_src.get('C1', 0):.3f}</td></tr>
            <tr><td style="{_nl}">EI_eff = E_s·I_s + 0.5E_s·I_sr + C₁·E_c·I_c</td><td style="{_n}">= {_src.get('EIeff_kNm2', 0):.0f} kN·m²</td></tr>
            <tr><td style="{_nl}">P_o = A_s·F_y,Stl + A_sr·F_y,Bar + 0.85A_c·f_ck</td><td style="{_n}">= {_src.get('Po_kN', 0):.0f} kN</td></tr>
            <tr><td style="{_nl}">P_e = π²EI_eff/(KL)²</td><td style="{_n}">= {_src.get('Pe_kN', 0):.0f} kN</td></tr>
            </table></div>
            """, unsafe_allow_html=True)

        # X-X Axis
        st.markdown(f"""
        <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
        <tr><td style="{_n}" colspan="2"><b>X-X Axis</b></td></tr>
        <tr><td style="{_nl}">ΦP_n(max)</td>
            <td style="{_n}">= {_phi_Pn_max:.1f} kN {'>' if _phi_Pn_max >= _Pu else '<'} P_u = {_Pu:.1f} kN &nbsp;--->&nbsp; {_ok_ng(_phi_Pn_max >= _Pu)}</td></tr>
        <tr><td style="{_nl}">ΦM_nx</td><td style="{_n}">= {_phi_Mnx:.1f} kN·m</td></tr>
        <tr><td style="{_n}" colspan="2"><b>Y-Y Axis</b></td></tr>
        <tr><td style="{_nl}">ΦP_n(max)</td>
            <td style="{_n}">= {_phi_Pn_max:.1f} kN {'>' if _phi_Pn_max >= _Pu else '<'} P_u = {_Pu:.1f} kN &nbsp;--->&nbsp; {_ok_ng(_phi_Pn_max >= _Pu)}</td></tr>
        <tr><td style="{_nl}">ΦM_ny</td><td style="{_n}">= {_phi_Mny:.1f} kN·m</td></tr>
        <tr><td style="{_n}" colspan="2">&nbsp;</td></tr>
        <tr><td style="{_nl}">R_com = M_ux/ΦM_nx + M_uy/ΦM_ny</td>
            <td style="{_n}">= {_Rcom:.3f} {'<' if _Rcom <= 1.0 else '>'} 1.000 &nbsp;--->&nbsp; {_ok_ng(_ok_Rcom)}</td></tr>
        </table></div>
        """, unsafe_allow_html=True)

    # ── P-M 다이어그램 (X-X, Y-Y 나란히) ──
    with st.container(border=True):
        st.markdown("#### ◆ X-X Axis / Y-Y Axis ◆")
        _pm_col1, _pm_col2 = st.columns(2)
        try:
            from visualization import plot_pm_diagram
            # X-X
            with _pm_col1:
                _rdx = dict(rd)
                _rdx['pm_curve_P'] = rd.get('pm_curve_Px')
                _rdx['pm_curve_M'] = rd.get('pm_curve_Mx')
                _rdx['pm_nominal_P'] = rd.get('pm_nominal_Px')
                _rdx['pm_nominal_M'] = rd.get('pm_nominal_Mx')
                _rdx['Mu_design'] = abs(_Mux)
                _amx = {'Pu': _Pu}
                fig_pmx = plot_pm_diagram(_rdx, _amx)
                fig_pmx.update_layout(title='X-X Axis', height=350)
                st.plotly_chart(fig_pmx, use_container_width=True, key=f"rv_pmx_{_name}")
            # Y-Y
            with _pm_col2:
                _rdy = dict(rd)
                _rdy['pm_curve_P'] = rd.get('pm_curve_Py')
                _rdy['pm_curve_M'] = rd.get('pm_curve_My')
                _rdy['pm_nominal_P'] = rd.get('pm_nominal_Py')
                _rdy['pm_nominal_M'] = rd.get('pm_nominal_My')
                _rdy['Mu_design'] = abs(_Muy)
                _amy = {'Pu': _Pu}
                fig_pmy = plot_pm_diagram(_rdy, _amy)
                fig_pmy.update_layout(title='Y-Y Axis', height=350)
                st.plotly_chart(fig_pmy, use_container_width=True, key=f"rv_pmy_{_name}")
        except Exception as _e_pm:
            st.caption(f"⚠️ P-M 다이어그램: {_e_pm}")

    # ── Check Shear Strength ──
    _col_sh = col_data.get('col_shear', {})
    with st.container(border=True):
        st.markdown("#### ◆ Check Shear Strength ◆")
        if _col_sh:
            _Vu_sh = _col_sh.get('Vu', 0)
            _phi_Vn_sh = _col_sh.get('phi_Vn', 0)
            _sh_ratio = _col_sh.get('ratio', 0)
            _sh_ok = _col_sh.get('ok', True)
            if _col_sh.get('is_src'):
                # SRC 전단
                _Vn_stl = _col_sh.get('Vn_stl', 0)
                _Vn_rebar = _col_sh.get('Vn_rebar', 0)
                st.markdown(f"""
                <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
                <tr><td style="{_nl}">Applied Shear Force : V_u</td><td style="{_n}">= {_Vu_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">V_n = 0.6·F_y·A_w + F_y,Bar·A_s,Bar·(d/s)</td><td style="{_n}">= {(_Vn_stl + _Vn_rebar):.2f} kN</td></tr>
                <tr><td style="{_nl}">ΦV_n = Φ·V_n</td><td style="{_n}">= {_phi_Vn_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">V_u/ΦV_n = {_sh_ratio:.3f}</td>
                    <td style="{_n}">{'<' if _sh_ratio <= 1.0 else '>'} 1.000 &nbsp;--->&nbsp; {_ok_ng(_sh_ok)}</td></tr>
                </table></div>
                """, unsafe_allow_html=True)
            else:
                # RC 전단
                _phi_Vc_sh = _col_sh.get('phi_Vc', 0)
                _phi_Vs_sh = _col_sh.get('phi_Vs', 0)
                st.markdown(f"""
                <div class="best-tbl"><table style="width:100%; border-collapse:collapse;">
                <tr><td style="{_nl}">Applied Shear Force : V_u</td><td style="{_n}">= {_Vu_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">ΦV_c (concrete)</td><td style="{_n}">= {_phi_Vc_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">ΦV_s (rebar)</td><td style="{_n}">= {_phi_Vs_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">ΦV_n = ΦV_c + ΦV_s</td><td style="{_n}">= {_phi_Vn_sh:.2f} kN</td></tr>
                <tr><td style="{_nl}">V_u/ΦV_n = {_sh_ratio:.3f}</td>
                    <td style="{_n}">{'<' if _sh_ratio <= 1.0 else '>'} 1.000 &nbsp;--->&nbsp; {_ok_ng(_sh_ok)}</td></tr>
                </table></div>
                """, unsafe_allow_html=True)
        else:
            st.caption("전단력(Vu) 미입력")

    # 경고/검토 불가
    na = col_data.get('not_available', {})
    if na:
        _na_text = "\n".join([f"- **{key}**: {msg}" for key, msg in na.items()])
        st.warning(f"**검토 불가 항목**\n\n{_na_text}")


def _render_review_column_detail(col_data):
    """기둥 1개의 검토 결과 상세 (BeST/기본 분기)."""
    # BeST 분기
    _name = col_data.get('name', '')
    if 'BeST' in _name or 'Steel' in _name:
        _render_best_column_detail(col_data)
        return

    rd = col_data.get('rebar_design', {})
    sl = col_data.get('slenderness', {})
    tie = col_data.get('tie_rebar_design', {})

    st.markdown(f"**{col_data['name']}** — {int(col_data['c_column'])}×{int(col_data['c_column'])}mm | "
                f"판정: {'✅ OK' if col_data['ok_overall'] else '❌ NG'}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("주철근", rd.get('rebar_string_col', '-'),
                  delta="OK" if col_data.get('ok_pm') else "NG",
                  delta_color="normal" if col_data.get('ok_pm') else "inverse")
        st.caption(f"ρ = {rd.get('rho', 0):.3f} | φPn_max = {rd.get('phi_Pn_max', 0):.0f} kN")

    with c2:
        st.metric("세장비", f"λ = {sl.get('lambda_ratio', 0):.1f}",
                  delta=sl.get('category', '-'),
                  delta_color="normal" if sl.get('ok') else "inverse")
        if sl.get('delta_ns') and sl['delta_ns'] > 1.0:
            st.caption(f"δ_ns = {sl['delta_ns']:.2f} (모멘트 확대)")

    with c3:
        st.metric("띠철근", f"{tie.get('tie_rebar_type', '-')}@{tie.get('tie_rebar_spacing', '-')}")
        st.caption(f"Pu = {col_data.get('Pu', 0):.0f} kN | Mu = {col_data.get('Mu', 0):.1f} kN·m")

    # P-M 다이어그램 (검토 모드: rebar_design에 pm_curve가 있으면 표시)
    if rd.get('pm_curve_P') is not None and rd.get('pm_curve_M') is not None:
        try:
            from visualization import plot_pm_diagram
            # 검토 모드 결과를 설계 모드 형식으로 매핑
            _rd_compat = dict(rd)
            if 'Mu_design' not in _rd_compat:
                _rd_compat['Mu_design'] = float(col_data.get('Mu', 0) or 0)
            _am_compat = {'Pu': float(col_data.get('Pu', 0) or 0)}
            fig_pm = plot_pm_diagram(_rd_compat, _am_compat)
            st.plotly_chart(fig_pm, use_container_width=True, key=f"rv_pm_{col_data['name']}")
        except Exception as _e_rv_pm:
            st.caption(f"⚠️ P-M 다이어그램 렌더링 실패: {_e_rv_pm}")
    else:
        st.info("ℹ️ P-M 다이어그램: 검토 모드 P-M 곡선 데이터 미생성 (추후 구현 예정)")

    # 기둥 단면도
    if rd.get('rebar_string_col') and rd.get('n_col', 0) > 0:
        try:
            from visualization import plot_column_section
            import re as _re_col
            _tie_dname = tie.get('tie_rebar_type', 'D10')
            _tie_dia_map = {'D10': 9.53, 'D13': 12.7}
            _m_main = _re_col.match(r'.*D(\d+)', rd.get('rebar_string_col', 'D19'))
            _main_dname = f"D{_m_main.group(1)}" if _m_main else 'D19'
            _main_dia_map = {'D13': 12.7, 'D16': 15.9, 'D19': 19.1, 'D22': 22.2, 'D25': 25.4, 'D29': 28.6}
            fig_sec = plot_column_section(
                col_data['c_column'],
                rd.get('n_col', 8),
                _main_dname,
                _main_dia_map.get(_main_dname, 19.1),
                _tie_dname,
                _tie_dia_map.get(_tie_dname, 9.53),
                tie.get('tie_rebar_spacing', 200),
            )
            st.pyplot(fig_sec); plt.close(fig_sec)
        except Exception as _e_rv_col:
            st.caption(f"⚠️ 기둥 단면도 렌더링 실패: {_e_rv_col}")
    else:
        st.info("ℹ️ 기둥 단면도: 배근 정보 부족")

    # 검토 불가 항목
    na = col_data.get('not_available', {})
    if na:
        _na_text = "\n".join([f"• **{key}**: {msg}" for key, msg in na.items()])
        st.warning(f"**검토 불가 항목**\n\n{_na_text}")

