import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd
import requests
import urllib3
from akshare.stock.cons import hk_js_decode
from py_mini_racer import MiniRacer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HOLDINGS_FILE = ROOT / "投资者行动" / "持仓情况.md"
ADVICE_REPORT_DIR = ROOT / "投资者行动" / "持仓分析与建议"
ARCHIVE_DIR = ROOT / "投资新闻归档"

CORE_INDUSTRY_ETFS = {
    "588000": {"theme": "科创50"},
    "159915": {"theme": "创业板"},
    "510300": {"theme": "沪深300"},
    "510500": {"theme": "中证500"},
    "510050": {"theme": "上证50"},
    "563360": {"theme": "中证A500"},
    "560050": {"theme": "中国A50"},
}

HOLDING_RELEVANT_ETFS = {
    "513050": {
        "theme": "央企红利",
        "related_funds": ["天弘中证央企红利50指数A(021561)"],
    },
    "159781": {
        "theme": "科创创业50",
        "related_funds": ["天弘中证科创创业50ETF联接A(012894)"],
    },
    "560050": {
        "theme": "中国A50",
        "related_funds": ["中银MSCI中国A50互联互通指数增强A(014623)"],
    },
    "562550": {
        "theme": "绿电",
        "related_funds": ["富国中证绿色电力ETF发起式联接A(020095)"],
    },
    "510300": {
        "theme": "沪深300",
        "related_funds": ["易方达沪深300指数精选增强A(010736)"],
    },
    "159996": {
        "theme": "家电",
        "related_funds": ["易方达中证家电龙头ETF联接C(018647)"],
    },
    "159995": {
        "theme": "芯片",
        "related_funds": ["汇添富中证芯片产业指数增强C(014194)"],
    },
    "588000": {
        "theme": "科创50",
        "related_funds": ["华商新趋势优选灵活配置混合(166301)"],
    },
    "511010": {
        "theme": "国债",
        "related_funds": ["中欧鼎利债券C(009520)"],
    },
}

EASTMONEY_MUTUAL_HISTORY_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
NORTHBOUND_WEEKLY_COMPONENT_TYPES = ("002", "004")
NORTHBOUND_WEEKLY_AGGREGATE_TYPE = "006"


def parse_args():
    parser = argparse.ArgumentParser(description="抓取持仓建议所需的市场动量基础数据")
    parser.add_argument("--date", required=True, help="分析日期，格式 YYYY-MM-DD")
    parser.add_argument(
        "--holdings-file",
        default=str(DEFAULT_HOLDINGS_FILE),
        help="持仓文件路径，默认读取 投资者行动/持仓情况.md",
    )
    parser.add_argument("--output", help="输出 JSON 文件路径；不传则打印到 stdout")
    return parser.parse_args()


def load_holdings_from_markdown(file_path):
    text = Path(file_path).read_text(encoding="utf-8")
    in_funds_section = False
    funds = []
    current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == "基金：":
            in_funds_section = True
            current = None
            continue

        if in_funds_section and stripped.endswith(":") and stripped != "基金：":
            break

        if not in_funds_section:
            continue

        if stripped.startswith("- "):
            current = {"name": stripped[2:].strip()}
            funds.append(current)
            continue

        if current is None:
            continue

        match = re.match(r"代码:\s*(\S+)", stripped)
        if match:
            current["code"] = match.group(1)
            continue

        match = re.match(r"持仓成本:\s*(\S+)", stripped)
        if match:
            current["cost"] = float(match.group(1))
            continue

        match = re.match(r"份数:\s*(\S+)", stripped)
        if match:
            current["shares"] = float(match.group(1))

    return [item for item in funds if item.get("code")]


def infer_sina_symbol(code):
    return f"{'sh' if code.startswith(('5', '6')) else 'sz'}{code}"


def raw_amount_to_yi_if_million(raw_value):
    numeric = pd.to_numeric(raw_value, errors="coerce")
    if pd.isna(numeric):
        return None
    return round(float(numeric) / 100, 2)


def safe_float(value, digits=None):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    result = float(numeric)
    if digits is not None:
        result = round(result, digits)
    return result


def safe_int(value):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return int(numeric)


def nearly_equal(left, right, tolerance=1e-6):
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def normalize_amount_text(amount_text):
    if amount_text is None:
        return None
    cleaned = str(amount_text).replace(",", "").replace("元", "").strip()
    return safe_float(cleaned, 2)


def get_prior_day_cutoff(as_of_date):
    return (pd.Timestamp(as_of_date).normalize() - timedelta(days=1)).date()


