from __future__ import annotations

CHARACTERS = {
    "egg_yuiran": {"name": "結卵", "stage": "egg", "profile": "結びの力を秘めたふしぎなたまご。", "secret": False},
    "baby_colon": {"name": "コロン", "stage": "baby1", "profile": "ころんと生まれた小さな命。", "secret": False},
    "baby_cororon": {"name": "コロロン", "stage": "baby2", "profile": "少しずつ感情が豊かになってきた。", "secret": False},
    "child_musubi": {"name": "ムスビー", "stage": "child", "profile": "いろんな個性に育っていく結びの子。", "secret": False},
    "adult_sarii": {"name": "鳳凰院さりぃ", "stage": "adult", "profile": "しつけや安定した育て方と相性がいい。", "secret": False},
    "adult_icecream": {"name": "あいすくりむ", "stage": "adult", "profile": "おやつやごきげんを大事にすると会いやすい。", "secret": False},
    "adult_kou": {"name": "虹守コウ", "stage": "adult", "profile": "あそびや愛情を重ねると会いやすい。", "secret": False},
    "adult_nazuna": {"name": "白雪なづな", "stage": "adult", "profile": "よく休ませて落ち着いて育てると会いやすい。", "secret": False},
    "adult_kanato": {"name": "陽色かなと", "stage": "adult", "profile": "全体のバランスが良いと会いやすい。", "secret": False},
    "adult_saina": {"name": "煩流サイナ", "stage": "adult", "profile": "ミニゲームや元気な育ち方と相性がいい。", "secret": False},
    "adult_akira": {"name": "橙ノあきら", "stage": "adult", "profile": "ごはんを中心に育てると会いやすい。", "secret": False},
    "adult_owl": {"name": "オウル・ノーグ", "stage": "adult", "profile": "夜の行動や睡眠の取り方で個性が出やすい。", "secret": False},
    "adult_ichiru": {"name": "海寧いちる", "stage": "adult", "profile": "やさしく安定して育てると会いやすい。", "secret": False},
    "secret_baaya": {"name": "ばあや", "stage": "adult", "profile": "ごくまれに会える隠しキャラ。", "secret": True},
    "secret_gugu": {"name": "百瀬ぐぐ", "stage": "adult", "profile": "すべてのルートに潜む超低確率キャラ。", "secret": True},
}

DEX_TARGETS = [
    "adult_sarii", "adult_icecream", "adult_kou", "adult_nazuna", "adult_kanato",
    "adult_saina", "adult_akira", "adult_owl", "adult_ichiru", "secret_baaya", "secret_gugu"
]

STAGE_SECONDS = {
    "egg": 10 * 60,
    "baby1": 40 * 60,
    "baby2": 8 * 60 * 60,
    "child": 24 * 60 * 60,
}

JOURNEY_MIN_SECONDS = 24 * 60 * 60
JOURNEY_MAX_SECONDS = 48 * 60 * 60
MINIGAME_COOLDOWN_SECONDS = 10 * 60

NOTIFICATION_REASON_TEXT = {
    "hunger": "🍚 おなかがすいているみたい！",
    "mood": "😣 ごきげんがさがっているみたい…",
    "poop": "💩 うんちがたまっているみたい！",
    "sick": "🤒 ぐあいがわるそう…",
    "sleepy": "🌙 ねむそうだよ… でんきをけしてあげよう。",
    "whim": "📢 ようはないのに よんでる！ しつけのチャンス！",
}

MUSIC_GAMES = {
    "rhythm": {"title": "リズムあそび", "question": "つぎのリズムとおなじものはどれ？ ♪ ♪ ♫", "choices": ["♪♪♫", "♪♫♪", "♫♪♪"], "answer": 0},
    "instrument": {"title": "音あて", "question": "メロディをささえることが多いのはどれ？", "choices": ["ドラム", "ピアノ", "ギター"], "answer": 1},
    "melody": {"title": "メロディ記憶", "question": "『ド レ ミ』とおなじならびはどれ？", "choices": ["ドレミ", "レミド", "ドミレ"], "answer": 0},
}

ADULT_EVOLUTION_RULES = {
    "adult_sarii": {"discipline": 1.6, "status": 1.2, "praise": 1.2, "stress_low": 0.7},
    "adult_icecream": {"snack": 1.6, "mood": 1.0, "weight_mid": 1.0},
    "adult_kou": {"play": 1.5, "minigame": 1.2, "affection": 1.0},
    "adult_nazuna": {"sleep": 1.5, "stress_low": 1.0, "weight_light": 0.8},
    "adult_kanato": {"balance": 1.4, "affection": 0.8},
    "adult_saina": {"minigame": 1.7, "mood": 1.0},
    "adult_akira": {"feed": 1.6, "weight_light": 0.8},
    "adult_owl": {"night": 1.8, "sleep": 0.8},
    "adult_ichiru": {"clean": 1.3, "stress_low": 1.2, "praise": 0.8},
}

EGG_IMAGE_KEYS = [
    "結卵_通常", "結卵_ノーマル", "結卵", "卵_通常", "卵", "たまご", "egg"
]

IMAGE_STATE_SUFFIXES = {
    "normal": ["通常", "ノーマル", ""],
    "feed": ["ごはん", "ご飯"],
    "snack": ["おやつ"],
    "sleepy": ["眠い", "ねむい"],
    "sick": ["病気", "びょうき"],
    "angry": ["怒り", "不機嫌"],
    "happy": ["喜び", "笑顔"],
    "poop": ["ウンチ", "うんち"],
    "letter": ["手紙"],
}
