#!/usr/bin/env python3
"""
cn_finance_news.py — 中国财经新闻与政策采集器 v3（纯curl版）
================================================================
输出字段: source | pubDate | title | description | link

用法:
  python3 cn_finance_news.py --days 3      # 默认3天
  python3 cn_finance_news.py --days 7      # 7天

依赖:
  pip install feedparser requests beautifulsoup4 --break-system-packages
"""

import subprocess, sys, json, re, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from collections import Counter

DEFAULT_DAYS = 3
OUT_FILE = Path.home() / "finance_news_latest.json"
CHINA_TZ = timezone(timedelta(hours=8))
SINA_PAGE_SIZE = 50
SINA_MAX_PAGES = 20

# ═══════════════════════════════════════════════════════════════════
# 数据源
# 工信部JSON需浏览器（见 extract_miit.js）
# ═══════════════════════════════════════════════════════════════════

JSON_FEEDS = [
    # 主流财经媒体（JSON接口）
    ("新浪财经", "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1"),
]

RSS_FEEDS = [
    # RSS源
    ("经济观察网", "http://www.eeo.com.cn/rss.xml"),
]


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def curl(url, timeout=20):
    try:
        r = subprocess.run(
            ["curl", "-sL",
             "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
             "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout + 5)
        if r.returncode != 0:
            return ""
        # 尝试多种编码解码
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                return r.stdout.decode(encoding)
            except UnicodeDecodeError:
                continue
        # 如果都失败，使用latin-1（不会失败）
        return r.stdout.decode('latin-1')
    except Exception as e:
        print(f"  [错误] curl请求失败: {e}")
        return ""


def parse_date(s):
    if not s: return ""
    s = s.replace("&#xa0;"," ").replace("&nbsp;"," ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d","%Y/%m/%d","%Y年%m月%d日","%d/%m/%Y"):
        try: return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d")
        except: pass
    if s.isdigit() and len(s) == 10:
        try: return datetime.fromtimestamp(int(s), tz=CHINA_TZ).strftime("%Y-%m-%d")
        except: pass
    m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", s)
    if m: return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return s[:10]


def in_range(date_str, max_days):
    if not date_str: return True
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - d).days <= max_days
    except: return True


def get_cn_today_and_yesterday():
    now_cn = datetime.now(CHINA_TZ)
    today_str = now_cn.strftime("%Y-%m-%d")
    yesterday_str = (now_cn - timedelta(days=1)).strftime("%Y-%m-%d")
    return today_str, yesterday_str


# ═══════════════════════════════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════════════════════════════

def parse_ndrc(html):
    """
    发改委: <li><a href="./202605/t20260520_xxxx.html">标题</a> ... <span>2026/05/20</span>
    """
    items = []
    pat = r'<li>\s*<a[^>]+href="(\./[^"]+)"[^>]*>([^<]+)</a>(?:[^<]|<(?!span))*<span[^>]*>(\d{4}[/\-]\d{2}[/\-]\d{2})</span>'
    for m in re.finditer(pat, html, re.DOTALL):
        rel = m.group(1).lstrip("./")
        ym  = rel[:6]
        items.append({
            "title": m.group(2).strip(),
            "link":  f"https://www.ndrc.gov.cn/xxgk/zcfb/tz/{ym}/{rel}",
            "pubDate": parse_date(m.group(3)),
            "description": "",
        })
    return items


def parse_html_list(html, base):
    """通用政府列表页"""
    items = []
    for line in html.split("\n"):
        if "href" not in line: continue
        dm = re.search(r"(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})", line)
        if not dm: continue
        am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', line)
        if not am: continue
        href = am.group(1)
        if not href.startswith("http"): href = urljoin(base, href)
        title = re.sub(r"<[^>]+>", "", am.group(2)).strip()
        if len(title) < 5: continue
        items.append({"title": title, "link": href,
                      "pubDate": parse_date(dm.group(1)), "description": ""})
    return items


def parse_sina_json(raw):
    try:
        data = json.loads(raw)
        out = []
        for it in data.get("result",{}).get("data",[]) or []:
            out.append({
                "title": it.get("title",""),
                "link":  it.get("url","") or it.get("wapurl",""),
                "pubDate": parse_date(it.get("ctime","")),
                "description": it.get("intro","") or it.get("summary",""),
            })
        return out
    except: return []


def build_sina_page_url(url, page, page_size):
    url = re.sub(r"([?&])num=\d+", rf"\1num={page_size}", url)
    url = re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
    return url


def parse_rss(raw):
    items = []
    for blk in re.findall(r"<item>(.*?)</item>|<entry>(.*?)</entry>", raw, re.DOTALL):
        b = blk[0] or blk[1]
        tm = re.search(r"<title[^>]*>(.*?)</title>", b, re.DOTALL)
        lm = re.search(r"<link[^>]*>(.*?)</link>|<link[^>]+href=\"([^\"]+)\"", b, re.DOTALL)
        pm = re.search(r"<pubDate>(.*?)</pubDate>|<published>(.*?)</published>|<dc:date>(.*?)</dc:date>", b, re.DOTALL)
        dm = re.search(r"<description>(.*?)</description>|<content:encoded>(.*?)</content:encoded>|<summary>(.*?)</summary>", b, re.DOTALL)
        title  = re.sub(r"<[^>]+>","",(tm.group(1) if tm else "")).strip()
        link   = ((lm.group(1) or lm.group(2)) if lm else "").strip()
        if not link:
            t = re.search(r'href="([^"]+)"', b)
            link = t.group(1) if t else ""
        pub    = ((pm.group(1) or pm.group(2) or pm.group(3)) if pm else "").strip()
        desc_raw = (dm.group(1) or dm.group(2) or dm.group(3)) if dm else ""
        desc_raw = desc_raw if desc_raw else ""
        desc   = re.sub(r"<[^>]+>","",desc_raw).strip()[:200]
        items.append({"title": title, "link": link,
                     "pubDate": parse_date(pub), "description": desc})
    return items


# ═══════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════


def collect_json(max_days):
    results = []
    today_str, yesterday_str = get_cn_today_and_yesterday()
    # 生成最近 max_days 天的日期集合（用于过滤）
    target_dates = set()
    from datetime import timedelta
    for i in range(max_days):
        d = datetime.now(CHINA_TZ) - timedelta(days=i)
        target_dates.add(d.strftime("%Y-%m-%d"))
    
    for name, url in JSON_FEEDS:
        print(f"  [JSON] {name} (最近{max_days}天) ... ", end="", flush=True)
        items = []
        for page in range(1, SINA_MAX_PAGES + 1):
            raw = curl(build_sina_page_url(url, page, SINA_PAGE_SIZE))
            if not raw:
                if page == 1:
                    print("失败（无响应）")
                break
            page_items = parse_sina_json(raw)
            if not page_items:
                break
            page_has_target = False
            for it in page_items:
                pub = it.get("pubDate", "")
                if pub in target_dates:
                    items.append(it)
                    page_has_target = True
            # 如果这页没有目标日期的新闻，说明已经翻过了（新浪按时间排序）
            if not page_has_target and page_items:
                # 检查是不是所有新闻都比目标范围更老
                oldest = min((it.get("pubDate","") for it in page_items if it.get("pubDate")), default="")
                if oldest and oldest < min(target_dates):
                    break
            if len(page_items) < SINA_PAGE_SIZE:
                break
        for it in items: it["source"] = name
        results.extend(items)
        print(f"{len(items)} 条" if items else "无数据")
    return results


def collect_rss(max_days):
    results = []
    today_str, yesterday_str = get_cn_today_and_yesterday()
    for name, url in RSS_FEEDS:
        print(f"  [RSS]  {name} ... ", end="", flush=True)
        raw = curl(url)
        if not raw:
            print("失败（无响应）")
            continue
        items = parse_rss(raw)
        for it in items: it["source"] = name
        # 用 max_days 动态过滤（与 JSON 源一致）
        items = [it for it in items if in_range(it["pubDate"], max_days)]
        results.extend(items)
        print(f"{len(items)} 条" if items else "无数据")
    return results


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--miit-json", type=str, default="",
                    help="工信部JSON（由extract_miit.js生成，合并进来）")
    args = ap.parse_args()
    max_days = args.days

    print("=" * 60)
    print(f"中国财经新闻采集器（最近 {max_days} 天，纯curl）")
    print("=" * 60)

    items = []
    items += collect_json(max_days)
    items += collect_rss(max_days)

    # 合并工信部JSON（如有）—— 标准化字段名（href→link）
    if args.miit_json and Path(args.miit_json).exists():
        print(f"\n  [合并] 工信部数据 from {args.miit_json}")
        with open(args.miit_json) as f:
            miit = json.load(f)
        for it in miit:
            it["source"] = "工信部"
            if "href" in it:
                it["link"] = it.pop("href")
        miit = [it for it in miit if in_range(it.get("pubDate",""), max_days)]
        items += miit
        print(f"  合并 {len(miit)} 条工信部记录")

    # 去重
    seen, uniq = set(), []
    for it in items:
        key = it["title"].strip()[:60]
        if key and key not in seen:
            seen.add(key); uniq.append(it)
    items = [it for it in uniq if it.get("title") and len(it["title"]) > 5]
    items.sort(key=lambda x: x.get("pubDate","1900") or "1900", reverse=True)

    total = len(items)
    print(f"\n共 {total} 条（去重后）")
    print("=" * 60)

    # 表格
    if items:
        print(f"| # | 来源 | 日期 | 标题 | 简述 |")
        print(f"|---|---|---|---|---|")
        for i, it in enumerate(items[:80], 1):
            t = it["title"][:60] + ("…" if len(it["title"])>60 else "")
            d = (it.get("description") or "")[:90].replace("\n"," ").replace("|","\\|")
            print(f"| {i} | {it.get('source','?')} | {it.get('pubDate','?')[:10]} | [{t}]({it['link']}) | {d} |")
    else:
        print("（无数据）")

    # JSON
    with open(OUT_FILE,"w",encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "days": max_days, "total": total, "items": items},
                  f, ensure_ascii=False, indent=2)
    print(f"\n完整JSON → {OUT_FILE}")

    # 来源统计（用于排查数据来源）
    source_count = Counter(it["source"] for it in items)
    print("\n来源统计:")
    for src, cnt in source_count.most_common():
        print(f"  {src}: {cnt}")
    
    # 调试：打印每个来源的标题长度分布
    print("\n调试 - 各来源标题长度范围:")
    for src in set(it["source"] for it in items):
        titles = [it["title"] for it in items if it["source"] == src]
        if titles:
            print(f"  {src}: {min(len(t) for t in titles)}-{max(len(t) for t in titles)} 字符")


if __name__ == "__main__":
    main()
