import numpy as np

def round_up_to_50(value):
    """값을 50mm 단위로 올림합니다."""
    return np.ceil(value / 50.0) * 50.0

class BeamAnalyzer:
    def __init__(self, L_beam, S_slab, t_slab, DL_area, LL_area, fc_k, fy, beam_type='X',
                 h_beam_override=None, b_beam_override=None):
        """
        Args:
            h_beam_override: 처짐 반복 설계 시 외부에서 지정하는 보 춤 (mm).
                             None이면 L/28 최적화 시작점 자동 적용.
            b_beam_override: 배근 반복 설계 시 외부에서 지정하는 보 폭 (mm).
                             None이면 h×0.5 시작점 자동 적용.
        """
        self.L_beam = L_beam / 1000.0  # mm → m
        self.S_slab = S_slab / 1000.0  # mm → m
        self.t_slab = t_slab
        self.DL_area = DL_area  # kN/m²
        self.LL_area = LL_area  # kN/m²
        self.fc_k = fc_k  # MPa
        self.fy = fy      # MPa
        self.beam_type = beam_type

        # KDS L/21 참조값 (처짐 면제 최소 깊이, 비교 표시용)
        self.h_beam_L21 = max(round_up_to_50(self.L_beam / 21.0 * 1000.0), 150.0)

        # 최적화 시작점: L/28 (처짐 반복 설계가 실제 필요 깊이를 결정)
        self.h_beam_start = max(round_up_to_50(self.L_beam / 28.0 * 1000.0), 150.0)

        # 처짐 반복 설계: override가 시작점보다 크면 적용, 아니면 시작점 사용
        if h_beam_override is not None:
            self.h_beam = float(h_beam_override)
        else:
            self.h_beam = self.h_beam_start

        # 보의 폭: h × 0.5 시작점 (b ≤ h 상한만 적용, 고정 최솟값 없음)
        self.b_beam_raw = self.h_beam * 0.5
        self.b_beam_start = min(round_up_to_50(self.b_beam_raw), self.h_beam)
        if b_beam_override is not None:
            self.b_beam = float(b_beam_override)
        else:
            self.b_beam = self.b_beam_start

        self._calculate_loads()

    def _calculate_loads(self):
        # 슬래브 자중 산정 (kN/m^2)
        # 콘크리트 단위중량 24 kN/m^3
        self.w_slab_self = (self.t_slab / 1000.0) * 24.0

        # 보 자중 산정 (kN/m)
        # 슬래브와 겹치는 부분(b×t_slab)은 슬래브 자중에 이미 포함되므로 제외
        # 보 자중 = b × (h - t_slab) × 24 kN/m³
        self.w_beam_self = (self.b_beam / 1000.0) * (max(self.h_beam - self.t_slab, 0.0) / 1000.0) * 24.0

        # 보에 작용하는 등분포 고정하중 (unfactored w_DL_unfactored, kN/m)
        self.w_DL_unfactored = (self.w_slab_self + self.DL_area) * self.S_slab + self.w_beam_self

        # 보에 작용하는 등분포 활하중 (unfactored w_LL_unfactored, kN/m)
        self.w_LL_unfactored = self.LL_area * self.S_slab

        # 계수 고정하중 (w_DL_factored, kN/m)
        self.w_DL_factored = 1.2 * self.w_DL_unfactored

        # 계수 활하중 (w_LL_factored, kN/m)
        self.w_LL_factored = 1.6 * self.w_LL_unfactored

        # 계수하중 조합 (w_u, kN/m) — KDS 41 10 15: 1.2D + 1.6L
        self.w_u = self.w_DL_factored + self.w_LL_factored

    def calculate_member_forces(self):
        """
        고정단 보(강접합)의 부재력을 계산합니다.
        M_neg: 지점부 부(-) 모멘트 (상부 인장), M_pos: 중앙부 정(+) 모멘트 (하부 인장)
        """
        # 고정단 보 휨모멘트
        M_neg = self.w_u * self.L_beam**2 / 12.0  # 지점부 부모멘트 (kN.m)
        M_pos = self.w_u * self.L_beam**2 / 24.0  # 중앙부 정모멘트 (kN.m)

        # 최대 전단력 (단부) - 단순보와 동일
        V_max = self.w_u * self.L_beam / 2.0

        # SFD 및 BMD 데이터
        x_steps = np.linspace(0, self.L_beam, 100) # m 단위
        SFD = V_max - self.w_u * x_steps  # 전단력 분포 (변경 없음)
        BMD = -M_neg + V_max * x_steps - self.w_u * x_steps**2 / 2.0  # 고정단 BMD

        return {
            "M_neg": M_neg, # 지점부 부모멘트 (kN.m)
            "M_pos": M_pos, # 중앙부 정모멘트 (kN.m)
            "V_max": V_max, # kN
            "x_steps": x_steps, # m
            "SFD": SFD, # kN
            "BMD": BMD # kN.m
        }

    def get_design_parameters(self):
        return {
            "t_slab": self.t_slab,       # mm
            "h_beam": self.h_beam,           # mm (처짐 검토 후 최종값)
            "h_beam_start": self.h_beam_start,  # mm (L/28 최적화 시작점)
            "h_beam_L21": self.h_beam_L21,      # mm (KDS L/21 참조값)
            "b_beam": self.b_beam,       # mm (배근 검토 후 최종값)
            "b_beam_start": self.b_beam_start,  # mm (h×0.5 시작점)
            "w_slab_self": self.w_slab_self, # kN/m^2
            "w_beam_self": self.w_beam_self, # kN/m
            "w_DL_unfactored": self.w_DL_unfactored, # kN/m
            "w_LL_unfactored": self.w_LL_unfactored, # kN/m
            "w_DL_factored": self.w_DL_factored, # kN/m
            "w_LL_factored": self.w_LL_factored, # kN/m
            "w_u": self.w_u # kN/m
        }

    def calculate_flexural_design(self, Mu, b, h, fc_k, fy):
        """
        KDS 기준에 따라 RC 보의 휨 설계를 수행하고 필요 주철근 면적(As)을 반환합니다.
        """
        warnings = []
        detailed_steps = {}

        # 단위 변환: kN·m -> N·mm
        Mu_Nmm = abs(Mu) * 1e6
        detailed_steps['Mu_Nmm'] = Mu_Nmm

        # 강도감소계수 φ 초기값 (인장지배 가정)
        phi = 0.85

        # ── 피복 + 유효깊이(d): 내부 2-패스 추정 ─────────────────────────
        # 1패스: D25 가정(d_c≈62.7mm)으로 As 추정 → 최적 철근직경(d_b) 추정 → d_c 정밀화
        _cover  = 40.0   # mm 주철근 피복두께 (KDS 41 20 52)
        _stir_r = 10.0   # mm 늑근 직경 (D10)
        _dc_init = _cover + _stir_r + 25.4 / 2.0  # ≈ 62.7mm (D25 초기 가정)
        _d_init  = h - _dc_init
        if _d_init > 0.0:
            _Rn_est   = (Mu_Nmm / 0.85) / (b * _d_init ** 2)
            _disc_est = 1.0 - (2.0 * _Rn_est) / (0.85 * fc_k)
            if _disc_est > 0.0:
                _rho_est = (0.85 * fc_k / fy) * (1.0 - np.sqrt(_disc_est))
                _rho_est = max(_rho_est, 1.4 / fy)   # rho_min 하한
                _As_est  = _rho_est * b * _d_init
            else:
                _As_est  = 0.0
        else:
            _As_est = 0.0
        # 최소 2가닥 기준으로 적합한 철근 직경 추정 (D13→D32 순서)
        _rebar_db_table = [
            (12.7, 126.7), (15.9, 198.6), (19.1, 286.5),
            (22.2, 387.1), (25.4, 506.7), (28.6, 642.4), (31.8, 794.2)
        ]
        _db_est = 25.4  # 기본값 (D25) — As=0 또는 As 매우 클 때
        for _db_c, _Ab_c in _rebar_db_table:
            if 2.0 * _Ab_c >= _As_est:
                _db_est = _db_c
                break
        d_c = _cover + _stir_r + _db_est / 2.0   # mm 정밀 d_c (2패스)
        d   = h - d_c                              # mm 정밀 유효깊이
        detailed_steps['d_c']        = d_c
        detailed_steps['d_c_db_est'] = _db_est     # 추정 철근 직경 기록
        detailed_steps['d']          = d

        if d <= 0:
            warnings.append("경고: 유효깊이(d)가 0 이하입니다. 단면 치수를 확인하세요.")
            return 0.0, warnings, detailed_steps

        # 등가응력블록 깊이 계수 beta1 (KDS 41 20 20 4.1.1 (4))
        if fc_k <= 28:
            beta1 = 0.85
        else:
            beta1 = max(0.65, 0.85 - 0.05 / 7.0 * (fc_k - 28))
        detailed_steps['beta1'] = beta1

        # 콘크리트 극한변형률 (KDS 41 20 20 4.1.1)
        # KDS 41 20 기준: fck 관계없이 εcu = 0.003 (구 0.0033 수정)
        epsilon_cu = 0.003

        # ── φ-ε_t 수렴 루프 (KDS 41 20 20 4.2.2: 전이구간 φ 보간) ─────────
        # φ → As → ε_t → φ 순환 의존성을 반복 계산으로 해소 (최대 10회)
        discriminant = 1.0
        rho_req = 0.0
        _phi_iter = 0
        for _phi_iter in range(10):
            Mn_Nmm = Mu_Nmm / phi
            Rn     = Mn_Nmm / (b * d**2)
            discriminant = 1 - (2 * Rn) / (0.85 * fc_k)
            if discriminant < 0:
                break  # 단면 부족 — φ 반복 불필요

            rho_req = (0.85 * fc_k / fy) * (1 - np.sqrt(discriminant))

            # ε_t 산정 (rho_min 적용 전, 순수 강도 기반)
            As_iter = rho_req * b * d
            a_iter  = (As_iter * fy) / (0.85 * fc_k * b)
            c_iter  = a_iter / beta1
            epsilon_t_iter = epsilon_cu * (d - c_iter) / c_iter if c_iter > 0 else 0.005

            # φ 갱신 (KDS 41 20 20)
            if epsilon_t_iter >= 0.005:
                phi_new = 0.85
            elif epsilon_t_iter <= 0.002:
                phi_new = 0.65
            else:
                phi_new = 0.65 + 0.20 * (epsilon_t_iter - 0.002) / 0.003

            if abs(phi_new - phi) < 1e-4:
                phi = phi_new
                break
            phi = phi_new

        detailed_steps['phi']          = phi
        detailed_steps['phi_iters']    = _phi_iter + 1
        detailed_steps['Mn_Nmm']       = Mu_Nmm / phi if discriminant >= 0 else 0
        detailed_steps['Rn']           = (Mu_Nmm / phi) / (b * d**2) if discriminant >= 0 else 0
        detailed_steps['discriminant'] = discriminant

        if discriminant < 0:
            warnings.append("오류: 단면이 너무 작아 휨모멘트를 버틸 수 없습니다. 보의 춤(h) 또는 폭(b)을 키우세요.")
            return 0.0, warnings, detailed_steps

        detailed_steps['rho_req_calculated'] = rho_req

        # 최소 철근비(rho_min) 검토
        rho_min1 = (0.25 * np.sqrt(fc_k)) / fy
        rho_min2 = 1.4 / fy
        rho_min  = max(rho_min1, rho_min2)
        detailed_steps['rho_min1'] = rho_min1
        detailed_steps['rho_min2'] = rho_min2
        detailed_steps['rho_min']  = rho_min

        if rho_req < rho_min:
            rho_req = rho_min
            warnings.append(f"정보: 최소 철근비({rho_min:.4f}) 미달로 인해 철근비가 {rho_req:.4f}로 상향 조정되었습니다.")
        detailed_steps['rho_req_final'] = rho_req

        # 최종 소요 철근량(As) 계산
        As = rho_req * b * d
        detailed_steps['As_calculated'] = As

        # 최종 ε_t 재계산 (rho_min 적용 후 As 기준)
        a = (As * fy) / (0.85 * fc_k * b)
        c = a / beta1
        epsilon_t = epsilon_cu * (d - c) / c if c > 0 else 0.005
        detailed_steps['a']         = a
        detailed_steps['c']         = c
        detailed_steps['epsilon_t'] = epsilon_t

        # 변형률 구간별 경고
        if epsilon_t < 0.002:
            warnings.append(f"경고: 순인장변형률({epsilon_t:.4f}) < 0.002 — 압축지배단면. φ={phi:.3f} 적용됨. 단면을 크게 키우세요.")
        elif epsilon_t < 0.004:
            warnings.append(f"경고: 순인장변형률({epsilon_t:.4f}) < 0.004 — KDS 41 20 20 최대 철근비 초과. 단면 크기를 키우세요.")
        elif epsilon_t < 0.005:
            warnings.append(f"정보: 순인장변형률({epsilon_t:.4f}) 전이구간 — φ={phi:.3f} 보간 적용됨.")

        # ρ_max 기록 (εt=0.004 기준)
        rho_max = (0.85 * beta1 * fc_k / fy) * (0.003 / (0.003 + 0.004))
        detailed_steps['rho_max'] = rho_max
        detailed_steps['rho_max_ok'] = epsilon_t >= 0.004

        return As, warnings, detailed_steps

    # ------------------------------------------------------------------
    # 정착길이 / 이음길이 (KDS 41 20 52)
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_development_length(db, fy, fc_k, position='bottom',
                                      cover=40.0, spacing=None,
                                      As_req=None, As_prov=None):
        """
        KDS 41 20 52 인장 이형철근 정착길이 및 겹이음길이 계산.

        Parameters
        ----------
        db       : float  철근 직경 (mm)
        fy       : float  항복강도 (MPa)
        fc_k     : float  콘크리트 압축강도 (MPa)
        position : str    'top' (상부철근) / 'bottom' (하부철근)
        cover    : float  피복두께 (mm)
        spacing  : float  철근 중심간격 (mm), None이면 피복 기반만 적용
        As_req   : float  소요 철근량 (mm²), None이면 감소 미적용
        As_prov  : float  배치 철근량 (mm²), None이면 감소 미적용

        Returns
        -------
        dict  {ld, ls_B, ldc, ldh, steps}
        """
        _sqrt_fck = np.sqrt(fc_k)

        # 1. 기본정착길이 ℓdb = 0.9·db·fy / (λ·√fck)
        _lambda = 1.0   # 보통콘크리트
        ldb = 0.9 * db * fy / (_lambda * _sqrt_fck)

        # 2. 보정계수
        alpha = 1.3 if position == 'top' else 1.0   # 상부철근 위치계수
        beta  = 1.0                                   # 무도막 철근
        gamma = 0.8 if db <= 19.1 else 1.0           # 철근 크기계수 (≤D19)

        # 3. (cb + Ktr) / db  — 간편법: Ktr = 0
        #    cb = min(피복~철근중심 거리, 철근 중심간격/2)  (KDS 41 20 52)
        cb_cover = cover + db / 2.0
        if spacing is not None and spacing > 0:
            cb = min(cb_cover, spacing / 2.0)
        else:
            cb = cb_cover
        cb_ktr = cb / db
        cb_ktr = min(cb_ktr, 2.5)   # 상한 2.5

        # 4. 인장 정착길이 ℓd (Method 2)
        ld = ldb * (alpha * beta * gamma) / cb_ktr
        ld = max(ld, 300.0)

        # 5. 소요량 초과 시 감소 (ld × As_req / As_prov ≥ 300mm)
        ld_unreduced = ld
        if As_req is not None and As_prov is not None and As_prov > 0:
            ratio = min(As_req / As_prov, 1.0)
            ld = max(ld * ratio, 300.0)

        # 6. 겹이음길이 (Class B — 일반적 경우)
        ls_B = 1.3 * ld

        # 7. 압축 정착길이
        ldc = max(0.25 * db * fy / _sqrt_fck, 0.043 * db * fy)
        ldc = max(ldc, 200.0)

        # 8. 표준갈고리 정착길이
        ldh = 0.24 * db * fy / (_lambda * _sqrt_fck)
        ldh = max(ldh, 8.0 * db, 150.0)

        steps = {
            'db': db, 'fy': fy, 'fc_k': fc_k,
            'position': position, 'cover': cover,
            'spacing': spacing,
            'cb': round(cb, 1), 'cb_cover': round(cb_cover, 1),
            'ldb': round(ldb, 0),
            'alpha': alpha, 'beta': beta, 'gamma': gamma,
            'cb_ktr': round(cb_ktr, 2),
            'ld_unreduced': round(ld_unreduced, 0),
        }

        return {
            'ld':   round(ld, 0),
            'ls_B': round(ls_B, 0),
            'ldc':  round(ldc, 0),
            'ldh':  round(ldh, 0),
            'steps': steps,
        }

    # ------------------------------------------------------------------
    # 균열 제어 검토 (KDS 41 20 50 — 간접균열제어: 철근 간격 제한)
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_crack_control(rebar_string, b_beam, cover, fy,
                                exposure='dry'):
        """
        KDS 41 20 50 간접균열제어 — 인장철근 최대 간격 검토.

        Parameters
        ----------
        rebar_string : str   예: '5-D25', '3-D22'
        b_beam       : float 보 폭 (mm)
        cover        : float 피복두께 (mm)
        fy           : float 철근 항복강도 (MPa)
        exposure     : str   'dry'(건조환경, k_cr=280) / 'other'(기타, k_cr=210)

        Returns
        -------
        dict  {ok, s_actual, s_max, s_limit1, s_limit2, fs, k_cr, cc, steps}
        """
        # 1. 철근 간격 산정
        parts = rebar_string.split('-')
        n_bars = int(parts[0])
        size_name = parts[1]
        rebar_specs = {
            "D10": 9.53, "D13": 12.7, "D16": 15.9, "D19": 19.1,
            "D22": 22.2, "D25": 25.4, "D29": 28.6, "D32": 31.8,
        }
        db = rebar_specs.get(size_name, 25.4)
        stirrup_dia = 9.53  # D10 스터럽

        # 실제 철근 간격 (중심~중심)
        cc = cover + stirrup_dia  # 인장철근 외면~콘크리트 표면 (KDS 41 20 50 4.2)
        if n_bars >= 2:
            edge = cover + stirrup_dia + db / 2.0
            s_actual = (b_beam - 2.0 * edge) / (n_bars - 1)
        else:
            s_actual = 0.0  # 1개면 간격 개념 없음

        # 2. 사용하중 시 철근 응력 (근사값)
        fs = (2.0 / 3.0) * fy  # KDS 허용 근사

        # 3. 환경 계수
        k_cr = 280.0 if exposure == 'dry' else 210.0

        # 4. 최대 간격 제한 (두 식 중 작은 값)
        s_limit_1 = 380.0 * (k_cr / fs) - 2.5 * cc
        s_limit_2 = 300.0 * (k_cr / fs)
        s_max = min(s_limit_1, s_limit_2)

        ok = (n_bars <= 1) or (s_actual <= s_max)

        steps = {
            'n_bars': n_bars, 'db': db, 'cc': cc,
            'fs': round(fs, 1), 'k_cr': k_cr,
            's_actual': round(s_actual, 1),
            's_limit_1': round(s_limit_1, 1),
            's_limit_2': round(s_limit_2, 1),
            's_max': round(s_max, 1),
        }
        return {'ok': ok, 's_actual': round(s_actual, 1),
                's_max': round(s_max, 1), 'steps': steps}

    def calculate_shear_design(self, Vu, b, d, fc_k, fy_t=400.0):
        """
        KDS 기준에 따라 RC 보의 전단 설계를 수행하고 늑근 간격을 반환합니다.
        :param Vu: 계수 전단력 (kN)
        :param b: 보의 폭 (mm)
        :param d: 보의 유효깊이 (mm)
        :param fc_k: 콘크리트 압축강도 (MPa)
        :param fy_t: 전단철근 항복강도 (MPa, 기본값 400 MPa)
        :return: s_final (mm), warnings (list of strings), detailed_steps (dict)
        """
        warnings = []
        detailed_steps = {}

        # 초기 변수 및 가정 설정
        phi = 0.75  # 전단 부재 강도감소계수
        lambda_factor = 1.0  # 경량콘크리트 계수 (보통 중량 콘크리트 가정)
        detailed_steps['phi'] = phi
        detailed_steps['fy_t'] = fy_t
        detailed_steps['d'] = d

        # 전단철근(늑근) 가정: D10 철근의 U자형 2가닥(2-legs) 배근
        A_sb = 71.33  # D10 철근 1가닥 단면적 (mm^2)
        A_v = 2 * A_sb  # 전단철근의 총 단면적 (mm^2)
        detailed_steps['A_v'] = A_v

        # 모든 하중 단위는 kN에서 N(뉴턴)으로 변환
        Vu_N = abs(Vu) * 1000
        detailed_steps['Vu_N'] = Vu_N

        # 1. 소요 공칭전단강도 (V_n)
        Vn_N = Vu_N / phi
        detailed_steps['Vn_N'] = Vn_N

        # 2. 콘크리트가 부담하는 전단강도 (V_c)
        Vc_N = (1/6) * lambda_factor * np.sqrt(fc_k) * b * d
        detailed_steps['Vc_N'] = Vc_N

        # 3. 전단철근이 부담해야 할 전단강도 (V_s)
        Vs_N = Vn_N - Vc_N
        detailed_steps['Vs_N'] = Vs_N

        # [예외 처리 1] 단면 부족 검토 (V_s의 상한선)
        Vs_max_N = (2/3) * np.sqrt(fc_k) * b * d
        detailed_steps['Vs_max_N'] = Vs_max_N
        if Vs_N > Vs_max_N:
            warnings.append("오류: 전단력이 너무 커서 단면이 파괴됩니다. 보의 단면(폭 b 또는 춤 h)을 키우세요.")
            return 0.0, warnings, detailed_steps

        # 4. 이론적 요구 간격(s_req) 및 최소 전단철근 간격(s_max_Av) 산정
        s_req = float('inf')
        if Vs_N > 0:
            s_req = (A_v * fy_t * d) / Vs_N
        else:
            warnings.append("정보: 콘크리트가 부담하는 전단강도가 충분하여 이론적으로 전단철근이 필요하지 않습니다. 최소 전단철근 규정에 따라 배근됩니다.")
            s_req = 1000000.0 # 매우 큰 값으로 설정하여 s_max_Av, s_max_geom에 의해 결정되도록 함
        detailed_steps['s_req'] = s_req

        # 최소 전단철근량에 의한 최대 간격 (s_max_Av)
        s_max_Av_numerator = A_v * fy_t
        s_max_Av_denominator = max(0.0625 * np.sqrt(fc_k) * b, 0.35 * b)
        s_max_Av = s_max_Av_numerator / s_max_Av_denominator
        detailed_steps['s_max_Av'] = s_max_Av

        # 5. KDS 규정에 따른 기하학적 최대 간격 (s_max_geom) 제한
        Vc_limit_N = (1/3) * np.sqrt(fc_k) * b * d
        detailed_steps['Vc_limit_N'] = Vc_limit_N

        s_max_geom = 0.0
        if Vs_N <= Vc_limit_N:
            s_max_geom = min(d / 2, 600.0)
        else: # 전단력이 매우 큰 경우
            s_max_geom = min(d / 4, 300.0)
        detailed_steps['s_max_geom'] = s_max_geom

        # 6. 최종 늑근 배근 간격(s) 결정
        s_raw = min(s_req, s_max_Av, s_max_geom)
        detailed_steps['s_raw'] = s_raw

        # 실무 치수 조정 (Rounding down)
        s_final = max(np.floor(s_raw / 50.0) * 50.0, 100.0)
        detailed_steps['s_final'] = s_final

        return s_final, warnings, detailed_steps

    def calculate_shear_zones(self, n_zones, V_max, b, d, fc_k, fy_t=400.0,
                              x_start=0.0):
        """경간을 n_zones 구간으로 균등 분할하여 각 구간의 늑근 간격을 산정합니다.

        보는 양단 고정보(등분포 하중)이므로 전단력 분포:
            Vu(x) = V_max - w_u * x  (x: 지점으로부터 거리, m 단위)

        각 구간의 설계 전단력은 구간 시작점(지점 쪽 끝)의 Vu를 사용합니다.
        (보수적 설계 — 구간 내 최대 전단력 기준)

        Parameters
        ----------
        n_zones : int  — 2, 3, 또는 4
        V_max   : float — 지점 최대 전단력 (kN)
        b, d    : float — 폭/유효깊이 (mm)
        fc_k    : float — 콘크리트 강도 (MPa)
        fy_t    : float — 늑근 항복강도 (MPa)
        x_start : float — 위험단면 시작 위치 (m), 기본 0.0

        Returns
        -------
        list[dict]  각 구간: zone_idx, x_start, x_end(m), Vu_kN, s(mm), 상세
        """
        L = self.L_beam   # m
        # 위험단면~중앙 구간을 n_zones 분할 (대칭이므로 반경간)
        L_eff = L / 2.0 - x_start  # 위험단면~중앙 거리
        if L_eff <= 0:
            L_eff = L / 2.0  # 안전장치
            x_start = 0.0
        zones = []
        for i in range(n_zones):
            x_s = x_start + i * L_eff / n_zones          # m
            x_e = x_start + (i + 1) * L_eff / n_zones    # m
            # SFD(x) = V_max - w_u * x  →  구간 내 최대 |SFD| 사용
            # (우측 지점부 구간은 SFD가 음수이므로 절댓값 기준)
            Vu_start = abs(V_max - self.w_u * x_s)
            Vu_end   = abs(V_max - self.w_u * x_e)
            Vu_zone  = max(Vu_start, Vu_end)   # kN — 구간 내 최대 |Vu|
            s, warn, steps = self.calculate_shear_design(Vu_zone, b, d, fc_k, fy_t)
            zones.append({
                'zone_idx':       i + 1,
                'x_start':        x_s,
                'x_end':          x_e,
                'Vu_kN':          Vu_zone,
                's':              s,
                'shear_warnings': warn,
                'shear_steps':    steps,
            })
        return zones

    def calculate_rebar_detailing(self, As_req, b, d_b_stirrup=10.0, max_agg_size=25.0,
                                  force_diameter=None):
        """
        KDS 기준에 따라 RC 보의 주철근 가닥수 및 배근을 자동화합니다.
        :param As_req: 소요 주철근 면적 (mm^2)
        :param b: 보의 폭 (mm)
        :param d_b_stirrup: 전단철근(늑근) 직경 (mm, 기본값 10mm)
        :param max_agg_size: 굵은골재 최대치수 (mm, 기본값 25mm)
        :param force_diameter: 이 값(mm) 이상의 직경만 후보로 사용 (직경 통일 시 활용)
        :return: rebar_string (str), As_provided (float), layer (int), warnings (list of strings), detailed_steps (dict)
        """
        warnings = []
        detailed_steps = {}

        # 상수 조건 (KDS 기준)
        cover = 40.0  # 주철근 피복두께 (mm)

        # 주철근 제원표 (KS D 3504 기준 Dictionary)
        rebar_specs = {
            "D10": {"diameter": 9.53,  "area": 71.33},
            "D13": {"diameter": 12.7,  "area": 126.7},
            "D16": {"diameter": 15.9,  "area": 198.6},
            "D19": {"diameter": 19.1,  "area": 286.5},
            "D22": {"diameter": 22.2,  "area": 387.1},
            "D25": {"diameter": 25.4,  "area": 506.7},
            "D29": {"diameter": 28.6,  "area": 642.4},
            "D32": {"diameter": 31.8,  "area": 794.2},
        }
        detailed_steps['rebar_specs'] = rebar_specs

        rebar_sizes_to_check = ["D13", "D16", "D19", "D22", "D25", "D29", "D32"]
        # force_diameter 적용: 해당 직경 미만 후보 제거
        if force_diameter is not None:
            rebar_sizes_to_check = [
                s for s in rebar_sizes_to_check
                if rebar_specs[s]["diameter"] >= force_diameter - 0.1  # 부동소수 허용
            ]
            if not rebar_sizes_to_check:
                rebar_sizes_to_check = ["D32"]  # 최소 1개 보장

        As_provided = 0.0
        rebar_string = "N/A"
        layer = 1
        
        found_single_layer_solution = False

        # 2. 최소 순간격(S_min) 및 유효 폭(b_net) 계산
        # 굵은골재 25 mm 가정 시 4/3 * 25 = 33.3 mm
        min_clear_spacing_agg = (4/3) * max_agg_size
        
        # 배근 가능한 유효 폭 (b_net) 산정
        # b_net = b - (2 * cover) - (2 * d_b_stirrup)
        b_net = b - (2 * cover) - (2 * d_b_stirrup)
        detailed_steps['cover'] = cover
        detailed_steps['d_b_stirrup'] = d_b_stirrup
        detailed_steps['max_agg_size'] = max_agg_size
        detailed_steps['min_clear_spacing_agg'] = min_clear_spacing_agg
        detailed_steps['b_net'] = b_net

        # 3. 철근 규격 및 가닥수(n) 탐색 알고리즘 (1단 배근)
        for size_name in rebar_sizes_to_check:
            specs = rebar_specs[size_name]
            d_b = specs["diameter"]
            A_b = specs["area"]

            # 철근의 최소 순간격 (S_min) 산정
            S_min = max(min_clear_spacing_agg, d_b)
            detailed_steps[f'S_min_{size_name}'] = S_min

            # 가닥수 산정
            n_raw = np.ceil(As_req / A_b)
            n = int(max(n_raw, 2)) # 최소 2가닥
            detailed_steps[f'n_calculated_{size_name}'] = n_raw
            detailed_steps[f'n_final_{size_name}'] = n

            # 1단 배근 시 필요 폭(req_width) 계산
            req_width = (n * d_b) + ((n - 1) * S_min)
            detailed_steps[f'req_width_{size_name}'] = req_width

            # 배치 가능 여부 검토
            if req_width <= b_net:
                As_provided = n * A_b
                rebar_string = f"{n}-" + size_name
                found_single_layer_solution = True
                break

        # 1단 배근 성공 시 선택된 철근 직경 기록 (C2: 처짐 계산용 d_c 정밀화)
        if found_single_layer_solution:
            detailed_steps['selected_rebar_diameter'] = d_b

        # 4. [예외 처리] 2단 배근 폴백 (Fallback)
        if not found_single_layer_solution:
            layer = 2
            # 규격을 가장 범용적인 대형 규격인 D25로 고정
            specs_D25 = rebar_specs["D25"]
            d_b_D25 = specs_D25["diameter"]
            A_b_D25 = specs_D25["area"]

            n_raw_D25 = np.ceil(As_req / A_b_D25)
            n_D25 = int(max(n_raw_D25, 2))

            # 2단 배근 유효깊이 보정 기록 (KDS 41 20 20)
            # d_c_2layer = cover + stirrup + d_b + 순간격(≥25,≥d_b) + d_b/2
            _stirrup_dia = d_b_stirrup
            _clear_gap = max(25.0, d_b_D25)  # 최소 순간격
            d_c_2layer = cover + _stirrup_dia + d_b_D25 + _clear_gap + d_b_D25 / 2.0
            detailed_steps['d_c_2layer'] = d_c_2layer

            As_provided = n_D25 * A_b_D25
            rebar_string = f"{n_D25}-D25"
            warnings.append("경고: 1단 배근이 불가하여 D25 철근으로 2단 배근이 적용되었습니다.")
            detailed_steps['fallback_rebar_size'] = "D25"
            detailed_steps['fallback_n'] = n_D25
            detailed_steps['fallback_As_provided'] = As_provided
            detailed_steps['selected_rebar_diameter'] = d_b_D25  # C2: 처짐용 d_c 정밀화

        detailed_steps['As_provided'] = As_provided
        detailed_steps['rebar_string'] = rebar_string
        detailed_steps['layer'] = layer

        return rebar_string, As_provided, layer, warnings, detailed_steps

    def calculate_deflection(self, As_provided_bot, As_provided_top, d_c_override=None):
        """
        KDS 41 20 30 4.3에 따른 처짐 계산 (강접합 고정단 보 기준).

        단기처짐: δ = wL⁴/(384·Ec·Ie)  [고정-고정 보, 등분포하중]
        장기처짐: λ_Δ·δ_DL  [KDS 41 20 30 4.3.4]

        Args:
            As_provided_bot: 실제 배근된 하부 주근 면적 (mm²)
            As_provided_top: 실제 배근된 상부 주근 면적 (mm²)
            d_c_override: 피복+늑근+주근반경 합계 (mm). None이면 D25 기준 기본값 사용.
                          C2 수정: calculation_manager에서 실제 배근 직경 기반으로 전달.
        Returns:
            처짐 계산 상세 결과 dict
        """
        steps = {}
        b    = self.b_beam          # mm
        h    = self.h_beam          # mm
        L    = self.L_beam * 1000.0 # mm (self.L_beam은 m 단위)
        fc_k = self.fc_k            # MPa

        # ── 1. 재료 특성 ──────────────────────────────────────────────
        Ec   = 8500.0 * (fc_k + 4.0) ** (1.0 / 3.0)  # MPa  (KDS 41 20 00)
        fr   = 0.63 * np.sqrt(fc_k)                   # MPa  (파괴계수)
        Es   = 200_000.0                               # MPa
        n    = Es / Ec                                 # 탄성계수비 (실수 사용, KDS 비규정사항)
        steps.update({'Ec': Ec, 'fr': fr, 'n': n})

        # ── 2. 총단면(비균열) 특성 ────────────────────────────────────
        Ig   = b * h ** 3 / 12.0   # mm⁴
        yt   = h / 2.0              # mm (중심축 ~ 인장연단)
        M_cr = fr * Ig / yt         # N·mm (균열 모멘트)
        steps.update({'Ig': Ig, 'yt': yt, 'M_cr_Nmm': M_cr, 'M_cr_kNm': M_cr / 1e6})

        # ── 3. 균열 단면 2차모멘트 Icr ───────────────────────────────
        # d_c: 실제 배근 직경 기반 정밀값 (C2 수정 — calculation_manager에서 전달)
        # d_c_override가 없으면 D25 기준 기본값 (40+10+12.7≈62.7mm) 사용
        d_c     = d_c_override if d_c_override is not None else (40.0 + 10.0 + 25.4 / 2.0)
        d       = h - d_c                     # mm 유효깊이
        d_prime = d_c                         # mm 압축철근 중심깊이

        # 인장철근비 (단근 근사로 중립축 산정)
        rho  = max(As_provided_bot / (b * d), 1e-6)
        k_v  = np.sqrt(2 * n * rho + (n * rho) ** 2) - n * rho
        x_cr = k_v * d                        # mm 균열 중립축 깊이

        Icr  = b * x_cr ** 3 / 3.0 + n * As_provided_bot * (d - x_cr) ** 2
        # 압축철근 기여 (중립축 아래인 경우에만)
        if As_provided_top > 0 and x_cr > d_prime:
            Icr += (n - 1) * As_provided_top * (x_cr - d_prime) ** 2
        steps.update({'d': d, 'rho': rho, 'x_cr': x_cr, 'Icr': Icr})

        # ── 4. 서비스 하중 (비계수, kN/m = N/mm) ─────────────────────
        w_DL    = self.w_DL_unfactored   # N/mm
        w_LL    = self.w_LL_unfactored   # N/mm
        w_total = w_DL + w_LL
        steps.update({'w_DL': w_DL, 'w_LL': w_LL, 'w_total': w_total})

        # ── 5. 서비스 모멘트 (강접합 고정단) ──────────────────────────
        # 지점부: M = wL²/12,  중앙부: M = wL²/24
        M_a_sup    = w_total * L ** 2 / 12.0  # N·mm (지점부)
        M_a_mid    = w_total * L ** 2 / 24.0  # N·mm (중앙부)
        M_a_DL_sup = w_DL    * L ** 2 / 12.0  # N·mm (지점부 DL)
        M_a_DL_mid = w_DL    * L ** 2 / 24.0  # N·mm (중앙부 DL)
        steps.update({'M_a_kNm': M_a_sup / 1e6, 'M_a_DL_kNm': M_a_DL_sup / 1e6,
                      'M_a_mid_kNm': M_a_mid / 1e6, 'M_a_DL_mid_kNm': M_a_DL_mid / 1e6})

        # ── 6. 유효 단면 2차모멘트 Ie (Branson 공식 + 가중평균) ──────
        # 양단 고정보: Ie_avg = 0.70·Ie_mid + 0.30·Ie_support (KDS 41 20 30)
        def compute_Ie(M_val):
            if M_val <= 0 or M_val <= M_cr:
                return Ig
            ratio = min(M_cr / M_val, 1.0)
            return min(ratio ** 3 * Ig + (1.0 - ratio ** 3) * Icr, Ig)

        Ie_sup   = compute_Ie(M_a_sup)
        Ie_mid   = compute_Ie(M_a_mid)
        Ie_total = 0.70 * Ie_mid + 0.30 * Ie_sup  # 가중평균

        Ie_DL_sup = compute_Ie(M_a_DL_sup)
        Ie_DL_mid = compute_Ie(M_a_DL_mid)
        Ie_DL     = 0.70 * Ie_DL_mid + 0.30 * Ie_DL_sup

        steps.update({'Ie_total': Ie_total, 'Ie_DL': Ie_DL,
                      'Ie_sup': Ie_sup, 'Ie_mid': Ie_mid,
                      'Ie_DL_sup': Ie_DL_sup, 'Ie_DL_mid': Ie_DL_mid,
                      'cracked': M_a_sup > M_cr})

        # ── 7. 단기(즉시) 처짐  δ = wL⁴/(384·Ec·Ie) ─────────────────
        delta_total_i = w_total * L ** 4 / (384.0 * Ec * Ie_total)  # mm
        delta_DL_i    = w_DL    * L ** 4 / (384.0 * Ec * Ie_DL)     # mm
        # 활하중 기여분 = 전체 - 사하중 (Ie 차이 반영)
        delta_LL_i    = max(delta_total_i - delta_DL_i, 0.0)         # mm
        steps.update({'delta_total_i': delta_total_i,
                      'delta_DL_i'   : delta_DL_i,
                      'delta_LL_i'   : delta_LL_i})

        # ── 8. 장기처짐  λ_Δ·(δ_DL + α·δ_LL)  (KDS 41 20 30 4.3.4) ──
        xi           = 2.0  # 60개월(5년) 이상 지속하중
        rho_prime    = As_provided_top / (b * d) if As_provided_top > 0 else 0.0
        lambda_delta = xi / (1.0 + 50.0 * rho_prime)
        alpha_sus    = 0.25  # 활하중의 지속 비율 (주거/사무: 0.25, KDS 41 20 30)
        delta_long   = lambda_delta * (delta_DL_i + alpha_sus * delta_LL_i)  # 추가 장기처짐 (mm)
        steps.update({'xi': xi, 'rho_prime': rho_prime,
                      'lambda_delta': lambda_delta, 'alpha_sus': alpha_sus,
                      'delta_long': delta_long})

        # ── 9. 허용처짐 (KDS 41 20 30 Table 4.3-1) ───────────────────
        # 활하중 즉시처짐 허용값
        delta_allow_LL     = L / 360.0
        # 장기처짐 + 활하중 즉시처짐 허용값
        delta_allow_total  = L / 240.0  # 비구조부재 손상 미고려
        delta_allow_strict = L / 480.0  # 비구조부재 손상 고려 (엄격 기준)
        delta_check        = delta_long + delta_LL_i  # 검토 총처짐
        steps.update({'delta_check'        : delta_check,
                      'delta_allow_LL'     : delta_allow_LL,
                      'delta_allow_total'  : delta_allow_total,
                      'delta_allow_strict' : delta_allow_strict})

        # ── 10. 판정 ─────────────────────────────────────────────────
        check_LL     = delta_LL_i  <= delta_allow_LL
        check_total  = delta_check <= delta_allow_total
        check_strict = delta_check <= delta_allow_strict
        ok = check_LL and check_total
        steps.update({'check_LL'    : check_LL,
                      'check_total' : check_total,
                      'check_strict': check_strict,
                      'ok'          : ok})

        # 처짐비 (여유율 확인용)
        steps['ratio_LL']    = delta_LL_i  / delta_allow_LL   if delta_allow_LL    > 0 else None
        steps['ratio_total'] = delta_check / delta_allow_total if delta_allow_total > 0 else None

        return steps

    # ─────────────────────────────────────────────────────────────────────
    # IMF 보 내진 상세 검토 (KDS 41 17 4.4)
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def calculate_imf_beam_detailing(h_beam, d, db_main, db_stirrup,
                                      As_top, As_bot, s_stirrup):
        """
        KDS 41 17 4.4 IMF 보 상세 검토.

        Returns:
            dict {l_ph, s_max_hinge, s_hinge_ok, bot_ratio_ok, steps, warnings}
        """
        warnings = []
        steps = {}

        # 1. 소성힌지 구간 길이
        l_ph = 2.0 * h_beam
        steps['l_ph'] = l_ph

        # 2. 힌지구간 늑근 최대간격
        s_max_hinge = min(d / 4.0, 8.0 * db_main, 24.0 * db_stirrup, 300.0)
        steps['s_max_hinge'] = s_max_hinge
        s_hinge_ok = s_stirrup <= s_max_hinge
        steps['s_hinge_ok'] = s_hinge_ok
        steps['s_stirrup'] = s_stirrup

        if not s_hinge_ok:
            warnings.append(
                f"경고: 소성힌지구간 늑근간격 {s_stirrup:.0f}mm > "
                f"최대허용 {s_max_hinge:.0f}mm — 힌지구간 늑근 간격 축소 필요")

        # 3. 첫 늑근 위치: 50mm from column face
        steps['first_stirrup'] = 50.0

        # 4. 하부근 ≥ 0.5 × 상부근 (접합부면)
        bot_ratio = As_bot / As_top if As_top > 0 else 1.0
        bot_ratio_ok = bot_ratio >= 0.5
        steps['bot_ratio'] = bot_ratio
        steps['bot_ratio_ok'] = bot_ratio_ok

        if not bot_ratio_ok:
            warnings.append(
                f"경고: 하부근/상부근 비율 {bot_ratio:.2f} < 0.5 — "
                "접합부면 하부근 보강 필요")

        return {
            'l_ph': l_ph,
            's_max_hinge': s_max_hinge,
            's_hinge_ok': s_hinge_ok,
            'bot_ratio_ok': bot_ratio_ok,
            'steps': steps,
            'warnings': warnings,
        }

