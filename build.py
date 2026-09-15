import shutil
from datetime import datetime
from pathlib import Path

import feedparser
import gspread
import yaml
from google.oauth2.service_account import Credentials
from jinja2 import Environment, FileSystemLoader


BASE_DIR = Path(__file__).parent

config_file = BASE_DIR / "config" / "site.yaml"
credentials_file = BASE_DIR / "credentials" / "google-service-account.json"
template_dir = BASE_DIR / "templates"
output_dir = BASE_DIR / "public"


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

departments = load_sheet(
    spreadsheet,
    "departments"
)

colleges = load_sheet(
    spreadsheet,
    "colleges"
)

librarians = load_sheet(
    spreadsheet,
    "librarians"
)

journals = load_sheet(
    spreadsheet,
    "journals"
)

department_journals = load_sheet(
    spreadsheet,
    "department_journals"
)

databases = load_sheet(
    spreadsheet,
    "databases"
)

department_databases = load_sheet(
    spreadsheet,
    "department_databases"
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