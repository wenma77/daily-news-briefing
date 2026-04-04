from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from .dedupe import build_fingerprint, normalize_title, similarity
from .llm import LLMError, OpenAICompatibleClient
from .models import FeedSource
from .models import ArticleCandidate, EventCard, NewsletterDraft, NewsletterItem
from .utils import trim_complete_sentence, truncate_text

LOW_VALUE_KEYWORDS = {
    "优惠",
    "折扣",
    "促销",
    "广告",
    "直播带货",
    "种草",
    "抽奖",
    "娱乐八卦",
}

ROUTINE_FINANCE_KEYWORDS = {
    "公开市场操作",
    "公开市场业务交易公告",
    "贷款市场报价利率报价行名单",
    "LPR报价行名单",
    "新开户",
    "IPO盘点",
    "收评",
    "收盘",
    "看盘",
    "盘中",
    "午评",
    "例会",
    "公开市场",
    "逆回购",
    "货币政策委员会",
    "数字人民币",
    "运营机构",
}

OFFICIAL_PROPAGANDA_KEYWORDS = {
    "术语表",
    "网站地图",
    "无障碍浏览",
    "党组",
    "读书班",
    "学习教育",
    "活动举行",
    "成功举办",
    "筹备工作",
    "未来之城",
    "活力",
    "质控中心",
    "工作会议",
    "内部工作",
    "门户网站",
    "组织观看",
    "成果展",
    "良好生态",
    "工作课",
    "体验课",
    "培训计划",
    "友好合作",
    "重要纽带",
    "电视电话会议",
    "保出行",
    "一图看懂",
}

HARD_INFO_KEYWORDS = {
    "新政",
    "通报",
    "签约",
    "生效",
    "补贴",
    "收储",
    "新增",
    "死亡",
    "受伤",
    "遇难",
    "事故",
    "灾害",
    "关税",
    "停火",
    "融资",
    "裁员",
    "并购",
    "收购",
    "降准",
    "降息",
    "加息",
    "站上",
    "突破",
    "暴涨",
    "暴跌",
    "扩围",
    "处罚",
    "上涨",
    "下跌",
    "跌超",
    "涨超",
    "大涨",
    "大跌",
    "重挫",
    "首提",
    "严禁",
    "挂牌督办",
    "开工",
    "投产",
}

WEAK_ANALYSIS_TITLE_KEYWORDS = {
    "焦点",
    "漫评",
    "双面美利坚",
    "新职业",
    "造梦者",
    "发生了什么",
    "各讲了哪些",
    "特色打法",
    "谈AI",
    "怎么用",
    "理性选择",
    "养虾",
    "现场",
    "如何",
    "逆势突围",
    "观望态度",
    "低开",
    "重挫",
    "狂飙",
    "豪言",
    "跻身前三",
    "券商年报",
    "表述",
    "讲了哪些",
    "隐形优势",
    "新趋势",
    "见底",
    "解码",
    "观察丨",
    "观点",
    "8点见",
    "访谈",
    "海斌访谈",
    "泼点冷水",
}

WEAK_PUBLIC_IMPACT_KEYWORDS = {
    "负责人就",
    "答记者问",
    "阳光招生",
    "重点任务",
    "重点班",
    "实验班",
    "快慢班",
    "义务教育学校",
    "检查指导组",
    "非合规车辆",
    "特殊教育",
    "孤独症",
    "保障体系",
    "专题宣讲",
    "推进建设",
    "世界一流",
    "强港",
    "已建成",
    "友好场景",
    "中文教育中心",
    "大赛启动",
    "通电话",
    "会见",
    "开设",
    "促消费",
    "频道",
    "培训会议",
    "座谈会",
    "算力之都",
    "打造",
    "回应时代命题",
    "谋新篇",
    "新场景",
    "消费+骑行",
    "出行提示",
    "出行预警",
    "遴选公告",
    "暖心服务",
    "奖励案例",
}

WEAK_SERVICE_NOTICE_KEYWORDS = {
    "安全教育周",
    "活动展开",
    "宣传周",
    "专项招生",
    "专项招生计划",
    "招生工作",
    "清明假期",
    "保出行",
    "交通部门多措施",
    "出行提示",
    "出行保障",
    "气象服务",
    "气象提示",
    "安全提示",
    "电视电话会议",
    "推进会",
    "工作部署",
    "组织开展",
    "宣传活动",
    "服务保障",
    "风险防范",
    "假期前后",
    "友好合作",
    "重要纽带",
    "共同发展",
    "全体会议",
    "主持召开",
    "委员会全体会议",
    "意向登记",
    "提前招生",
    "家庭教育指导",
    "实践活动",
    "社会保障卡",
    "一卡通",
}

GENERIC_TITLE_BLOCKERS = {
    "推进工作",
    "服务保障",
    "持续完善",
    "建立机制",
    "组织开展",
    "工作部署",
    "推进会",
    "活动展开",
    "宣传周",
    "教育周",
    "招生工作",
}

WEAK_TECHNOLOGY_KEYWORDS = {
    "平台成立",
    "协同平台",
    "服务平台",
    "产业协同",
    "赋能",
    "推进建设",
    "组网建设",
    "应用落地",
    "生态建设",
    "加快培育",
    "产业平台",
    "算力之都",
    "新场景",
    "谋新篇",
    "算力银行",
    "算力超市",
    "进入讨论",
    "商业边界",
    "受关注",
}

HARD_TECH_ACTION_KEYWORDS = {
    "收购",
    "并购",
    "融资",
    "裁员",
    "推出",
    "发布模型",
    "新模型",
    "开源",
    "自研",
    "禁售",
    "制裁",
    "量产",
    "投产",
    "订单",
    "财报",
    "芯片",
    "半导体",
    "GPU",
    "HBM",
}

MAJOR_ENTERPRISE_ACTION_KEYWORDS = {
    "收购",
    "并购",
    "谈判",
    "融资",
    "裁员",
    "禁售",
    "剥离",
    "分拆",
    "合作",
    "投资",
}

TECH_GOSSIP_KEYWORDS = {
    "分手细节",
    "首次公开",
    "除了品牌",
    "说“不”",
    "说“不”？",
    "引发争议",
    "遭质疑",
    "分析人士质疑",
    "并购逻辑",
    "内幕",
    "秘闻",
}

PUBLIC_IMPACT_TOPIC_KEYWORDS = {
    "AI",
    "人工智能",
    "教育",
    "高考",
    "招生",
    "住房",
    "房贷",
    "医疗",
    "医保",
    "卫健",
    "交通",
    "出行",
    "航班",
    "铁路",
    "地铁",
    "高速",
    "食品安全",
    "药品",
    "就业",
    "社保",
    "养老",
    "气象",
}

PUBLIC_IMPACT_RESULT_KEYWORDS = {
    "事故",
    "灾害",
    "死亡",
    "受伤",
    "遇难",
    "伤亡",
    "爆炸",
    "火灾",
    "洪水",
    "地震",
    "台风",
    "暴雨",
    "山火",
    "中毒",
    "停运",
    "停航",
    "停课",
    "停诊",
    "召回",
    "通报",
    "处罚",
    "挂牌督办",
    "问责",
    "严禁",
    "塌方",
    "坍塌",
    "侵权",
    "版权",
    "肖像",
    "盗脸",
}

HARD_PUBLIC_POLICY_KEYWORDS = {
    "高考改革",
    "考试改革",
    "房贷利率",
    "医保目录",
    "药品召回",
    "食品安全",
}

HARD_INTERNATIONAL_KEYWORDS = {
    "特朗普",
    "白宫",
    "对华",
    "关税",
    "伊朗",
    "以色列",
    "加沙",
    "乌克兰",
    "俄乌",
    "停火",
    "制裁",
    "军事",
    "袭击",
    "战争",
    "冲突",
    "中东",
    "红海",
    "哈马斯",
    "北约",
    "欧盟",
}

FOREIGN_LOCATION_KEYWORDS = {
    "美国",
    "伊朗",
    "以色列",
    "乌克兰",
    "俄罗斯",
    "巴西",
    "英国",
    "法国",
    "德国",
    "日本",
    "韩国",
    "印度",
    "加沙",
    "中东",
    "欧洲",
}

HARD_EVENT_OVERRIDE_KEYWORDS = {
    "死亡",
    "受伤",
    "遇难",
    "伤亡",
    "通报",
    "处罚",
    "挂牌督办",
    "关税",
    "停火",
    "制裁",
    "收储",
    "生效",
    "签约",
    "裁员",
    "收购",
    "并购",
    "停运",
    "停航",
    "停课",
}

LOW_VALUE_TITLE_KEYWORDS = {
    "研学",
    "论坛",
    "峰会",
    "讲座",
    "开班",
    "开营",
    "参观",
    "校庆",
    "校园",
    "大学",
    "学院",
    "征文",
    "招聘会",
    "开幕",
    "闭幕",
    "旅游节",
    "美丽中国",
    "发布会",
    "体验店",
    "上新",
    "评选",
    "榜单",
    "被曝",
    "曝光",
    "传感器",
    "眼镜",
    "手表",
    "手机",
    "耳机",
    "档案库",
    "健身",
    "最喜欢",
    "采访",
    "OTA",
    "升级",
    "开箱",
    "上手",
    "拆解",
    "爆料",
    "订阅",
    "独家",
    "晚报",
    "挑战赛",
    "报名",
    "00后",
    "博士",
    "补偿方案",
    "致歉",
    "开售",
    "实时查看",
    "股民可索赔",
    "署名文章",
    "互利共赢",
    "新纪元",
    "世界说",
    "发展机遇",
    "稳了",
    "还有多远",
    "致歉",
    "补偿",
    "街区",
    "量稳质升",
    "持续增强",
    "帮推",
    "大会",
    "齐聚",
    "创新大会",
    "报名",
    "看盘",
    "利空",
    "利好",
    "媒体报道",
    "活动举行",
    "成功举办",
    "筹备工作",
    "工作会议",
    "读书班",
    "党组",
    "学习教育",
    "质控中心",
    "周报",
    "财报速递",
    "速递丨",
    "出海·能源",
    "投向标",
    "硬科技投向标",
    "商经情报局",
    "环球市场",
    "含视频",
    "第一时间",
    "8点见",
    "新华视点",
    "小长假里看中国",
    "品质生活",
    "巾帼奋斗者",
    "点亮学子梦想",
    "时刻表",
    "财经观察",
    "访谈",
    "海斌访谈",
    "一卡通",
    "社会保障卡",
    "第94波",
    "波攻势",
}

EARNINGS_KEYWORDS = {
    "财报",
    "业绩",
    "营收",
    "净利",
    "营利",
    "亏损",
    "双降",
    "年报",
    "季报",
    "中报",
    "一季报",
    "半年报",
}

