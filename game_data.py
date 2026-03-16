from __future__ import annotations

CHARACTERS = {
    "egg_yuiran": {"name": "結卵", "asset_base": "結卵", "asset_aliases": ["卵", "たまご"], "stage": "egg", "profile": "結びの力を秘めたふしぎなたまご。", "secret": False},
    "baby_colon": {"name": "コロン", "asset_base": "コロン", "asset_aliases": [], "stage": "baby1", "profile": "ころんと生まれた小さな命。", "secret": False},
    "baby_cororon": {"name": "コロロン", "asset_base": "コロロン", "asset_aliases": [], "stage": "baby2", "profile": "少しずつ感情が豊かになってきた。", "secret": False},
    "child_musubi": {"name": "ムスビー", "asset_base": "ムスビー", "asset_aliases": [], "stage": "child", "profile": "いろんな個性に育っていく結びの子。", "secret": False},
    "adult_sarii": {"name": "鳳凰院さりぃ", "asset_base": "鳳凰院さりぃ", "asset_aliases": [], "stage": "adult", "profile": "しつけが伸びやすく、優等生寄りに育つ。", "secret": False},
    "adult_icecream": {"name": "あいすくりむ", "asset_base": "あいすくりむ", "asset_aliases": [], "stage": "adult", "profile": "おやつやごきげんと相性がよい。", "secret": False},
    "adult_kou": {"name": "虹守コウ", "asset_base": "虹守コウ", "asset_aliases": [], "stage": "adult", "profile": "遊びの効果が高い。", "secret": False},
    "adult_nazuna": {"name": "白雪なづな", "asset_base": "白雪なづな", "asset_aliases": [], "stage": "adult", "profile": "よく眠り、安定しやすい。", "secret": False},
    "adult_kanato": {"name": "陽色かなと", "asset_base": "陽色かなと", "asset_aliases": [], "stage": "adult", "profile": "全体バランスが良い。", "secret": False},
    "adult_saina": {"name": "煩流サイナ", "asset_base": "煩流サイナ", "asset_aliases": [], "stage": "adult", "profile": "ミニゲームと相性が良い。", "secret": False},
    "adult_akira": {"name": "橙ノあきら", "asset_base": "橙ノあきら", "asset_aliases": [], "stage": "adult", "profile": "ごはんで元気になりやすい。", "secret": False},
    "adult_owl": {"name": "オウル・ノーグ", "asset_base": "オウル・ノーグ", "asset_aliases": [], "stage": "adult", "profile": "夜型。夜の活動で個性が出る。", "secret": False},
    "adult_ichiru": {"name": "海寧いちる", "asset_base": "海寧いちる", "asset_aliases": [], "stage": "adult", "profile": "ストレスを低く保つと会いやすい。", "secret": False},
    "secret_baaya": {"name": "ばあや", "asset_base": "ばあや", "asset_aliases": [], "stage": "adult", "profile": "さりぃルートからごく稀に現れる。", "secret": True},
    "secret_gugu": {"name": "百瀬ぐぐ", "asset_base": "百瀬ぐぐ", "asset_aliases": [], "stage": "adult", "profile": "すべてのルートに潜む超低確率進化。", "secret": True},
}

DEX_TARGETS = [
    "adult_sarii", "adult_icecream", "adult_kou", "adult_nazuna", "adult_kanato",
    "adult_saina", "adult_akira", "adult_owl", "adult_ichiru", "secret_baaya", "secret_gugu"
]

STAGE_SECONDS = {
    "egg_yuiran": 10 * 60,
    "baby_colon": 40 * 60,
    "baby_cororon": 8 * 60 * 60,
    "child_musubi": 24 * 60 * 60,
}
JOURNEY_MIN_SECONDS = 24 * 60 * 60
JOURNEY_MAX_SECONDS = 48 * 60 * 60
EVOLUTION_WARNING_SECONDS = 10 * 60
MINIGAME_COOLDOWN_SECONDS = 10 * 60
RANDOM_EVENT_INTERVAL_SECONDS = 45 * 60

NOTIFICATION_REASON_TEXT = {
    "hunger": "🍚 おなかがすいているみたい！",
    "mood": "😣 ごきげんがさがっているみたい…",
    "poop": "💩 うんちがたまっているみたい！",
    "sick": "🤒 ぐあいがわるそう…",
    "sleepy": "🌙 ねむそうだよ… でんきをけしてあげよう。",
    "whim": "📢 ようはないのに よんでる！ しつけのチャンス！",
}

RANDOM_EVENTS = [
    "🍬 おやつがほしそう",
    "⚽ あそびたそう",
    "😢 なんだかさみしそう",
    "💤 うとうとしている",
    "🎶 ごきげんで鼻歌をうたっている",
]

MUSIC_GAMES = {
    "rhythm": {"title": "リズムあそび", "question": "つぎのリズムとおなじものはどれ？ ♪ ♪ ♫", "choices": ["♪♪♫", "♪♫♪", "♫♪♪"], "answer": 0},
    "instrument": {"title": "音あて", "question": "メロディをささえることが多いのはどれ？", "choices": ["ドラム", "ピアノ", "ギター"], "answer": 1},
    "melody": {"title": "メロディ記憶", "question": "『ド レ ミ』とおなじならびはどれ？", "choices": ["ドレミ", "レミド", "ドミレ"], "answer": 0},
}


STATE_IMAGE_ALIASES = {
    "normal": ["通常", "ノーマル"],
    "feed": ["ごはん", "ご飯"],
    "snack": ["おやつ"],
    "sleep": ["眠い", "ねむい", "睡眠"],
    "sick": ["病気", "びょうき"],
    "angry": ["怒り", "いかり"],
    "happy": ["喜び", "うれしい"],
    "poop": ["ウンチ", "うんち"],
    "letter": ["手紙"],
}
EGG_IMAGE_KEYS = ["卵", "たまご", "結卵", "結卵_通常", "egg_yuiran"]
