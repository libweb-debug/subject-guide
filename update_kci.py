import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


BASE_DIR = Path(__file__).parent

credentials_file = (
    BASE_DIR
    / "credentials"
    / "google-service-account.json"
)

load_dotenv(BASE_DIR / ".env")

KCI_API_KEY = os.getenv("KCI_API_KEY")

if not KCI_API_KEY:
    raise RuntimeError(
        "KCI_API_KEY가 설정되어 있지 않습니다."
    )

KCI_API_URL = (
    "https://open.kci.go.kr/"
    "po/openapi/openApiSearch.kci"
)

KCI_YEAR = "2025"
KCI_YEARS = "2"


# --------------------------------------------------
# Google Sheets 연결
# --------------------------------------------------

def get_spreadsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = (
        Credentials.from_service_account_file(
            credentials_file,
            scopes=scopes,
        )
    )

    client = gspread.authorize(credentials)

    return client.open("Subject Guide Data")


# --------------------------------------------------
# ISSN 정규화
# --------------------------------------------------

def normalize_issn(value):
    return (
        str(value or "")
        .replace("-", "")
        .strip()
        .upper()
    )


# --------------------------------------------------
# KCI citation 검색
# --------------------------------------------------

def search_kci_journal(title):
    params = {
        "apiCode": "citation",
        "key": KCI_API_KEY,
        "journal": title,
        "year": KCI_YEAR,
        "years": KCI_YEARS,
        "page": "1",
        "displayCount": "100",
    }

    response = requests.get(
        KCI_API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return ET.fromstring(response.text)


# --------------------------------------------------
# KCI citationDetail 조회
# --------------------------------------------------

def get_kci_detail(kci_journal_id):
    params = {
        "apiCode": "citationDetail",
        "key": KCI_API_KEY,
        "id": kci_journal_id,
    }

    response = requests.get(
        KCI_API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return ET.fromstring(response.text)


# --------------------------------------------------
# 저널 1건 KCI 정보 조회
# --------------------------------------------------

def get_kci_info(
    title,
    issn,
    saved_kci_journal_id="",
):
    title = str(title or "").strip()
    target_issn = normalize_issn(issn)

    saved_kci_journal_id = str(
        saved_kci_journal_id or ""
    ).strip()

    if not title or not target_issn:
        return None

        # --------------------------------------------------
    # 1. 기존 kci_journal_id가 있으면
    #    citation 검색을 생략하고 바로 상세조회
    # --------------------------------------------------

    if saved_kci_journal_id:

        detail_root = None

        try:
            detail_root = get_kci_detail(
                saved_kci_journal_id
            )

        except (
            requests.RequestException,
            ET.ParseError,
        ):
            print(
                f"KCI 저장 ID 조회 실패 → 재검색: "
                f"{title} / "
                f"{saved_kci_journal_id}"
            )

        if detail_root is not None:

            detail_journal = detail_root.find(
                ".//outputData/record/journalInfo"
            )

            if detail_journal is not None:

                kci_issn = (
                    detail_journal.findtext("issn")
                    or ""
                ).strip()

                kci_eissn = (
                    detail_journal.findtext("eissn")
                    or ""
                ).strip()

                issn_match = (
                    target_issn
                    == normalize_issn(kci_issn)
                    or target_issn
                    == normalize_issn(kci_eissn)
                )

                if issn_match:

                    registration = (
                        detail_journal.findtext(
                            "registration/"
                            "kci-registration"
                        )
                        or ""
                    ).strip()

                    detail_if = ""

                    for citation_index in (
                        detail_root.findall(
                            ".//journal-citation-index-history/"
                            "journal-citation-index"
                        )
                    ):
                        if (
                            citation_index.get("year")
                            == KCI_YEAR
                        ):
                            detail_if = (
                                citation_index.findtext(
                                    "impactFactor"
                                )
                                or ""
                            ).strip()

                            break

                    return {
                        "kci_if": detail_if,
                        "kci_registration": registration,
                        "kci_year": KCI_YEAR,
                        "kci_journal_id": (
                            saved_kci_journal_id
                        ),
                        "kci_eissn": kci_eissn,
                        "kci_updated_at": (
                            datetime.now()
                            .strftime("%Y-%m-%d")
                        ),
                    }

        # 저장된 ID가 잘못됐거나 ISSN이 맞지 않으면
        # 아래 citation 검색으로 내려가서 ID를 다시 찾음
        print(
            f"KCI journal-id 재검색: {title}"
        )

    # --------------------------------------------------
    # 2. kci_journal_id가 없거나
    #    기존 ID가 맞지 않으면 저널명으로 검색
    # --------------------------------------------------

    try:
        citation_root = search_kci_journal(title)

    except (
        requests.RequestException,
        ET.ParseError,
    ) as e:
        print(
            f"KCI citation 조회 실패: "
            f"{title} / {e}"
        )
        return None

    for record in citation_root.findall(
        ".//outputData/record"
    ):
        journal_info = record.find("journalInfo")

        if journal_info is None:
            continue

        kci_journal_id = (
            journal_info.get("journal-id")
            or ""
        ).strip()

        if not kci_journal_id:
            continue

        citation_info = record.find(
            "citationInfo"
        )

        citation_if = ""

        if citation_info is not None:
            citation_if = (
                citation_info.findtext(
                    "impactFactor"
                )
                or ""
            ).strip()

        try:
            detail_root = get_kci_detail(
                kci_journal_id
            )

        except (
            requests.RequestException,
            ET.ParseError,
        ) as e:
            print(
                f"KCI 상세 조회 실패: "
                f"{title} / "
                f"{kci_journal_id} / "
                f"{e}"
            )
            continue

        detail_journal = detail_root.find(
            ".//outputData/record/journalInfo"
        )

        if detail_journal is None:
            continue

        kci_issn = (
            detail_journal.findtext("issn")
            or ""
        ).strip()

        kci_eissn = (
            detail_journal.findtext("eissn")
            or ""
        ).strip()

        issn_match = (
            target_issn
            == normalize_issn(kci_issn)
            or target_issn
            == normalize_issn(kci_eissn)
        )

        if not issn_match:
            continue

        registration = (
            detail_journal.findtext(
                "registration/"
                "kci-registration"
            )
            or ""
        ).strip()

        detail_if = ""

        for citation_index in (
            detail_root.findall(
                ".//journal-citation-index-history/"
                "journal-citation-index"
            )
        ):
            if (
                citation_index.get("year")
                == KCI_YEAR
            ):
                detail_if = (
                    citation_index.findtext(
                        "impactFactor"
                    )
                    or ""
                ).strip()

                break

        final_if = (
            detail_if
            or citation_if
        )

        return {
            "kci_if": final_if,
            "kci_registration": registration,
            "kci_year": KCI_YEAR,
            "kci_journal_id": kci_journal_id,
            "kci_eissn": kci_eissn,
            "kci_updated_at": (
                datetime.now()
                .strftime("%Y-%m-%d")
            ),
        }

    return None


# --------------------------------------------------
# journals 시트 갱신
# --------------------------------------------------

def main():
    spreadsheet = get_spreadsheet()

    worksheet = spreadsheet.worksheet(
        "journals"
    )

    rows = worksheet.get_all_records(
    numericise_ignore=["all"]
)

    headers = worksheet.row_values(1)

    column_map = {
        name: index + 1
        for index, name in enumerate(headers)
    }

    required_columns = [
        "journal_id",
        "title",
        "issn",
        "region",
        "kci_if",
        "kci_registration",
        "kci_year",
        "kci_journal_id",
        "kci_eissn",
        "kci_updated_at",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in column_map
    ]

    if missing_columns:
        raise RuntimeError(
            "journals 시트에 필요한 컬럼이 없습니다: "
            + ", ".join(missing_columns)
        )

    for row_number, row in enumerate(
        rows,
        start=2,
    ):
        region = str(
            row.get("region", "")
        ).strip()

        if region != "국내":
            continue

        title = str(
            row.get("title", "")
        ).strip()

        issn = str(
            row.get("issn", "")
        ).strip()

        if not title or not issn:
            print(
                f"건너뜀: {title or '(제목 없음)'} "
                f"/ ISSN 없음"
            )
            continue

        print(
            f"KCI 조회 중: "
            f"{title} ({issn})"
        )

        kci_info = get_kci_info(
            title=title,
            issn=issn,
            saved_kci_journal_id=row.get(
                "kci_journal_id",
                "",
            ),
        )

        if not kci_info:
            print(
                f"KCI 매칭 실패: "
                f"{title} ({issn})"
            )
            continue

        updates = []

        for field_name, value in {
            "kci_if": kci_info["kci_if"],
            "kci_registration": (
                kci_info["kci_registration"]
            ),
            "kci_year": kci_info["kci_year"],
            "kci_journal_id": (
                kci_info["kci_journal_id"]
            ),
            "kci_eissn": (
                kci_info["kci_eissn"]
            ),
            "kci_updated_at": (
                kci_info["kci_updated_at"]
            ),
        }.items():

            cell = gspread.utils.rowcol_to_a1(
                row_number,
                column_map[field_name],
            )

            updates.append(
                {
                    "range": cell,
                    "values": [[value]],
                }
            )

        worksheet.batch_update(updates)

        print(
            f"갱신 완료: "
            f"{title} / "
            f"{kci_info['kci_registration']} / "
            f"IF {kci_info['kci_if']}"
        )

        # KCI 서버에 너무 빠르게 연속 요청하지 않도록
        # 짧은 간격을 둡니다.
        time.sleep(0.2)


if __name__ == "__main__":
    main()