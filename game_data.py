from __future__ import annotations

CHARACTERS = {
    'egg_yuiran': {'name': '結卵', 'stage': 'egg', 'profile': '結びの力を秘めたふしぎなたまご。', 'secret': False, 'image_base': '結卵'},
    'baby_colon': {'name': 'コロン', 'stage': 'baby1', 'profile': 'ころんと生まれた小さな命。', 'secret': False, 'image_base': 'コロン'},
    'baby_cororon': {'name': 'コロロン', 'stage': 'baby2', 'profile': '少しずつ感情が豊かになってきた。', 'secret': False, 'image_base': 'コロロン'},
    'child_musubi': {'name': 'ムスビー', 'stage': 'child', 'profile': 'いろんな個性に育っていく結びの子。', 'secret': False, 'image_base': 'ムスビー'},
    'adult_sarii': {'name': '鳳凰院さりぃ', 'stage': 'adult', 'profile': 'しつけが得意で落ち着いて育ちやすい。', 'secret': False, 'image_base': '鳳凰院さりぃ'},
    'adult_icecream': {'name': 'あいすくりむ', 'stage': 'adult', 'profile': 'おやつやごきげんと相性がいい。', 'secret': False, 'image_base': 'あいすくりむ'},
    'adult_kou': {'name': '虹守コウ', 'stage': 'adult', 'profile': 'あそびや愛情を重ねると会いやすい。', 'secret': False, 'image_base': '虹守コウ'},
    'adult_nazuna': {'name': '白雪なづな', 'stage': 'adult', 'profile': 'よく休んで安定すると会いやすい。', 'secret': False, 'image_base': '白雪なづな'},
    'adult_kanato': {'name': '陽色かなと', 'stage': 'adult', 'profile': '全体のバランスが良い。', 'secret': False, 'image_base': '陽色かなと'},
    'adult_saina': {'name': '煩流サイナ', 'stage': 'adult', 'profile': 'ミニゲームや勢いと相性がいい。', 'secret': False, 'image_base': '煩流サイナ'},
    'adult_akira': {'name': '橙ノあきら', 'stage': 'adult', 'profile': 'ごはんで元気を取り戻しやすい。', 'secret': False, 'image_base': '橙ノあきら'},
    'adult_owl': {'name': 'オウル・ノーグ', 'stage': 'adult', 'profile': '夜の雰囲気で個性が出る。', 'secret': False, 'image_base': 'オウル・ノーグ'},
    'adult_ichiru': {'name': '海寧いちる', 'stage': 'adult', 'profile': 'やさしく安定して育てると会いやすい。', 'secret': False, 'image_base': '海寧いちる'},
    'secret_baaya': {'name': 'ばあや', 'stage': 'adult', 'profile': 'ごくまれに出会えるひみつの姿。', 'secret': True, 'image_base': 'ばあや'},
    'secret_gugu': {'name': '百瀬ぐぐ', 'stage': 'adult', 'profile': 'とてもまれに出会えるひみつの姿。', 'secret': True, 'image_base': '百瀬ぐぐ'},
}

DEX_TARGETS = [
    'adult_sarii', 'adult_icecream', 'adult_kou', 'adult_nazuna', 'adult_kanato',
    'adult_saina', 'adult_akira', 'adult_owl', 'adult_ichiru', 'secret_baaya', 'secret_gugu',
]

STAGE_SECONDS = {
    'egg_yuiran': 10 * 60,
    'baby_colon': 40 * 60,
    'baby_cororon': 8 * 60 * 60,
    'child_musubi': 24 * 60 * 60,
}

EVOLUTION_WARNING_SECONDS = 10 * 60
MINIGAME_COOLDOWN_SECONDS = 10 * 60
RANDOM_EVENT_INTERVAL_SECONDS = 45 * 60

CALL_REASON_TEXT = {
    'hunger': '🍚 おなかがすいているみたい！',
    'mood': '😣 ごきげんが下がっているみたい…',
    'poop': '💩 うんちがたまっているみたい！',
    'sick': '🤒 ぐあいが悪そう…',
    'sleepy': '🌙 ねむそうだよ… でんきをけしてあげよう。',
    'whim': '📢 とくに用はないけどよんでる！ しつけのチャンス！',
}

RANDOM_EVENTS = [
    '🍬 おやつがほしそう',
    '⚽ あそびたそう',
    '😢 なんだかさみしそう',
    '💤 うとうとしている',
    '🎶 ごきげんで鼻歌をうたっている',
]

MUSIC_GAMES = {
    'rhythm': {'title': 'リズムあそび', 'question': '今日はどんな気分？', 'choices': ['ノリノリ', 'ふつう', 'ねむい'], 'answer': 0},
    'instrument': {'title': '音あて', 'question': 'どれで遊びたい？', 'choices': ['ドラム', 'ピアノ', 'ギター'], 'answer': 1},
    'melody': {'title': 'メロディ記憶', 'question': 'いっしょに歌う？', 'choices': ['うたう', 'きく', 'ねる'], 'answer': 0},
}

IMAGE_STATE_ALIASES = {
    '通常': ['通常', 'ノーマル'],
    'ごはん': ['ごはん', 'ご飯', '食事'],
    'おやつ': ['おやつ'],
    '眠い': ['眠い', 'ねむい', '睡眠'],
    '病気': ['病気', 'びょうき'],
    '怒り': ['怒り', '怒', '不機嫌'],
    '喜び': ['喜び', '笑顔', 'ごきげん'],
    'ウンチ': ['ウンチ', 'うんち'],
    '手紙': ['手紙'],
}

EGG_IMAGE_KEYS = [
    '結卵_通常', '結卵_ノーマル', '結卵', '卵_通常', '卵', 'たまご', 'egg'
]
