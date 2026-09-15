import os
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# 기본 설정
# --------------------------------------------------

load_dotenv()

KCI_API_KEY = os.getenv("KCI_API_KEY")

if not KCI_API_KEY:
    raise RuntimeError("KCI_API_KEY가 설정되어 있지 않습니다.")

KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"

TARGET_TITLE = "경영교육연구"
TARGET_ISSN = "1598-8651"
TARGET_YEAR = "2025"


# --------------------------------------------------
# ISSN 비교용
# 1598-8651 / 15988651을 동일하게 처리
# --------------------------------------------------

def normalize_issn(value):
    return (value or "").replace("-", "").strip().upper()


# --------------------------------------------------
# 1. 저널명으로 citation 검색
# --------------------------------------------------

citation_params = {
    "apiCode": "citation",
    "key": KCI_API_KEY,
    "journal": TARGET_TITLE,
    "year": TARGET_YEAR,
    "years": "2",
    "page": "1",
    "displayCount": "100",
}

response = requests.get(
    KCI_API_URL,
    params=citation_params,
    timeout=30,
)

response.raise_for_status()

root = ET.fromstring(response.text)

total = root.findtext(".//outputData/result/total")

print(f"저널명 검색 결과: {total}건")


# --------------------------------------------------
# 2. 검색된 저널들을 하나씩 확인
# --------------------------------------------------

matched = False

for record in root.findall(".//outputData/record"):

    journal_info = record.find("journalInfo")

    if journal_info is None:
        continue

    kci_journal_id = journal_info.get("journal-id")
    journal_name = journal_info.findtext("journal-name") or ""
    publisher_name = journal_info.findtext("publisher-name") or ""

    citation_info = record.find("citationInfo")

    citation_if = ""

    if citation_info is not None:
        citation_if = citation_info.findtext("impactFactor") or ""

    print()
    print("----------------------------------------")
    print(f"후보 저널명: {journal_name}")
    print(f"발행기관: {publisher_name}")
    print(f"KCI journal-id: {kci_journal_id}")
    print(f"citation IF: {citation_if}")

    if not kci_journal_id:
        continue


    # --------------------------------------------------
    # 3. journal-id로 citationDetail 조회
    # --------------------------------------------------

    detail_params = {
        "apiCode": "citationDetail",
        "key": KCI_API_KEY,
        "id": kci_journal_id,
    }

    detail_response = requests.get(
        KCI_API_URL,
        params=detail_params,
        timeout=30,
    )

    detail_response.raise_for_status()

    detail_root = ET.fromstring(detail_response.text)

    detail_journal = detail_root.find(".//outputData/record/journalInfo")

    if detail_journal is None:
        print("citationDetail 결과 없음")
        continue

    issn = detail_journal.findtext("issn") or ""
    eissn = detail_journal.findtext("eissn") or ""

    registration = (
        detail_journal.findtext("registration/kci-registration")
        or ""
    )

    print(f"ISSN: {issn}")
    print(f"eISSN: {eissn}")
    print(f"KCI 등재정보: {registration}")


    # --------------------------------------------------
    # 4. 우리 시트 ISSN과 최종 비교
    # --------------------------------------------------

    target_issn = normalize_issn(TARGET_ISSN)

    issn_match = (
        target_issn == normalize_issn(issn)
        or target_issn == normalize_issn(eissn)
    )

    if not issn_match:
        print("→ ISSN 불일치")
        continue

    print("→ ISSN 일치")


    # --------------------------------------------------
    # 5. citationDetail에서 2025년 IF 확인
    # --------------------------------------------------

    detail_if = ""

    for citation_index in detail_root.findall(
        ".//journal-citation-index-history/journal-citation-index"
    ):
        if citation_index.get("year") == TARGET_YEAR:
            detail_if = citation_index.findtext("impactFactor") or ""
            break

    # 상세정보에 없으면 citation 결과의 IF 사용
    final_if = detail_if or citation_if


    # --------------------------------------------------
    # 최종 결과
    # --------------------------------------------------

    print()
    print("========================================")
    print("최종 매칭 성공")
    print("========================================")
    print(f"저널명: {journal_name}")
    print(f"ISSN: {issn}")
    print(f"eISSN: {eissn}")
    print(f"발행기관: {publisher_name}")
    print(f"KCI 등재정보: {registration}")
    print(f"KCI IF ({TARGET_YEAR}): {final_if}")
    print(f"KCI journal-id: {kci_journal_id}")

    matched = True
    break


if not matched:
    print()
    print("ISSN이 일치하는 KCI 저널을 찾지 못했습니다.")