def parse_report_date_from_path(path):
    match = re.search(r"投资建议报告_(\d{8})\.html$", path.name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d").date()


def find_previous_advice_report(as_of_date):
    target_date = pd.Timestamp(as_of_date).date()
    candidates = []
    if not ADVICE_REPORT_DIR.exists():
        return None

    for path in ADVICE_REPORT_DIR.glob("投资建议报告_*.html"):
        report_date = parse_report_date_from_path(path)
        if report_date is None or report_date >= target_date:
            continue
        candidates.append((report_date, path))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def extract_report_holdings(report_path):
    text = Path(report_path).read_text(encoding="utf-8")
    results = []

    legacy_pattern = re.compile(
        r'\{\s*full:\s*"(?P<full>[^"]+)"\s*,\s*name:\s*"(?P<name>[^"]+)"\s*,\s*code:\s*"(?P<code>\d+)"\s*,\s*nav:\s*"(?P<nav>[^"]+)"\s*,\s*amount:\s*"(?P<amount>[^"]+)"\s*,\s*weight:\s*"(?P<weight>[^"]+)"\s*\}'
    )

    for match in legacy_pattern.finditer(text):
        nav = safe_float(match.group("nav"), 4)
        amount = normalize_amount_text(match.group("amount"))
        shares = None
        if nav not in (None, 0) and amount is not None:
            shares = round(amount / nav, 2)
        results.append(
            {
                "full": match.group("full"),
                "name": match.group("name"),
                "code": match.group("code"),
                "report_nav": nav,
                "report_amount": amount,
                "report_weight": match.group("weight"),
                "shares": shares,
            }
        )

    if results:
        return results

    array_match = re.search(r'const\s+funds\s*=\s*(\[.*?\]);', text, re.S)
    if not array_match:
        return results

    try:
        payload = json.loads(array_match.group(1))
    except json.JSONDecodeError:
        return results

    for item in payload:
        nav = safe_float(item.get("nav"), 4)
        amount = normalize_amount_text(item.get("amount"))
        shares = None
        if nav not in (None, 0) and amount is not None:
            shares = round(amount / nav, 2)
        results.append(
            {
                "full": item.get("full"),
                "name": item.get("name"),
                "code": item.get("code"),
                "report_nav": nav,
                "report_amount": amount,
                "report_weight": item.get("weight"),
                "shares": shares,
            }
        )

    return results


def load_previous_snapshot_costs(report_date):
    snapshot_path = ARCHIVE_DIR / report_date.strftime("%Y-%m") / report_date.strftime("%Y-%m-%d") / "raw_data" / f"analysis_snapshot_{report_date.strftime('%Y-%m-%d')}.json"
    if not snapshot_path.exists():
        return {}, snapshot_path

    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, snapshot_path

    costs = {}
    for item in payload.get("holdings", []):
        code = item.get("code")
        if not code:
            continue
        costs[code] = {
            "cost": safe_float(item.get("cost"), 4),
            "name": item.get("name"),
        }
    return costs, snapshot_path


def load_previous_report_context(as_of_date):
    previous_report = find_previous_advice_report(as_of_date)
    if previous_report is None:
        return {
            "status": "no_previous_report",
            "note": "未找到早于本次分析日期的历史投资建议 HTML 报告。",
        }

    report_date, report_path = previous_report
    report_holdings = extract_report_holdings(report_path)
    costs_by_code, snapshot_path = load_previous_snapshot_costs(report_date)

    holdings = []
    for item in report_holdings:
        cost_info = costs_by_code.get(item["code"], {})
        holdings.append(
            {
                "code": item["code"],
                "name": item["name"],
                "full": item["full"],
                "shares": item.get("shares"),
                "report_nav": item.get("report_nav"),
                "report_amount": item.get("report_amount"),
                "report_weight": item.get("report_weight"),
                "cost": cost_info.get("cost"),
            }
        )

    return {
        "status": "success",
        "report_date": str(report_date),
        "report_path": str(report_path.resolve()),
        "snapshot_path": str(snapshot_path.resolve()) if snapshot_path.exists() else None,
        "holdings": holdings,
        "note": "上一份报告中的持仓份额由悬浮卡片里的总金额 / 当时净值反推得到；卖出盈亏按本次官方净值做估算。",
    }


def merge_holdings_for_nav(current_holdings, previous_context):
    merged = {item["code"]: dict(item) for item in current_holdings}

    for item in previous_context.get("holdings", []):
        if item["code"] in merged:
            continue
        merged[item["code"]] = {
            "code": item["code"],
            "name": item.get("name"),
            "cost": item.get("cost"),
            "shares": item.get("shares"),
        }

    return list(merged.values())


def build_holding_valuation_snapshot(holdings, fund_navs):
    nav_map = {item["code"]: item for item in fund_navs if item.get("status") == "success"}
    results = []
    total_amount = 0.0

    for item in holdings:
        code = item["code"]
        nav_row = nav_map.get(code)
        shares = safe_float(item.get("shares"), 2)
        cost = safe_float(item.get("cost"), 4)
        official_nav = safe_float(nav_row.get("official_nav"), 4) if nav_row else None
        nav_date = nav_row.get("nav_date") if nav_row else None
        holding_amount = None
        cost_amount = None
        floating_pnl_amount = None
        floating_pnl_pct = None

        if shares is not None and official_nav is not None:
            holding_amount = round(shares * official_nav, 2)
            total_amount += holding_amount
        if shares is not None and cost is not None:
            cost_amount = round(shares * cost, 2)
        if holding_amount is not None and cost_amount is not None:
            floating_pnl_amount = round(holding_amount - cost_amount, 2)
            if cost_amount != 0:
                floating_pnl_pct = round(floating_pnl_amount / cost_amount * 100, 2)

        results.append(
            {
                "code": code,
                "name": item["name"],
                "shares": shares,
                "cost": cost,
                "official_nav": official_nav,
                "nav_date": nav_date,
                "holding_amount": holding_amount,
                "cost_amount": cost_amount,
                "floating_pnl_amount": floating_pnl_amount,
                "floating_pnl_pct": floating_pnl_pct,
            }
        )

    total_amount = round(total_amount, 2)
    for item in results:
        if total_amount and item.get("holding_amount") is not None:
            item["holding_weight_pct"] = round(item["holding_amount"] / total_amount * 100, 2)
        else:
            item["holding_weight_pct"] = None

    return {
        "status": "success",
        "total_holding_amount": total_amount,
        "holdings": results,
    }


def build_analysis_snapshot(payload):
    holdings_source = payload.get("holdings_source")
    valuation = payload.get("holding_valuation_snapshot") or {}
    valuation_rows = valuation.get("holdings") or []
    total_holding_amount = valuation.get("total_holding_amount")
    change_summary = payload.get("holdings_change_vs_previous_report") or {}
    change_rows = change_summary.get("changes") or []
    relevant_etf_daily = payload.get("relevant_etf_daily") or []

    changes_by_code = {item.get("code"): item for item in change_rows if item.get("code")}
    etf_by_full = {}
    for item in relevant_etf_daily:
        if item.get("status") != "success":
            continue
        for related_full in item.get("related_funds") or []:
            etf_by_full[related_full] = item

    holdings = []
    for item in valuation_rows:
        code = item.get("code")
        name = item.get("name")
        if not code or not name:
            continue
        full = f"{name}({code})"
        change = changes_by_code.get(code) or {}
        related_etf = etf_by_full.get(full) or {}
        holdings.append(
            {
                "code": code,
                "name": name,
                "full": full,
                "shares": item.get("shares"),
                "cost": item.get("cost"),
                "official_nav": item.get("official_nav"),
                "nav_date": item.get("nav_date"),
                "holding_amount": item.get("holding_amount"),
                "holding_cost_amount": item.get("cost_amount"),
                "floating_pnl_amount": item.get("floating_pnl_amount"),
                "floating_pnl_pct": item.get("floating_pnl_pct"),
                "holding_weight_pct": item.get("holding_weight_pct"),
                "share_change_type": change.get("change_type"),
                "previous_shares": change.get("previous_shares"),
                "share_delta": change.get("share_delta"),
                "related_etf": related_etf.get("code"),
                "related_etf_name": related_etf.get("theme"),
                "related_etf_change_pct": related_etf.get("change_pct"),
            }
        )

    total_cost_amount = 0.0
    total_floating_pnl_amount = 0.0
    has_cost_amount = False
    has_floating_amount = False
    for item in holdings:
        holding_cost_amount = item.get("holding_cost_amount")
        floating_pnl_amount = item.get("floating_pnl_amount")
        if holding_cost_amount is not None:
            total_cost_amount += holding_cost_amount
            has_cost_amount = True
        if floating_pnl_amount is not None:
            total_floating_pnl_amount += floating_pnl_amount
            has_floating_amount = True

    total_cost_amount = round(total_cost_amount, 2) if has_cost_amount else None
    total_floating_pnl_amount = round(total_floating_pnl_amount, 2) if has_floating_amount else None
    total_floating_pnl_pct = None
    if total_cost_amount not in (None, 0) and total_floating_pnl_amount is not None:
        total_floating_pnl_pct = round(total_floating_pnl_amount / total_cost_amount * 100, 2)

    return {
        "generated_at": payload.get("generated_at"),
        "as_of_date": payload.get("as_of_date"),
        "day_level_cutoff_date": payload.get("day_level_cutoff_date"),
        "holdings_source": holdings_source,
        "holdings_count": len(holdings),
        "changed_funds_count": change_summary.get("changed_funds_count", 0),
        "previous_report_date": change_summary.get("previous_report_date"),
        "previous_snapshot_path": change_summary.get("previous_snapshot_path"),
        "total_holding_amount": total_holding_amount,
        "total_cost_amount": total_cost_amount,
        "total_floating_pnl_amount": total_floating_pnl_amount,
        "total_floating_pnl_pct": total_floating_pnl_pct,
        "holdings": holdings,
    }


def infer_analysis_snapshot_output_path(market_momentum_output_path):
    output_path = Path(market_momentum_output_path)
    name = output_path.name
    if not name.startswith("market_momentum_") or not name.endswith(".json"):
        return output_path.with_name("analysis_snapshot.json")
    return output_path.with_name(name.replace("market_momentum_", "analysis_snapshot_", 1))


def build_holdings_change_summary(current_holdings, previous_context, fund_navs):
    if previous_context.get("status") != "success":
        return {
            "status": previous_context.get("status", "no_previous_report"),
            "note": previous_context.get("note"),
            "changes": [],
        }

    current_map = {item["code"]: item for item in current_holdings}
    previous_map = {item["code"]: item for item in previous_context.get("holdings", [])}
    nav_map = {item["code"]: item for item in fund_navs if item.get("status") == "success"}
    changes = []

    for code in sorted(set(current_map) | set(previous_map)):
        current_item = current_map.get(code)
        previous_item = previous_map.get(code)
        current_shares = safe_float(current_item.get("shares"), 2) if current_item else 0.0
        previous_shares = safe_float(previous_item.get("shares"), 2) if previous_item else 0.0
        current_shares = current_shares if current_shares is not None else 0.0
        previous_shares = previous_shares if previous_shares is not None else 0.0
        share_delta = round(current_shares - previous_shares, 2)

        if nearly_equal(current_shares, previous_shares, tolerance=0.005):
            change_type = "unchanged"
        elif previous_item is None:
            change_type = "new"
        elif current_item is None:
            change_type = "cleared"
        elif share_delta > 0:
            change_type = "increased"
        else:
            change_type = "reduced"

        nav_row = nav_map.get(code)
        official_nav = safe_float(nav_row.get("official_nav"), 4) if nav_row else None
        nav_date = nav_row.get("nav_date") if nav_row else None
        estimated_sold_shares = None
        estimated_transaction_amount = None
        estimated_cost_basis_amount = None
        estimated_realized_pnl_amount = None
        estimated_realized_pnl_pct = None
        estimated_realized_status = None

        if change_type in {"reduced", "cleared"}:
            estimated_sold_shares = round(previous_shares - current_shares, 2)
            cost = safe_float((previous_item or {}).get("cost"), 4)
            if estimated_sold_shares and official_nav is not None:
                estimated_transaction_amount = round(estimated_sold_shares * official_nav, 2)
            if estimated_sold_shares and cost is not None:
                estimated_cost_basis_amount = round(estimated_sold_shares * cost, 2)
            if estimated_transaction_amount is not None and estimated_cost_basis_amount is not None:
                estimated_realized_pnl_amount = round(
                    estimated_transaction_amount - estimated_cost_basis_amount, 2
                )
                if estimated_cost_basis_amount != 0:
                    estimated_realized_pnl_pct = round(
                        estimated_realized_pnl_amount / estimated_cost_basis_amount * 100, 2
                    )
                if estimated_realized_pnl_amount > 0:
                    estimated_realized_status = "estimated_profit"
                elif estimated_realized_pnl_amount < 0:
                    estimated_realized_status = "estimated_loss"
                else:
                    estimated_realized_status = "estimated_breakeven"

        changes.append(
            {
                "code": code,
                "name": (current_item or previous_item).get("name"),
                "change_type": change_type,
                "previous_shares": previous_shares,
                "current_shares": current_shares,
                "share_delta": share_delta,
                "official_nav": official_nav,
                "nav_date": nav_date,
                "estimated_sold_shares": estimated_sold_shares,
                "estimated_transaction_amount_at_current_nav": estimated_transaction_amount,
                "estimated_cost_basis_amount": estimated_cost_basis_amount,
                "estimated_realized_pnl_amount": estimated_realized_pnl_amount,
                "estimated_realized_pnl_pct": estimated_realized_pnl_pct,
                "estimated_realized_status": estimated_realized_status,
            }
        )

    changed_count = len([item for item in changes if item["change_type"] != "unchanged"])
    return {
        "status": "success",
        "previous_report_date": previous_context.get("report_date"),
        "previous_report_path": previous_context.get("report_path"),
        "previous_snapshot_path": previous_context.get("snapshot_path"),
        "note": previous_context.get("note"),
        "changed_funds_count": changed_count,
        "changes": changes,
    }


def get_northbound_daily_raw(as_of_date, lookback_days=7):
    """返回分析日之前最近一个交易日的北向原始字段，同时写出联网交叉验证后的单位换算。"""
    try:
        cutoff_date = get_prior_day_cutoff(as_of_date)
        start_date = cutoff_date - timedelta(days=lookback_days - 1)
        rows = fetch_eastmoney_mutual_deal_history(
            start_date.strftime("%Y-%m-%d"), cutoff_date.strftime("%Y-%m-%d")
        )
        if not rows:
            return {"status": "not_found", "requested_as_of_date": as_of_date, "cutoff_date": str(cutoff_date)}

        frame = pd.DataFrame(rows)
        frame["TRADE_DATE"] = pd.to_datetime(frame["TRADE_DATE"], errors="coerce").dt.normalize()
        frame = frame[
            (frame["TRADE_DATE"] >= pd.Timestamp(start_date))
            & (frame["TRADE_DATE"] <= pd.Timestamp(cutoff_date))
            & (frame["MUTUAL_TYPE"].astype(str) == "005")
        ].copy()
        if frame.empty:
            return {"status": "not_found", "requested_as_of_date": as_of_date, "cutoff_date": str(cutoff_date)}

        frame = frame.sort_values(by="TRADE_DATE", ascending=False)
        row = frame.iloc[0].to_dict()
        if row is None:
            return {"status": "not_found", "requested_as_of_date": as_of_date, "cutoff_date": str(cutoff_date)}
        deal_amt_raw = row.get("DEAL_AMT")
        net_deal_amt_raw = row.get("NET_DEAL_AMT")
        buy_amt_raw = row.get("BUY_AMT")
        sell_amt_raw = row.get("SELL_AMT")
        return {
            "status": "raw_record_available",
            "requested_as_of_date": as_of_date,
            "cutoff_date": str(cutoff_date),
            "date": str(pd.Timestamp(row.get("TRADE_DATE")).date()),
            "report_name": "RPT_MUTUAL_DEAL_HISTORY",
            "mutual_type": "005",
            "deal_amt_raw": deal_amt_raw,
            "net_deal_amt_raw": net_deal_amt_raw,
            "buy_amt_raw": buy_amt_raw,
            "sell_amt_raw": sell_amt_raw,
            "unit_self_evident": False,
            "unit_inferred_online": "million_rmb",
            "unit_inferred_online_label": "百万元",
            "deal_amt_yi_if_raw_unit_is_million": raw_amount_to_yi_if_million(deal_amt_raw),
            "net_deal_amt_yi_if_raw_unit_is_million": raw_amount_to_yi_if_million(net_deal_amt_raw),
            "buy_amt_yi_if_raw_unit_is_million": raw_amount_to_yi_if_million(buy_amt_raw),
            "sell_amt_yi_if_raw_unit_is_million": raw_amount_to_yi_if_million(sell_amt_raw),
            "unit_validation_basis": [
                "AkShare 在线文档把 stock_hsgt_hist_em 的成交额相关字段标注为亿元。",
                "AkShare 远端源码 stock_hsgt_hist_em 对 RPT_MUTUAL_DEAL_HISTORY 的 NET_DEAL_AMT / BUY_AMT / SELL_AMT 做了 /100 后输出为亿元。",
            ],
            "note": "响应行本身没有给数值单位打标签，但联网交叉验证后可按百万元理解；例如 DEAL_AMT=358681.44 时，对应约 3586.81 亿元。",
        }
    except Exception as exc:
        return {"status": "error", "requested_as_of_date": as_of_date, "message": str(exc)}


def fetch_eastmoney_mutual_deal_history(start_date, end_date):
    all_rows = []
    page_number = 1

    while True:
        response = requests.get(
            EASTMONEY_MUTUAL_HISTORY_URL,
            params={
                "sortColumns": "TRADE_DATE,MUTUAL_TYPE",
                "sortTypes": "1,1",
                "pageSize": "500",
                "pageNumber": str(page_number),
                "reportName": "RPT_MUTUAL_DEAL_HISTORY",
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "filter": f"(TRADE_DATE>='{start_date}')(TRADE_DATE<='{end_date}')",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json() or {}
        result = payload.get("result") or {}
        rows = result.get("data") or []
        all_rows.extend(rows)

        pages = safe_int(result.get("pages")) or 1
        if page_number >= pages:
            break
        page_number += 1

    return all_rows


def get_northbound_weekly_summary(as_of_date, days=7):
    """优先用东财原始表的 006 北向汇总类型直接计算近7天净流向。"""
    try:
        target_date = pd.Timestamp(get_prior_day_cutoff(as_of_date))
        start_date = target_date - timedelta(days=days - 1)
        rows = fetch_eastmoney_mutual_deal_history(start_date.strftime("%Y-%m-%d"), target_date.strftime("%Y-%m-%d"))
        if not rows:
            return {
                "status": "not_found",
                "period": f"近{days}天",
                "latest_available_date": None,
                "note": "东财 RPT_MUTUAL_DEAL_HISTORY 未返回目标窗口数据。",
            }

        frame = pd.DataFrame(rows)
        frame["TRADE_DATE"] = pd.to_datetime(frame["TRADE_DATE"], errors="coerce").dt.normalize()
        frame = frame[(frame["TRADE_DATE"] >= start_date) & (frame["TRADE_DATE"] <= target_date)]
        if frame.empty:
            return {
                "status": "not_found",
                "period": f"近{days}天",
                "latest_available_date": None,
                "note": "东财 RPT_MUTUAL_DEAL_HISTORY 在目标窗口内无可用记录。",
            }

        latest_available = frame["TRADE_DATE"].max()
        aggregate = frame[frame["MUTUAL_TYPE"].astype(str) == NORTHBOUND_WEEKLY_AGGREGATE_TYPE].copy()
        if aggregate.empty:
            return {
                "status": "aggregate_type_missing",
                "period": f"近{days}天",
                "latest_available_date": None if pd.isna(latest_available) else str(latest_available.date()),
                "note": "目标窗口内未找到北向汇总类型 006，无法直接计算近7天净流向。",
            }

        aggregate["NET_DEAL_AMT"] = pd.to_numeric(aggregate["NET_DEAL_AMT"], errors="coerce")
        aggregate["BUY_AMT"] = pd.to_numeric(aggregate["BUY_AMT"], errors="coerce")
        aggregate["SELL_AMT"] = pd.to_numeric(aggregate["SELL_AMT"], errors="coerce")

        if aggregate["NET_DEAL_AMT"].isna().all():
            return {
                "status": "nan_detected",
                "period": f"近{days}天",
                "latest_available_date": None if pd.isna(latest_available) else str(latest_available.date()),
                "note": "目标窗口内东财 006 北向汇总记录的 NET_DEAL_AMT 全为 NaN。",
            }

        aggregate = aggregate.sort_values(by="TRADE_DATE", ascending=True)
        total_net_in = float(aggregate["NET_DEAL_AMT"].sum())
        direction = "流入" if total_net_in > 0 else "流出" if total_net_in < 0 else "中性"
        daily_rows = []
        for _, row in aggregate.iterrows():
            daily_rows.append(
                {
                    "date": str(row["TRADE_DATE"].date()),
                    "mutual_type": str(row.get("MUTUAL_TYPE")),
                    "net_deal_amt_raw": safe_float(row.get("NET_DEAL_AMT"), 2),
                    "buy_amt_raw": safe_float(row.get("BUY_AMT"), 2),
                    "sell_amt_raw": safe_float(row.get("SELL_AMT"), 2),
                }
            )

        return {
            "status": "success",
            "period": f"近{days}天",
            "latest_available_date": str(latest_available.date()),
            "direction": direction,
            "source": "Eastmoney RPT_MUTUAL_DEAL_HISTORY",
            "aggregate_mutual_type": NORTHBOUND_WEEKLY_AGGREGATE_TYPE,
            "component_mutual_types": list(NORTHBOUND_WEEKLY_COMPONENT_TYPES),
            "raw_unit_inferred_online_label": "百万元",
            "window_trade_days": len(daily_rows),
            "daily_net_flow": daily_rows,
            "total_net_deal_amt_raw": round(total_net_in, 2),
            "total_net_in_yi_if_raw_unit_is_million": raw_amount_to_yi_if_million(total_net_in),
            "note": "东财原始表中 006 类型的 BUY_AMT / SELL_AMT / NET_DEAL_AMT 与 002+004 按日相加一致，可视作北向汇总；数值按百万元理解时，近7天净流向可换算为亿元。",
        }
    except Exception as exc:
        return {"status": "error", "period": f"近{days}天", "message": str(exc)}


def get_sina_etf_history(symbol):
    url = f"https://finance.sina.com.cn/realstock/company/{symbol}/hisdata_klc2/klc_kl.js"
    response = requests.get(url, timeout=20, verify=False)
    response.raise_for_status()
    if "=" not in response.text:
        raise ValueError(f"unexpected payload for {symbol}")

    payload = response.text.split("=")[1].split(";")[0].replace('"', "")
    js = MiniRacer()
    js.eval(hk_js_decode)
    rows = js.call("d", payload)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None).dt.date
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values(by="date", ascending=True).reset_index(drop=True)


def get_eastmoney_etf_history(code):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Connection": "close",
    }
    endpoints = [
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://91.push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://60.push2his.eastmoney.com/api/qt/stock/kline/get",
    ]
    secid_candidates = [
        f"{'1' if code.startswith(('5', '6')) else '0'}.{code}",
        f"{'0' if code.startswith(('5', '6')) else '1'}.{code}",
    ]
    last_error = None

    for endpoint in endpoints:
        for secid in secid_candidates:
            try:
                response = requests.get(
                    endpoint,
                    headers=headers,
                    params={
                        "secid": secid,
                        "fields1": "f1,f2,f3,f4,f5,f6",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                        "klt": "101",
                        "fqt": "0",
                        "beg": "19900101",
                        "end": "20500101",
                        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                        "lmt": "100000",
                    },
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json() or {}
                klines = ((payload.get("data") or {}).get("klines")) or []
                if not klines:
                    raise ValueError(f"empty kline for secid={secid}")

                rows = []
                for item in klines:
                    parts = item.split(",")
                    if len(parts) < 7:
                        continue
                    rows.append(
                        {
                            "date": parts[0],
                            "open": parts[1],
                            "close": parts[2],
                            "high": parts[3],
                            "low": parts[4],
                            "volume": parts[5],
                            "amount": parts[6],
                        }
                    )

                df = pd.DataFrame(rows)
                if df.empty:
                    raise ValueError(f"parsed kline empty for secid={secid}")

                df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
                for column in ["open", "close", "high", "low", "volume", "amount"]:
                    df[column] = pd.to_numeric(df[column], errors="coerce")

                df = df.dropna(subset=["date", "close"]).sort_values(by="date", ascending=True).reset_index(drop=True)
                if df.empty:
                    raise ValueError(f"cleaned kline empty for secid={secid}")

                return df
            except Exception as exc:
                last_error = exc

    raise ValueError(f"Eastmoney fallback failed: {last_error}")


def build_etf_daily_from_history(df, code, theme, symbol, source, as_of_date):
    target_date = get_prior_day_cutoff(as_of_date)
    if df.empty:
        return {
            "code": code,
            "theme": theme,
            "symbol": symbol,
            "status": "empty",
        }

    eligible = df[df["date"] <= target_date]
    if eligible.empty:
        return {
            "code": code,
            "theme": theme,
            "symbol": symbol,
            "status": "date_not_found",
        }

    idx = int(eligible.index[-1])
    row = df.loc[idx]
    prev_close = None
    change_pct = None
    if idx > 0 and pd.notna(df.loc[idx - 1, "close"]):
        prev_close = float(df.loc[idx - 1, "close"])
        if prev_close != 0:
            change_pct = round((float(row["close"]) / prev_close - 1) * 100, 2)

    return {
        "code": code,
        "theme": theme,
        "symbol": symbol,
        "status": "success",
        "date": str(row["date"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "prev_close": prev_close,
        "change_pct": change_pct,
        "volume": safe_int(row.get("volume")),
        "amount": safe_int(row.get("amount")),
        "source": source,
    }


def get_single_etf_daily(code, theme, as_of_date):
    symbol = infer_sina_symbol(code)

    try:
        df = get_sina_etf_history(symbol)
        result = build_etf_daily_from_history(
            df,
            code=code,
            theme=theme,
            symbol=symbol,
            source="Sina 历史 K 线（requests verify=False + hk_js_decode）",
            as_of_date=as_of_date,
        )
        if result["status"] == "success":
            return result
    except Exception as exc:
        sina_error = str(exc)
    else:
        sina_error = "Sina returned no eligible ETF daily row"

    try:
        fallback_df = get_eastmoney_etf_history(code)
        return build_etf_daily_from_history(
            fallback_df,
            code=code,
            theme=theme,
            symbol=symbol,
            source="Eastmoney 历史 K 线 fallback",
            as_of_date=as_of_date,
        )
    except Exception as exc:
        return {
            "code": code,
            "theme": theme,
            "symbol": symbol,
            "status": "error",
            "message": f"Sina failed: {sina_error}; Eastmoney fallback failed: {exc}",
        }


def get_core_industry_etf_daily(as_of_date):
    results = []

    for code, meta in CORE_INDUSTRY_ETFS.items():
        results.append(get_single_etf_daily(code, meta["theme"], as_of_date))

    return results


def get_sw_l2_industry_daily(as_of_date):
    """抓取申万二级行业指数日报数据（收盘指数、涨跌幅、市盈率、市净率等）。

    若 cutoff_date 为非交易日，自动往前最多回溯 5 天寻找最近交易日数据。
    """
    try:
        # 从分析日本身开始往前回溯，找到最近有数据的交易日
        start_date = pd.Timestamp(as_of_date).normalize().date()

        # 尝试从 start_date 开始往前最多 5 天，找到有数据的最近交易日
        found_df = None
        found_date = None
        for offset in range(6):
            check_date = start_date - timedelta(days=offset)
            date_str = check_date.strftime("%Y%m%d")
            try:
                df = ak.index_analysis_daily_sw(symbol="二级行业", start_date=date_str, end_date=date_str)
                if not df.empty:
                    found_df = df
                    found_date = check_date
                    break
            except Exception:
                continue

        if found_df is None:
            return {
                "status": "empty",
                "requested_date": str(start_date),
                "note": "申万二级行业日报返回空数据，回溯5天仍无可用交易日。",
            }

        industries = []
        for _, row in found_df.iterrows():
            industries.append(
                {
                    "index_code": str(row.get("指数代码", "")),
                    "index_name": str(row.get("指数名称", "")),
                    "date": str(row.get("发布日期", "")),
                    "close_index": safe_float(row.get("收盘指数"), 2),
                    "change_pct": safe_float(row.get("涨跌幅"), 2),
                    "turnover_rate": safe_float(row.get("换手率"), 2),
                    "pe_ttm": safe_float(row.get("市盈率"), 2),
                    "pb": safe_float(row.get("市净率"), 2),
                    "volume_yi_gu": safe_float(row.get("成交量"), 2),
                    "avg_price": safe_float(row.get("均价"), 2),
                    "turnover_pct": safe_float(row.get("成交额占比"), 2),
                    "circulating_market_cap_yi": safe_float(row.get("流通市值"), 2),
                    "avg_circulating_market_cap_yi": safe_float(row.get("平均流通市值"), 2),
                    "dividend_yield_pct": safe_float(row.get("股息率"), 2),
                }
            )

        # 按涨跌幅排序（降序），方便日报使用
        industries_sorted = sorted(
            industries, key=lambda x: x.get("change_pct") or 0, reverse=True
        )

        return {
            "status": "success",
            "source": "申万宏源研究 index_analysis_daily_sw",
            "requested_date": str(start_date),
            "actual_date": str(found_date),
            "count": len(industries_sorted),
            "industries": industries_sorted,
        }
    except Exception as exc:
        return {
            "status": "error",
            "requested_date": str(pd.Timestamp(as_of_date).normalize().date()),
            "message": str(exc),
        }


def build_relevant_etf_daily(as_of_date, core_industry_etf_daily):
    core_by_code = {item["code"]: item for item in core_industry_etf_daily}
    results = []

    for code, meta in HOLDING_RELEVANT_ETFS.items():
        theme = meta.get("theme") or CORE_INDUSTRY_ETFS.get(code, {}).get("theme", "未知主题")
        base = core_by_code.get(code) or get_single_etf_daily(code, theme, as_of_date)
        item = dict(base)
        item["related_funds"] = meta["related_funds"]
        results.append(item)

    return results


def get_fund_nav_batch(holdings):
    results = []
    for item in holdings:
        code = item["code"]
        try:
            df_hist = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if df_hist.empty:
                results.append({"code": code, "name": item["name"], "status": "empty"})
                continue

            cutoff_date = get_prior_day_cutoff(item["as_of_date"])
            df_hist = df_hist.copy()
            df_hist["净值日期"] = pd.to_datetime(df_hist["净值日期"], errors="coerce").dt.date
            eligible = df_hist[df_hist["净值日期"] <= cutoff_date]
            if eligible.empty:
                results.append(
                    {
                        "code": code,
                        "name": item["name"],
                        "status": "date_not_found",
                        "requested_as_of_date": item["as_of_date"],
                        "cutoff_date": str(cutoff_date),
                    }
                )
                continue

            last_nav_row = eligible.iloc[-1]
            results.append(
                {
                    "code": code,
                    "name": item["name"],
                    "status": "success",
                    "requested_as_of_date": item["as_of_date"],
                    "cutoff_date": str(cutoff_date),
                    "official_nav": float(last_nav_row["单位净值"]),
                    "nav_date": str(last_nav_row["净值日期"]),
                }
            )
        except Exception as exc:
            results.append({"code": code, "name": item["name"], "status": "error", "message": str(exc)})
    return results


def build_payload(as_of_date, holdings_file):
    holdings = load_holdings_from_markdown(holdings_file)
    previous_report_context = load_previous_report_context(as_of_date)
    holdings_for_nav = merge_holdings_for_nav(holdings, previous_report_context)
    for item in holdings_for_nav:
        item["as_of_date"] = as_of_date
    core_industry_etf_daily = get_core_industry_etf_daily(as_of_date)
    fund_official_navs = get_fund_nav_batch(holdings_for_nav)
    holding_valuation_snapshot = build_holding_valuation_snapshot(holdings, fund_official_navs)
    holdings_change_vs_previous_report = build_holdings_change_summary(
        current_holdings=holdings,
        previous_context=previous_report_context,
        fund_navs=fund_official_navs,
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of_date": as_of_date,
        "day_level_cutoff_date": str(get_prior_day_cutoff(as_of_date)),
        "holdings_source": str(Path(holdings_file).resolve()),
        "holdings_count": len(holdings),
        "holdings": holdings,
        "previous_report_context": previous_report_context,
        "northbound_daily_raw": get_northbound_daily_raw(as_of_date),
        "northbound_weekly_summary": get_northbound_weekly_summary(as_of_date=as_of_date),
        "core_industry_etf_daily": core_industry_etf_daily,
        "sw_l2_industry_daily": get_sw_l2_industry_daily(as_of_date),
        "relevant_etf_daily": build_relevant_etf_daily(as_of_date, core_industry_etf_daily),
        "fund_official_navs": fund_official_navs,
        "holding_valuation_snapshot": holding_valuation_snapshot,
        "holdings_change_vs_previous_report": holdings_change_vs_previous_report,
    }


def main():
    args = parse_args()
    payload = build_payload(as_of_date=args.date, holdings_file=args.holdings_file)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    analysis_snapshot = build_analysis_snapshot(payload)
    analysis_snapshot_serialized = json.dumps(analysis_snapshot, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
        analysis_snapshot_output_path = infer_analysis_snapshot_output_path(output_path)
        analysis_snapshot_output_path.write_text(analysis_snapshot_serialized + "\n", encoding="utf-8")
        print(f"written: {output_path}")
        print(f"written: {analysis_snapshot_output_path}")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
