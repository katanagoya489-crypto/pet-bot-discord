from __future__ import annotations

CHARACTERS = {
    "egg_yuiran": {"name": "結卵", "stage": "egg", "profile": "結びの力を秘めたふしぎなたまご。", "secret": False, "asset_base": "結卵"},
    "baby_colon": {"name": "コロン", "stage": "baby1", "profile": "ころんと生まれた小さな命。", "secret": False, "asset_base": "コロン"},
    "baby_cororon": {"name": "コロロン", "stage": "baby2", "profile": "少しずつ感情が豊かになってきた。", "secret": False, "asset_base": "コロロン"},
    "child_musubi": {"name": "ムスビー", "stage": "child", "profile": "いろんな個性に育っていく結びの子。", "secret": False, "asset_base": "ムスビー"},
    "adult_sarii": {"name": "鳳凰院さりぃ", "stage": "adult", "profile": "しつけが伸びやすく、優等生寄りに育つ。", "secret": False, "asset_base": "鳳凰院さりぃ"},
    "adult_icecream": {"name": "あいすくりむ", "stage": "adult", "profile": "おやつやごきげんと相性がよい。", "secret": False, "asset_base": "あいすくりむ"},
    "adult_kou": {"name": "虹守コウ", "stage": "adult", "profile": "遊びの効果が高い。", "secret": False, "asset_base": "虹守コウ"},
    "adult_nazuna": {"name": "白雪なづな", "stage": "adult", "profile": "よく眠り、安定しやすい。", "secret": False, "asset_base": "白雪なづな"},
    "adult_kanato": {"name": "陽色かなと", "stage": "adult", "profile": "全体バランスが良い。", "secret": False, "asset_base": "陽色かなと"},
    "adult_saina": {"name": "煩流サイナ", "stage": "adult", "profile": "ミニゲームと相性が良い。", "secret": False, "asset_base": "煩流サイナ"},
    "adult_akira": {"name": "橙ノあきら", "stage": "adult", "profile": "ごはんで元気になりやすい。", "secret": False, "asset_base": "橙ノあきら"},
    "adult_owl": {"name": "オウル・ノーグ", "stage": "adult", "profile": "夜型。夜の活動で個性が出る。", "secret": False, "asset_base": "オウル・ノーグ"},
    "adult_ichiru": {"name": "海寧いちる", "stage": "adult", "profile": "ストレスを低く保つと会いやすい。", "secret": False, "asset_base": "海寧いちる"},
    "secret_baaya": {"name": "ばあや", "stage": "adult", "profile": "さりぃルートからごく稀に現れる。", "secret": True, "asset_base": "ばあや"},
    "secret_gugu": {"name": "百瀬ぐぐ", "stage": "adult", "profile": "すべてのルートに潜む超低確率進化。", "secret": True, "asset_base": "百瀬ぐぐ"},
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

IMAGE_STATE_ALIASES = {
    "normal": ["通常", "ふつう", "通常立ち", "立ち絵"],
    "feed": ["ごはん", "ご飯"],
    "snack": ["おやつ"],
    "sleepy": ["眠い", "ねむい", "睡眠"],
    "sick": ["病気", "びょうき"],
    "poop": ["ウンチ", "うんち", "汚れ"],
    "angry": ["怒り", "不機嫌"],
    "happy": ["喜び", "ごきげん", "嬉しい"],
    "hatch": ["孵化", "割れる", "卵割れる"],
    "egg": ["卵", "たまご"],
    "letter": ["手紙"],
}
