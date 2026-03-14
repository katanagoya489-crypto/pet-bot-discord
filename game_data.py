
from __future__ import annotations

CHARACTERS = {
    "egg_yuiran": {"name": "結卵", "stage": "egg", "profile": "結びの力を秘めたふしぎなたまご。", "x_url": "", "secret": False},
    "baby_colon": {"name": "コロン", "stage": "baby1", "profile": "ころんと生まれた小さな命。", "x_url": "", "secret": False},
    "baby_cororon": {"name": "コロロン", "stage": "baby2", "profile": "少しずつ感情が豊かになってきた。", "x_url": "", "secret": False},
    "child_musubi": {"name": "ムスビー", "stage": "child", "profile": "いろんな個性に育っていく結びの子。", "x_url": "", "secret": False},

    "adult_sarii": {"name": "鳳凰院さりぃ", "stage": "adult", "profile": "華やかで堂々とした存在。みんなを導く太陽のような存在。", "x_url": "", "secret": False},
    "adult_icecream": {"name": "あいすくりむ", "stage": "adult", "profile": "甘くやさしく、自由な発想で周りを笑顔にする。", "x_url": "", "secret": False},
    "adult_kou": {"name": "虹守コウ", "stage": "adult", "profile": "やさしさと芯の強さを持つ存在。音楽と物語を愛する守護者。", "x_url": "", "secret": False},
    "adult_nazuna": {"name": "白雪なづな", "stage": "adult", "profile": "静けさと透明感を持ち、やわらかく寄り添ってくれる。", "x_url": "", "secret": False},
    "adult_kanato": {"name": "陽色かなと", "stage": "adult", "profile": "あたたかくバランス感覚のよい、安心感のある存在。", "x_url": "", "secret": False},
    "adult_saina": {"name": "煩流サイナ", "stage": "adult", "profile": "刺激と勢いを持ちながら、音に強いこだわりを見せる。", "x_url": "", "secret": False},
    "adult_akira": {"name": "橙ノあきら", "stage": "adult", "profile": "エネルギッシュで親しみやすく、元気を分けてくれる。", "x_url": "", "secret": False},
    "adult_owl": {"name": "オウル・ノーグ", "stage": "adult", "profile": "夜に強く、落ち着いた知性を感じさせる存在。", "x_url": "", "secret": False},
    "adult_ichiru": {"name": "海寧いちる", "stage": "adult", "profile": "穏やかで海のように深く、安定感のあるやさしさを持つ。", "x_url": "", "secret": False},

    "secret_baaya": {"name": "ばあや", "stage": "adult", "profile": "さりぃの結びからごく稀に現れる、面倒見のよい特別な存在。", "x_url": "", "secret": True},
    "secret_gugu": {"name": "百瀬ぐぐ", "stage": "adult", "profile": "すべてのルートに潜む超低確率の特別進化。", "x_url": "", "secret": True},
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
MINIGAME_COOLDOWN_SECONDS = 10 * 60
POOP_LIMIT = 3

NOTIFICATION_MODES = ["tamagotchi", "normal", "quiet", "mute"]

CARE_LABELS = {
    "hunger": [(0, 20, "おなかいっぱい"), (21, 50, "ふつう"), (51, 80, "ぺこぺこ"), (81, 100, "ひもじい")],
    "mood": [(0, 20, "ふきげん"), (21, 50, "ふつう"), (51, 80, "ごきげん"), (81, 100, "るんるん")],
    "sleepiness": [(0, 20, "ぱっちり"), (21, 50, "すこしねむい"), (51, 80, "ねむそう"), (81, 100, "もう限界")],
    "affection": [(0, 20, "よそよそしい"), (21, 50, "なじんできた"), (51, 80, "なついてる"), (81, 100, "だいすき")],
    "stress": [(0, 20, "おだやか"), (21, 50, "ふつう"), (51, 80, "やや高い"), (81, 100, "かなり高い")],
}

MUSIC_GAMES = {
    "rhythm": {
        "title": "リズムあそび",
        "question": "つぎのリズムと同じものはどれ？  ♪ ♪ ♫",
        "choices": ["♪♪♫", "♪♫♪", "♫♪♪"],
        "answer": 0,
    },
    "instrument": {
        "title": "音あて",
        "question": "メロディを支えることが多いのはどれ？",
        "choices": ["ドラム", "ピアノ", "ギター"],
        "answer": 1,
    },
    "melody": {
        "title": "メロディ記憶",
        "question": "『ド レ ミ』と同じ並びはどれ？",
        "choices": ["ドレミ", "レミド", "ドミレ"],
        "answer": 0,
    },
}