MAJOR_COMPANY_KEYWORDS = {
    "OpenAI",
    "微软",
    "谷歌",
    "Google",
    "苹果",
    "Apple",
    "Meta",
    "亚马逊",
    "Amazon",
    "英伟达",
    "NVIDIA",
    "特斯拉",
    "Tesla",
    "台积电",
    "TSMC",
    "阿里",
    "腾讯",
    "华为",
    "比亚迪",
    "字节",
    "字节跳动",
}

DOMESTIC_SIGNAL_KEYWORDS = {
    "国务院",
    "央行",
    "财政部",
    "证监会",
    "工信部",
    "发改委",
    "住建部",
    "政策",
    "监管",
    "专项债",
    "房地产",
    "A股",
    "港股",
    "华为",
    "腾讯",
    "阿里",
    "小米",
    "比亚迪",
    "宁德时代",
    "芯片",
    "半导体",
    "算力",
    "应急",
    "灾害",
    "事故",
    "食品安全",
}

INTERNATIONAL_SIGNAL_KEYWORDS = {
    "OpenAI",
    "微软",
    "谷歌",
    "Google",
    "苹果",
    "Apple",
    "Meta",
    "亚马逊",
    "Amazon",
    "英伟达",
    "NVIDIA",
    "特斯拉",
    "Tesla",
    "台积电",
    "TSMC",
    "Samsung",
    "美联储",
    "Fed",
    "欧盟",
    "欧央行",
    "FDA",
    "关税",
    "停火",
    "乌克兰",
    "中东",
    "以色列",
    "OPEC",
}

MARKET_SIGNAL_KEYWORDS = {
    "融资",
    "IPO",
    "并购",
    "裁员",
    "财报",
    "原油",
    "黄金",
    "美股",
    "A股",
    "港股",
    "芯片",
    "半导体",
    "算力",
    "GPU",
    "HBM",
    "AI",
    "人工智能",
}

PUBLIC_IMPACT_KEYWORDS = {
    "地震",
    "洪水",
    "台风",
    "暴雨",
    "山火",
    "事故",
    "灾害",
    "食品安全",
    "药品召回",
    "医保目录",
    "房贷利率",
    "停运",
    "停航",
    "停课",
    "召回",
    "死亡",
    "遇难",
    "受伤",
    "伤亡",
    "挂牌督办",
    "处罚",
    "通报",
    "爆炸",
    "火灾",
    "塌方",
    "坍塌",
}

GENERIC_AGGREGATOR_HINTS = {
    "Google News",
    "谷歌新闻",
}

PRIMARY_PUBLISHERS = {
    "Reuters World",
    "Reuters Business",
    "Reuters Technology",
    "Reuters",
    "Federal Reserve Monetary Policy",
    "商务部新闻发布",
    "工信部新闻发布会",
    "中国人民银行首页公开信息",
    "华尔街见闻",
    "新华网",
    "央视网",
    "新京报",
    "界面新闻",
    "财联社",
    "财新",
    "第一财经",
    "每日经济新闻",
    "证券时报",
    "中国证券报",
    "经济观察报",
    "澎湃新闻",
    "新华社",
    "人民日报",
    "央视新闻",
    "彭博",
    "彭博社",
    "金融时报",
    "FT中文网",
    "华尔街日报中文网",
}

SECONDARY_PUBLISHERS = {
    "21财经",
    "21世纪经济报道",
    "界面",
    "经济日报",
    "中国日报网",
    "中国新闻网",
    "上海证券报",
    "美国之音",
    "thepaper.cn",
    "stcn.com",
    "bjnews.com.cn",
}

DOMESTIC_REFERENCE_PUBLISHERS = {
    "财联社",
    "第一财经",
    "证券时报",
    "每日经济新闻",
    "中国证券报",
    "经济观察报",
    "界面新闻",
    "界面",
    "澎湃新闻",
    "21财经",
    "21世纪经济报道",
    "经济日报",
    "中国新闻网",
    "中国日报网",
    "新华社",
    "人民日报",
    "央视新闻",
}

MARKET_ALLOWED_PUBLISHERS = {
    "财联社",
    "第一财经",
    "证券时报",
    "中国证券报",
    "每日经济新闻",
    "经济观察报",
    "21财经",
    "21世纪经济报道",
    "华尔街见闻",
    "Reuters",
    "Reuters Business",
}

PRIMARY_DOMAIN_SUFFIXES = {
    "reuters.com",
    "federalreserve.gov",
    "news.un.org",
    "un.org",
    "gov.cn",
    "mofcom.gov.cn",
    "miit.gov.cn",
    "pbc.gov.cn",
    "news.cn",
    "xinhuanet.com",
    "cctv.com",
    "people.com.cn",
    "cls.cn",
    "yicai.com",
    "stcn.com",
    "nbd.com.cn",
    "cnstock.com",
    "eeo.com.cn",
    "thepaper.cn",
    "jiemian.com",
    "caixin.com",
    "wallstreetcn.com",
    "21jingji.com",
    "chinanews.com.cn",
    "jingjiribao.cn",
}

SECONDARY_DOMAIN_SUFFIXES = {
    "yicai.com",
    "21jingji.com",
    "jiemian.com",
    "thepaper.cn",
    "chinadaily.com.cn",
    "cnstock.com",
    "bjnews.com.cn",
    "voachinese.com",
}

OFFICIAL_DOMAIN_SUFFIXES = {
    "gov.cn",
    "federalreserve.gov",
    "news.un.org",
    "un.org",
    "mofcom.gov.cn",
    "miit.gov.cn",
    "pbc.gov.cn",
    "news.cn",
    "xinhuanet.com",
    "cctv.com",
    "people.com.cn",
    "jingjiribao.cn",
}

OFFICIAL_PUBLISHER_HINTS = {
    "gov.cn",
    "Federal Reserve",
    "UN News",
    "商务部",
    "工信部",
    "人民银行",
    "新华网",
    "央视网",
    "经济日报",
    "jingjiribao.cn",
    "新华社",
    "人民日报",
    "央视新闻",
    "中国新闻网",
    "中国日报网",
}

DISALLOWED_PUBLISHER_HINTS = {
    "新浪财经",
    "新浪网",
    "sina.cn",
    "tech.sina.cn",
    "同花顺",
    "凤凰网",
    "凤凰网财经",
    "搜狐网",
    "36Kr",
    "36氪",
    "36 Kr",
    "cnBeta",
    "东方财富",
    "富途牛牛",
    "TechCrunch",
    "Binance",
    "DoNews",
    "ByDrug",
    "InfoQ",
    "智源社区",
    "中金在线",
    "电子工程专辑",
    "swjtu.edu.cn",
    "大学",
    "学院",
}

DISALLOWED_DOMAIN_SUFFIXES = {
    "sina.com.cn",
    "sina.cn",
    "10jqka.com.cn",
    "ifeng.com",
    "36kr.com",
    "sohu.com",
    "sohu.com.cn",
    "cnbeta.com",
    "eastmoney.com",
    "futunn.com",
    "binance.com",
    "techcrunch.com",
    "donews.com",
    "infoq.cn",
    "zhidx.com",
    "opinion.caixin.com",
    "tv.cctv.com",
    "swjtu.edu.cn",
    "edu.cn",
}

FINAL_ALLOWED_DOMAINS = {
    "reuters.com",
    "federalreserve.gov",
    "news.un.org",
    "un.org",
    "wallstreetcn.com",
    "thepaper.cn",
    "bjnews.com.cn",
    "news.cn",
    "xinhuanet.com",
    "cctv.com",
    "people.com.cn",
    "cls.cn",
    "yicai.com",
    "stcn.com",
    "cnstock.com",
    "nbd.com.cn",
    "eeo.com.cn",
    "jiemian.com",
    "caixin.com",
    "21jingji.com",
    "chinanews.com.cn",
    "jingjiribao.cn",
    "voachinese.com",
    "gov.cn",
    "mofcom.gov.cn",
    "miit.gov.cn",
    "pbc.gov.cn",
    "mem.gov.cn",
    "moe.gov.cn",
    "mot.gov.cn",
    "mohurd.gov.cn",
    "nhc.gov.cn",
    "stats.gov.cn",
    "samr.gov.cn",
}

BUSINESS_IMPACT_KEYWORDS = {
    "财报",
    "营收",
    "利润",
    "净利",
    "裁员",
    "收购",
    "并购",
    "融资",
    "IPO",
    "监管",
    "处罚",
    "诉讼",
    "禁令",
    "关税",
    "停火",
    "产能",
    "供应链",
    "订单",
    "交付",
    "政策",
    "利率",
    "加息",
    "降息",
}


