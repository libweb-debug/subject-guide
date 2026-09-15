import shutil
from datetime import datetime
from pathlib import Path
import feedparser
import gspread
import yaml
from google.oauth2.service_account import Credentials
from jinja2 import Environment, FileSystemLoader
import os
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

import subprocess

BASE_DIR = Path(__file__).parent

config_file = BASE_DIR / "config" / "site.yaml"
credentials_file = BASE_DIR / "credentials" / "google-service-account.json"
template_dir = BASE_DIR / "templates"
output_dir = BASE_DIR / "public"

# .env 파일의 환경변수 로드
load_dotenv(BASE_DIR / ".env")

# 도서관 신착도서 API 키
library_api_key = os.getenv("LIBRARY_API_KEY")
if not library_api_key:
    raise RuntimeError("LIBRARY_API_KEY가 설정되어 있지 않습니다.")

# -------------------------
# Google Sheets 연결
# -------------------------

def get_spreadsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    credentials = Credentials.from_service_account_file(
        credentials_file,
        scopes=scopes
    )

    client = gspread.authorize(credentials)

    return client.open("Subject Guide Data")


# -------------------------
# 원하는 시트 읽기
# -------------------------

def load_sheet(spreadsheet, sheet_name):
    worksheet = spreadsheet.worksheet(sheet_name)

    return worksheet.get_all_records()


# -------------------------
# 공지사항 RSS
# -------------------------

def fetch_notices(config):
    rss_url = config["notice"]["rss_url"]
    detail_url = config["notice"]["detail_url"]
    notice_count = config["notice"]["count"]

    feed = feedparser.parse(rss_url)

    notices = []

    for entry in feed.entries[:notice_count]:

        guid = entry.get("id", "")

        post_id = guid.split("p=")[-1]

        notice_url = detail_url.format(
            post_id=post_id
        )

        published = entry.get("published", "")

        try:
            published_date = datetime.strptime(
                published,
                "%a, %d %b %Y %H:%M:%S %z"
            ).strftime("%Y-%m-%d")

        except ValueError:
            published_date = published

        notices.append({
            "title": entry.get("title", ""),
            "date": published_date,
            "url": notice_url,
        })

    return notices

# -------------------------
# 주제별 신착도서
# -------------------------

