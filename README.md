
# Discord たまごっち風Bot 完全版

## 概要
- ボタン主体のDiscord育成Bot
- 個別スレッドで育成
- 呼び出し / しつけ / うんち / 病気 / おるすばん搭載
- 成熟進化、旅立ち、図鑑登録あり
- 画像なしでも動作。明日以降に `game_data.py` の `message_id` を埋めて画像差し込み可能

## 初回セットアップ
1. `.env.example` を `.env` にコピー
2. 値を埋める
3. 依存関係を入れる
   `pip install -r requirements.txt`
4. 起動
   `python bot.py`
5. Discordで管理者が
   `!setup_panel`
   を打つ

## コマンド
- `!setup_panel` 入口パネルを設置
- `!status` 現在の文字状態を確認
- `!dex` 図鑑確認
- `!set_sleep 00:00 07:00` 自分のスリープ時間を設定

## Railwayで並走する方法
既存ゲームと並走するなら、
- **別サービス** を作る
- **別Volume** をつける
- `DATABASE_PATH=/data/bot.db` にする
- 同じGitHubリポジトリなら、このBot用のディレクトリだけを **Root Directory** に設定する
- Start Command は `python bot.py`

## 明日やること
- キャラチャンネルへ画像投稿
- 各画像のメッセージID取得
- `game_data.py` の `message_id` に反映
- 必要なら画像取得ロジックを追加