@dataclass(slots=True)
class AINewsEditor:
    client: OpenAICompatibleClient
    headline_count: int
    brief_count: int
    keyword_count: int
    event_similarity: float
    source_registry: dict[str, FeedSource] = field(default_factory=dict)

    def clean_candidates(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        if not candidates:
            return []
        heuristic_cleaned = self._heuristic_clean(candidates)
        prompt_items = [item.to_prompt_dict() for item in candidates]
        system_prompt = (
            "你是严谨的中文新闻值班主编。"
            "请只保留真正重要、可信、信息量足够的新闻候选。"
            "禁止追逐八卦、营销稿、导购稿、纯观点稿。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "从候选新闻中保留适合做每日重点新闻简报的条目。",
                "rules": [
                    "优先级：国际地缘/战争/全球冲突 > 科技与AI > 重大民生与公共事件 > 重大政策监管 > 市场财经",
                    "优先保留国际大事、战争冲突、关税与能源、科技和AI、国内重大事故灾害、民生公共事件和真正高热度综合事件",
                    "财经和央行类只保留极少数真正会显著影响全国或全球预期的新闻",
                    "国际新闻只要大公司、大市场、大事件，不要国外小公司小动作",
                    "剔除地方小事、校园新闻、会展论坛、软文、营销稿、信息不足条目",
                    "如果只是普通产品发布、小额融资、区域小新闻、鸡毛蒜皮事件、例行金融公告、盘面解读，一律删除",
                    "输出字段 kept_ids，值为候选 id 数组",
                ],
                "candidates": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            kept_ids = {str(item).strip() for item in data.get("kept_ids", []) if str(item).strip()}
            cleaned = [item for item in candidates if item.id in kept_ids]
            if cleaned:
                return self._apply_candidate_gate(self._merge_candidates(cleaned, heuristic_cleaned))
        except LLMError:
            pass
        return self._apply_candidate_gate(heuristic_cleaned)

    def quality_score(self, candidate: ArticleCandidate) -> int:
        return self._quality_score(candidate)

    def group_events(
        self,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        if not candidates:
            return []
        heuristic_events = self._heuristic_group(candidates, seen_fingerprints)
        prompt_items = [item.to_prompt_dict() for item in candidates]
        system_prompt = (
            "你是中文新闻编辑台的统筹编辑。"
            "请把同一事件的多篇报道合并为事件卡片，并按重要性打分。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "把候选新闻聚合为事件卡片。",
                "rules": [
                    "同一事件的多篇报道必须合并",
                    "importance_score 取 0 到 100 的整数",
                    "category 只用：国内、国际、财经、科技、其他",
                    "每个事件需要 title、summary、article_ids",
                    "重点看影响力和热度，不要把鸡毛蒜皮的小事聚成事件",
                    "不要输出最近 3 天已经推送过的重复事件",
                ],
                "recent_sent_fingerprints": sorted(seen_fingerprints),
                "candidates": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            events = self._events_from_json(data, candidates, seen_fingerprints)
            if events:
                return self._merge_events(events, heuristic_events)
        except LLMError:
            pass
        return heuristic_events

    def curate_events(self, events: list[EventCard]) -> list[EventCard]:
        if not events:
            return []
        heuristic_events = [event for event in events if self._passes_event_gate(event)]
        prompt_items = [
            {
                "event_id": event.event_id,
                "title": event.title,
                "category": event.category,
                "importance_score": event.importance_score,
                "source_name": event.source_name,
                "summary": event.summary,
            }
            for event in events
        ]
        system_prompt = (
            "你是中文新闻编辑部的总编终审。"
            "你的任务不是凑条数，而是从候选事件里留下真正值得进入每日重点新闻邮件的内容。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "对事件卡片做最终终审筛选。",
                "rules": [
                    "只保留影响范围大、市场关注高、后续影响强、信息可信的事件",
                    "优先保留：国际地缘局势、战争冲突、关税与能源、AI与半导体重大变化、重大民生与公共事件、真正会改变全国或全球预期的政策动作",
                    "剔除：产品小更新、功能升级、展会大会、活动预告、花边采访、口号式稿件、宣传稿、单一公司小融资、小作文式解读",
                    "剔除：例行央行公告、LPR名单、新开户数、IPO盘点、盘面解读、午评收评类条目",
                    "剔除角度重复的同一事件，只保留更硬、更源头、更清晰的一条",
                    "允许保留很多条，但不能为了数量降低质量标准",
                    "输出字段 kept_event_ids，值为 event_id 数组，按你建议的优先顺序排序",
                ],
                "events": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            kept_ids = [str(item).strip() for item in data.get("kept_event_ids", []) if str(item).strip()]
            curated = self._ordered_events_from_ids(kept_ids, events)
            if curated:
                merged = self._merge_events(curated, heuristic_events)
                return [event for event in merged if self._passes_event_gate(event)]
        except LLMError:
            pass
        return heuristic_events

    def draft_newsletter(self, events: list[EventCard], date_label: str, subject_template: str) -> NewsletterDraft:
        if not events:
            return NewsletterDraft(
                subject=subject_template.format(date=date_label),
                overview="今天没有形成足够稳定且重要的事件集合，本期仅保留空白简报框架。",
                lead_items=[],
                brief_items=[],
                watch_items=[],
                keywords=["候选不足"],
            )
        heuristic_final = self._finalize_draft(
            self._heuristic_draft(events, date_label, subject_template),
            events,
            date_label,
            subject_template,
        )
        event_map = {event.event_id: event for event in events}

        prompt_items = [item.to_prompt_dict() for item in events]
        system_prompt = (
            "你是顶级中文新闻编辑，要写一封适合邮件推送的每日重点新闻简报。"
            "风格要克制、专业、信息密度高，像编辑部筛出来的早报。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "输出最终 newsletter。",
                "rules": [
                    f"lead_items 最多 {self.headline_count} 条",
                    f"brief_items 最多 {self.brief_count} 条，且不能与 lead_items 重复",
                    "每条都要包含 event_id、title、source_name、summary、link、category",
                    "如果是国际事件且存在同一事件下的高质量国内报道，可额外输出 domestic_reference_url 和 domestic_reference_name",
                    "lead_items 放真正值得细看的重点新闻，summary 用 60 到 120 字中文，必须写完整，不要省略号，并尽量包含关键数字、关键动作或关键市场反应",
                    "brief_items 放额外的高质量新闻清单，summary 用 30 到 70 字中文，必须是完整短句，不能靠点击链接才读懂",
                    "watch_items 输出 2 到 4 条短句，每条都写后续值得观察的变量，不写预测性结论",
                    "lead_items 里优先放国际局势、科技AI、民生公共事件；财经和央行类最多只保留极少数真正重要的内容",
                    "不要为了凑数加入影响很小的小新闻",
                    "不要写‘为什么重要’这种模板化句子，也不要重复空话",
                    "标题直接说重点，来源单独写在 source_name",
                    f"keywords 输出 3 到 {self.keyword_count} 个",
                    "overview 是 1 段中文，概括当天最重要趋势，不要写套话",
                    "如果当天有效事件不足，允许少于目标条数，禁止编造或重复填充",
                ],
                "subject_template": subject_template,
                "date": date_label,
                "events": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            draft = self._finalize_draft(
                self._build_draft_from_json(data, events, date_label, subject_template),
                events,
                date_label,
                subject_template,
            )
            if draft.lead_items or draft.brief_items:
                heuristic_score = self._draft_quality_score(heuristic_final, event_map, events)
                llm_score = self._draft_quality_score(draft, event_map, events)
                if heuristic_score > llm_score:
                    return heuristic_final
                return draft
        except LLMError:
            pass
        return heuristic_final

    def _events_from_json(
        self,
        data: dict,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        by_id = {item.id: item for item in candidates}
        events: list[EventCard] = []
        for index, item in enumerate(data.get("events", []), start=1):
            article_ids = [str(article_id) for article_id in item.get("article_ids", []) if str(article_id) in by_id]
            if not article_ids:
                continue
            group_articles = [by_id[article_id] for article_id in article_ids]
            representative = self._pick_representative(group_articles)
            title = str(item.get("title", "")).strip() or representative.title
            category = str(item.get("category", "")).strip() or representative.category_hint
            if category == "国际":
                representative = self._pick_representative(group_articles, prefer_non_domestic=True)
            domestic_reference_url, domestic_reference_name = self._select_domestic_reference(
                group_articles,
                representative.url,
            )
            fingerprint = build_fingerprint(title, category)
            if fingerprint in seen_fingerprints:
                continue
            summary = self._best_event_summary(
                group_articles,
                preferred=str(item.get("summary", "")).strip(),
                title=title,
                source_name=representative.publisher or representative.source,
                representative=representative,
                limit=160,
            )
            events.append(
                EventCard(
                    event_id=f"E{index}",
                    title=title,
                    category=category,
                    importance_score=max(0, min(100, int(item.get("importance_score", 50)))),
                    summary=summary,
                    article_ids=article_ids,
                    representative_url=representative.url,
                    source_name=representative.publisher or representative.source,
                    domestic_reference_url=domestic_reference_url,
                    domestic_reference_name=domestic_reference_name,
                    why_it_matters=truncate_text(str(item.get("why_it_matters", "")).strip(), 120),
                    fingerprint=fingerprint,
                )
            )
        return sorted(
            [event for event in events if self._passes_event_gate(event)],
            key=lambda event: event.importance_score,
            reverse=True,
        )

    def _build_draft_from_json(
        self,
        data: dict,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        event_map = {event.event_id: event for event in events}

        def build_item(raw_item: dict) -> NewsletterItem | None:
            event_id = str(raw_item.get("event_id", "")).strip()
            event = event_map.get(event_id)
            if not event:
                return None
            summary = self._usable_summary(
                str(raw_item.get("summary", "")).strip() or event.summary,
                title=str(raw_item.get("title", "")).strip() or event.title,
                source_name=str(raw_item.get("source_name", "")).strip() or event.source_name,
                limit=150,
            )
            return NewsletterItem(
                event_id=event_id,
                title=str(raw_item.get("title", "")).strip() or event.title,
                summary=summary,
                link=str(raw_item.get("link", "")).strip() or event.representative_url,
                category=str(raw_item.get("category", "")).strip() or event.category,
                source_name=str(raw_item.get("source_name", "")).strip() or event.source_name,
                domestic_reference_url=(
                    str(raw_item.get("domestic_reference_url", "")).strip() or event.domestic_reference_url
                ),
                domestic_reference_name=(
                    str(raw_item.get("domestic_reference_name", "")).strip() or event.domestic_reference_name
                ),
            )

        lead_items = [item for item in (build_item(raw) for raw in data.get("lead_items", [])) if item]
        brief_items = [item for item in (build_item(raw) for raw in data.get("brief_items", [])) if item]
        seen_ids = {item.event_id for item in lead_items}
        brief_items = [item for item in brief_items if item.event_id not in seen_ids]

        return NewsletterDraft(
            subject=str(data.get("subject", "")).strip() or subject_template.format(date=date_label),
            overview=trim_complete_sentence(str(data.get("overview", "")).strip(), 220),
            lead_items=lead_items[: self.headline_count],
            brief_items=brief_items[: self.brief_count],
            watch_items=[
                truncate_text(str(item).strip(), 42)
                for item in data.get("watch_items", [])
                if str(item).strip()
            ][:4],
            keywords=[
                truncate_text(str(keyword).strip(), 18)
                for keyword in data.get("keywords", [])
                if str(keyword).strip()
            ][: self.keyword_count],
        )

    def _heuristic_clean(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        results: list[ArticleCandidate] = []
        for candidate in candidates:
            if self._quality_score(candidate) < 1:
                continue
            results.append(candidate)
        results.sort(key=self._quality_score, reverse=True)
        return results[: max(self.headline_count + self.brief_count + 40, 80)]

    def _quality_score(self, candidate: ArticleCandidate) -> int:
        text = self._candidate_text(candidate)
        publisher = self._publisher_name(candidate)
        domain = self._candidate_domain(candidate)
        source_tier = self._governed_source_tier_value(candidate.source)
        publisher_tier = self._publisher_tier_value(publisher, domain)
        source_role = self._source_role_value(candidate.source)
        publisher_role = self._publisher_role_value(publisher, domain)
        trusted = publisher in PRIMARY_PUBLISHERS
        secondary = publisher in SECONDARY_PUBLISHERS
        trusted_domain = self._matches_domain_suffix(domain, PRIMARY_DOMAIN_SUFFIXES)
        secondary_domain = self._matches_domain_suffix(domain, SECONDARY_DOMAIN_SUFFIXES)
        domestic_signal = self._contains_any(text, DOMESTIC_SIGNAL_KEYWORDS)
        international_signal = self._contains_any(text, INTERNATIONAL_SIGNAL_KEYWORDS)
        market_signal = self._contains_any(text, MARKET_SIGNAL_KEYWORDS)
        public_impact = self._has_strong_public_impact(text)
        business_impact = self._contains_any(text, BUSINESS_IMPACT_KEYWORDS)
        family = self._event_family_from_text(text)
        score = 0

        effective_tier = max(source_tier, publisher_tier)
        effective_role = max(source_role, publisher_role)
        if effective_tier >= 3:
            score += 3
        elif effective_tier == 2:
            score += 1
        if effective_role >= 3:
            score += 1
        if trusted:
            score += 3
        if secondary:
            score += 1
        if trusted_domain:
            score += 3
        elif secondary_domain:
            score += 1
        if domestic_signal:
            score += 2
        if international_signal:
            score += 3
        if market_signal:
            score += 2
        if public_impact:
            score += 2
        if business_impact:
            score += 2
        if candidate.category_hint in {"国内", "国际", "财经", "科技"}:
            score += 1
        if candidate.article_text_source == "article" and len(candidate.article_text) >= 100:
            score += 1
        elif len(candidate.feed_summary) >= 60:
            score += 1
        if any(publisher.startswith(prefix) for prefix in ("Reuters", "财联社", "新华社", "界面新闻", "第一财经")):
            score += 1
        if family in {"international_geopolitics", "technology", "public_impact"}:
            score += 3
        elif family == "policy":
            score += 1
        elif family == "market":
            score -= 1
        if self._is_hard_international_event(text):
            score += 3
        if self._is_hard_technology_event(text):
            score += 2

        if self._contains_any(text, LOW_VALUE_KEYWORDS):
            score -= 4
        if self._contains_any(candidate.title, LOW_VALUE_TITLE_KEYWORDS):
            score -= 4
        if self._contains_any(candidate.title, WEAK_ANALYSIS_TITLE_KEYWORDS):
            score -= 5
        if self._contains_any(candidate.title, WEAK_PUBLIC_IMPACT_KEYWORDS):
            score -= 16
        if self._is_weak_service_notice(candidate.title, text):
            score -= 20
        if self._is_local_low_impact(candidate.title):
            score -= 10
        if "教育部" in candidate.title and "保障体系" in candidate.title:
            score -= 3
        if self._is_routine_finance(candidate):
            score -= 14
        if self._is_official_propaganda(candidate.title, text):
            score -= 10
        if self._is_soft_technology_event(candidate.title, text):
            score -= 10
        if self._is_technology_gossip(candidate.title, text):
            score -= 10
        if self._is_roundup_title(candidate.title):
            score -= 12
        if self._is_low_value_earnings_story(candidate.title, text):
            score -= 12
        if self._is_weather_alert_service(candidate.title, text):
            score -= 12
        if self._is_major_enterprise_event(candidate.title, text):
            score += 2
        if "融资" in candidate.title and not (trusted or domestic_signal or international_signal):
            score -= 3
        if publisher == "新浪财经":
            score -= 2
        if self._matches_domain_suffix(domain, DISALLOWED_DOMAIN_SUFFIXES):
            score -= 6
        if secondary and not (business_impact or domestic_signal or international_signal or market_signal):
            score -= 3
        if self._contains_any(publisher, DISALLOWED_PUBLISHER_HINTS):
            score -= 6
        if any(hint in publisher for hint in GENERIC_AGGREGATOR_HINTS):
            score -= 1
        if candidate.category_hint == "国际" and not (
            international_signal or market_signal or business_impact or trusted or trusted_domain
        ):
            score -= 2
        if candidate.category_hint == "国内" and not (
            domestic_signal or market_signal or business_impact or public_impact or trusted or trusted_domain
        ):
            score -= 1
        if candidate.category_hint == "科技" and not (international_signal or domestic_signal or business_impact):
            score -= 2
        if len(text) < 40:
            score -= 1
        return score

    def _heuristic_group(
        self,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        events: list[EventCard] = []
        groups: list[list[ArticleCandidate]] = []
        for candidate in sorted(candidates, key=lambda item: item.published_at, reverse=True):
            norm_title = normalize_title(candidate.title)
            matched_group: list[ArticleCandidate] | None = None
            for group in groups:
                if similarity(norm_title, normalize_title(group[0].title)) >= self.event_similarity:
                    matched_group = group
                    break
            if matched_group is None:
                groups.append([candidate])
            else:
                matched_group.append(candidate)

        for index, group in enumerate(groups, start=1):
            representative = self._pick_representative(group)
            category = representative.category_hint or "其他"
            if category == "国际":
                representative = self._pick_representative(group, prefer_non_domestic=True)
            domestic_reference_url, domestic_reference_name = self._select_domestic_reference(
                group,
                representative.url,
            )
            fingerprint = build_fingerprint(representative.title, category)
            if fingerprint in seen_fingerprints:
                continue
            quality_score = self._quality_score(representative)
            if quality_score < 1:
                continue
            score = min(
                100,
                42
                + max(0, quality_score) * 8
                + min(20, (len(group) - 1) * 6)
                + (8 if category in {"国内", "国际", "财经", "科技"} else 0),
            )
            events.append(
                EventCard(
                    event_id=f"E{index}",
                    title=representative.title,
                    category=category,
                    importance_score=score,
                    summary=self._best_event_summary(
                        group,
                        preferred=representative.article_text or representative.feed_summary,
                        title=representative.title,
                        source_name=representative.publisher or representative.source,
                        representative=representative,
                        limit=140,
                    ),
                    article_ids=[item.id for item in group],
                    representative_url=representative.url,
                    source_name=representative.publisher or representative.source,
                    domestic_reference_url=domestic_reference_url,
                    domestic_reference_name=domestic_reference_name,
                    fingerprint=fingerprint,
                )
            )
        return sorted(
            [event for event in events if self._passes_event_gate(event)],
            key=lambda event: event.importance_score,
            reverse=True,
        )

    def _heuristic_draft(
        self,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        selected = sorted(events, key=lambda event: event.importance_score, reverse=True)
        lead_events = selected[: self.headline_count]
        lead_ids = {item.event_id for item in lead_events}
        brief_events = [event for event in selected if event.event_id not in lead_ids][: self.brief_count]

        lead_items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=self._usable_summary(event.summary, title=event.title, source_name=event.source_name, limit=140),
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
                domestic_reference_url=event.domestic_reference_url,
                domestic_reference_name=event.domestic_reference_name,
            )
            for event in lead_events
        ]
        brief_items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=self._usable_summary(event.summary, title=event.title, source_name=event.source_name, limit=70),
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
                domestic_reference_url=event.domestic_reference_url,
                domestic_reference_name=event.domestic_reference_name,
            )
            for event in brief_events
        ]
        top_categories = [
            category
            for category, _count in Counter(event.category for event in selected[:10]).most_common(self.keyword_count)
        ]
        overview = (
            "今日重点主要集中在"
            + "、".join(top_categories or ["综合"])
            + "方向，重点是高影响政策、头部公司动态和市场变化。"
        )
        return NewsletterDraft(
            subject=subject_template.format(date=date_label),
            overview=overview,
            lead_items=lead_items,
            brief_items=brief_items,
            watch_items=self._build_watch_items(selected),
            keywords=top_categories[: self.keyword_count],
        )

    def _finalize_draft(
        self,
        draft: NewsletterDraft,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        available_events = sorted(events, key=lambda event: event.importance_score, reverse=True)
        event_map = {event.event_id: event for event in available_events}

        def unique_items(items: list[NewsletterItem]) -> list[NewsletterItem]:
            seen_ids: set[str] = set()
            seen_titles: list[str] = []
            results: list[NewsletterItem] = []
            for item in items:
                norm_title = normalize_title(item.title)
                if item.event_id in seen_ids:
                    continue
                if item.event_id not in event_map:
                    continue
                if self._contains_any(item.title, LOW_VALUE_TITLE_KEYWORDS):
                    continue
                if any(similarity(norm_title, existing) >= 0.55 for existing in seen_titles):
                    continue
                seen_ids.add(item.event_id)
                seen_titles.append(norm_title)
                results.append(item)
            return results

        preferred_leads = unique_items(draft.lead_items)
        lead_items = self._apply_lead_family_cap(preferred_leads, event_map)
        lead_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=True) for item in lead_items]
        used_ids = {item.event_id for item in lead_items}
        brief_items = [item for item in unique_items(draft.brief_items) if item.event_id not in used_ids]
        brief_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=False) for item in brief_items]
        used_ids.update(item.event_id for item in brief_items)

        def fallback_item(event: EventCard, *, long_summary: bool) -> NewsletterItem:
            return NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=self._usable_summary(
                    event.summary,
                    title=event.title,
                    source_name=event.source_name,
                    limit=140 if long_summary else 70,
                ),
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
                domestic_reference_url=event.domestic_reference_url,
                domestic_reference_name=event.domestic_reference_name,
            )

        for event in available_events:
            if event.event_id in used_ids:
                continue
            if not self._passes_event_gate(event):
                continue
            preferred_leads.append(fallback_item(event, long_summary=True))

        lead_items = self._apply_lead_family_cap(preferred_leads, event_map)
        lead_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=True) for item in lead_items]
        used_ids = {item.event_id for item in lead_items}
        for event in available_events:
            if len(brief_items) >= self.brief_count:
                break
            if event.event_id in used_ids:
                continue
            if not self._passes_event_gate(event):
                continue
            brief_items.append(fallback_item(event, long_summary=False))
            used_ids.add(event.event_id)

        lead_items = self._apply_lead_family_cap(unique_items(lead_items), event_map)
        lead_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=True) for item in lead_items]
        lead_items = self._rebalance_lead_domestic(lead_items, available_events, event_map)
        lead_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=True) for item in unique_items(lead_items)]
        lead_ids = {item.event_id for item in lead_items}
        brief_items = [item for item in unique_items(brief_items) if item.event_id not in lead_ids]
        brief_items = self._apply_brief_caps(brief_items, event_map)
        brief_items = self._rebalance_domestic_items(lead_items, brief_items, available_events, event_map)
        brief_items = [item for item in unique_items(brief_items) if item.event_id not in lead_ids]
        brief_items = [self._normalize_newsletter_item(item, event_map[item.event_id], long_summary=False) for item in brief_items]

        overview = draft.overview.strip()
        if not overview:
            overview = "今天的重点新闻已按影响范围、热度和可信度筛过一遍，以下是最值得看的事件。"

        available_count = len(available_events)
        if available_count < 3:
            shortage_note = f"今日共筛出 {available_count} 条可纳入简报的事件，未额外补入低价值条目。"
            if shortage_note not in overview:
                overview = truncate_text(f"{overview} {shortage_note}", 220)

        keywords = [keyword for keyword in draft.keywords if keyword]
        if not keywords:
            keywords = [
                category
                for category, _count in Counter(event.category for event in available_events).most_common(self.keyword_count)
            ]

        watch_items = [item for item in draft.watch_items if item]
        if not watch_items:
            watch_items = self._build_watch_items(available_events)

        return NewsletterDraft(
            subject=draft.subject or subject_template.format(date=date_label),
            overview=overview,
            lead_items=lead_items[: self.headline_count],
            brief_items=brief_items[: self.brief_count],
            watch_items=watch_items[:4],
            keywords=keywords[: self.keyword_count],
        )

    def _apply_brief_caps(
        self,
        candidates: list[NewsletterItem],
        event_map: dict[str, EventCard],
    ) -> list[NewsletterItem]:
        selected: list[NewsletterItem] = []
        finance_count = 0
        central_bank_count = 0
        google_link_count = 0
        source_counts: Counter[str] = Counter()
        for item in candidates:
            event = event_map.get(item.event_id)
            if event is None or not self._is_publishable_event(event, lead=False):
                continue
            text = f"{item.title} {item.summary}"
            if event is not None:
                text = f"{text} {event.title} {event.summary}"
            is_finance = item.category == "财经" or (event is not None and self.event_family(event) == "market")
            is_central_bank = self._contains_any(text, {"央行", "LPR", "MLF", "逆回购", "公开市场", "货币政策委员会"})
            if is_finance and finance_count >= 2:
                continue
            if is_central_bank and central_bank_count >= 1:
                continue
            if source_counts[item.source_name] >= 2:
                continue
            if self._is_google_news_url(item.link) and not item.domestic_reference_url:
                if google_link_count >= 6:
                    continue
                google_link_count += 1
            selected.append(item)
            source_counts[item.source_name] += 1
            finance_count += 1 if is_finance else 0
            central_bank_count += 1 if is_central_bank else 0
        return selected

    def _apply_lead_family_cap(
        self,
        candidates: list[NewsletterItem],
        event_map: dict[str, EventCard],
    ) -> list[NewsletterItem]:
        family_priority = {
            "international_geopolitics": 8,
            "technology": 7,
            "public_impact": 6,
            "policy": 2,
            "enterprise": 2,
            "market": 1,
        }
        family_caps = {
            "international_geopolitics": 4,
            "technology": 2,
            "public_impact": 1,
            "policy": 1,
            "enterprise": 1,
            "market": 1,
        }

        def item_event(item: NewsletterItem) -> EventCard | None:
            return event_map.get(item.event_id)

        def item_family(item: NewsletterItem) -> str:
            event = item_event(item)
            if event is None:
                return "enterprise"
            return self.event_family(event)

        def finance_like(item: NewsletterItem) -> bool:
            event = item_event(item)
            if event is None:
                return item.category == "财经"
            family = self.event_family(event)
            return event.category == "财经" or family == "market"

        def central_bank_like(item: NewsletterItem) -> bool:
            event = item_event(item)
            text = f"{item.title} {item.summary}"
            if event is not None:
                text = f"{text} {event.title} {event.summary}"
            return self._contains_any(text, {"央行", "LPR", "MLF", "逆回购", "公开市场", "货币政策委员会"})

        ranked_candidates = sorted(
            [item for item in candidates if item.event_id in event_map],
            key=lambda item: (
                family_priority.get(item_family(item), 0),
                1 if self._is_hard_international_event(f"{item.title} {item.summary}") else 0,
                1 if self._is_hard_technology_event(f"{item.title} {item.summary}") else 0,
                item_event(item).importance_score if item_event(item) else 0,
            ),
            reverse=True,
        )

        def family_bucket(family_name: str) -> list[NewsletterItem]:
            return [item for item in ranked_candidates if item_family(item) == family_name]

        selected: list[NewsletterItem] = []
        deferred: list[NewsletterItem] = []
        seen: set[str] = set()
        family_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        finance_count = 0
        central_bank_count = 0
        google_link_count = 0

        def try_add(item: NewsletterItem) -> bool:
            nonlocal finance_count, central_bank_count, google_link_count
            if item.event_id in seen:
                return False
            event = item_event(item)
            if event is None or not self._is_publishable_event(event, lead=True):
                return False
            family = item_family(item)
            is_finance = finance_like(item)
            is_central_bank = central_bank_like(item)
            if family_counts[family] >= family_caps.get(family, 2):
                return False
            if source_counts[item.source_name] >= 2:
                return False
            if is_finance and finance_count >= 1:
                return False
            if is_central_bank and central_bank_count >= 1:
                return False
            if self._is_google_news_url(item.link) and not item.domestic_reference_url:
                if google_link_count >= 4:
                    return False
                google_link_count += 1
            selected.append(item)
            seen.add(item.event_id)
            family_counts[family] += 1
            source_counts[item.source_name] += 1
            finance_count += 1 if is_finance else 0
            central_bank_count += 1 if is_central_bank else 0
            return True

        for must_have_family in (
            "international_geopolitics",
            "international_geopolitics",
            "technology",
            "public_impact",
            "technology",
        ):
            for item in family_bucket(must_have_family):
                if try_add(item):
                    break

        for item in ranked_candidates:
            if item.event_id in seen:
                deferred.append(item)
                continue
            if not try_add(item):
                deferred.append(item)
            if len(selected) >= self.headline_count:
                return selected

        for item in deferred:
            if len(selected) >= self.headline_count:
                break
            try_add(item)
        return selected

    def _merge_candidates(
        self,
        primary: list[ArticleCandidate],
        fallback: list[ArticleCandidate],
    ) -> list[ArticleCandidate]:
        by_id: dict[str, ArticleCandidate] = {}
        for item in primary + fallback:
            by_id[item.id] = item
        merged = sorted(by_id.values(), key=self._quality_score, reverse=True)
        return merged[: max(self.headline_count + self.brief_count + 40, 80)]

    def _apply_candidate_gate(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        filtered = [candidate for candidate in candidates if self._passes_candidate_gate(candidate)]
        filtered.sort(key=self._quality_score, reverse=True)
        return filtered

    def _merge_events(self, primary: list[EventCard], fallback: list[EventCard]) -> list[EventCard]:
        merged: list[EventCard] = []
        for event in primary + fallback:
            matched_index: int | None = None
            event_title = normalize_title(event.title)
            event_articles = set(event.article_ids)
            for index, existing in enumerate(merged):
                existing_title = normalize_title(existing.title)
                same_articles = bool(event_articles & set(existing.article_ids))
                similar_title = similarity(event_title, existing_title) >= 0.5
                same_fingerprint = (
                    event.fingerprint
                    and existing.fingerprint
                    and event.fingerprint == existing.fingerprint
                )
                if same_articles or similar_title or same_fingerprint:
                    matched_index = index
                    break
            if matched_index is None:
                merged.append(event)
                continue
            existing = merged[matched_index]
            if event.importance_score > existing.importance_score:
                merged[matched_index] = event
        return sorted(merged, key=lambda event: event.importance_score, reverse=True)

    @staticmethod
    def _ordered_events_from_ids(event_ids: list[str], events: list[EventCard]) -> list[EventCard]:
        event_map = {event.event_id: event for event in events}
        ordered: list[EventCard] = []
        seen: set[str] = set()
        for event_id in event_ids:
            event = event_map.get(event_id)
            if not event or event_id in seen:
                continue
            ordered.append(event)
            seen.add(event_id)
        for event in events:
            if event.event_id in seen:
                continue
            ordered.append(event)
        return ordered

    @staticmethod
    def _contains_any(text: str, keywords: set[str]) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    @staticmethod
    def _candidate_text(candidate: ArticleCandidate) -> str:
        return " ".join(
            part.strip()
            for part in [candidate.title, candidate.feed_summary, candidate.article_text]
            if part and part.strip()
        )

    @staticmethod
    def _publisher_name(candidate: ArticleCandidate) -> str:
        return (candidate.publisher or candidate.source).strip()

    @staticmethod
    def _domain_from_url(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def _candidate_domain(self, candidate: ArticleCandidate) -> str:
        return self._domain_from_url(candidate.url)

    @staticmethod
    def _matches_domain_suffix(domain: str, suffixes: set[str]) -> bool:
        return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in suffixes)

    def event_family(self, event: EventCard) -> str:
        text = f"{event.title} {event.summary} {event.category}"
        return self._event_family_from_text(text)

    def _event_family_from_text(self, text: str) -> str:
        if self._has_strong_public_impact(text):
            return "public_impact"
        if self._contains_any(text, {"AI", "芯片", "半导体", "算力", "OpenAI", "GPU", "HBM", "英伟达", "微软", "谷歌"}):
            return "technology"
        if self._contains_any(text, HARD_INTERNATIONAL_KEYWORDS | {"美国宣布"}):
            return "international_geopolitics"
        if self._contains_any(text, {"A股", "美股", "债市", "油价", "原油", "黄金", "利率", "LPR", "MLF", "IPO"}):
            return "market"
        if self._contains_any(text, {"央行", "美联储", "Fed", "政策", "监管", "商务部", "证监会", "工信部", "发改委"}):
            return "policy"
        return "enterprise"

    def _has_strong_public_impact(self, text: str) -> bool:
        if self._contains_any(text, PUBLIC_IMPACT_KEYWORDS | HARD_PUBLIC_POLICY_KEYWORDS):
            return True
        topic_hit = self._contains_any(text, PUBLIC_IMPACT_TOPIC_KEYWORDS)
        result_hit = self._contains_any(text, PUBLIC_IMPACT_RESULT_KEYWORDS)
        if topic_hit and result_hit:
            return True
        if re.search(r"\d", text) and topic_hit and self._contains_any(
            text,
            {"停运", "停航", "停课", "召回", "通报", "处罚", "下调", "上调", "调整", "取消"},
        ):
            return True
        return False

    def _is_hard_international_event(self, text: str) -> bool:
        if not self._contains_any(text, HARD_INTERNATIONAL_KEYWORDS):
            return False
        return self._contains_any(
            text,
            {
                "关税",
                "停火",
                "制裁",
                "袭击",
                "战争",
                "冲突",
                "军演",
                "轰炸",
                "谈判",
                "豁免",
                "宣布",
                "升级",
                "回应",
                "表态",
                "敦促",
                "警告",
                "告急",
                "边缘",
                "外溢",
                "政策",
            },
        )

    def _is_hard_technology_event(self, text: str) -> bool:
        if not self._contains_any(text, {"AI", "人工智能", "OpenAI", "芯片", "半导体", "算力", "英伟达", "微软", "谷歌"}):
            return False
        return self._contains_any(text, HARD_TECH_ACTION_KEYWORDS)

    def _is_weak_service_notice(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, WEAK_SERVICE_NOTICE_KEYWORDS):
            return False
        return not self._contains_any(combined, HARD_EVENT_OVERRIDE_KEYWORDS)

    def _is_soft_technology_event(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, WEAK_TECHNOLOGY_KEYWORDS):
            return False
        if self._contains_any(combined, {"模型", "芯片", "半导体", "GPU", "HBM", "发布", "推出", "自研", "量产", "投产"}):
            return not self._is_hard_technology_event(combined)
        return True

    def _is_technology_gossip(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, {"AI", "人工智能", "OpenAI", "微软", "谷歌", "英伟达"}):
            return False
        if self._contains_any(combined, {"播客", "科技播客", "脱口秀", "节目"}):
            return True
        if not self._contains_any(combined, TECH_GOSSIP_KEYWORDS):
            return False
        if self._contains_any(combined, {"模型", "芯片", "半导体", "GPU", "HBM", "算力", "发布", "推出"}):
            return False
        return True

    def _is_roundup_title(self, title: str) -> bool:
        if self._contains_any(title, {"周报", "日报", "月报", "财报速递", "速递丨", "出海·能源"}):
            return True
        return title.count("；") >= 2 and "｜" in title

    def _is_low_value_earnings_story(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, EARNINGS_KEYWORDS):
            return False
        if self._contains_any(title, {"药品及钢铝", "关税", "制裁"}):
            return False
        if not self._contains_any(combined, MAJOR_COMPANY_KEYWORDS):
            return True
        if self._contains_any(combined, {"创纪录", "超预期", "暴跌", "暴涨", "大跌", "大涨", "裁员", "收购"}):
            return False
        return True

    def _is_major_enterprise_event(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, MAJOR_COMPANY_KEYWORDS):
            return False
        return self._contains_any(combined, MAJOR_ENTERPRISE_ACTION_KEYWORDS)

    def _is_weather_alert_service(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, {"气象灾害", "大风", "暴雨", "寒潮", "应急响应"}):
            return False
        if self._contains_any(combined, {"死亡", "受伤", "遇难", "停运", "停航", "停课", "通报", "处罚"}):
            return False
        return True

    def _is_foreign_relay_story(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if self._is_hard_international_event(combined):
            return False
        if not self._contains_any(combined, FOREIGN_LOCATION_KEYWORDS):
            return False
        if not self._contains_any(combined, {"坠毁", "遇难", "受伤", "事故", "爆炸", "脱轨", "警报", "袭击"}):
            return False
        if self._contains_any(combined, {"对华", "中方", "外交部", "关税", "停火", "制裁"}):
            return False
        return True

    def _is_interview_opinion_story(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if not self._contains_any(combined, {"访谈", "海斌访谈", "泼点冷水"}):
            return False
        if self._has_hard_information(title, text):
            return False
        return True

    def _is_domestic_priority_event(self, event: EventCard) -> bool:
        text = f"{event.title} {event.summary}"
        if self._contains_any(text, HARD_INTERNATIONAL_KEYWORDS):
            return False
        if self._contains_any(text, FOREIGN_LOCATION_KEYWORDS) and not self._contains_any(
            text,
            {"国务院", "市场监管总局", "应急管理部", "国家卫健委", "教育部", "住建部", "商务部", "工信部"},
        ):
            return False
        if self._is_weak_service_notice(event.title, event.summary):
            return False
        if self._is_weather_alert_service(event.title, event.summary):
            return False
        family = self.event_family(event)
        if event.category == "国内":
            return self._has_hard_information(event.title, event.summary) or self._has_strong_public_impact(text)
        if family == "public_impact":
            return self._has_strong_public_impact(text)
        if family == "policy":
            return self._has_hard_information(event.title, event.summary)
        return False

    def _domestic_priority_rank(self, event: EventCard) -> tuple[int, int]:
        text = f"{event.title} {event.summary}"
        score = event.importance_score
        if self._contains_any(text, {"市场监管总局", "国务院", "国家卫健委", "应急管理部", "教育部", "商务部"}):
            score += 12
        if self._contains_any(text, {"通报", "处罚", "罚款", "不合格", "召回", "食品安全", "挂牌督办", "遇难", "受伤", "事故"}):
            score += 10
        if self._contains_any(text, {"新华网", "央视网", "新京报", "澎湃", "中国新闻网"}):
            score += 4
        if re.search(r"[县区乡镇]", event.title) and not self._contains_any(text, {"事故", "受伤", "遇难", "处罚", "通报"}):
            score -= 6
        return score, event.importance_score

    def _rebalance_domestic_items(
        self,
        lead_items: list[NewsletterItem],
        brief_items: list[NewsletterItem],
        available_events: list[EventCard],
        event_map: dict[str, EventCard],
    ) -> list[NewsletterItem]:
        target_domestic = 3
        current_domestic = sum(
            1
            for item in (lead_items + brief_items)
            if item.event_id in event_map and self._is_domestic_priority_event(event_map[item.event_id])
        )
        if current_domestic >= target_domestic:
            return brief_items

        used_ids = {item.event_id for item in (lead_items + brief_items)}
        additions: list[NewsletterItem] = []
        domestic_candidates = sorted(
            [
                event
                for event in available_events
                if event.event_id not in used_ids
                and self._is_domestic_priority_event(event)
                and self._is_publishable_event(event, lead=False)
            ],
            key=self._domestic_priority_rank,
            reverse=True,
        )
        for event in domestic_candidates:
            if current_domestic >= target_domestic:
                break
            additions.append(
                NewsletterItem(
                    event_id=event.event_id,
                    title=event.title,
                    summary=self._usable_summary(
                        event.summary,
                        title=event.title,
                        source_name=event.source_name,
                        limit=70,
                    ),
                    link=event.representative_url,
                    category=event.category,
                    source_name=event.source_name,
                    domestic_reference_url=event.domestic_reference_url,
                    domestic_reference_name=event.domestic_reference_name,
                )
            )
            used_ids.add(event.event_id)
            current_domestic += 1

        return brief_items + additions

    def _rebalance_lead_domestic(
        self,
        lead_items: list[NewsletterItem],
        available_events: list[EventCard],
        event_map: dict[str, EventCard],
    ) -> list[NewsletterItem]:
        domestic_in_lead = sum(
            1
            for item in lead_items
            if item.event_id in event_map and self._is_domestic_priority_event(event_map[item.event_id])
        )
        if domestic_in_lead >= 1:
            return lead_items
        if len(lead_items) >= self.headline_count:
            return lead_items

        used_ids = {item.event_id for item in lead_items}
        domestic_candidates = sorted(
            [
                event
                for event in available_events
                if event.event_id not in used_ids
                and self._is_domestic_priority_event(event)
                and (
                    self._is_publishable_event(event, lead=True)
                    or (self._is_publishable_event(event, lead=False) and event.importance_score >= 80)
                )
            ],
            key=self._domestic_priority_rank,
            reverse=True,
        )
        if not domestic_candidates:
            return lead_items
        event = domestic_candidates[0]
        return lead_items + [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=self._usable_summary(
                    event.summary,
                    title=event.title,
                    source_name=event.source_name,
                    limit=140,
                ),
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
                domestic_reference_url=event.domestic_reference_url,
                domestic_reference_name=event.domestic_reference_name,
            )
        ]

    def _draft_quality_score(
        self,
        draft: NewsletterDraft,
        event_map: dict[str, EventCard],
        available_events: list[EventCard],
    ) -> int:
        all_items = draft.lead_items + draft.brief_items
        score = len(draft.lead_items) * 4 + len(draft.brief_items) * 2
        domestic_total = sum(
            1 for item in all_items if item.event_id in event_map and self._is_domestic_priority_event(event_map[item.event_id])
        )
        domestic_lead = sum(
            1 for item in draft.lead_items if item.event_id in event_map and self._is_domestic_priority_event(event_map[item.event_id])
        )
        score += domestic_total * 2
        score += domestic_lead * 5
        score -= sum(1 for item in all_items if self._is_google_news_url(item.link)) * 2
        blocked_penalty = sum(
            1
            for item in all_items
            if self._contains_any(
                item.title,
                LOW_VALUE_TITLE_KEYWORDS
                | WEAK_ANALYSIS_TITLE_KEYWORDS
                | WEAK_PUBLIC_IMPACT_KEYWORDS
                | WEAK_SERVICE_NOTICE_KEYWORDS,
            )
        )
        score -= blocked_penalty * 6
        if len(draft.lead_items) < 4:
            score -= 6
        if len(draft.brief_items) < 6:
            score -= 4
        if any(self._is_domestic_priority_event(event) for event in available_events) and domestic_lead == 0:
            score -= 8
        return score

    def _is_self_explanatory_title(self, title: str) -> bool:
        cleaned = self._sanitize_summary_text(title, "")
        if len(cleaned) < 12:
            return False
        if self._is_weak_service_notice(cleaned, cleaned):
            return False
        if self._is_soft_technology_event(cleaned, cleaned):
            return False
        if self._is_technology_gossip(cleaned, cleaned):
            return False
        if self._is_roundup_title(cleaned):
            return False
        if self._is_low_value_earnings_story(cleaned, cleaned):
            return False
        if self._contains_any(cleaned, GENERIC_TITLE_BLOCKERS) and not (
            self._has_hard_information(cleaned, cleaned)
            or self._has_strong_public_impact(cleaned)
            or self._is_hard_international_event(cleaned)
            or self._is_hard_technology_event(cleaned)
        ):
            return False
        return True

    def _is_routine_finance(self, candidate: ArticleCandidate) -> bool:
        text = f"{candidate.title} {candidate.feed_summary} {candidate.article_text}"
        if not self._contains_any(text, ROUTINE_FINANCE_KEYWORDS):
            return False
        exception_keywords = {"降准", "降息", "站上", "突破", "暴涨", "暴跌", "创纪录", "大幅", "超预期"}
        return not self._contains_any(text, exception_keywords)

    def _is_official_propaganda(self, title: str, text: str) -> bool:
        return self._contains_any(f"{title} {text}", OFFICIAL_PROPAGANDA_KEYWORDS)

    @staticmethod
    def _is_google_news_url(url: str) -> bool:
        return "news.google.com" in url

    def _is_local_low_impact(self, title: str) -> bool:
        if not re.search(r"[县区乡镇旗盟州市]", title):
            return False
        if not self._contains_any(title, {"开展", "启动", "推进", "举办", "部署"}):
            return False
        strong_local_keywords = {"事故", "收储", "严禁", "挂牌督办", "死亡", "遇难", "关税", "处罚"}
        return not self._contains_any(title, strong_local_keywords)

    def _has_hard_information(self, title: str, text: str) -> bool:
        combined = f"{title} {text}"
        if self._is_weak_service_notice(title, text):
            return False
        if self._contains_any(combined, HARD_INFO_KEYWORDS):
            return True
        if re.search(r"\d", combined) and self._contains_any(
            combined,
            {
                "事故",
                "死亡",
                "遇难",
                "补贴",
                "签约",
                "关税",
                "新增",
                "处罚",
                "收储",
                "扩围",
                "融资",
                "裁员",
                "上涨",
                "下跌",
                "大涨",
                "大跌",
                "涨超",
                "跌超",
                "重挫",
                "停运",
                "停航",
                "停课",
            },
        ):
            return True
        return False

    def _summary_consistent_with_title(self, title: str, summary: str) -> bool:
        title_norm = normalize_title(title)
        summary_norm = normalize_title(summary)
        if not summary_norm:
            return False
        if similarity(title_norm, summary_norm) >= 0.32:
            return True
        title_family = self._event_family_from_text(title)
        summary_family = self._event_family_from_text(summary)
        keyword_pool = (
            DOMESTIC_SIGNAL_KEYWORDS
            | INTERNATIONAL_SIGNAL_KEYWORDS
            | MARKET_SIGNAL_KEYWORDS
            | PUBLIC_IMPACT_KEYWORDS
            | BUSINESS_IMPACT_KEYWORDS
            | {"特朗普", "伊朗", "中国", "钢铝", "原油", "油价", "教育部", "工信部", "OpenAI", "微软", "Nvidia"}
        )
        title_keywords = {keyword for keyword in keyword_pool if keyword.lower() in title.lower()}
        summary_keywords = {keyword for keyword in keyword_pool if keyword.lower() in summary.lower()}
        overlap = title_keywords & summary_keywords
        if title_keywords:
            needed = 2 if len(title_keywords) >= 2 else 1
            return len(overlap) >= needed
        return title_family == summary_family and title_family != "enterprise"

    def _source_meta(self, source_name: str) -> FeedSource | None:
        return self.source_registry.get(source_name)

    @staticmethod
    def _tier_value(tier: str) -> int:
        return {"S": 3, "A": 2, "B": 1}.get(tier.upper().strip(), 1)

    @staticmethod
    def _role_value(role: str) -> int:
        return {"official": 3, "media": 2, "discovery": 1}.get(role.strip().lower(), 1)

    def _source_tier_value(self, source_name: str) -> int:
        source = self._source_meta(source_name)
        return self._tier_value(source.tier) if source else 1

    def _source_role_value(self, source_name: str) -> int:
        source = self._source_meta(source_name)
        return self._role_value(source.role) if source else 1

    def _governed_source_tier_value(self, source_name: str) -> int:
        if self._source_role_value(source_name) < 2:
            return 1
        return self._source_tier_value(source_name)

    def _publisher_tier_value(self, publisher: str, domain: str) -> int:
        if publisher in PRIMARY_PUBLISHERS or self._matches_domain_suffix(domain, PRIMARY_DOMAIN_SUFFIXES):
            return 3
        if publisher in SECONDARY_PUBLISHERS or self._matches_domain_suffix(domain, SECONDARY_DOMAIN_SUFFIXES):
            return 2
        return 1

    def _publisher_role_value(self, publisher: str, domain: str) -> int:
        if self._contains_any(publisher, OFFICIAL_PUBLISHER_HINTS) or self._matches_domain_suffix(
            domain,
            OFFICIAL_DOMAIN_SUFFIXES,
        ):
            return 3
        if (
            publisher in PRIMARY_PUBLISHERS
            or publisher in SECONDARY_PUBLISHERS
            or self._matches_domain_suffix(domain, PRIMARY_DOMAIN_SUFFIXES)
            or self._matches_domain_suffix(domain, SECONDARY_DOMAIN_SUFFIXES)
        ):
            return 2
        return 1

    def _passes_candidate_gate(self, candidate: ArticleCandidate) -> bool:
        publisher = self._publisher_name(candidate)
        text = self._candidate_text(candidate)
        domain = self._candidate_domain(candidate)
        score = self._quality_score(candidate)
        source_role = self._source_role_value(candidate.source)
        if self._matches_domain_suffix(domain, DISALLOWED_DOMAIN_SUFFIXES):
            return False
        if self._contains_any(publisher, DISALLOWED_PUBLISHER_HINTS):
            return False
        if self._is_interview_opinion_story(candidate.title, text):
            return False
        if self._is_foreign_relay_story(candidate.title, text):
            return False
        if self._is_weak_service_notice(candidate.title, text):
            return False
        if self._is_soft_technology_event(candidate.title, text):
            return False
        if self._is_technology_gossip(candidate.title, text):
            return False
        if self._is_roundup_title(candidate.title):
            return False
        if self._is_low_value_earnings_story(candidate.title, text):
            return False
        if self._is_weather_alert_service(candidate.title, text):
            return False
        if source_role >= 2 and self._is_official_propaganda(candidate.title, text):
            return False
        if source_role >= 2 and not self._has_hard_information(candidate.title, text):
            return False
        if (
            publisher in PRIMARY_PUBLISHERS
            or publisher in SECONDARY_PUBLISHERS
            or self._matches_domain_suffix(domain, PRIMARY_DOMAIN_SUFFIXES)
            or self._matches_domain_suffix(domain, SECONDARY_DOMAIN_SUFFIXES)
            or source_role >= 2
        ):
            return score >= 1
        if self._contains_any(publisher, OFFICIAL_PUBLISHER_HINTS) or self._matches_domain_suffix(
            domain,
            OFFICIAL_DOMAIN_SUFFIXES,
        ):
            return score >= 1
        strong_signal = (
            self._contains_any(text, DOMESTIC_SIGNAL_KEYWORDS)
            or self._contains_any(text, INTERNATIONAL_SIGNAL_KEYWORDS)
            or self._contains_any(text, MARKET_SIGNAL_KEYWORDS)
            or self._contains_any(text, PUBLIC_IMPACT_KEYWORDS)
            or self._contains_any(text, BUSINESS_IMPACT_KEYWORDS)
        )
        return strong_signal and score >= 8

    def _passes_event_gate(self, event: EventCard) -> bool:
        if self._contains_any(event.title, LOW_VALUE_TITLE_KEYWORDS):
            return False
        if self._contains_any(event.title, WEAK_ANALYSIS_TITLE_KEYWORDS):
            return False
        if self._contains_any(event.title, WEAK_PUBLIC_IMPACT_KEYWORDS):
            return False
        if self._is_interview_opinion_story(event.title, event.summary):
            return False
        if self._is_foreign_relay_story(event.title, event.summary):
            return False
        if self._is_weak_service_notice(event.title, event.summary):
            return False
        if self._is_local_low_impact(event.title):
            return False
        if self._is_official_propaganda(event.title, event.summary):
            return False
        if self._is_soft_technology_event(event.title, event.summary):
            return False
        if self._is_technology_gossip(event.title, event.summary):
            return False
        if self._is_roundup_title(event.title):
            return False
        if self._is_low_value_earnings_story(event.title, event.summary):
            return False
        if self._is_weather_alert_service(event.title, event.summary):
            return False
        event_like = ArticleCandidate(
            id=event.event_id,
            title=event.title,
            source=event.source_name,
            publisher=event.source_name,
            published_at=datetime.now(UTC),
            url=event.representative_url,
            feed_summary=event.summary,
            category_hint=event.category,
        )
        if self._is_routine_finance(event_like):
            return False
        if self._matches_domain_suffix(self._domain_from_url(event.representative_url), DISALLOWED_DOMAIN_SUFFIXES):
            return False
        if self._contains_any(event.source_name, DISALLOWED_PUBLISHER_HINTS):
            return False
        if self.event_family(event) == "market":
            domain = self._domain_from_url(event.representative_url)
            allowed_market_domain = self._matches_domain_suffix(
                domain,
                {"cls.cn", "yicai.com", "stcn.com", "cnstock.com", "nbd.com.cn", "eeo.com.cn", "wallstreetcn.com", "reuters.com"},
            )
            if event.source_name not in MARKET_ALLOWED_PUBLISHERS and not allowed_market_domain:
                return False
        if self._source_role_value(event.source_name) >= 2 and not self._has_hard_information(event.title, event.summary):
            return False
        return True

    def _is_publishable_event(self, event: EventCard, *, lead: bool) -> bool:
        domain = self._domain_from_url(event.representative_url)
        text = f"{event.title} {event.summary}"
        if self._matches_domain_suffix(domain, DISALLOWED_DOMAIN_SUFFIXES):
            return False
        if self._contains_any(event.source_name, DISALLOWED_PUBLISHER_HINTS):
            return False
        if self._is_interview_opinion_story(event.title, event.summary):
            return False
        if self._is_foreign_relay_story(event.title, event.summary):
            return False
        if (
            not lead
            and self._contains_any(text, {"盗脸", "侵权", "肖像", "漏洞", "网络攻击", "窃取"})
            and (
                self._matches_domain_suffix(domain, FINAL_ALLOWED_DOMAINS)
                or event.source_name in PRIMARY_PUBLISHERS
                or event.source_name in SECONDARY_PUBLISHERS
            )
        ):
            return True
        if self._is_weak_service_notice(event.title, event.summary):
            return False
        if self._is_soft_technology_event(event.title, event.summary):
            return False
        if self._is_technology_gossip(event.title, event.summary):
            return False
        if self._is_roundup_title(event.title):
            return False
        if self._is_low_value_earnings_story(event.title, event.summary):
            return False
        if self._is_weather_alert_service(event.title, event.summary):
            return False
        strong_source_name = (
            event.source_name in PRIMARY_PUBLISHERS
            or event.source_name in SECONDARY_PUBLISHERS
            or self._contains_any(event.source_name, OFFICIAL_PUBLISHER_HINTS)
            or self._matches_domain_suffix(event.source_name.lower().removeprefix("www."), FINAL_ALLOWED_DOMAINS)
        )
        family = self.event_family(event)
        if (
            family == "technology"
            and not lead
            and self._contains_any(text, {"盗脸", "侵权", "肖像", "漏洞", "网络攻击", "窃取"})
            and (self._matches_domain_suffix(domain, FINAL_ALLOWED_DOMAINS) or strong_source_name)
        ):
            return True
        if family == "technology" and lead and not self._is_hard_technology_event(text):
            return False
        if family == "technology" and not lead and not (
            self._is_hard_technology_event(text)
            or self._has_strong_public_impact(text)
            or self._contains_any(text, {"盗脸", "侵权", "肖像", "漏洞", "网络攻击", "窃取"})
        ):
            return False
        if family == "international_geopolitics" and lead and not self._is_hard_international_event(text):
            return False
        google_only = self._is_google_news_url(event.representative_url) and not event.domestic_reference_url
        if google_only:
            if family == "market":
                return False
            if family == "enterprise" and not self._is_major_enterprise_event(text, text):
                return False
            if self._contains_any(event.title, WEAK_ANALYSIS_TITLE_KEYWORDS | WEAK_PUBLIC_IMPACT_KEYWORDS):
                return False
            if lead and family == "public_impact" and not self._contains_any(
                event.title,
                {"事故", "灾害", "死亡", "遇难", "挂牌督办", "收储", "严禁", "关税", "停火", "冲突"},
            ):
                return False
            if lead and family == "policy" and not self._contains_any(
                event.title,
                {"收储", "处罚", "新政", "生效", "签约", "关税", "豁免", "部署", "通报", "事故", "停火", "遇难"},
            ):
                return False
            if family == "policy" and not self._contains_any(
                event.title,
                {"收储", "处罚", "新政", "生效", "签约", "关税", "豁免", "部署", "通报", "事故", "停火", "遇难", "漏洞", "攻击", "网络攻击", "窃取"},
            ):
                return False
        if self._matches_domain_suffix(domain, FINAL_ALLOWED_DOMAINS):
            if lead and not self._is_self_explanatory_title(event.title):
                usable = self._usable_summary(event.summary, title=event.title, source_name=event.source_name, limit=140)
                if not usable:
                    return False
            return True
        if strong_source_name:
            if lead and not self._is_self_explanatory_title(event.title):
                usable = self._usable_summary(event.summary, title=event.title, source_name=event.source_name, limit=140)
                if not usable:
                    return False
            return True
        if lead:
            return False
        if not self._is_self_explanatory_title(event.title):
            usable = self._usable_summary(event.summary, title=event.title, source_name=event.source_name, limit=70)
            if not usable:
                return False
        return self._has_hard_information(event.title, event.summary) and not self._is_google_news_url(event.representative_url)

    def _select_domestic_reference(
        self,
        articles: list[ArticleCandidate],
        representative_url: str,
    ) -> tuple[str, str]:
        candidates = [
            article
            for article in articles
            if article.url != representative_url and self._is_domestic_reference_candidate(article)
        ]
        if not candidates:
            return "", ""
        selected = max(
            candidates,
            key=self._candidate_rank,
        )
        return selected.url, self._publisher_name(selected)

    def _build_watch_items(self, events: list[EventCard]) -> list[str]:
        watch_items: list[str] = []
        for event in events:
            item = self._watch_item_for_event(event)
            if not item or item in watch_items:
                continue
            watch_items.append(item)
            if len(watch_items) >= 4:
                break
        return watch_items[:4]

    def _watch_item_for_event(self, event: EventCard) -> str:
        text = f"{event.title} {event.summary}"
        if self._contains_any(text, {"原油", "油价", "OPEC", "中东"}):
            return "关注油价上行是否继续外溢到全球风险资产与通胀预期。"
        if self._contains_any(text, {"央行", "MLF", "逆回购", "利率", "债市", "美联储", "Fed"}):
            return "关注流动性投放与利率预期是否继续影响股债市场定价。"
        if self._contains_any(text, {"商务部", "关税", "经贸", "收购", "并购", "Meta"}):
            return "关注经贸与跨境交易监管后续是否出现进一步表态或执行动作。"
        if self._contains_any(text, {"A股", "创业板", "港股", "美股"}):
            return "关注风险偏好变化是否继续推动股市板块分化。"
        if self._contains_any(text, {"AI", "芯片", "半导体", "算力", "GPU"}):
            return "关注算力、芯片与AI资本开支链条的后续验证。"
        if self._contains_any(text, {"就业", "住房", "教育", "医疗", "事故", "灾害", "食品安全", "交通"}):
            return "关注相关部门后续通报、处置进展与配套措施。"
        return ""

    def _sanitize_summary_text(self, summary: str, source_name: str) -> str:
        text = trim_complete_sentence(summary, 200)
        text = re.sub(r"\b(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", text)
        if source_name:
            text = text.replace(source_name, "")
        text = re.sub(r"^(原标题[:：]\s*)", "", text)
        text = re.sub(r"[?？!！]{2,}", "", text)
        text = re.sub(r"[.…]{2,}$", "", text)
        return re.sub(r"\s{2,}", " ", text).strip(" -|_")

    def _clean_title_text(self, title: str) -> str:
        text = self._sanitize_summary_text(title, "")
        text = re.sub(r"\s*[|｜丨]\s*(环球市场|新闻8点见|硬科技投向标|GPT周报|财报速递).*$", "", text)
        text = re.sub(r"[（(]含视频[)）]", "", text)
        text = re.sub(r"[，,]\s*实测来了$", "", text)
        return re.sub(r"\s{2,}", " ", text).strip(" -|_")

    def _is_weak_summary(self, title: str, summary: str) -> bool:
        if not summary:
            return True
        if len(summary) < 20:
            return True
        if summary.endswith(("...", "…")):
            return True
        if self._contains_any(summary, WEAK_SERVICE_NOTICE_KEYWORDS):
            return True
        title_norm = normalize_title(title)
        summary_norm = normalize_title(summary)
        if summary_norm == title_norm:
            return True
        if summary_norm.startswith(title_norm) or similarity(title_norm, summary_norm) >= 0.82:
            return True
        return False

    def _usable_summary(self, summary: str, *, title: str, source_name: str, limit: int) -> str:
        cleaned = self._sanitize_summary_text(summary, source_name)
        if not cleaned:
            return ""
        shortened = trim_complete_sentence(cleaned, limit)
        if self._is_weak_summary(title, shortened):
            return ""
        return shortened

    def _best_event_summary(
        self,
        articles: list[ArticleCandidate],
        *,
        preferred: str,
        title: str,
        source_name: str,
        representative: ArticleCandidate,
        limit: int,
    ) -> str:
        preferred_summary = self._usable_summary(preferred, title=title, source_name=source_name, limit=limit)
        if preferred_summary and self._summary_consistent_with_title(title, preferred_summary):
            return preferred_summary
        fallback_candidates: list[str] = []
        similar_articles = [
            article
            for article in articles
            if similarity(normalize_title(article.title), normalize_title(title)) >= 0.45
            or article.id == representative.id
        ]
        for article in similar_articles:
            for raw in (article.article_text, article.feed_summary):
                cleaned = self._usable_summary(
                    raw,
                    title=title,
                    source_name=article.publisher or article.source,
                    limit=limit,
                )
                if cleaned and self._summary_consistent_with_title(title, cleaned):
                    fallback_candidates.append(cleaned)
        if fallback_candidates:
            return max(fallback_candidates, key=len)
        fallback = self._fallback_summary_from_title(title, limit)
        if fallback:
            return fallback
        if self._is_self_explanatory_title(title):
            return trim_complete_sentence(title, limit)
        return ""

    def _fallback_summary_from_title(self, title: str, limit: int) -> str:
        cleaned = self._sanitize_summary_text(title, "")
        if not self._is_self_explanatory_title(cleaned):
            return ""
        if cleaned and cleaned[-1] not in "。！？":
            cleaned = f"{cleaned}。"
        return trim_complete_sentence(cleaned, limit)

    def _normalize_newsletter_item(
        self,
        item: NewsletterItem,
        event: EventCard,
        *,
        long_summary: bool,
    ) -> NewsletterItem:
        clean_title = self._clean_title_text(item.title or event.title)
        summary = self._usable_summary(
            item.summary or event.summary,
            title=clean_title,
            source_name=item.source_name or event.source_name,
            limit=140 if long_summary else 70,
        )
        if not summary or not self._summary_consistent_with_title(clean_title, summary):
            summary = self._fallback_summary_from_title(clean_title, 140 if long_summary else 70)
        return NewsletterItem(
            event_id=item.event_id,
            title=clean_title,
            summary=summary,
            link=item.link,
            category=item.category,
            source_name=item.source_name,
            domestic_reference_url=item.domestic_reference_url,
            domestic_reference_name=item.domestic_reference_name,
        )

    def _is_domestic_reference_candidate(self, candidate: ArticleCandidate) -> bool:
        publisher = self._publisher_name(candidate)
        domain = self._candidate_domain(candidate)
        if self._matches_domain_suffix(domain, DISALLOWED_DOMAIN_SUFFIXES):
            return False
        if self._contains_any(publisher, DISALLOWED_PUBLISHER_HINTS):
            return False
        if self._source_role_value(candidate.source) == 1 and self._governed_source_tier_value(candidate.source) <= 1:
            if publisher not in DOMESTIC_REFERENCE_PUBLISHERS and not self._matches_domain_suffix(
                domain,
                PRIMARY_DOMAIN_SUFFIXES | SECONDARY_DOMAIN_SUFFIXES | OFFICIAL_DOMAIN_SUFFIXES,
            ):
                return False
        if max(self._governed_source_tier_value(candidate.source), self._publisher_tier_value(publisher, domain)) < 2:
            return False
        if publisher in DOMESTIC_REFERENCE_PUBLISHERS:
            return True
        if self._matches_domain_suffix(domain, PRIMARY_DOMAIN_SUFFIXES | SECONDARY_DOMAIN_SUFFIXES | OFFICIAL_DOMAIN_SUFFIXES):
            return True
        return False

    def _is_non_domestic_source(self, candidate: ArticleCandidate) -> bool:
        publisher = self._publisher_name(candidate)
        domain = self._candidate_domain(candidate)
        if publisher.startswith("Reuters"):
            return True
        return domain == "reuters.com" or domain.endswith(".reuters.com") or domain == "federalreserve.gov"

    def _candidate_rank(self, candidate: ArticleCandidate) -> tuple[int, int, int, int, float]:
        publisher = self._publisher_name(candidate)
        domain = self._candidate_domain(candidate)
        tier = max(self._governed_source_tier_value(candidate.source), self._publisher_tier_value(publisher, domain))
        role = max(self._source_role_value(candidate.source), self._publisher_role_value(publisher, domain))
        non_domestic = 1 if self._is_non_domestic_source(candidate) else 0
        non_google = 0 if self._is_google_news_url(candidate.url) else 1
        return (
            tier,
            role,
            non_domestic,
            non_google,
            self._quality_score(candidate),
            candidate.published_at.timestamp(),
        )

    def _pick_representative(
        self,
        articles: list[ArticleCandidate],
        *,
        prefer_non_domestic: bool = False,
    ) -> ArticleCandidate:
        if prefer_non_domestic:
            non_domestic = [article for article in articles if self._is_non_domestic_source(article)]
            if non_domestic:
                articles = non_domestic
        return max(
            articles,
            key=self._candidate_rank,
        )