def fetch_new_arrivals(api_key, subjects):

    api_url = "https://libapi.donga.ac.kr/dalis/SLIMA.openapi2.SubjectNew.cls"

    books_by_recn = {}

    for subject in subjects:
        parent_subject = str(
            subject.get("parent_subject", "")
        ).strip()

        child_subject = str(
            subject.get("child_subject", "")
        ).strip()

        # 대주제 또는 소주제가 비어 있으면 건너뜀
        if not parent_subject or not child_subject:
            continue

        params = {
            "key": api_key,
            "loc": "DALIS",
            "version": "1.0",
            "pNCode": parent_subject,
            "pWNCode": child_subject,
        }

        # ----------------------------------------------------
        # 신착도서 API 호출
        #
        # 해당 API는 Python requests/urllib 호출 시
        # 연결이 강제로 종료되는 문제가 있어,
        # 실제 정상 호출이 확인된 curl을 사용합니다.
        # ----------------------------------------------------

        curl_command = shutil.which("curl.exe") or shutil.which("curl")

        if not curl_command:
            print("신착도서 API 호출 실패: curl을 찾을 수 없습니다.")
            continue


        # ------------------------------------------------------------
        # curl 설정
        # ------------------------------------------------------------
        # API 키를 명령행 인자로 넘기지 않고
        # curl의 표준입력(stdin)으로 전달합니다.
        # ------------------------------------------------------------

        curl_config = f"""
        silent
        show-error
        fail
        location
        get
        max-time = 10

        url = "{api_url}"

        data-urlencode = "key={api_key}"
        data-urlencode = "loc=DALIS"
        data-urlencode = "version=1.0"
        data-urlencode = "pNCode={parent_subject}"
        data-urlencode = "pWNCode={child_subject}"
        """


        try:
            result = subprocess.run(
                [
                    curl_command,
                    "--config",
                    "-"
                ],
                input=curl_config,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=True,
            )

            xml_body = result.stdout

        except subprocess.TimeoutExpired:
            print(
                f"신착도서 API 시간 초과 "
                f"({parent_subject} / {child_subject})"
            )
            continue

        except subprocess.CalledProcessError as e:
            print(
                f"신착도서 API 호출 실패 "
                f"({parent_subject} / {child_subject}): "
                f"{e.stderr.strip()}"
            )
            continue

        try:
            root = ET.fromstring(xml_body)

        except ET.ParseError as e:
            print(
                f"신착도서 XML 파싱 실패 "
                f"({parent_subject} / {child_subject}): {e}"
            )
            continue

        # API 결과코드 확인
        result_code = root.findtext(
            "./head/resultCode",
            default="",
        ).strip()

        if result_code and result_code.upper() != "OK":
            print(
                f"신착도서 API 오류 "
                f"({parent_subject} / {child_subject}): "
                f"{result_code}"
            )
            continue

        # metadata/item 반복
        for item in root.findall("./metadata/item"):

            recn = (
                item.findtext("recn", default="")
                or ""
            ).strip()

            if not recn:
                continue

            # 여러 분류에서 같은 책이 조회될 수 있으므로
            # recn 기준으로 중복 제거
            if recn in books_by_recn:
                continue

            books_by_recn[recn] = {
                "recn": recn,
                "title": (
                    item.findtext(
                        "stitle",
                        default=""
                    )
                    or ""
                ).strip(),

                "author": (
                    item.findtext(
                        "author",
                        default=""
                    )
                    or ""
                ).strip(),

                "publisher": (
                    item.findtext(
                        "publisher",
                        default=""
                    )
                    or ""
                ).strip(),

                "pubyear": (
                    item.findtext(
                        "pubyear",
                        default=""
                    )
                    or ""
                ).strip(),

                "url": (
                    "https://library.donga.ac.kr/"
                    "resource/library-catalog/"
                    f"?app=mirtech&mod=detail&record_id={recn}"
                ),
            }

    books = list(books_by_recn.values())

    # 출판년도 최신순
    books.sort(
        key=lambda book: int(book["pubyear"])
        if str(book["pubyear"]).isdigit()
        else 0,
        reverse=True,
    )

    # 최대 9권
    return books[:9]

# -------------------------
# 사이트 설정 읽기
# -------------------------

