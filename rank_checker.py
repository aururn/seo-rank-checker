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
import concurrent.futures
import random

# ログ設定
logging.basicConfig(
    filename='/home/ec2-user/seo-rank-checker/rank_checker.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Google検索順位取得関数（最大50位）
def get_google_rank(api_key, cse_id, query, target_url, max_results=50):
    search_url = "https://www.googleapis.com/customsearch/v1"
    rank = None

    for start in range(1, max_results + 1, 10):
        params = {
            'key': api_key,
            'cx': cse_id,
            'q': query,
            'num': 10,
            'start': start
        }
        response = requests.get(search_url, params=params)
        results = response.json()

        if 'items' not in results:
            break  # 検索結果がない場合は終了

        for idx, item in enumerate(results['items'], start=start):
            if target_url in item['link']:
                return idx  # 対象URLが見つかった順位を返す

        # APIのクォータ制限などで追加のページが取得できない場合も終了
        if 'nextPage' not in results.get('queries', {}):
            break

        # リクエスト間に待機時間を設けてAPIへの負荷を軽減
        time.sleep(random.uniform(1, 2))  # 1〜2秒のランダムな待機

    return rank  # 見つからなかった場合はNone

# Yahoo検索順位取得関数（最大50位）
def get_yahoo_rank(query, target_url, max_results=50):
    base_url = "https://search.yahoo.co.jp/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    rank = None

    for page in range(1, (max_results // 10) + 1):
        params = {
            'p': query,
            'b': (page - 1) * 10 + 1  # 検索結果の開始位置
        }
        response = requests.get(base_url, params=params, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Yahooの検索結果のHTML構造に基づいて結果を抽出
        results = soup.find_all('div', class_='Sw-Card')  # クラス名は実際のHTMLに合わせて調整

        for idx, result in enumerate(results, start=(page - 1) * 10 + 1):
            link = result.find('a', href=True)
            if link and target_url in link['href']:
                return idx  # 対象URLが見つかった順位を返す

        # 次のページが存在しない場合は終了
        if not results:
            break

        # リクエスト間に待機時間を設けてサイトへの負荷を軽減
        time.sleep(random.uniform(1, 2))  # 1〜2秒のランダムな待機

    return rank  # 見つからなかった場合はNone

# Googleスプレッドシート認証
def authenticate_google_sheets(creds_json):
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(creds_json, scopes=scopes)
    client = gspread.authorize(credentials)
    return client

# ターゲットの順位取得とシートへの書き込み
def process_target(target, google_api_key, google_cse_id, sheet, date_str):
    try:
        keyword = target['keyword']
        url = target['url']

        # Google順位取得（最大50位）
        google_rank = get_google_rank(google_api_key, google_cse_id, keyword, url, max_results=50)
        google_rank_str = str(google_rank) if google_rank else '未表示'

        # Yahoo順位取得（最大50位）
        yahoo_rank = get_yahoo_rank(keyword, url, max_results=50)
        yahoo_rank_str = str(yahoo_rank) if yahoo_rank else '未表示'

        # シートに追加するデータ
        row = [date_str, keyword, url, google_rank_str, yahoo_rank_str]

        # シートに書き込み
        sheet.append_row(row)

        # ログに成功を記録
        logging.info(f"Successfully updated ranks for keyword: '{keyword}'")

    except Exception as e:
        logging.error(f"Error processing target {target}: {e}")

# データ更新関数
def update_rankings():
    try:
        # 環境変数の取得
        google_api_key = os.getenv('GOOGLE_API_KEY')
        google_cse_id = os.getenv('GOOGLE_CSE_ID')
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')  # '/home/ec2-user/seo-rank-checker/service_account.json'
        spreadsheet_id = os.getenv('SPREADSHEET_ID')  # スプレッドシートのキー

        # デバッグ用ログ（環境変数が設定されているか確認）
        logging.info(f"GOOGLE_API_KEY is set: {bool(google_api_key)}")
        logging.info(f"GOOGLE_CSE_ID is set: {bool(google_cse_id)}")
        logging.info(f"GOOGLE_CREDENTIALS_JSON is set: {bool(credentials_json)}")
        logging.info(f"SPREADSHEET_ID is set: {bool(spreadsheet_id)}")

        if not google_api_key or not google_cse_id or not credentials_json or not spreadsheet_id:
            raise ValueError("One or more environment variables are not set.")

        # ファイルの存在確認
        if not os.path.isfile(credentials_json):
            raise FileNotFoundError(f"Service account JSON file not found at: {credentials_json}")

        # キーワードとターゲットURLのリスト
        targets = [
            {
                'keyword': 'どら焼き 有名',
                'url': 'https://tsuboya.net/blogs/blog/dorayaki_famous'
            },
            {
                'keyword': 'あんこ 栄養',
                'url': 'https://tsuboya.net/blogs/blog/anko_nutrients'
            },
            # 他のキーワードとURLを追加する場合は、ここに追加
        ]

        # 認証
        client = authenticate_google_sheets(credentials_json)

        # スプレッドシートをキーで開く
        spreadsheet = client.open_by_key(spreadsheet_id)
        sheet = spreadsheet.sheet1  # 1つ目のシートを使用する場合

        # 日付取得
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 並列処理の設定
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(process_target, target, google_api_key, google_cse_id, sheet, date_str)
                for target in targets
            ]
            for future in concurrent.futures.as_completed(futures):
                if future.exception():
                    logging.error(f"Error in thread: {future.exception()}")

        logging.info(f"Updated rankings at {datetime.now()}")
        print(f"Updated rankings at {datetime.now()}")

    except Exception as e:
        logging.error(f"Error updating rankings: {e}")
        print(f"Error updating rankings: {e}")

# スケジューリング設定
def schedule_tasks():
    # 2日に1回実行するようにスケジュールを設定
    schedule.every(2).days.do(update_rankings)
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
        print("aaaaaaa") 
    else:
        # 初回実行
        update_rankings()
        # 定期的な順位チェックを開始
        schedule_tasks()

if __name__ == "__main__":
    main()
