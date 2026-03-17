import numpy as np

class ColumnAnalyzer:
    # 1. __init__ 에 Pu, Mux, Muy 추가 (양방향 휨모멘트 지원)
    def __init__(self, h_column, b_beam_x, b_beam_y, fc_k, fy, Pu=0, Mu=0,
                 Mux=None, Muy=None,
                 c_column_override=None, beta_d=None):
        self.h_column = h_column
        self.b_beam_x = b_beam_x
        self.b_beam_y = b_beam_y
        self.fc_k = fc_k
        self.fy = fy

        # 외부에서 입력받은 하중 (단위: kN, kN.m)
        self.Pu = Pu

        # 양방향 휨모멘트: Mux, Muy가 모두 주어지면 SRSS 조합으로 설계 Mu 산정
        # 그렇지 않으면 기존 Mu 단일값 사용
        if Mux is not None and Muy is not None:
            self.Mux = float(Mux)
            self.Muy = float(Muy)
            self.Mu  = float(np.sqrt(Mux**2 + Muy**2))  # SRSS 조합
        else:
            self.Mux = None
            self.Muy = None
            self.Mu  = float(Mu)

        # 기둥 단면 자동 결정 (정방형 기둥 가정)
        # c = max(b_x, b_y) + 100: 접합부 철근 정착을 위해 보보다 크게 설정
        # 400mm 고정 최솟값 제거: 세장비·P-M 검토가 구조적 최소 치수를 결정
        self.c_column_raw = max(self.b_beam_x, self.b_beam_y) + 100
        self.c_column_from_beam = self._round_up_to_50(self.c_column_raw)

        if c_column_override is not None:
            self.c_column = float(c_column_override)
        else:
            self.c_column = self.c_column_from_beam

        self.Ag = self.c_column * self.c_column # 기둥 총 단면적 (mm^2)
        self._beta_d_input = beta_d  # None이면 0.6 폴백 (KDS 41 20 40)
        self.column_design_steps = {}

    def _round_up_to_50(self, value): 
        return np.ceil(value / 50) * 50 

    def get_column_dimensions(self):
        return {
            'c_column_raw': self.c_column_raw,
            'c_column_from_beam': self.c_column_from_beam,
            'c_column': self.c_column,
            'Ag': self.Ag
        }

    def calculate_slenderness(self):
        """
        KDS 41 20 40 세장비 검토 및 모멘트 증폭 (비횡구속 프레임 가정 안함 — 횡구속 프레임 δ_ns).

        - k = 1.0 (보수적: 핀-핀 가정)
        - r = 0.3 * c (정방형 단면)
        - λ = k * l_u / r
          ≤ 22   → 단주 (short), 증폭 없음
          22~100 → 세장주 (slender), δ_ns 증폭
          > 100  → 설계 불가 (prohibited), 단면 증가 필요
        """
        k = 1.0
        l_u = float(self.h_column)          # 비지지 길이 (mm)
        r   = 0.3 * self.c_column           # 회전반경 (mm)
        lambda_ratio = k * l_u / r

        Ec  = 8500.0 * (self.fc_k + 4.0) ** (1.0 / 3.0)   # MPa
        Ig  = self.c_column ** 4 / 12.0                     # mm⁴
        beta_d = self._beta_d_input if self._beta_d_input is not None else 0.6  # KDS 41 20 40
        EI  = 0.4 * Ec * Ig / (1.0 + beta_d)               # N·mm²
        Pc_N  = np.pi ** 2 * EI / (k * l_u) ** 2           # N (임계좌굴하중)
        Pc_kN = Pc_N / 1000.0                               # kN
        Cm  = 1.0                                           # 균일모멘트 보수적 가정
        Pu_N = self.Pu * 1000.0                             # kN → N

        if lambda_ratio <= 22:
            category  = 'short'
            stable    = True
            delta_ns  = 1.0
            ok        = True
        elif lambda_ratio <= 100:
            category = 'slender'
            stable   = (Pu_N < 0.75 * Pc_N)
            if stable:
                denom    = 1.0 - Pu_N / (0.75 * Pc_N)
                delta_ns = max(Cm / denom, 1.0)
                ok       = True
            else:
                delta_ns = None
                ok       = False   # 좌굴 불안정 → 단면 증가 필요
        else:
            category = 'prohibited'
            stable   = False
            delta_ns = None
            ok       = False

        Mu_magnified = (delta_ns * self.Mu) if delta_ns is not None else None
        # 방향별 증폭값 (#58)
        Mux_magnified = (delta_ns * self.Mux) if (delta_ns is not None and self.Mux is not None) else None
        Muy_magnified = (delta_ns * self.Muy) if (delta_ns is not None and self.Muy is not None) else None

        return {
            'k': k,
            'l_u': l_u,
            'r': r,
            'lambda_ratio': lambda_ratio,
            'category': category,
            'Ec': Ec,
            'Ig': Ig,
            'beta_d': beta_d,
            'EI': EI,
            'Pc_kN': Pc_kN,
            'Cm': Cm,
            'delta_ns': delta_ns,
            'Mu_original': self.Mu,
            'Mu_magnified': Mu_magnified,
            'Mux_original': self.Mux,
            'Muy_original': self.Muy,
            'Mux_magnified': Mux_magnified,
            'Muy_magnified': Muy_magnified,
            'stable': stable,
            'ok': ok,
        }

    def calculate_member_forces_arrays(self):
        # 기둥 높이(mm) → m 단위로 변환 후 100개 구간으로 나눔 (입력 단위 mm 고정)
        h_m = self.h_column / 1000.0
        z_steps = np.linspace(0, h_m, 100)

        # AFD: 기둥 전체에서 일정한 압축력(Pu)이 작용한다고 가정
        afd_vals = np.full_like(z_steps, self.Pu)

        # BMD: 강접합 - 상하 모두 보가 연결되어 반곡점이 기둥 중앙에 형성
        # z=0에서 -Mu, z=H/2에서 0, z=H에서 +Mu (역대칭 분포)
        bmd_vals = self.Mu * (2.0 * z_steps / h_m - 1.0)

        return {
            'z_steps': z_steps,
            'AFD': afd_vals,
            'BMD': bmd_vals
        }
    
    # 2. 더미 코드가 있던 하중 계산 로직은 입력값을 그대로 저장하도록 수정 
    def calculate_axial_load_and_moment(self): 
        self.column_design_steps['Pu'] = self.Pu 
        self.column_design_steps['Mu'] = self.Mu 
        return { 
            'Pu': self.Pu, 
            'Mu': self.Mu 
        } 

    # 3. KDS 41 20 기준 P-M 상관도 기반 주철근 설계 로직
    def calculate_rebar_design(self): 
        rebar_specs = { 
            "D10": {"diameter": 9.53, "area": 71.33}, 
            "D13": {"diameter": 12.7, "area": 126.7}, 
            "D16": {"diameter": 15.9, "area": 198.6}, 
            "D19": {"diameter": 19.1, "area": 286.5},
            "D22": {"diameter": 22.2, "area": 387.1}, 
            "D25": {"diameter": 25.4, "area": 506.7}, 
            "D29": {"diameter": 28.6, "area": 642.4}, 
            "D32": {"diameter": 31.8, "area": 794.2}, 
            "D35": {"diameter": 35.8, "area": 1006.0}, 
        } 
        
        # 1) 최소 편심 및 설계 모멘트 보정
        e_min = 15 + 0.03 * self.c_column  # mm
        is_min_ecc_applied = False
        Mu_design = self.Mu

        if self.Pu > 0:
            e_actual = (self.Mu * 1000 / self.Pu)  # mm
            if e_actual < e_min:
                Mu_design = (self.Pu * e_min) / 1000.0  # kN.m
                is_min_ecc_applied = True
        else:
            # Pu=0: 순수 휨 상태 — 편심 개념 미적용, 최소편심 보정 건너뜀
            e_actual = None

        # 2) P-M 상관도 검토 루프 (철근량 및 단면 크기 결정)
        # D22→D25→D29→D32 순서로 최적 규격 자동 탐색 (n_col > 12 시 다음 규격으로 상향)
        rebar_sizes_col    = ["D22", "D25", "D29", "D32"]
        _size_idx          = 0
        rebar_type_col     = rebar_sizes_col[_size_idx]
        rebar_area_col     = rebar_specs[rebar_type_col]['area']
        rebar_diameter_col = rebar_specs[rebar_type_col]['diameter']

        # 초기 철근 개수 (최소 4개)
        n_col = 4
        phi_Pn_max = 0
        phi_Pn_b = 0
        phi_Mn_b = 0
        phi_Mn_o = 0

        _pm_max_iter = 60  # 무한 루프 방지 (규격 4종 × n 탐색 최대 15단계 여유)
        _pm_iter = 0
        safe = False
        _fit_ok     = False   # 배근 적합성 결과 (루프 종료 후 참조용 초기값)
        _n_per_side = 2       # 한 변 최대 철근 수 초기값
        while not safe:
            _pm_iter += 1
            if _pm_iter > _pm_max_iter:
                # 수렴 실패: 마지막 상태로 강제 종료
                break

            As_total = n_col * rebar_area_col
            rho = As_total / self.Ag

            # 철근비 제한 (1% ~ 8%)
            if rho > 0.08:
                # 8% 초과 시 단면 크기 증가 및 재시작
                self.c_column += 50
                self.Ag = self.c_column * self.c_column
                n_col = 4
                continue
            
            # P-M 주요 점 계산 (3점 포락선 모델)
            # 압축지배(점 A·B) φ=0.65, 인장지배(점 C) φ=0.85 (KDS 41 20 20 4.2.2)
            phi_comp = 0.65  # 압축지배 강도감소계수 (띠철근)
            phi_tens = 0.85  # 인장지배 강도감소계수
            beta1 = max(0.85 - 0.05 / 7.0 * (self.fc_k - 28), 0.65) if self.fc_k > 28 else 0.85

            # C5 수정: cover_approx를 실제 철근 직경으로 계산 (구 65mm 하드코딩 제거)
            # cover(40) + 띠철근 직경(D10=9.53) + 주근 반경
            _col_cover = 40.0
            _tie_dia_c = 9.53   # D10 기준 (가장 많이 쓰이는 띠철근)
            cover_approx = _col_cover + _tie_dia_c + rebar_diameter_col / 2.0
            d_eff   = self.c_column - cover_approx   # 인장측 철근 중심까지 유효깊이
            d_prime = cover_approx                   # 압축측 철근 중심 깊이

            # 점 A: 순수 압축 (KDS 41 20 20 4.2.1)
            # Po = 0.85*fck*(Ag-Ast) + fy*Ast, φPn_max = 0.80*φ*Po
            Pn_max = 0.85 * self.fc_k * (self.Ag - As_total) + self.fy * As_total
            phi_Pn_max = 0.80 * phi_comp * Pn_max / 1000.0  # kN

            # 점 B: 균형 파괴 (Balanced Point)
            # c_b = εcu*Es / (εcu*Es + fy) * d_eff  (εcu=0.003, Es=200,000)
            c_b = (600.0 / (600.0 + self.fy)) * d_eff
            a_b = beta1 * c_b

            # 대칭 배근 가정 (As' = As = As_total/2)
            As_half = As_total / 2.0
            h_half  = self.c_column / 2.0

            # 균형점 압축철근 응력 (c_b > d_prime 이므로 압축 상태 확인)
            fs_prime = min(600.0 * (c_b - d_prime) / c_b, self.fy)
            # NOTE: 인장철근 응력 = fy 고정 (보수적 가정, c≤c_b이면 εs≥εy이므로 안전측)
            Pn_b = (0.85 * self.fc_k * a_b * self.c_column
                    + As_half * fs_prime - As_half * self.fy)
            Mn_b = (0.85 * self.fc_k * a_b * self.c_column * (h_half - a_b / 2.0)
                    + As_half * fs_prime * (h_half - d_prime)
                    + As_half * self.fy  * (d_eff  - h_half))

            # 점 B: φ = 0.65 (균형파괴 εt = εy, 압축지배 경계)
            phi_Pn_b = phi_comp * Pn_b / 1000.0  # kN
            phi_Mn_b = phi_comp * Mn_b / 1e6      # kN·m

            # 점 C: 순수 휨 — Pn=0이 되는 c_o를 이분법으로 산정 (C6 수정)
            # 평형: 0.85·fck·β1·c·b + As'·fs'(c) - As·fy = 0
            # (대칭 배근: As'=As=As_half, 인장철근은 항복 가정)
            _c_lo, _c_hi = 1e-6, self.c_column
            for _ in range(60):
                _c_mid = (_c_lo + _c_hi) / 2.0
                _fs_c  = min(max(600.0 * (_c_mid - d_prime) / _c_mid, -self.fy), self.fy)
                _Pn_c  = (0.85 * self.fc_k * beta1 * _c_mid * self.c_column
                          + As_half * _fs_c - As_half * self.fy)
                if _Pn_c < 0.0:
                    _c_lo = _c_mid
                else:
                    _c_hi = _c_mid
                if _c_hi - _c_lo < 0.01:
                    break
            c_o  = (_c_lo + _c_hi) / 2.0
            a_o  = beta1 * c_o
            fs_o = min(max(600.0 * (c_o - d_prime) / c_o, -self.fy), self.fy)
            Mn_o = (0.85 * self.fc_k * a_o * self.c_column * (h_half - a_o / 2.0)
                    + As_half * fs_o  * (h_half - d_prime)
                    + As_half * self.fy * (d_eff - h_half))
            phi_Mn_o = phi_tens * Mn_o / 1e6  # kN·m (φ=0.85, 인장지배)

            # εy = fy/Es: φ 전이구간 하한 변형률 (fy 의존)
            eps_y = self.fy / 200000.0

            # 3) 하중 포인트가 포락선 내부에 있는지 확인
            # A-B 구간: 직선 근사 (압축지배, 볼록성 무시 가능)
            # B-C 구간: c 분할 + εt 기반 φ 보간 (C3 수정)
            if self.Pu <= phi_Pn_max:
                if self.Pu >= phi_Pn_b:
                    # Line A-B: 직선
                    M_limit = (phi_Pn_max - self.Pu) * (phi_Mn_b / (phi_Pn_max - phi_Pn_b))
                    if Mu_design <= M_limit: safe = True
                else:
                    # B-C 구간: c를 c_b → 0까지 50분할, 각 점에서 εt → φ 보간 (C3)
                    N_bc   = 50
                    c_vals = np.linspace(c_b, 1e-6, N_bc + 1)
                    P_prev = phi_Pn_b
                    M_prev = phi_Mn_b
                    M_limit = phi_Mn_o  # 기본값: C점 (Pu ≈ 0)
                    for c_i in c_vals[1:]:
                        a_i = beta1 * c_i
                        # C4 수정: 압축측 철근 응력 — c < d' 시 인장 허용 [-fy, fy]
                        fs_p_i = min(max(600.0 * (c_i - d_prime) / c_i, -self.fy), self.fy)
                        # 공칭 압축력 및 모멘트
                        Pn_i = (0.85 * self.fc_k * a_i * self.c_column
                                + As_half * fs_p_i - As_half * self.fy)
                        Mn_i = (0.85 * self.fc_k * a_i * self.c_column * (h_half - a_i / 2.0)
                                + As_half * fs_p_i * (h_half - d_prime)
                                + As_half * self.fy  * (d_eff  - h_half))
                        # C3 수정: εt → φ 보간 (KDS 41 20 20 4.2.2)
                        eps_t_i = 0.003 * max(d_eff - c_i, 0.0) / c_i
                        if eps_t_i >= 0.005:
                            phi_i = phi_tens
                        elif eps_t_i <= eps_y:
                            phi_i = phi_comp
                        else:
                            phi_i = (phi_comp
                                     + (phi_tens - phi_comp) * (eps_t_i - eps_y)
                                     / (0.005 - eps_y))
                        P_cur = phi_i * Pn_i / 1000.0
                        M_cur = phi_i * Mn_i / 1e6
                        # Pu가 [P_cur, P_prev] 구간에 있으면 선형 보간
                        if P_cur <= self.Pu <= P_prev:
                            t = ((self.Pu - P_cur) / (P_prev - P_cur)
                                 if P_prev != P_cur else 0.0)
                            M_limit = M_cur + t * (M_prev - M_cur)
                            break
                        P_prev = P_cur
                        M_prev = M_cur
                    if Mu_design <= M_limit: safe = True
            
            # 안전하지 않거나 철근비 1% 미만이면 철근 추가 또는 규격 상향
            if not safe or rho < 0.01:
                if n_col > 12 and _size_idx < len(rebar_sizes_col) - 1:
                    # n이 12 초과 시 → 다음 규격으로 업그레이드 후 n=4 리셋
                    _size_idx          += 1
                    rebar_type_col      = rebar_sizes_col[_size_idx]
                    rebar_area_col      = rebar_specs[rebar_type_col]['area']
                    rebar_diameter_col  = rebar_specs[rebar_type_col]['diameter']
                    n_col = 4
                else:
                    n_col += 2
                safe = False  # 다시 검토
            else:
                # P-M 통과 → 배근 적합성 검토 (KDS 기준 최소 순간격)
                # 정방형 기둥: 한 변 최대 철근 수 = ceil(n_col/4) + 1 (모서리 포함)
                _n_per_side  = int(np.ceil(n_col / 4)) + 1
                _s_min_col   = max(40.0, 1.5 * rebar_diameter_col)  # 최소 순간격 (mm)
                _cover_col   = 40.0   # 주근 피복 (mm)
                _tie_dia_col = 9.53   # D10 띠철근 직경 (mm)
                # 가용 폭: 첫 철근 중심 ~ 마지막 철근 중심
                _avail_col = (self.c_column
                              - 2.0 * (_cover_col + _tie_dia_col + rebar_diameter_col / 2.0))
                # 필요 폭: (n_per_side - 1)개 간격 × (d_b + s_min)
                _req_col   = (_n_per_side - 1) * (rebar_diameter_col + _s_min_col)
                _fit_ok    = _avail_col >= _req_col

                if _fit_ok:
                    # Bresler 이축 휨 검토 (이축 모멘트 존재 시)
                    if (self.Mux is not None and self.Muy is not None
                            and self.Mux > 0 and self.Muy > 0 and self.Pu > 0):
                        _br = self._bresler_check(
                            self.Pu, self.Mux, self.Muy,
                            n_col * rebar_area_col, d_eff, d_prime, beta1,
                            phi_comp, phi_tens, eps_y)
                        if not _br['safe']:
                            # Bresler 불만족 → 철근 추가
                            if n_col > 12 and _size_idx < len(rebar_sizes_col) - 1:
                                _size_idx += 1
                                rebar_type_col = rebar_sizes_col[_size_idx]
                                rebar_area_col = rebar_specs[rebar_type_col]['area']
                                rebar_diameter_col = rebar_specs[rebar_type_col]['diameter']
                                n_col = 4
                            else:
                                n_col += 2
                            safe = False
                            continue
                    break  # P-M + 배근 적합성 + Bresler 모두 통과 → 확정
                else:
                    # 배근 불가 → 규격 상향 우선, 최대 규격이면 단면 증가
                    if _size_idx < len(rebar_sizes_col) - 1:
                        _size_idx          += 1
                        rebar_type_col      = rebar_sizes_col[_size_idx]
                        rebar_area_col      = rebar_specs[rebar_type_col]['area']
                        rebar_diameter_col  = rebar_specs[rebar_type_col]['diameter']
                        n_col = 4
                    else:
                        # D32에서도 배근 불가 → 단면 50mm 증가 (규격은 D32 유지, D22 재시작 안 함)
                        self.c_column      += 50
                        self.Ag             = self.c_column * self.c_column
                        n_col = 4
                    safe = False

        As_provided_col = n_col * rebar_area_col
        rebar_string_col = f"{n_col}-{rebar_type_col}"

        # ── P-M 포락선 다점 계산 (시각화용) ─────────────────────────────────
        # 중립축 c를 Pn=Pn_cap 경계부터 스윕 (flat-top 영역 포인트 낭비 방지)
        _c_sweep_lo = 1e-3                           # 순수인장 근사
        # φ 전이구간 경계 c 값: εt = 0.003*(d-c)/c → c = 0.003*d/(0.003+εt)
        _c_trans_hi = 0.003 * d_eff / (0.003 + eps_y)   # εt = eps_y (φ=0.65)
        _c_trans_lo = 0.003 * d_eff / (0.003 + 0.005)   # εt = 0.005 (φ=0.85)
        # Pn = 0.80·Pno(공칭캡)이 되는 c를 이분법으로 탐색 → 스윕 시작점
        _Pno = (0.85 * self.fc_k * (self.Ag - As_total) + self.fy * As_total)
        _Pn_cap_N = 0.80 * _Pno  # N 단위
        _c_bisect_lo, _c_bisect_hi = _c_trans_hi, self.c_column / beta1 * 2.0
        for _ in range(40):
            _c_mid = (_c_bisect_lo + _c_bisect_hi) / 2.0
            _a_mid = min(beta1 * _c_mid, self.c_column)
            _fsp_mid = min(max(600.0 * (_c_mid - d_prime) / _c_mid, -self.fy), self.fy)
            _fst_mid = min(max(600.0 * (d_eff - _c_mid) / _c_mid, -self.fy), self.fy)
            _Pn_mid = (0.85 * self.fc_k * _a_mid * self.c_column
                       + As_half * _fsp_mid - As_half * _fst_mid)
            if _Pn_mid > _Pn_cap_N:
                _c_bisect_hi = _c_mid
            else:
                _c_bisect_lo = _c_mid
        _c_sweep_hi = _c_bisect_hi  # Pn ≈ Pn_cap인 c (이 위는 flat-top)
        # 3구간 분할: 압축지배 40점 + φ전이 30점 + 인장지배 30점
        _c_zone1 = np.linspace(_c_sweep_hi, _c_trans_hi, 40, endpoint=False)  # 캡~균형점
        _c_zone2 = np.linspace(_c_trans_hi, _c_trans_lo, 30, endpoint=False)  # φ 전이구간
        _c_zone3 = np.linspace(_c_trans_lo, _c_sweep_lo, 30)                  # 인장지배
        _c_arr_vis = np.concatenate([_c_zone1, _c_zone2, _c_zone3])
        # 0.80φPn 상한 (KDS 41 20 20 — 우발편심 상한)
        _phi_Pn_cap = (0.80 * phi_comp
                       * (0.85 * self.fc_k * (self.Ag - As_total) + self.fy * As_total)
                       / 1000.0)   # kN

        _pm_P = []       # 설계강도 (φ 적용)
        _pm_M = []
        _pm_Pn = []      # 공칭강도 (φ 미적용, 시각화 비교용)
        _pm_Mn = []
        for _c_i in _c_arr_vis:
            _a_i   = min(beta1 * _c_i, self.c_column)
            # 압축측 철근 응력 [-fy, fy]
            _fsp_i = min(max(600.0 * (_c_i - d_prime) / _c_i, -self.fy), self.fy)
            # 인장측 철근 응력 (항복 상한)
            _fst_i = min(max(600.0 * (d_eff - _c_i) / _c_i, -self.fy), self.fy)

            _Pn_i = (0.85 * self.fc_k * _a_i * self.c_column
                     + As_half * _fsp_i - As_half * _fst_i)
            _Mn_i = (0.85 * self.fc_k * _a_i * self.c_column * (h_half - _a_i / 2.0)
                     + As_half * _fsp_i * (h_half - d_prime)
                     + As_half * _fst_i * (d_eff   - h_half))

            # 공칭강도 저장 (0.80·Pno 상한 — KDS 우발편심)
            _Pn_cap = 0.80 * (0.85 * self.fc_k * (self.Ag - As_total) + self.fy * As_total) / 1000.0
            _pm_Pn.append(min(_Pn_i / 1000.0, _Pn_cap))
            _pm_Mn.append(max(_Mn_i / 1e6, 0.0))

            _eps_ti = 0.003 * max(d_eff - _c_i, 0.0) / _c_i
            if   _eps_ti >= 0.005: _phi_i = phi_tens
            elif _eps_ti <= eps_y: _phi_i = phi_comp
            else:
                _phi_i = (phi_comp
                          + (phi_tens - phi_comp) * (_eps_ti - eps_y) / (0.005 - eps_y))

            _pm_P.append(min(_phi_i * _Pn_i / 1000.0, _phi_Pn_cap))
            _pm_M.append(max(_phi_i * _Mn_i / 1e6,    0.0))

        # 순수인장 점 추가 (P = -φt·fy·As, M = 0) — 순수인장 φ = 0.90 (KDS 41 20 20)
        _pm_P.append(-0.90 * self.fy * As_total / 1000.0)
        _pm_M.append(0.0)
        _pm_Pn.append(-self.fy * As_total / 1000.0)
        _pm_Mn.append(0.0)

        # 결과 저장
        self.column_design_steps.update({
            'As_req_col': As_total if rho >= 0.01 else 0.01 * self.Ag,
            'As_provided_col': As_provided_col,
            'rebar_string_col': rebar_string_col,
            'n_col': n_col,
            'rebar_type_col': rebar_type_col,
            'rebar_diameter_col': rebar_diameter_col,
            'phi_Pn_max': phi_Pn_max,
            'phi_Pn_b': phi_Pn_b,
            'phi_Mn_b': phi_Mn_b,
            'phi_Mn_o': phi_Mn_o,
            'Mu_design': Mu_design,
            'is_min_ecc_applied': is_min_ecc_applied,
            'e_min': e_min,
            'e_actual': e_actual,
            'rho': rho,
            'fit_ok': _fit_ok,
            'n_per_side': _n_per_side,
            'pm_curve_P': _pm_P,
            'pm_curve_M': _pm_M,
            'pm_nominal_P': _pm_Pn,
            'pm_nominal_M': _pm_Mn,
            'Pn_max': _Pn_cap,      # 공칭 상한 0.80·Pno (kN)
            'pm_safe': safe,        # P-M 포락선 내부 여부
        })
 
        # ── Bresler 이축 휨 검토 (Mux, Muy 모두 > 0일 때) ──────────────
        bresler = None
        if self.Mux is not None and self.Muy is not None and self.Mux > 0 and self.Muy > 0 and self.Pu > 0:
            bresler = self._bresler_check(
                self.Pu, self.Mux, self.Muy,
                As_provided_col, d_eff, d_prime, beta1,
                phi_comp, phi_tens, eps_y)
        self.column_design_steps['bresler'] = bresler

        return self.column_design_steps

    def _find_Pn_at_eccentricity(self, e_target, As_total, d_eff, d_prime, beta1):
        """주어진 편심 e(mm)에서 P-M 곡선상의 공칭 Pn(N)을 이분법으로 탐색."""
        As_half = As_total / 2.0
        h_half = self.c_column / 2.0
        c_lo, c_hi = 1e-3, self.c_column * 3.0

        for _ in range(60):
            c_mid = (c_lo + c_hi) / 2.0
            a_i = min(beta1 * c_mid, self.c_column)
            fs_p = min(max(600.0 * (c_mid - d_prime) / c_mid, -self.fy), self.fy)
            fs_t = min(max(600.0 * (d_eff - c_mid) / c_mid, -self.fy), self.fy)

            Pn = (0.85 * self.fc_k * a_i * self.c_column
                  + As_half * fs_p - As_half * fs_t)
            Mn = (0.85 * self.fc_k * a_i * self.c_column * (h_half - a_i / 2.0)
                  + As_half * fs_p * (h_half - d_prime)
                  + As_half * fs_t * (d_eff - h_half))

            if Pn <= 0:
                c_lo = c_mid
                continue
            e_calc = Mn / Pn  # mm
            if e_calc > e_target:
                c_lo = c_mid
            else:
                c_hi = c_mid
            if c_hi - c_lo < 0.01:
                break

        return max(Pn, 0.0)  # N

    def _bresler_check(self, Pu, Mux, Muy, As_total, d_eff, d_prime, beta1,
                       phi_comp, phi_tens, eps_y):
        """
        Bresler 역수하중법: 1/Pn = 1/Pnx + 1/Pny - 1/Pno

        Args:
            Pu:  계수 축력 (kN)
            Mux: X방향 계수 모멘트 (kN·m)
            Muy: Y방향 계수 모멘트 (kN·m)
        Returns:
            dict {safe, Pn_bresler, Pnx, Pny, Pno, phi_Pn, ratio, steps}
        """
        steps = {}

        # 편심 (mm 단위)
        Pu_N = Pu * 1000.0  # N
        ex = Mux * 1e6 / Pu_N if Pu_N > 0 else 0.0  # mm
        ey = Muy * 1e6 / Pu_N if Pu_N > 0 else 0.0  # mm
        steps['ex_mm'] = ex
        steps['ey_mm'] = ey

        # Pnx: X축만 편심 (ex)
        Pnx = self._find_Pn_at_eccentricity(ex, As_total, d_eff, d_prime, beta1)
        # Pny: Y축만 편심 (ey) — 정방형이므로 Pnx == Pny일 수 있음
        Pny = self._find_Pn_at_eccentricity(ey, As_total, d_eff, d_prime, beta1)
        # Pno: 순수 압축
        As_half = As_total / 2.0
        Pno = 0.85 * self.fc_k * (self.Ag - As_total) + self.fy * As_total  # N

        steps['Pnx_kN'] = Pnx / 1000.0
        steps['Pny_kN'] = Pny / 1000.0
        steps['Pno_kN'] = Pno / 1000.0

        # Bresler: 1/Pn = 1/Pnx + 1/Pny - 1/Pno
        if Pnx > 0 and Pny > 0 and Pno > 0:
            inv_Pn = 1.0 / Pnx + 1.0 / Pny - 1.0 / Pno
            if inv_Pn > 0:
                Pn_bresler = 1.0 / inv_Pn  # N
            else:
                Pn_bresler = Pno  # 보수적
        else:
            Pn_bresler = 0.0

        # φ 결정: Pu 수준에서의 εt → φ 보간
        # 간단하게 압축지배 phi_comp 적용 (Pu > 0이면 통상 압축지배)
        phi = phi_comp
        phi_Pn = phi * Pn_bresler / 1000.0  # kN

        steps['Pn_bresler_kN'] = Pn_bresler / 1000.0
        steps['phi'] = phi
        steps['phi_Pn_kN'] = phi_Pn

        safe = Pu <= phi_Pn
        ratio = Pu / phi_Pn if phi_Pn > 0 else float('inf')
        steps['ratio'] = ratio

        return {
            'safe': safe,
            'Pn_bresler': Pn_bresler / 1000.0,  # kN
            'Pnx': Pnx / 1000.0,
            'Pny': Pny / 1000.0,
            'Pno': Pno / 1000.0,
            'phi_Pn': phi_Pn,
            'ratio': ratio,
            'steps': steps,
        }

    # 4. KDS 기준이 반영된 띠철근 설계 로직
    def calculate_tie_rebar_design(self): 
        # 현재 배근된 주철근 직경 가져오기 
        main_rebar_dia = self.column_design_steps['rebar_diameter_col'] 
        main_rebar_type = self.column_design_steps['rebar_type_col'] 
        
        # 1) 띠철근 직경 결정 (KDS: 주철근 D32 이하 -> D10, D35 이상 -> D13) 
        if int(main_rebar_type.replace('D', '')) <= 32: 
            tie_rebar_type = "D10" 
            tie_rebar_diameter = 9.53 
        else: 
            tie_rebar_type = "D13" 
            tie_rebar_diameter = 12.7 
 
        # 2) 띠철근 간격 결정 (KDS 기준 3가지 조건 중 최솟값) 
        cond1 = 16 * main_rebar_dia 
        cond2 = 48 * tie_rebar_diameter 
        cond3 = self.c_column # 단면 최소 치수 
        
        max_spacing = min(cond1, cond2, cond3) 
        
        # 실무적으로 시공을 위해 50mm 단위로 내림 처리 (예: 318mm -> 300mm) 
        tie_rebar_spacing = int(np.floor(max_spacing / 50) * 50) 
        
        self.column_design_steps.update({ 
            'tie_rebar_type': tie_rebar_type, 
            'tie_rebar_diameter': tie_rebar_diameter, 
            'tie_rebar_spacing': tie_rebar_spacing 
        }) 
 
        return self.column_design_steps

    # ─────────────────────────────────────────────────────────────────────
    # 보-기둥 접합부 전단 검토 (KDS 41 17)
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def calculate_joint_shear(As_beam_top, fy, fc_k, c_column, b_beam,
                              M_neg_beam, h_column,
                              joint_type='interior', frame_type='OMF'):
        """
        보-기둥 접합부 전단 검토.

        Args:
            As_beam_top: 보 상부근 면적 (mm²)
            fy:          철근 항복강도 (MPa)
            fc_k:        콘크리트 압축강도 (MPa)
            c_column:    기둥 단면 치수 (mm, 정방형 가정)
            b_beam:      보 폭 (mm)
            M_neg_beam:  보 단부 부모멘트 (kN·m)
            h_column:    기둥 높이 (mm)
            joint_type:  'interior' / 'exterior'
            frame_type:  'OMF' / 'IMF'

        Returns:
            dict {ok, Vj, phi_Vn, ratio, steps, warnings}
        """
        warnings = []
        steps = {}

        # 응력 증폭 계수 α_o
        alpha_o = 1.25 if frame_type == 'IMF' else 1.0
        steps['alpha_o'] = alpha_o

        # T = As × α_o × fy (보 상부근 인장력)
        T = As_beam_top * alpha_o * fy / 1000.0  # kN
        steps['T_kN'] = T

        # V_col: 기둥 전단력 = M_neg_beam / (h_column/2) (반곡점 가정)
        # M_neg_beam은 보 단부 계수 부모멘트(kN·m)이며, 기둥 모멘트 ≈ 보 모멘트로 근사
        h_col_m = h_column / 1000.0
        V_col = 2.0 * abs(M_neg_beam) / h_col_m if h_col_m > 0 else 0.0
        steps['V_col_kN'] = V_col

        # Vj = T - V_col
        Vj = T - V_col
        steps['Vj_kN'] = Vj

        # 접합부 유효면적 Aj
        b_eff = min(c_column, b_beam + c_column)
        Aj = c_column * b_eff  # mm²
        steps['b_eff'] = b_eff
        steps['Aj'] = Aj

        # γ 계수 (KDS 41 17)
        gamma_map = {
            ('interior', 'IMF'): 1.7,
            ('interior', 'OMF'): 1.0,
            ('exterior', 'IMF'): 1.25,
            ('exterior', 'OMF'): 0.75,
        }
        gamma = gamma_map.get((joint_type, frame_type), 1.0)
        steps['gamma'] = gamma

        # φVn = φ × γ × √fck × Aj  (N → kN)
        phi = 0.75
        phi_Vn = phi * gamma * np.sqrt(fc_k) * Aj / 1000.0  # kN
        steps['phi'] = phi
        steps['phi_Vn_kN'] = phi_Vn

        # 판정
        ok = abs(Vj) <= phi_Vn
        ratio = abs(Vj) / phi_Vn if phi_Vn > 0 else float('inf')
        steps['ratio'] = ratio

        if not ok:
            warnings.append(
                f"경고: 접합부 전단 Vj={abs(Vj):.1f}kN > φVn={phi_Vn:.1f}kN — "
                "기둥 단면 증가 또는 접합부 보강 필요")

        return {'ok': ok, 'Vj': Vj, 'phi_Vn': phi_Vn,
                'ratio': ratio, 'steps': steps, 'warnings': warnings}

    # ─────────────────────────────────────────────────────────────────────
    # IMF 기둥 내진 상세 검토 (KDS 41 17 4.5)
    # ─────────────────────────────────────────────────────────────────────
    def calculate_imf_column_detailing(self, h_column, db_main, db_tie, s_tie_normal):
        """
        KDS 41 17 4.5 IMF 기둥 상세 검토.

        Args:
            h_column:     기둥 높이 (mm)
            db_main:      주철근 직경 (mm)
            db_tie:       띠철근 직경 (mm)
            s_tie_normal: 일반구간 띠철근 간격 (mm)

        Returns:
            dict {l_o, s_max_confine, s_confine_ok, steps, warnings}
        """
        warnings = []
        steps = {}

        # 1. 구속구간 길이
        l_o = max(self.c_column, h_column / 6.0, 450.0)
        steps['l_o'] = l_o

        # 2. 구속구간 띠철근 최대간격
        s_max_confine = min(self.c_column / 2.0, 8.0 * db_main,
                            24.0 * db_tie, 300.0)
        steps['s_max_confine'] = s_max_confine
        s_confine_ok = s_tie_normal <= s_max_confine
        steps['s_confine_ok'] = s_confine_ok
        steps['s_tie_normal'] = s_tie_normal

        if not s_confine_ok:
            warnings.append(
                f"경고: 구속구간 띠철근간격 {s_tie_normal:.0f}mm > "
                f"최대허용 {s_max_confine:.0f}mm — 구속구간 띠철근 간격 축소 필요")

        return {
            'l_o': l_o,
            's_max_confine': s_max_confine,
            's_confine_ok': s_confine_ok,
            'steps': steps,
            'warnings': warnings,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 강기둥-약보 검토 (KDS 41 17 4.5: ΣMn_col ≥ 1.2 × ΣMn_beam)
    # ─────────────────────────────────────────────────────────────────────
    def calculate_strong_column_weak_beam(self, Pu, Mn_beam_x, Mn_beam_y):
        """
        KDS 41 17 4.5: ΣMn_col ≥ 1.2 × ΣMn_beam

        Args:
            Pu:         기둥 축력 (kN)
            Mn_beam_x:  X방향 보 공칭 휨강도 (kN·m)
            Mn_beam_y:  Y방향 보 공칭 휨강도 (kN·m)

        Returns:
            dict {ok, ratio, Mn_col_sum, Mn_beam_sum, steps}
        """
        steps = {}

        # 기둥 공칭 휨강도: 현재 배근+축력에서의 Mn
        # P-M 곡선에서 Pu에 대응하는 Mn을 역산
        rd = self.column_design_steps
        As_total = rd.get('As_provided_col', 0.0)
        beta1 = max(0.85 - 0.05 / 7.0 * (self.fc_k - 28), 0.65) if self.fc_k > 28 else 0.85
        _col_cover = 40.0
        _tie_dia = 9.53
        _rebar_dia = rd.get('rebar_diameter_col', 25.4)
        cover_approx = _col_cover + _tie_dia + _rebar_dia / 2.0
        d_eff = self.c_column - cover_approx
        d_prime = cover_approx
        As_half = As_total / 2.0
        h_half = self.c_column / 2.0

        # c를 탐색하여 Pu에 대응하는 Mn 산정
        Pu_N = Pu * 1000.0  # N
        c_lo, c_hi = 1e-3, self.c_column * 3.0
        Mn_col = 0.0
        for _ in range(60):
            c_mid = (c_lo + c_hi) / 2.0
            a_i = min(beta1 * c_mid, self.c_column)
            fs_p = min(max(600.0 * (c_mid - d_prime) / c_mid, -self.fy), self.fy)
            fs_t = min(max(600.0 * (d_eff - c_mid) / c_mid, -self.fy), self.fy)
            Pn_i = (0.85 * self.fc_k * a_i * self.c_column
                    + As_half * fs_p - As_half * fs_t)
            if Pn_i > Pu_N:
                c_hi = c_mid
            else:
                c_lo = c_mid
            if c_hi - c_lo < 0.01:
                break
        c_at_Pu = (c_lo + c_hi) / 2.0
        a_at_Pu = min(beta1 * c_at_Pu, self.c_column)
        fs_p = min(max(600.0 * (c_at_Pu - d_prime) / c_at_Pu, -self.fy), self.fy)
        fs_t = min(max(600.0 * (d_eff - c_at_Pu) / c_at_Pu, -self.fy), self.fy)
        Mn_col = (0.85 * self.fc_k * a_at_Pu * self.c_column * (h_half - a_at_Pu / 2.0)
                  + As_half * fs_p * (h_half - d_prime)
                  + As_half * fs_t * (d_eff - h_half))
        Mn_col_kNm = Mn_col / 1e6

        # ΣMn_col = 2 × Mn_col (상하 기둥, 대칭 가정)
        Mn_col_sum = 2.0 * Mn_col_kNm
        # ΣMn_beam = 양측 보 공칭 강도
        Mn_beam_sum = abs(Mn_beam_x) + abs(Mn_beam_y)

        steps['Mn_col_kNm'] = Mn_col_kNm
        steps['Mn_col_sum'] = Mn_col_sum
        steps['Mn_beam_x'] = abs(Mn_beam_x)
        steps['Mn_beam_y'] = abs(Mn_beam_y)
        steps['Mn_beam_sum'] = Mn_beam_sum

        ratio = Mn_col_sum / (1.2 * Mn_beam_sum) if Mn_beam_sum > 0 else float('inf')
        ok = ratio >= 1.0
        steps['ratio'] = ratio

        return {
            'ok': ok,
            'ratio': ratio,
            'Mn_col_sum': Mn_col_sum,
            'Mn_beam_sum': Mn_beam_sum,
            'steps': steps,
        }