with open(config_file, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


# -------------------------
# Google Sheets 연결
# -------------------------

spreadsheet = get_spreadsheet()


# -------------------------
# 각 시트 읽기
# -------------------------

departments = load_sheet(spreadsheet, "departments")

colleges = load_sheet(spreadsheet, "colleges")

librarians = load_sheet(spreadsheet, "librarians")

journals = load_sheet(spreadsheet, "journals")

department_journals = load_sheet(spreadsheet, "department_journals")

databases = load_sheet(spreadsheet, "databases")

department_databases = load_sheet(spreadsheet, "department_databases")

book_subjects = load_sheet(spreadsheet, "book_subjects")

new_arrival_subjects = load_sheet(spreadsheet, "new_arrival_subjects")

# ============================================================
# 학과별 주제가이드 목록 페이지용 데이터 구성
# ------------------------------------------------------------
# Google Sheets의 colleges, departments 데이터를 이용해서
# "단과대학별 학과 목록" 형태로 묶어줍니다.
# 이 college_groups 데이터는 나중에 guide-list.html에서 사용합니다.
# ============================================================

college_groups = []


# ------------------------------------------------------------
# active가 Y인 단과대학만 가져옵니다.
# sort_order 값이 작은 단과대학부터 화면에 표시하기 위해 정렬합니다.
# ------------------------------------------------------------

active_colleges = [
    college
    for college in colleges
    if str(college.get("active", "")).upper() == "Y"
]

active_colleges.sort(
    key=lambda college: int(
        college.get("sort_order", 9999)
    )
)


# ------------------------------------------------------------
# 각 단과대학에 속한 학과들을 찾아서 묶습니다.
# ------------------------------------------------------------

for college in active_colleges:

    # 현재 단과대학의 college_id
    current_college_id = college.get("college_id")

    # 현재 단과대학에 속하면서 active=Y인 학과만 선택
    college_departments = [
        department
        for department in departments
        if (
            department.get("college_id") == current_college_id
            and str(department.get("active", "")).upper() == "Y"
        )
    ]

    # 학과도 sort_order 순으로 정렬
    college_departments.sort(
        key=lambda department: int(
            department.get("sort_order", 9999)
        )
    )

    # 실제 학과가 있는 단과대학만 목록에 추가
    if college_departments:
        college_groups.append(
            {
                "college_id": current_college_id,
                "college_name": college.get("college_name", ""),
                "departments": college_departments,
            }
        )
# -------------------------
# ID로 빠르게 찾을 수 있도록 변환
# -------------------------

college_by_id = {
    row["college_id"]: row
    for row in colleges
    if str(row.get("active", "")).upper() == "Y"
}

librarian_by_id = {
    row["librarian_id"]: row
    for row in librarians
    if str(row.get("active", "")).upper() == "Y"
}

journal_by_id = {
    row["journal_id"]: row
    for row in journals
    if str(row.get("active", "")).upper() == "Y"
}

database_by_id = {
    row["database_id"]: row
    for row in databases
    if str(row.get("active", "")).upper() == "Y"
}
# -------------------------
# 공지사항
# -------------------------

notices = fetch_notices(config)

# -------------------------
# public 초기화
# -------------------------

if output_dir.exists():
    shutil.rmtree(output_dir)

output_dir.mkdir()


# -------------------------
# static 복사
# -------------------------

static_source = BASE_DIR / "static"
static_output = output_dir / "static"

shutil.copytree(
    static_source,
    static_output
)


# -------------------------
# Jinja2
# -------------------------

env = Environment(
    loader=FileSystemLoader(template_dir)
)


# -------------------------
# 생성할 페이지
# -------------------------

pages = [
    {
        "template": "guide/home.html",
        "folder": "",
    },
    {
        "template": "guide/book.html",
        "folder": "book",
    },
    {
        "template": "guide/journal.html",
        "folder": "journal",
    },
    {
        "template": "guide/database.html",
        "folder": "database",
    },
]

# ============================================================
# 학과별 주제가이드 전체 목록 페이지 생성
# ------------------------------------------------------------

# 목록 페이지용 템플릿 불러오기
guide_list_template = env.get_template(
    "guide-list.html"
)

# college_groups 데이터를 템플릿에 전달해서 HTML 생성
guide_list_html = guide_list_template.render(
    college_groups=college_groups,
    site=config,
)


# ------------------------------------------------------------
# 1. 사이트 루트용 페이지 생성
#    결과: public/index.html
#
#    접속 주소:
#    https://dlibguide.netlify.app/
# ------------------------------------------------------------

root_index_file = output_dir / "index.html"

root_index_file.write_text(
    guide_list_html,
    encoding="utf-8",
)


# ------------------------------------------------------------
# 2. /guide/ 경로용 페이지 생성
#    결과: public/guide/index.html
#
#    접속 주소:
#    https://dlibguide.netlify.app/guide/
# ------------------------------------------------------------

guide_index_file = (
    output_dir
    / "guide"
    / "index.html"
)

# guide 폴더가 없으면 생성
guide_index_file.parent.mkdir(
    parents=True,
    exist_ok=True,
)

# HTML 파일 저장
guide_index_file.write_text(
    guide_list_html,
    encoding="utf-8",
)


# -------------------------
# 학과별 사이트 생성
# -------------------------

for department in departments:

    if str(
        department.get("active", "")
    ).upper() != "Y":
        continue


    # 학과에 연결된 단과대 찾기
    college = college_by_id.get(
        department.get("college_id", ""),
        {}
    )


    # 학과에 연결된 담당사서 찾기
    librarian = librarian_by_id.get(
        department.get("librarian_id", ""),
        {}
    )


    department_slug = department["slug"]

    guide_root = (
        output_dir
        / "guide"
        / department_slug
    )

    department_id = department["department_id"]

    # ============================================================
    # 학과별 신착도서 분류 조회
    # ============================================================
    department_new_arrival_subjects = [
        row
        for row in new_arrival_subjects
        if row.get("department_id") == department_id
    ]


    # ============================================================
    # 신착도서 API 조회
    # ============================================================

    new_arrivals = fetch_new_arrivals(
        library_api_key,
        department_new_arrival_subjects,
    )

    # ============================================================
    # 학과별 주제별 도서 브라우징 데이터 구성
    # ------------------------------------------------------------
    department_book_subjects = [
        row
        for row in book_subjects
        if row.get("department_id") == department_id
    ]

    # ------------------------------------------------------------
    # call_number 기준으로 정렬
    # ------------------------------------------------------------

    def call_number_sort_key(row):
        try:
            return float(row.get("call_number", 999999))
        except (TypeError, ValueError):
            return 999999


    department_book_subjects.sort(
        key=call_number_sort_key
    )

 # 저널
    department_journal_rows = [
        row
        for row in department_journals
        if (
            row.get("department_id") == department_id
            and str(row.get("active", "")).upper() == "Y"
        )
    ]

    department_journal_rows.sort(
    key=lambda row: int(row.get("sort_order", 9999))
    )

    department_journal_list = []

    for relation in department_journal_rows:
        journal = journal_by_id.get(
            relation.get("journal_id")
        )

        if journal:
            department_journal_list.append(journal)

    domestic_journals = [
            journal
            for journal in department_journal_list
            if journal.get("region") == "국내"
        ]

    international_journals = [
            journal
            for journal in department_journal_list
            if journal.get("region") == "국외"
        ]

 # DB
    department_database_rows = [
        row
        for row in department_databases
        if (
            row.get("department_id") == department_id
            and str(row.get("active", "")).upper() == "Y"
        )
    ]

    department_database_rows.sort(
                key=lambda row: int(row.get("sort_order", 9999))
        )

    department_database_list = []

    for relation in department_database_rows:

        database = database_by_id.get(
            relation.get("database_id")
        )

        if database:

            item = dict(database)

            item["category"] = relation.get("category","")
            department_database_list.append(item)   

    major_databases = [
    db
    for db in department_database_list
    if db.get("category") == "전공"
    ]

    domestic_databases = [
        db
        for db in department_database_list
        if db.get("category") == "국내"
    ]

    international_databases = [
        db
        for db in department_database_list
        if db.get("category") == "국외"
    ]           
    # 템플릿에 전달할 전체 데이터
    data = {
        "site": config,
        "notices": notices,

        "department": department,
        "college": college,
        "librarian": librarian,

        "domestic_journals": domestic_journals,
        "international_journals": international_journals,

        "major_databases": major_databases,
        "domestic_databases": domestic_databases,
        "international_databases": international_databases,

        "book_subjects": department_book_subjects,

        "new_arrivals": new_arrivals,

        # 기존 base.html과 호환하기 위해 유지
        "department_name": department.get(
            "department_name",
            ""
        ),

        "department_slug": department.get(
            "slug",
            ""
        ),
    }


    for page in pages:

        template = env.get_template(
            page["template"]
        )

        html = template.render(**data)


        if page["folder"] == "":
            output_file = (
                guide_root
                / "index.html"
            )

        else:
            output_file = (
                guide_root
                / page["folder"]
                / "index.html"
            )


        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )


        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(html)


        print(
            f"생성 완료: "
            f"{department['department_name']} "
            f"→ {output_file}"
        )