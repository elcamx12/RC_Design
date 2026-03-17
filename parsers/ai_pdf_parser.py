"""
ai_pdf_parser.py
────────────────
pdfplumber로 텍스트 추출 → Claude API(Haiku)로 구조화 데이터 추출

사용:
    from ai_pdf_parser import parse_pdf_with_ai
    result = parse_pdf_with_ai("path/to/file.pdf", api_key="sk-ant-...")
"""
import os
import re
import json

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

try:
    import anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# 관련 페이지 필터 키워드
# ─────────────────────────────────────────────────────────────────────────────
RELEVANT_KW = [
    'Beam Span', 'BeST.RC', 'BeST.Steel',
    'Column Height', 'Moment (Mu)', 'midas Gen RC',
    'Design Force', 'Factored Shear', 'Bending Moment Capacity',
    'MEMBER :', 'Design Condition',
]

# ─────────────────────────────────────────────────────────────────────────────
# AI 시스템 프롬프트
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 구조 설계 계산서(MIDAS Gen, BeST.RC, BeST.Steel 소프트웨어 출력물)에서
부재 정보를 추출하는 전문가입니다.

주어진 텍스트에서 모든 구조 부재의 설계 정보를 추출하여 반드시 순수 JSON만 반환하세요.
마크다운 코드블록(```)을 절대 사용하지 말고, JSON 텍스트만 출력하세요.

=== 반환 JSON 스키마 ===
{
  "members": [
    {
      "name": "부재명(문자열)",
      "type": "beam | column | slab | foundation | base_plate",
      "software": "MIDAS Gen | BeST.RC | BeST.Steel",
      "section": {
        "B_mm": null,
        "H_mm": null,
        "Cx_mm": null,
        "Cy_mm": null
      },
      "material": {
        "fck_MPa": null,
        "fy_MPa": null,
        "fys_MPa": null
      },
      "geometry": {
        "span_m": null,
        "height_m": null
      },
      "design_forces": {
        "Mu_neg_I_kNm": null,
        "Mu_neg_MID_kNm": null,
        "Mu_neg_J_kNm": null,
        "Mu_pos_I_kNm": null,
        "Mu_pos_MID_kNm": null,
        "Mu_pos_J_kNm": null,
        "Vu_I_kN": null,
        "Vu_MID_kN": null,
        "Vu_J_kN": null,
        "Pu_kN": null,
        "Mux_kNm": null,
        "Muy_kNm": null
      },
      "load_combinations": {
        "Mu_neg_lc": null,
        "Mu_pos_lc": null,
        "Vu_lc": null,
        "axial_lc": null
      },
      "rebar": {
        "top": null,
        "bottom": null,
        "stirrup": null
      },
      "check_ratio": {
        "moment": null,
        "shear": null,
        "axial": null
      }
    }
  ]
}

=== 중요 규칙 ===
1. 단위 변환:
   - MIDAS Gen은 KPa 사용 → MPa로 변환 (÷1000)
     예: fck=30000 KPa → fck_MPa=30, fy=500000 KPa → fy_MPa=500
   - BeST.RC/BeST.Steel은 N/mm² 직접 사용 = MPa
2. 보(beam)의 Moment는 END-I / MID / END-J 세 위치 값을 각각 추출
3. (-) 부 모멘트와 (+) 정 모멘트를 구분하여 추출
4. 하중조합 번호는 배열로 저장. 예: [11, 25, 15]
5. 같은 부재가 MIDAS Gen과 BeST.RC 두 형식으로 나오면 정보를 합쳐서 하나의 객체로 반환
6. 텍스트에 없는 값은 null로 표시
7. 기둥 단면: MIDAS Gen은 단면 치수가 텍스트에 없을 수 있음 → null 허용
8. 배근 정보: "3-D19", "2-D10@125" 등을 문자열로 저장
9. 검토비(Check Ratio): Mu/φMn, Vu/(φVc+φVs) 등 값을 check_ratio에 저장
"""


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 함수
# ─────────────────────────────────────────────────────────────────────────────

def extract_relevant_pages(pdf_path: str) -> tuple:
    """pdfplumber로 관련 페이지 텍스트 추출"""
    if not PDFPLUMBER_OK:
        raise ImportError("pdfplumber 미설치: pip install pdfplumber")

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if any(kw in text for kw in RELEVANT_KW):
                pages.append({"page": i + 1, "text": text})

    return pages, total


def parse_pdf_with_ai(pdf_path: str, api_key: str = None) -> dict:
    """
    PDF 구조계산서를 AI로 파싱.

    반환 dict:
        members      : 추출된 부재 리스트
        pages_total  : PDF 전체 페이지 수
        pages_used   : 분석에 사용된 페이지 수
        raw_text     : AI에 전달한 전체 텍스트
        raw_response : AI 원본 응답
        error        : 오류 메시지 (없으면 None)
    """
    if not ANTHROPIC_OK:
        raise ImportError("anthropic 미설치: pip install anthropic")

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    # 1. 관련 페이지 추출
    pages, total = extract_relevant_pages(pdf_path)
    if not pages:
        return {
            "members": [], "pages_total": total, "pages_used": 0,
            "raw_text": "", "raw_response": "관련 페이지 없음", "error": None,
        }

    combined = "\n\n".join(
        f"--- 페이지 {p['page']} ---\n{p['text']}" for p in pages
    )

    # 2. Claude API 호출
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"다음 구조계산서 텍스트에서 모든 부재 정보를 추출하세요:\n\n{combined}",
        }],
    )
    raw_response = message.content[0].text

    # 3. JSON 파싱 (마크다운 코드블록 제거 후)
    json_text = re.sub(r"```(?:json)?\s*", "", raw_response).strip("`").strip()
    data, error = _safe_json_parse(json_text)

    return {
        "members":      data.get("members", []),
        "pages_total":  total,
        "pages_used":   len(pages),
        "raw_text":     combined,
        "raw_response": raw_response,
        "error":        error,
    }


def _safe_json_parse(text: str) -> tuple:
    """JSON 파싱, 실패 시 {} 반환 + 오류 메시지"""
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        # { } 범위 찾아서 재시도
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group(0)), None
            except Exception:
                pass
        return {}, f"JSON 파싱 실패:\n{text[:300]}"


# ─────────────────────────────────────────────────────────────────────────────
# CLI 테스트
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python ai_pdf_parser.py <PDF경로> [API_KEY]")
        sys.exit(1)

    key = sys.argv[2] if len(sys.argv) > 2 else None
    result = parse_pdf_with_ai(sys.argv[1], api_key=key)

    print(f"\n사용 페이지: {result['pages_used']}/{result['pages_total']}")
    print(f"추출 부재 수: {len(result['members'])}\n")
    for m in result['members']:
        print(f"  [{m.get('type','?'):8s}] {m.get('name','?'):12s} "
              f"| {m.get('software','?')} "
              f"| B={m.get('section',{}).get('B_mm')} H={m.get('section',{}).get('H_mm')}")
    if result.get('error'):
        print(f"\n⚠ {result['error']}")
