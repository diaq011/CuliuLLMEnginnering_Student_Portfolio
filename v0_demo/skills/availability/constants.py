from __future__ import annotations

WEEK_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

WEEK_LABELS = {
    "mon": "周一",
    "tue": "周二",
    "wed": "周三",
    "thu": "周四",
    "fri": "周五",
    "sat": "周六",
    "sun": "周日",
}

DAY_NAME_TO_KEY = {
    "mon": "mon",
    "tue": "tue",
    "wed": "wed",
    "thu": "thu",
    "fri": "fri",
    "sat": "sat",
    "sun": "sun",
    "周一": "mon",
    "星期一": "mon",
    "周二": "tue",
    "星期二": "tue",
    "周三": "wed",
    "星期三": "wed",
    "周四": "thu",
    "星期四": "thu",
    "周五": "fri",
    "星期五": "fri",
    "周六": "sat",
    "星期六": "sat",
    "周日": "sun",
    "周天": "sun",
    "星期日": "sun",
    "星期天": "sun",
}

CN_DIGIT = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

NEGATION_MARKERS = ("不是", "没空", "不行", "不能", "没", "不在", "没有")
CONTRAST_SPLITTERS = ("但是", "但", "不过", "然而")
PERIOD_KEYWORDS = (
    ("noon", ("中午", "午间")),
    ("afternoon", ("下午", "午后")),
    ("evening", ("晚上", "晚间", "夜里", "夜间")),
    ("morning", ("早上", "上午", "早晨", "清晨")),
    ("late_night", ("凌晨", "半夜")),
)

APPEND_KEYWORDS = ("还有", "再加", "另外", "额外", "再加上", "增加", "添加", "补上", "也多")
REPLACE_KEYWORDS = ("全部重来", "重新设置", "清空", "覆盖", "替换全部")
BUSY_KEYWORDS = ("没空", "忙", "上课", "补习", "培训", "有事", "考试", "排满", "占用", "不能", "不行")
AVAILABLE_KEYWORDS = ("有空", "能学", "方便", "空闲", "有时间", "可以", "能够")
TIME_INFO_PATTERNS = (
    r"\d{1,2}:\d{2}",
    r"\d{1,2}\s*点",
    r"[零一二两三四五六七八九十]+点",
    r"工作日|周末|周[一二三四五六日天]|星期",
    r"早上|上午|中午|下午|晚上|夜间|放学后",
)

SKILL_NAME = "availability-parser"
SKILL_VERSION = "1.1.0"
