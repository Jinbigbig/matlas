"""matlas 自采公共模块：体彩接口抓取/解析 + 队名归一。

从 jinbet/update_odds_net.py 抽取的三个纯函数（映射表原文照搬，保证口径一致），
加上 matlas 自己的代理兜底——与 scripts/fetch_odds_full.py 同口径，宿主侧每分钟跑。
容器内体彩接口 HTTP 567，故依赖本模块的脚本只在宿主侧调度。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

API = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://www.sporttery.cn/jc/jsq/zqhhgg/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _opener():
    """体彩接口需走本地代理，计划任务环境不继承会话变量，显式 fallback。"""
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or "http://127.0.0.1:65053")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def fetch_odds_from_lottery():
    """从体彩官网 API 抓取赔率 JSON 文本；失败返回空串。"""
    try:
        req = urllib.request.Request(API, headers=HEADERS)
        with _opener().open(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 获取体彩赔率失败: {e}")
        return ""


RESULT_TEAM_NAME_MAP = {
    '埃尔沃斯堡': '埃沃斯堡', '拜仁慕尼黑': '拜仁',
    '布斯巴达': '布斯巴达', '布拉格斯巴达': '布斯巴达',
    '圣吉联合': '圣吉联合', '圣吉尔联合': '圣吉联合',
    '奥林匹亚': '奥林匹亚', '奥林匹亚科斯': '奥林匹亚',
    '米亚尔比': '米亚尔比',
    '布拉迪斯': '布拉迪斯', '布拉加': '布拉迪斯',
    '奈梅亨': '奈梅亨', 'NEC奈梅亨': '奈梅亨',
    '里昂': '里昂',
    '博德闪耀': '博德闪耀',
    '塞伊奈': '塞伊奈', '塞伊奈约基': '塞伊奈',
    '哈尔姆斯': '哈尔姆斯', '哈尔姆斯塔德': '哈尔姆斯',
    '天狼星': '天狼星',
    '佐加顿斯': '佐加顿斯',
    '韦斯特罗': '韦斯特罗', '韦斯特罗斯': '韦斯特罗',
    '巴竞技': '巴竞技', '巴拉纳竞技': '巴竞技',
    '维多利亚': '维多利亚',
    '里莫': '里莫', '里奥阿维': '里莫',
    '桑托斯': '桑托斯',
    '奥胡斯': '奥胡斯',
    '费内巴切': '费内巴切',
    '格风暴': '格风暴', '格拉茨风暴': '格风暴',
    '弗鲁米嫩': '弗鲁米嫩', '弗鲁米嫩塞': '弗鲁米嫩',
    '达伽马': '达伽马', '瓦斯科达伽马': '达伽马',
    '哈马费萨': '哈马费萨', '哈马赫费萨利': '哈马费萨',
    '赫尔辛基': '赫尔辛基',
    'TPS图尔': 'TPS图尔', 'TPS图尔库': 'TPS图尔',
    '玛丽港': '玛丽港',
    '拉赫蒂': '拉赫蒂',
    '雅罗': '雅罗', '雅罗足球': '雅罗',
    '腓特烈': '腓特烈', '腓特烈斯塔': '腓特烈',
    '桑纳菲': '桑纳菲', '桑纳菲尤尔': '桑纳菲',
    '萨尔普斯堡': '萨尔普斯堡', '萨普斯堡': '萨尔普斯堡',
    '厄尔格里特': '厄尔格里特', '厄格里特': '厄尔格里特',
    '赫根': '赫根',
    '卡尔马': '卡尔马',
    '浦项制铁': '浦项',
    '金泉尚武': '金泉尚武',
    '全北现代': '全北现代',
    '首尔FC': '首尔FC',
    '江原FC': '江原FC',
    '富川FC': '富川FC',
    '波特兰': '波特兰', '波特兰伐木工': '波特兰',
    '西雅图': '西雅图', '西雅图海湾人': '西雅图',
    '洛城银河': '洛城银河', '洛杉矶银河': '洛城银河',
    '达拉斯': '达拉斯', '达拉斯FC': '达拉斯',
    '圣路易城': '圣路易城', '圣路易斯城': '圣路易城',
    '盐湖城': '盐湖城', '皇家盐湖城': '盐湖城',
    '芝加哥': '芝加哥', '芝加哥火焰': '芝加哥',
    '夏洛特FC': '夏洛特FC',
    '温哥华': '温哥华', '温哥华白帽': '温哥华',
    '洛杉矶FC': '洛杉矶FC',
    '迈国际': '迈国际', '迈阿密国际': '迈国际',
    '哥伦布': '哥伦布', '哥伦布机员': '哥伦布',
    '赫尔火花': '赫尔火花', '赫尔辛基火花': '赫尔火花',
    '坦佩雷山猫': '坦佩雷山猫', '坦山猫': '坦佩雷山猫',
    '库奥皮奥': '库奥皮奥',
    '斯达': '斯达', '斯塔贝克': '斯达',
    '维京': '维京',
    # 新增缺失的队名映射
    '阿拉木图': '阿拉木图', '阿拉木图凯拉特': '阿拉木图',
    '索列夫': '索列夫', '索菲亚列夫斯基': '索列夫',
    '里独立': '里独立', '里瓦达维亚独立': '里独立',
    '巴黎圣曼': '巴黎圣曼', '巴黎圣日尔曼': '巴黎圣曼',
    '帕梅拉斯': '帕梅拉斯', '帕尔梅拉斯': '帕梅拉斯',
    '波特诺': '波特诺', '波特诺山丘': '波特诺',
    # === 体彩官方全简称对照表（2026-05/06/07/08月竞彩网通知，长名→SCHEDULE标准名）===
    # 规则：标准名=SCHEDULE当前在用名；API可能返回官方简称或全名，都要能归一到标准名
    # 【瑞超】体彩官方全简称（2026-04-21通知）
    'AIK索尔纳': '索尔纳', '索尔纳': '索尔纳',
    '布鲁马波卡纳': '布鲁马波', '布鲁马': '布鲁马波',  # SCHEDULE标准=布鲁马波（比官方简称多1字，避免"布鲁马"误匹配其他）
    '代格福什': '代格福什', '代格福': '代格福什',
    '佐加顿斯': '佐加顿斯', '佐加顿': '佐加顿斯',
    '埃尔夫斯堡': '埃夫斯堡', '埃尔夫': '埃夫斯堡',  # SCHEDULE标准=埃夫斯堡（之前已修复方向）
    '哥德堡盖斯': '盖斯', '盖斯': '盖斯',
    'IFK哥德堡': '哥德堡', '哥德堡': '哥德堡',
    '哈尔姆斯塔德': '哈尔姆斯', '哈尔姆': '哈尔姆斯',  # SCHEDULE标准=哈尔姆斯
    '马尔默': '马尔默',
    '米亚尔比': '米亚尔比', '米亚尔': '米亚尔比',
    '厄尔格里特': '厄尔格里特', '厄格里': '厄尔格里特',
    '天狼星': '天狼星',
    '韦斯特罗斯': '韦斯特罗', '韦斯罗': '韦斯特罗',
    # 【芬超】体彩官方全简称（2026-04-21通知）
    'AC奥卢': 'AC奥卢',
    '赫尔辛基火花': '赫尔火花', '赫火花': '赫尔火花',
    '赫尔辛基': '赫尔辛基', '赫尔辛': '赫尔辛基',
    '坦佩雷山猫': '坦佩雷山猫', '坦山猫': '坦佩雷山猫',
    '国际图尔库': '国际图', '国际图尔': '国际图', '国际图': '国际图',
    '库奥皮奥': '库奥皮奥', '库奥皮': '库奥皮奥',
    '塞伊奈约基': '塞伊奈', '塞伊奈': '塞伊奈',
    'TPS图尔库': 'TPS图尔', 'TP图尔': 'TPS图尔',
    '瓦萨': '瓦萨',
    # 【葡超】体彩官方全简称（2026-08-04通知）
    '阿尔维卡': '阿尔维卡', '阿维卡': '阿尔维卡',
    '阿马多拉': '阿马多拉', '阿马多': '阿马多拉',
    '卡萨皮亚': '卡萨皮亚', '卡萨': '卡萨皮亚',
    '埃斯托里尔': '埃斯托里', '埃斯托': '埃斯托里',  # SCHEDULE标准=埃斯托里（之前已修复）
    '法马利康': '法马利康', '法马利': '法马利康',
    '吉维森特': '吉维森特', '吉维森': '吉维森特',
    '吉马良斯': '吉马良斯', '吉马良': '吉马良斯',
    '马里迪莫': '马里迪莫', '马里迪': '马里迪莫',
    '摩雷伦斯': '摩雷伦斯', '摩雷伦': '摩雷伦斯',
    '葡萄牙国民': '葡国民',
    '里奥阿维': '里莫', '里奥阿': '里莫',  # SCHEDULE标准=里莫
    '里斯本竞技': '里斯本', '里斯本': '里斯本',
    '圣克拉拉': '圣克拉拉', '圣克拉': '圣克拉拉',
    # 【巴甲】体彩官方全简称（2026-07-14通知）
    '米内罗竞技': '米内罗', '米内罗': '米内罗',
    '巴拉纳竞技': '巴竞技', '巴拉竞': '巴竞技',  # SCHEDULE标准=巴竞技
    '巴伊亚': '巴伊亚',
    '博塔弗戈': '博塔弗戈', '博塔弗': '博塔弗戈',
    '沙佩科恩斯': '沙佩科恩斯', '沙佩科': '沙佩科恩斯',
    '科里蒂巴': '科里蒂巴', '科里蒂': '科里蒂巴',
    '科林蒂安': '科林蒂安', '科林蒂': '科林蒂安',
    '克鲁塞罗': '克鲁塞罗', '克鲁塞': '克鲁塞罗',
    '弗拉门戈': '弗拉门戈', '弗拉门': '弗拉门戈',
    '格雷米奥': '格雷米奥', '格雷米': '格雷米奥',
    '巴西国际': '巴西国际', '巴国际': '巴西国际',
    '米拉索尔': '米拉索尔', '米拉索': '米拉索尔',
    '帕尔梅拉斯': '帕梅拉斯', '帕尔梅': '帕梅拉斯',  # SCHEDULE标准=帕梅拉斯
    '布拉干蒂诺RB': '布拉干蒂诺RB', '布拉RB': '布拉干蒂诺RB',
    '圣保罗': '圣保罗',
    '维多利亚': '维多利亚', '维多利': '维多利亚',
    # 【解放者杯】体彩官方全简称（2026-04-21通知）
    '巴兰基亚青年': '巴兰基亚青年', '巴兰基': '巴兰基亚青年',
    '时刻准备': '时刻准备', '时准备': '时刻准备',
    '瓜亚基尔巴塞罗那': '瓜亚基尔巴塞罗那', '瓜亚基': '瓜亚基尔巴塞罗那',
    '玻利瓦尔': '玻利瓦尔', '玻利瓦': '玻利瓦尔',
    '博卡青年': '博卡青年', '博卡': '博卡青年',
    '普拉滕斯': '普拉滕斯', '普拉滕': '普拉滕斯',
    '科金博联': '科金博联', '科金博': '科金博联',
    '拉瓜伊拉': '拉瓜伊拉', '拉瓜伊': '拉瓜伊拉',
    '托利马体育': '托利马体育', '托利马': '托利马体育',
    '拉普拉塔大学生': '拉普大学', '拉大学': '拉普大学',
    '德尔瓦耶独立': '德尔瓦耶独立', '德尔瓦': '德尔瓦耶独立',
    '麦德林独立': '麦德林独立', '麦独立': '麦德林独立',
    '圣菲独立': '圣菲独立', '菲独立': '圣菲独立',
    '基多体育大学': '基多体大', '基体大': '基多体大',
    '亚松森自由': '亚松森自由', '亚自由': '亚松森自由',
    '蒙得维的亚国民': '蒙得维的亚国民', '蒙国民': '蒙得维的亚国民',
    '佩纳罗尔': '佩纳罗尔', '佩纳罗': '佩纳罗尔',
    '罗萨里奥中央': '罗萨里奥中央', '罗萨里': '罗萨里奥中央',
    '水晶体育': '水晶体育', '水晶体': '水晶体育',
    '天主大学': '天主大学', '天主大': '天主大学',
    '大学生体育': '大学生体育', '大体育': '大学生体育',
    '委内瑞拉中央大学': '委内瑞拉中央大学', '中央大': '委内瑞拉中央大学',
    # 【世界杯/国家队】体彩官方全简称（2026-06-02通知）
    '阿尔及利亚': '阿尔及利亚', '阿尔及': '阿尔及利亚',
    '澳大利亚': '澳大利亚', '澳大利': '澳大利亚',
    '哥伦比亚': '哥伦比亚', '哥伦比': '哥伦比亚',
    '厄瓜多尔': '厄瓜多尔', '厄瓜多': '厄瓜多尔',
    '塞内加尔': '塞内加尔', '塞内加': '塞内加尔',
    # === 补充缺失的变体映射（统一到短名，与已完赛赛果 key 一致，避免重复比赛） ===
    # 瑞超：埃夫斯堡/埃尔夫斯堡 统一
    '埃夫斯堡': '埃夫斯堡',
    # 荷甲：鹿斯巴达/鹿特丹斯巴达 统一
    '鹿斯巴达': '鹿斯巴达', '鹿特丹斯巴达': '鹿斯巴达',
    # 葡超：葡国民/葡萄牙国民、埃斯托里/埃斯托里尔 统一
    '葡国民': '葡国民',
    '埃斯托里': '埃斯托里',
    # 英冠：狼队/伍尔弗汉普顿/伍尔弗 统一（API可能返回截断短名"伍尔弗"）
    '狼队': '狼队', '伍尔弗汉普顿': '狼队', '伍尔弗': '狼队',
    # 英超/社区盾：曼城/曼彻斯特城 统一
    '曼城': '曼城', '曼彻斯特城': '曼城',
    # 【欧冠/西甲】皇家马德里 → 皇马（2026-09-08 修复）
    # 现象：体彩顺序行返回官方全名"皇家马德里"（2041xxx，常无赔率），
    #       SCHEDULE/外部源用短名"皇马"（5502xxx，带赔率），两者未归一 →
    #       ODDS 里同场次出现两个键，UI 三处列表（赛果录入/赛果预测/添加记录）重复渲染一条 008。
    '皇家马德里': '皇马',
    # 沙职：胡巴尔卡德西亚 → 胡巴卡德（2026-09-08，同 008 类别名行问题）
    '胡巴尔卡德西亚': '胡巴卡德',
    # 同理：巴塞罗那 → 巴萨（预置，避免同日欧冠/西甲再出别名行）
    '巴塞罗那': '巴萨',
    '马德里竞技': '马竞',
    # === 2026-09-18 补充：体彩赛果API 官方全名 → SCHEDULE/ODDS 官方简称 ===
    # 现象：SCHEDULE 同场出现「简称行（带赔率与 matchId 5498xxx）」与「全名行
    #       （2041xxx 旧ID、赔率/让球/比分盘/战绩全空）」两行，未归一 → 当日生成
    #       18 行（真实 14 场）。下游按「后写胜」保留全名行 → 该场丢掉让球盘、
    #       比分盘与球队评级历史（报告 4.1 显示「无让球盘」、比分引擎无历史）。
    #       results_history 已统一为简称，故一律归一到简称。
    '沃尔夫斯堡': '沃夫斯堡',
    '达姆施塔特': '达姆施塔',
    '布里斯托尔城': '布城',
    '奥斯陆KFUM': '奥斯KFUM',
    '卡塔尔亚足': '卡塔尔23',
    # === 从原 TEAM_NAME_MAP 合并的有用变体映射（国家队/联赛，消除变体差异） ===
    '民主刚果': '刚果（金）', '刚果金': '刚果（金）', '刚果(金)': '刚果（金）',
    '乌兹别克': '乌兹别克斯坦', '乌兹别克斯坦': '乌兹别克斯坦',
    '阿尔及利': '阿尔及利亚', '阿尔及利亚': '阿尔及利亚',
    '沙特': '沙特阿拉伯', '沙特阿拉伯': '沙特阿拉伯',
    '贝西克塔斯': '贝西克塔', '斯普利特海杜克': '斯海杜克',
    '安德莱赫特': '安德莱', '费伦茨瓦罗斯': '费伦茨',
    '多伦多FC': '多伦多', '多伦多': '多伦多',
    '利勒斯特罗姆': '利勒斯特', '利勒斯特': '利勒斯特',
    '布鲁马波卡纳': '布鲁马波', '克里蒂安松': '克里斯蒂',
    '莫雷伦斯': '摩雷伦斯', '摩雷伦斯': '摩雷伦斯',
    '奥林匹亚科斯': '奥林匹亚', '布拉格斯巴达': '布斯巴达',
    '阿拉木图凯拉特': '阿拉木图', '索菲亚列夫斯基': '索列夫',
    '里瓦达维亚独立': '里独立', '巴黎圣日尔曼': '巴黎圣曼',
    '帕尔梅拉斯': '帕梅拉斯', '波特诺山丘': '波特诺',
    '莱比锡红牛': '莱红牛', '曼彻斯特联': '曼联',
    '中国女足': '中国女', '中国香港女足': '中国港女',
    '阿布扎比艾因': '艾因', '利雅得胜利': '利雅胜利',
    '米德尔斯堡': '米堡',
}


def _get_sorted_team_mapping():
    """返回按模式长度从长到短排序的队名映射列表，确保更具体的模式先匹配"""
    return sorted(RESULT_TEAM_NAME_MAP.items(), key=lambda x: len(x[0]), reverse=True)

_CRS_KEY_MAP = {}
for _h in range(6):
    for _a in range(6):
        _key = f's{_h:02d}s{_a:02d}'
        _CRS_KEY_MAP[_key] = f'{_h}:{_a}'
# 胜其他/平其他/负其他
_CRS_KEY_MAP['s1sh'] = '胜其他'
_CRS_KEY_MAP['s1sd'] = '平其他'
_CRS_KEY_MAP['s1sa'] = '负其他'

# 总进球key映射：API中 ttg 的 s0-s7 → 0-7+
_TTG_KEY_MAP = {f's{i}': str(i) for i in range(7)}
_TTG_KEY_MAP['s7'] = '7+'

# 半全场key映射：API中 hafu 的 key → 半全场文本
_HAFU_KEY_MAP = {
    'hh': '胜胜', 'hd': '胜平', 'ha': '胜负',
    'dh': '平胜', 'dd': '平平', 'da': '平负',
    'ah': '负胜', 'ad': '负平', 'aa': '负负',
}


def canonical_team_name(name):
    """全局队名标准化（按 key 长度从长到短匹配 RESULT_TEAM_NAME_MAP）。"""
    if not name:
        return ''
    name = str(name).strip()
    for map_name, standard_name in _get_sorted_team_mapping():
        if map_name in name:
            return standard_name
    return name


def parse_lottery_json(json_text):
    """解析体彩 JSON → (odds_data, schedule_data)，key 为 {日期}_{主}_{客}。"""
    odds_data = {}
    schedule_data = {}
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f'[错误] JSON解析失败: {e}')
        return odds_data, schedule_data
    if not data.get('success') or not data.get('value'):
        print(f'[错误] API返回失败: {data.get("errorMessage", "未知错误")}')
        return odds_data, schedule_data
    value = data['value']
    match_info_list = value.get('matchInfoList', [])
    league_list = value.get('leagueList', [])
    league_map = {}
    for l in league_list:
        lid = l.get('leagueId', '')
        lname = l.get('leagueNameAbbr', '') or l.get('leagueName', '')
        if lid and lname:
            league_map[str(lid)] = lname
    for date_info in match_info_list:
        business_date = date_info.get('businessDate', '')
        for m in date_info.get('subMatchList', []):
            home = m.get('homeTeamAllName', '') or m.get('homeTeamAbbName', '')
            away = m.get('awayTeamAllName', '') or m.get('awayTeamAbbName', '')
            if not home or not away:
                continue
            home = re.sub(r'\[[^\]]+\]', '', home).strip()
            away = re.sub(r'\[[^\]]+\]', '', away).strip()
            home = canonical_team_name(home)
            away = canonical_team_name(away)
            league = league_map.get(str(m.get('leagueId', '')), '')
            had = m.get('had', {})
            hhad = m.get('hhad', {})
            handicap = hhad.get('goalLine', '') or hhad.get('goalLineValue', '')
            score_odds = {name: crs.get(k, '') for k, name in _CRS_KEY_MAP.items()
                          if crs.get(k, '') and float(crs[k]) > 0} if (crs := m.get('crs', {})) else {}
            zjq_odds = {name: ttg.get(k, '') for k, name in _TTG_KEY_MAP.items()
                        if ttg.get(k, '') and float(ttg[k]) > 0} if (ttg := m.get('ttg', {})) else {}
            bqc_odds = {name: hafu.get(k, '') for k, name in _HAFU_KEY_MAP.items()
                        if hafu.get(k, '') and float(hafu[k]) > 0} if (hafu := m.get('hafu', {})) else {}
            key = f'{business_date}_{home}_{away}'
            odds_data[key] = {
                '胜': had.get('h', ''), '平': had.get('d', ''), '负': had.get('a', ''),
                '让球': [], '比分': score_odds, '总进球': zjq_odds, '半全场': bqc_odds,
                'league': league, 'matchId': str(m.get('matchId', '')),
                'matchNo': str(m.get('matchNum', '')), 'matchNumStr': m.get('matchNumStr', ''),
                'matchDate': business_date, 'matchTime': (m.get('matchTime', '') or '')[:5],
            }
            if handicap and (hhad.get('h') or hhad.get('d') or hhad.get('a')):
                odds_data[key]['让球'].append({
                    'handicap': handicap, '胜': hhad.get('h', ''),
                    '平': hhad.get('d', ''), '负': hhad.get('a', '')})
            if business_date not in schedule_data:
                schedule_data[business_date] = []
            schedule_data[business_date].append({
                'home': home, 'away': away, 'league': league,
                'matchId': str(m.get('matchId', '')), 'matchNo': str(m.get('matchNum', '')),
                'matchNumStr': m.get('matchNumStr', ''), 'matchTime': (m.get('matchTime', '') or '')[:5]})
    return odds_data, schedule_data
