"""
1방향 슬래브 구조설계 엔진 (KDS 41 20 00)

1m 폭 고정단 보로 모델링하여 휨/전단/처짐/배근을 설계합니다.
경간: L_short (단변 방향), 두께: t_slab (calculation_manager에서 결정)
"""
import numpy as np


# ── 슬래브용 철근 규격 (D10 ~ D16) ─────────────────────────────────────
SLAB_REBAR_SPECS = {
    "D10": {"diameter": 9.53,  "area": 71.33},
    "D13": {"diameter": 12.7,  "area": 126.7},
    "D16": {"diameter": 15.9,  "area": 198.6},
}
SLAB_REBAR_SIZES = ["D10", "D13", "D16"]


class SlabAnalyzer:
    """1방향 슬래브 구조설계 (1m 폭 고정단 스트립)"""

    def __init__(self, L_slab, t_slab, DL_area, LL_area, fc_k, fy):
        """
        Args:
            L_slab:  슬래브 경간 = L_short (mm) — 내부에서 m 변환
            t_slab:  슬래브 두께 (mm) — calculation_manager에서 결정
            DL_area: 추가 마감하중 (kN/m²), 슬래브 자중 제외
            LL_area: 활하중 (kN/m²)
            fc_k:    콘크리트 압축강도 (MPa)
            fy:      철근 항복강도 (MPa)
        """
        self.L_slab = L_slab / 1000.0  # mm → m
        self.t_slab = t_slab           # mm
        self.b_strip = 1000.0          # mm (1m 스트립, 항상 고정)
        self.DL_area = DL_area
        self.LL_area = LL_area
        self.fc_k = fc_k
        self.fy = fy

        # 슬래브 피복두께 (KDS 41 20 50 — 옥내 슬래브)
        self.cover = 20.0  # mm
        # 경계조건 (처짐 면제 두께 판정용, 기본값: 양단 연속)
        self.boundary_condition = 'both_continuous'

        self._calculate_loads()

    # ─────────────────────────────────────────────────────────────────────
    # 하중 산정
    # ─────────────────────────────────────────────────────────────────────
    def _calculate_loads(self):
        """1m 스트립 하중 (kN/m²→kN/m)"""
        self.w_slab_self = (self.t_slab / 1000.0) * 24.0  # kN/m² (자중)

        # 1m 스트립이므로 kN/m² = kN/m
        self.w_DL_unfactored = self.w_slab_self + self.DL_area  # kN/m
        self.w_LL_unfactored = self.LL_area                      # kN/m

        self.w_DL_factored = 1.2 * self.w_DL_unfactored  # kN/m
        self.w_LL_factored = 1.6 * self.w_LL_unfactored  # kN/m

        # 계수하중 조합 (KDS 41 10 15: 1.2D + 1.6L)
        self.w_u = self.w_DL_factored + self.w_LL_factored

    # ─────────────────────────────────────────────────────────────────────
    # 부재력 산정 (고정단 보)
    # ─────────────────────────────────────────────────────────────────────
    def calculate_member_forces(self):
        """고정단 보(1m 스트립) 부재력"""
        L = self.L_slab  # m
        M_neg = self.w_u * L ** 2 / 12.0   # kN·m (지점부 부모멘트)
        M_pos = self.w_u * L ** 2 / 24.0   # kN·m (중앙부 정모멘트)
        V_max = self.w_u * L / 2.0         # kN

        x_steps = np.linspace(0, L, 100)
        SFD = V_max - self.w_u * x_steps
        BMD = -M_neg + V_max * x_steps - self.w_u * x_steps ** 2 / 2.0

        return {
            "M_neg": M_neg, "M_pos": M_pos, "V_max": V_max,
            "x_steps": x_steps, "SFD": SFD, "BMD": BMD,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 설계 파라미터 요약
    # ─────────────────────────────────────────────────────────────────────
    def get_design_parameters(self):
        return {
            "t_slab": self.t_slab,
            "L_slab": self.L_slab,  # m
            "b_strip": self.b_strip,
            "cover": self.cover,
            "w_slab_self": self.w_slab_self,
            "w_DL_unfactored": self.w_DL_unfactored,
            "w_LL_unfactored": self.w_LL_unfactored,
            "w_DL_factored": self.w_DL_factored,
            "w_LL_factored": self.w_LL_factored,
            "w_u": self.w_u,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 휨 설계 (KDS 41 20 20)
    # ─────────────────────────────────────────────────────────────────────
    def calculate_flexural_design(self, Mu):
        """
        슬래브 1m 스트립 휨 설계.
        beam_engine과 동일한 ε_t-φ 수렴 루프를 사용하되 슬래브 특화 사항 반영.

        Args:
            Mu: 계수 휨모멘트 (kN·m, 1m 폭 당)
        Returns:
            (As_req_mm2, warnings, detailed_steps)
        """
        warnings = []
        steps = {}

        b = self.b_strip   # 1000 mm
        h = self.t_slab    # mm
        fc_k = self.fc_k
        fy = self.fy

        Mu_Nmm = abs(Mu) * 1e6
        steps['Mu_Nmm'] = Mu_Nmm

        # 피복+주근반경(스터럽 없음): d_c = cover + d_b/2
        # 1패스: D10 가정으로 초기 추정
        _db_init = 9.53  # D10
        d_c = self.cover + _db_init / 2.0
        d = h - d_c
        steps['d_c'] = d_c
        steps['d'] = d

        if d <= 0:
            warnings.append("경고: 유효깊이(d)가 0 이하. 슬래브 두께를 확인하세요.")
            return 0.0, warnings, steps

        # β₁ (KDS 41 20 20 4.1.1)
        if fc_k <= 28:
            beta1 = 0.85
        else:
            beta1 = max(0.65, 0.85 - 0.05 / 7.0 * (fc_k - 28))
        steps['beta1'] = beta1

        epsilon_cu = 0.003
        phi = 0.85  # 초기값 (인장지배 가정)

        # φ-ε_t 수렴 루프
        discriminant = 1.0
        rho_req = 0.0
        _phi_iter = 0
        for _phi_iter in range(10):
            Mn_Nmm = Mu_Nmm / phi
            Rn = Mn_Nmm / (b * d ** 2)
            discriminant = 1.0 - (2.0 * Rn) / (0.85 * fc_k)
            if discriminant < 0:
                break

            rho_req = (0.85 * fc_k / fy) * (1.0 - np.sqrt(discriminant))

            As_iter = rho_req * b * d
            a_iter = (As_iter * fy) / (0.85 * fc_k * b)
            c_iter = a_iter / beta1
            eps_t = epsilon_cu * (d - c_iter) / c_iter if c_iter > 0 else 0.005

            if eps_t >= 0.005:
                phi_new = 0.85
            elif eps_t <= 0.002:
                phi_new = 0.65
            else:
                phi_new = 0.65 + 0.20 * (eps_t - 0.002) / 0.003

            if abs(phi_new - phi) < 1e-4:
                phi = phi_new
                break
            phi = phi_new

        steps['phi'] = phi
        steps['phi_iters'] = _phi_iter + 1
        steps['discriminant'] = discriminant

        if discriminant < 0:
            warnings.append("오류: 슬래브 단면이 모멘트를 지지할 수 없습니다. t_slab을 증가시키세요.")
            return 0.0, warnings, steps

        steps['rho_req_calculated'] = rho_req

        # 최소 철근비 — 수축·온도 철근비만 적용 (KDS 41 20 20)
        # 슬래브는 보의 휨 최소 철근비(0.25√fck/fy, 1.4/fy)를 적용하지 않음
        if fy >= 400:
            rho_min = 0.0018
        elif fy <= 300:
            rho_min = 0.0020
        else:
            rho_min = 0.0020 - 0.0002 * (fy - 300.0) / 100.0

        steps['rho_min'] = rho_min

        if rho_req < rho_min:
            rho_req = rho_min
            warnings.append(f"정보: 최소 철근비({rho_min:.4f}) 적용됨.")
        steps['rho_req_final'] = rho_req

        As = rho_req * b * d
        steps['As_calculated'] = As

        # 최종 ε_t 재계산
        a = (As * fy) / (0.85 * fc_k * b)
        c = a / beta1
        epsilon_t = epsilon_cu * (d - c) / c if c > 0 else 0.005
        steps['a'] = a
        steps['c'] = c
        steps['epsilon_t'] = epsilon_t

        if epsilon_t < 0.004:
            warnings.append(f"경고: ε_t={epsilon_t:.4f} < 0.004 — 슬래브 두께를 증가시키세요.")

        return As, warnings, steps

    # ─────────────────────────────────────────────────────────────────────
    # 배근 상세 — 간격 기반 ("D10@200")
    # ─────────────────────────────────────────────────────────────────────
    def calculate_rebar_detailing(self, As_req):
        """
        1m 폭 당 소요 As를 만족하는 최소 규격·간격 조합을 탐색.
        출력 형태: "D10@200" (beam의 "5-D22" 개수 기반과 다름)

        Args:
            As_req: 소요 철근량 (mm²/m)
        Returns:
            (rebar_string, As_provided, warnings, detailed_steps)
        """
        warnings = []
        steps = {}
        steps['As_req'] = As_req

        if As_req <= 0:
            return "불필요", 0.0, warnings, steps

        s_max = min(3.0 * self.t_slab, 450.0)  # KDS 41 20 20 최대 간격
        steps['s_max'] = s_max

        for size_name in SLAB_REBAR_SIZES:
            spec = SLAB_REBAR_SPECS[size_name]
            A_b = spec["area"]
            d_b = spec["diameter"]

            # 소요 간격: A_b / (As_req / 1000) × 1000 = 1000 × A_b / As_req
            s_req = 1000.0 * A_b / As_req
            # 25mm 단위 내림 (시공 실용)
            s_rounded = max(np.floor(s_req / 25.0) * 25.0, 100.0)
            s_rounded = float(s_rounded)

            steps[f's_req_{size_name}'] = s_req
            steps[f's_rounded_{size_name}'] = s_rounded

            if s_rounded <= s_max and s_rounded >= 100.0:
                As_provided = 1000.0 * A_b / s_rounded
                # As_provided가 소요량 이상인 경우에만 채택
                if As_provided >= As_req:
                    rebar_string = f"{size_name}@{int(s_rounded)}"
                    steps['rebar_string'] = rebar_string
                    steps['As_provided'] = As_provided
                    steps['selected_size'] = size_name
                    steps['selected_spacing'] = s_rounded
                    steps['selected_diameter'] = d_b
                    return rebar_string, As_provided, warnings, steps

        # 폴백: D16@100 (가장 촘촘)
        warnings.append("경고: D16@100으로도 부족합니다. t_slab 증가를 검토하세요.")
        As_provided = 1000.0 * SLAB_REBAR_SPECS["D16"]["area"] / 100.0
        rebar_string = "D16@100"
        steps['rebar_string'] = rebar_string
        steps['As_provided'] = As_provided
        steps['selected_size'] = "D16"
        steps['selected_spacing'] = 100.0
        steps['selected_diameter'] = 15.9
        return rebar_string, As_provided, warnings, steps

    # ─────────────────────────────────────────────────────────────────────
    # 균열 제어 검토 (KDS 14 20 50 — 슬래브 간접균열제어)
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def calculate_crack_control(rebar_string, cover, fy, exposure='dry'):
        """
        슬래브 균열 제어 검토 — 간격 기반 배근의 최대 간격 제한.

        Parameters
        ----------
        rebar_string : str   예: 'D13@125'
        cover        : float 피복두께 (mm)
        fy           : float 철근 항복강도 (MPa)
        exposure     : str   'dry' / 'other'

        Returns
        -------
        dict  {ok, s_actual, s_max, steps}
        """
        if not rebar_string or '@' not in rebar_string:
            return {'ok': True, 's_actual': 0, 's_max': 0, 'steps': {}}

        spacing = float(rebar_string.split('@')[1])
        s_actual = spacing  # 슬래브는 간격 = 철근 중심 간격

        fs = (2.0 / 3.0) * fy
        k_cr = 280.0 if exposure == 'dry' else 210.0
        cc = cover

        s_limit_1 = 380.0 * (k_cr / fs) - 2.5 * cc
        s_limit_2 = 300.0 * (k_cr / fs)
        s_max = min(s_limit_1, s_limit_2)

        ok = s_actual <= s_max
        steps = {
            'cc': cc, 'fs': round(fs, 1), 'k_cr': k_cr,
            's_actual': round(s_actual, 1),
            's_limit_1': round(s_limit_1, 1),
            's_limit_2': round(s_limit_2, 1),
            's_max': round(s_max, 1),
        }
        return {'ok': ok, 's_actual': round(s_actual, 1),
                's_max': round(s_max, 1), 'steps': steps}

    # ─────────────────────────────────────────────────────────────────────
    # 전단 검토
    # ─────────────────────────────────────────────────────────────────────
    def calculate_shear_check(self, V_max, d_b_actual=None, w_u=None):
        """
        슬래브 전단 검토 (콘크리트만으로 부담, 스터럽 없음).

        Args:
            V_max: 계수 전단력 (kN) — 지점면 최대전단력
            d_b_actual: 실제 배근된 철근 직경 (mm), None이면 D10(9.53) 가정
            w_u: 계수 등분포하중 (kN/m), 전달 시 위험단면(d) 전단력 적용
        Returns:
            (ok, warnings, detailed_steps)
        """
        warnings = []
        steps = {}

        b = self.b_strip  # 1000 mm
        # 유효깊이: 실제 배근 철근경 기준
        d_b = d_b_actual if d_b_actual is not None else 9.53
        d = self.t_slab - self.cover - d_b / 2.0
        phi = 0.75

        steps['b'] = b
        steps['d'] = d
        steps['phi'] = phi

        # 위험단면 전단력 (KDS 41 20 22: 지점면에서 d 떨어진 곳)
        steps['V_max_face'] = abs(V_max)
        if w_u is not None and w_u > 0:
            d_m = d / 1000.0  # mm → m
            V_critical = abs(V_max) - w_u * d_m
            steps['V_at_d'] = V_critical
            steps['d_critical_m'] = d_m
        else:
            V_critical = abs(V_max)

        # Vc = (1/6)·√fck·b·d (N)
        Vc_N = (1.0 / 6.0) * np.sqrt(self.fc_k) * b * d
        phi_Vc_N = phi * Vc_N
        Vu_N = V_critical * 1000.0  # kN → N

        steps['Vc_kN'] = Vc_N / 1000.0
        steps['phi_Vc_kN'] = phi_Vc_N / 1000.0
        steps['Vu_kN'] = V_critical

        ok = Vu_N <= phi_Vc_N
        steps['ok'] = ok

        if not ok:
            warnings.append(
                f"경고: Vu={Vu_N/1000:.1f}kN > φVc={phi_Vc_N/1000:.1f}kN — "
                "슬래브 두께(t_slab)를 증가시키세요."
            )
        else:
            _ratio = Vu_N / phi_Vc_N if phi_Vc_N > 0 else 0
            steps['ratio'] = _ratio

        return ok, warnings, steps

    # ─────────────────────────────────────────────────────────────────────
    # 처짐 검토 (Branson Ie — beam_engine과 동일 로직, 슬래브 특화)
    # ─────────────────────────────────────────────────────────────────────
    def calculate_deflection(self, As_provided_bot, As_provided_top=0.0, d_b_bot=9.53):
        """
        KDS 41 20 30 4.3 처짐 검토 (1m 스트립, 고정단).
        최소두께(L/20) 충족 시 면제 가능 여부도 판정.

        Args:
            As_provided_bot: 하부근 면적 (mm²/m)
            As_provided_top: 상부근 면적 (mm²/m)
        Returns:
            처짐 상세 결과 dict
        """
        steps = {}
        b = self.b_strip    # 1000 mm
        h = self.t_slab     # mm
        L = self.L_slab * 1000.0  # mm
        fc_k = self.fc_k

        # ── 1. 재료 특성 ──────────────────────────────────────────────
        Ec = 8500.0 * (fc_k + 4.0) ** (1.0 / 3.0)  # MPa
        fr = 0.63 * np.sqrt(fc_k)                    # MPa (파괴계수)
        Es = 200_000.0
        n = Es / Ec
        steps.update({'Ec': Ec, 'fr': fr, 'n': n})

        # ── 2. 총단면 특성 ────────────────────────────────────────────
        Ig = b * h ** 3 / 12.0
        yt = h / 2.0
        M_cr = fr * Ig / yt  # N·mm
        steps.update({'Ig': Ig, 'yt': yt, 'M_cr_Nmm': M_cr, 'M_cr_kNm': M_cr / 1e6})

        # ── 3. 균열 단면 2차모멘트 Icr ────────────────────────────────
        d_b = d_b_bot  # 실제 배근 철근경 사용 (기본값 D10=9.53)
        d_c = self.cover + d_b / 2.0
        d = h - d_c
        d_prime = d_c

        rho = max(As_provided_bot / (b * d), 1e-6)
        k_v = np.sqrt(2 * n * rho + (n * rho) ** 2) - n * rho
        x_cr = k_v * d

        # Icr_mid: 중앙부 — 하부근이 인장근
        Icr_mid = b * x_cr ** 3 / 3.0 + n * As_provided_bot * (d - x_cr) ** 2
        if As_provided_top > 0 and x_cr > d_prime:
            Icr_mid += (n - 1) * As_provided_top * (x_cr - d_prime) ** 2

        # Icr_sup: 지점부 — 상부근이 인장근 (KDS 41 20 30)
        if As_provided_top > 0:
            rho_sup = max(As_provided_top / (b * d), 1e-6)
            k_sup = np.sqrt(2 * n * rho_sup + (n * rho_sup) ** 2) - n * rho_sup
            x_cr_sup = k_sup * d
            Icr_sup = b * x_cr_sup ** 3 / 3.0 + n * As_provided_top * (d - x_cr_sup) ** 2
            if As_provided_bot > 0 and x_cr_sup > d_prime:
                Icr_sup += (n - 1) * As_provided_bot * (x_cr_sup - d_prime) ** 2
        else:
            Icr_sup = Icr_mid  # 상부근 없으면 동일

        steps.update({'d': d, 'rho': rho, 'x_cr': x_cr,
                      'Icr': Icr_mid, 'Icr_sup': Icr_sup})

        # ── 4. 서비스 하중 ────────────────────────────────────────────
        w_DL = self.w_DL_unfactored  # kN/m = N/mm 환산 시 동일 값
        w_LL = self.w_LL_unfactored
        w_total = w_DL + w_LL
        steps.update({'w_DL': w_DL, 'w_LL': w_LL, 'w_total': w_total})

        # ── 5. 서비스 모멘트 (고정단) ─────────────────────────────────
        M_a_sup = w_total * L ** 2 / 12.0  # N·mm
        M_a_mid = w_total * L ** 2 / 24.0
        M_a_DL_sup = w_DL * L ** 2 / 12.0
        M_a_DL_mid = w_DL * L ** 2 / 24.0
        steps.update({'M_a_kNm': M_a_sup / 1e6, 'M_a_DL_kNm': M_a_DL_sup / 1e6,
                      'M_a_mid_kNm': M_a_mid / 1e6})

        # ── 6. 유효 단면 2차모멘트 Ie (Branson) ───────────────────────
        def compute_Ie(M_val, Icr_val):
            if M_val <= 0 or M_val <= M_cr:
                return Ig
            ratio = min(M_cr / M_val, 1.0)
            return min(ratio ** 3 * Ig + (1.0 - ratio ** 3) * Icr_val, Ig)

        Ie_sup = compute_Ie(M_a_sup, Icr_sup)
        Ie_mid = compute_Ie(M_a_mid, Icr_mid)
        Ie_total = 0.70 * Ie_mid + 0.30 * Ie_sup

        Ie_DL_sup = compute_Ie(M_a_DL_sup, Icr_sup)
        Ie_DL_mid = compute_Ie(M_a_DL_mid, Icr_mid)
        Ie_DL = 0.70 * Ie_DL_mid + 0.30 * Ie_DL_sup

        steps.update({'Ie_total': Ie_total, 'Ie_DL': Ie_DL,
                      'cracked': M_a_sup > M_cr})

        # ── 7. 단기(즉시) 처짐 δ = wL⁴/(384·Ec·Ie) ──────────────────
        delta_total_i = w_total * L ** 4 / (384.0 * Ec * Ie_total)
        delta_DL_i = w_DL * L ** 4 / (384.0 * Ec * Ie_DL)
        delta_LL_i = max(delta_total_i - delta_DL_i, 0.0)
        steps.update({'delta_total_i': delta_total_i,
                      'delta_DL_i': delta_DL_i,
                      'delta_LL_i': delta_LL_i})

        # ── 8. 장기처짐 λ_Δ·(δ_DL + α·δ_LL) ────────────────────────
        xi = 2.0  # 60개월 이상
        rho_prime = As_provided_top / (b * d) if As_provided_top > 0 else 0.0
        lambda_delta = xi / (1.0 + 50.0 * rho_prime)
        alpha_sus = 0.25
        delta_long = lambda_delta * (delta_DL_i + alpha_sus * delta_LL_i)
        steps.update({'xi': xi, 'rho_prime': rho_prime,
                      'lambda_delta': lambda_delta, 'delta_long': delta_long})

        # ── 9. 허용처짐 ──────────────────────────────────────────────
        delta_allow_LL = L / 360.0
        delta_allow_total = L / 240.0
        delta_allow_strict = L / 480.0
        delta_check = delta_long + delta_LL_i
        steps.update({'delta_check': delta_check,
                      'delta_allow_LL': delta_allow_LL,
                      'delta_allow_total': delta_allow_total,
                      'delta_allow_strict': delta_allow_strict})

        # ── 10. 판정 ─────────────────────────────────────────────────
        check_LL = delta_LL_i <= delta_allow_LL
        check_total = delta_check <= delta_allow_total
        ok = check_LL and check_total
        steps.update({'check_LL': check_LL, 'check_total': check_total, 'ok': ok})

        steps['ratio_LL'] = delta_LL_i / delta_allow_LL if delta_allow_LL > 0 else None
        steps['ratio_total'] = delta_check / delta_allow_total if delta_allow_total > 0 else None

        # 최소두께 면제 판정 (KDS 41 20 30 Table 4.3-1)
        # 양단 연속: L/28, 1단 연속: L/24, 단순 지지: L/20, 캔틸레버: L/10
        _bc = getattr(self, 'boundary_condition', 'both_continuous')
        _h_min_map = {'simple': 20.0, 'one_continuous': 24.0,
                      'both_continuous': 28.0, 'cantilever': 10.0}
        h_min_exempt = L / _h_min_map.get(_bc, 28.0)
        steps['h_min_exempt'] = h_min_exempt
        steps['min_thickness_exempt'] = self.t_slab >= h_min_exempt

        return steps
