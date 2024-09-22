import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import schedule
import time
import os
import logging
import argparse
import sys

# ログ設定
logging.basicConfig(
    filename='/home/ec2-user/seo-rank-checker/rank_checker.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Google検索順位取得関数
def get_google_rank(api_key, cse_id, query, target_url):
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': cse_id,
        'q': query,
        'num': 10
    }
    response = requests.get(search_url, params=params)
    results = response.json()

    if 'items' not in results:
        return None

    for idx, item in enumerate(results['items'], start=1):
        if target_url in item['link']:
            return idx
    return None

# Yahoo検索順位取得関数
def get_yahoo_rank(query, target_url):
    base_url = "https://search.yahoo.co.jp/search"
    params = {
        'p': query
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    response = requests.get(base_url, params=params, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Yahooの検索結果のHTML構造は変更される可能性があるため、適宜修正が必要
    results = soup.find_all('div', class_='Sw-Card')  # クラス名は実際のYahoo検索結果に合わせて調整

    for idx, result in enumerate(results, start=1):
        link = result.find('a', href=True)
        if link and target_url in link['href']:
            return idx
    return None

# Googleスプレッドシート認証
def authenticate_google_sheets(creds_json):
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(creds_json, scopes=scopes)
    client = gspread.authorize(credentials)
    return client

# データ更新関数
def update_rankings():
    try:
        # 設定
        google_api_key = os.getenv('GOOGLE_API_KEY')
        google_cse_id = os.getenv('GOOGLE_CSE_ID')
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')  # '/home/ec2-user/seo-rank-checker/service_account.json'

        # デバッグ用ログ（環境変数が設定されているか確認）
        logging.info(f"GOOGLE_API_KEY is set: {bool(google_api_key)}")
        logging.info(f"GOOGLE_CSE_ID is set: {bool(google_cse_id)}")
        logging.info(f"GOOGLE_CREDENTIALS_JSON is set: {bool(credentials_json)}")

        if not google_api_key or not google_cse_id or not credentials_json:
            raise ValueError("One or more environment variables are not set.")

        # ファイルの存在確認
        if not os.path.isfile(credentials_json):
            raise FileNotFoundError(f"Service account JSON file not found at: {credentials_json}")

        spreadsheet_name = 'SEO Rankings'  # スプレッドシートの名前
        sheet_name = 'Rankings'             # 使用するシート名（例: 'Rankings'）

        # キーワードとターゲットURLのリスト
        targets = [
            {
                'keyword': 'どら焼き　有名',
                'url': 'https://tsuboya.net/blogs/blog/dorayaki_famous'
            },
            # 他のキーワードとURLを追加する場合は、ここに追加
        ]

        # 認証
        client = authenticate_google_sheets(credentials_json)

        # シート取得
        sheet = client.open(spreadsheet_name).worksheet(sheet_name)

        # 日付取得
        date_str = datetime.now().strftime("%Y-%m-%d")

        # 各ターゲットの順位を取得し、シートに書き込み
        for target in targets:
            keyword = target['keyword']
            url = target['url']

            # Google順位取得
            google_rank = get_google_rank(google_api_key, google_cse_id, keyword, url)
            google_rank_str = google_rank if google_rank else '未表示'

            # Yahoo順位取得
            yahoo_rank = get_yahoo_rank(keyword, url)
            yahoo_rank_str = yahoo_rank if yahoo_rank else '未表示'

            # シートに追加するデータ
            row = [date_str, keyword, url, google_rank_str, yahoo_rank_str]

            # シートに書き込み
            sheet.append_row(row)

        logging.info(f"Updated rankings at {datetime.now()}")
        print(f"Updated rankings at {datetime.now()}")

    except Exception as e:
        logging.error(f"Error updating rankings: {e}")
        print(f"Error updating rankings: {e}")

# スケジューリング設定
def schedule_tasks():
    schedule.every().day.at("00:00").do(update_rankings)
    logging.info("Scheduler started. Waiting for scheduled tasks...")
    print("Scheduler started. Waiting for scheduled tasks...")

    while True:
        schedule.run_pending()
        time.sleep(60)  # 1分ごとにチェック

def main():
    parser = argparse.ArgumentParser(description='SEO Rank Checker')
    parser.add_argument('--run-once', action='store_true', help='Run the rank checker once and exit')
    args = parser.parse_args()

    if args.run_once:
        update_rankings()
    else:
        schedule_tasks()

if __name__ == "__main__":
    main()
