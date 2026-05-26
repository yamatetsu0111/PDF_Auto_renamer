import os
import re
import csv
from pathlib import Path
from datetime import datetime
from pypdf import PdfReader
from dotenv import load_dotenv

# main.pyがあるフォルダの絶対パスを取得し、そこにある .env を確実に読み込む
current_dir = Path(__file__).parent
load_dotenv(verbose=True, dotenv_path=current_dir / ".env")

# ===== 設定 =====
# .env から文字列として取得し、Pathオブジェクトに変換（rglobなどを使うため必須）
MY_COMPANY_DIR = Path(os.environ.get("MY_COMPANY_DIR", "./data_systena"))
COMPANY_DIR = Path(os.environ.get("COMPANY_DIR", "./data_kojima"))

# .env からCSVログの出力先を取得
log_file_str = os.environ.get("LOG_FILE")
if log_file_str:
    LOG_FILE = Path(log_file_str)
else:
    # .envに書かれていない場合の予備（ユーザーのデスクトップに作成する）
    LOG_FILE = Path.home() / "Desktop" / "rename_log.csv"

# ===== 正規表現 =====
# 自社
EST_NO_FROM_NAME = re.compile(r"\((\d{6,})\)")
DATE_JP = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
VALID_NAME = re.compile(r"20\d{6}_.+_見積書_\d+\.pdf$")  # 見積書のみ対象

# 他社
COMPANY_PATTERN = re.compile(r"^([A-Z]{2}\d{4})")
COMPANY_DONE_PATTERN = re.compile(r"^[A-Z]{2}\d{4}_見積書_\d{8}\.pdf$")

# 件数
processed_count = 0

# ===== ログ =====
def write_log(src, dst, status, message):
    # 保存先フォルダが存在しない場合は、自動でフォルダを作成する（親切設計）
    if not LOG_FILE.parent.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
    exists = LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["日時", "元ファイル", "新ファイル", "ステータス", "メッセージ"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            src,
            dst,
            status,
            message
        ])

# ===== 共通 =====
def is_old_folder(path: Path) -> bool:
    return "old" in [p.name.lower() for p in path.parents]

def extract_text(pdf: Path) -> str:
    try:
        reader = PdfReader(str(pdf))
        return "".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        write_log(pdf.name, "", "ERROR", f"PDF読込失敗: {e}")
        return ""

# ===== 他社処理（見積書のみ）=====
def process_company(pdf: Path):
    global processed_count

    if is_old_folder(pdf):
        write_log(pdf.name, "", "SKIP", "oldフォルダ")
        return

    # 注文書除外
    if "注文書" in pdf.name:
        write_log(pdf.name, "", "SKIP", "注文書のため対象外（他社）")
        return

    # 既にリネーム済み
    if COMPANY_DONE_PATTERN.match(pdf.name):
        write_log(pdf.name, "", "SKIP", "命名規則一致（他社）")
        return

    m = COMPANY_PATTERN.match(pdf.name)
    if not m:
        write_log(pdf.name, "", "SKIP", "見積番号取得不可（他社）")
        return

    est_no = m.group(1)

    date_str = datetime.fromtimestamp(
        pdf.stat().st_ctime
    ).strftime("%Y%m%d")

    new_name = f"{est_no}_見積書_{date_str}.pdf"
    new_path = pdf.with_name(new_name)

    if new_path.exists():
        write_log(pdf.name, "", "SKIP", "同名ファイル既存")
        return

    pdf.rename(new_path)
    write_log(pdf.name, new_name, "RENAMED", "他社処理")
    processed_count += 1

# ===== 自社処理（見積書のみ）=====
def process_my_company(pdf: Path):
    global processed_count

    if is_old_folder(pdf):
        write_log(pdf.name, "", "SKIP", "oldフォルダ")
        return

    # 既にリネーム済み
    if VALID_NAME.match(pdf.name):
        write_log(pdf.name, "", "SKIP", "命名規則一致")
        return

    # 注文書除外（／なしは注文書）
    if "／" not in pdf.name:
        write_log(pdf.name, "", "SKIP", "注文書のため対象外")
        return

    m = EST_NO_FROM_NAME.search(pdf.name)
    if not m:
        write_log(pdf.name, "", "SKIP", "見積番号取得不可")
        return

    est_no = m.group(1)
    folder_name = pdf.parent.name

    text = extract_text(pdf)
    dm = DATE_JP.search(text)
    if not dm:
        write_log(pdf.name, "", "SKIP", "見積日取得不可")
        return

    y, mth, d = dm.groups()
    date_str = f"{y}{int(mth):02d}{int(d):02d}"

    new_name = f"{date_str}_{folder_name}_見積書_{est_no}.pdf"
    new_path = pdf.with_name(new_name)

    if new_path.exists():
        write_log(pdf.name, "", "SKIP", "同名ファイル既存")
        return

    pdf.rename(new_path)
    write_log(pdf.name, new_name, "RENAMED", "システナ処理")
    processed_count += 1

# ===== メイン =====
def main():
    global processed_count

    # システナ
    for pdf in MY_COMPANY_DIR.rglob("*.pdf"):
        process_my_company(pdf)

    # コジマ
    for pdf in COMPANY_DIR.rglob("*.pdf"):
        process_company(pdf)

    if processed_count == 0:
        write_log("", "", "INFO", "対象ファイルなし。処理は行われませんでした")
        print("✅ 何もすることがありませんでした")
    else:
        print(f"✅ {processed_count} 件のファイルを処理しました")

# ===== 実行 =====
if __name__ == "__main__":
    main()