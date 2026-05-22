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
    "512480": {"theme": "半导体"},
    "516160": {"theme": "新能源"},
    "515790": {"theme": "光伏"},
    "512170": {"theme": "医药"},
    "159928": {"theme": "消费"},
    "510230": {"theme": "金融"},
    "512660": {"theme": "军工"},
    "159995": {"theme": "芯片"},
    "515070": {"theme": "人工智能"},
    "512880": {"theme": "证券"},
    "512800": {"theme": "银行"},
    "512690": {"theme": "白酒"},
}

HOLDING_RELEVANT_ETFS = {
    "516160": {
        "related_funds": ["嘉实新能源新材料股票A(003984)"],
    },
    "510300": {
        "related_funds": ["中欧沪深300指数量化增强C(021758)"],
    },
    "510500": {
        "related_funds": ["长城中证500指数增强C(007413)"],
    },
    "588000": {
        "related_funds": [
            "易方达上证科创50联接C(011609)",
            "财通新视野灵活配置混合A(005851)",
            "华商新趋势优选灵活配置混合(166301)",
        ],
    },
    "511010": {
        "related_funds": [
            "嘉实稳固收益债券D(024212)",
            "中欧鼎利债券C(009520)",
        ],
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
    pattern = re.compile(
        r'\{\s*full:\s*"(?P<full>[^"]+)"\s*,\s*name:\s*"(?P<name>[^"]+)"\s*,\s*code:\s*"(?P<code>\d+)"\s*,\s*nav:\s*"(?P<nav>[^"]+)"\s*,\s*amount:\s*"(?P<amount>[^"]+)"\s*,\s*weight:\s*"(?P<weight>[^"]+)"\s*\}'
    )
    results = []

    for match in pattern.finditer(text):
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


def get_northbound_daily_raw(date_str):
    """保留东方财富原始字段，同时写出联网交叉验证后的单位换算。"""
    try:
        response = requests.get(
            EASTMONEY_MUTUAL_HISTORY_URL,
            params={
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
                "pageSize": "500",
                "pageNumber": "1",
                "reportName": "RPT_MUTUAL_DEAL_HISTORY",
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "filter": f"(TRADE_DATE='{date_str}')",
            },
            timeout=20,
        )
        response.raise_for_status()
        rows = (((response.json() or {}).get("result") or {}).get("data") or [])
        row = next((item for item in rows if str(item.get("MUTUAL_TYPE")) == "005"), None)
        if row is None:
            return {"status": "not_found", "date": date_str}
        deal_amt_raw = row.get("DEAL_AMT")
        net_deal_amt_raw = row.get("NET_DEAL_AMT")
        buy_amt_raw = row.get("BUY_AMT")
        sell_amt_raw = row.get("SELL_AMT")
        return {
            "status": "raw_record_available",
            "date": date_str,
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
        return {"status": "error", "date": date_str, "message": str(exc)}


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
        target_date = pd.Timestamp(as_of_date).normalize()
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


def get_single_etf_daily(code, theme, as_of_date):
    target_date = pd.Timestamp(as_of_date).date()
    symbol = infer_sina_symbol(code)

    try:
        df = get_sina_etf_history(symbol)
        if df.empty:
            return {
                "code": code,
                "theme": theme,
                "symbol": symbol,
                "status": "empty",
            }

        row_index = df.index[df["date"] == target_date]
        if len(row_index) == 0:
            return {
                "code": code,
                "theme": theme,
                "symbol": symbol,
                "status": "date_not_found",
            }

        idx = int(row_index[0])
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
            "volume": int(row["volume"]),
            "amount": int(row["amount"]),
            "source": "Sina 历史 K 线（requests verify=False + hk_js_decode）",
        }
    except Exception as exc:
        return {
            "code": code,
            "theme": theme,
            "symbol": symbol,
            "status": "error",
            "message": str(exc),
        }


def get_core_industry_etf_daily(as_of_date):
    results = []

    for code, meta in CORE_INDUSTRY_ETFS.items():
        results.append(get_single_etf_daily(code, meta["theme"], as_of_date))

    return results


def build_relevant_etf_daily(as_of_date, core_industry_etf_daily):
    core_by_code = {item["code"]: item for item in core_industry_etf_daily}
    results = []

    for code, meta in HOLDING_RELEVANT_ETFS.items():
        theme = CORE_INDUSTRY_ETFS.get(code, {}).get("theme", "未知主题")
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

            last_nav_row = df_hist.iloc[-1]
            results.append(
                {
                    "code": code,
                    "name": item["name"],
                    "status": "success",
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
        "holdings_source": str(Path(holdings_file).resolve()),
        "holdings_count": len(holdings),
        "holdings": holdings,
        "previous_report_context": previous_report_context,
        "northbound_daily_raw": get_northbound_daily_raw(as_of_date),
        "northbound_weekly_summary": get_northbound_weekly_summary(as_of_date=as_of_date),
        "core_industry_etf_daily": core_industry_etf_daily,
        "relevant_etf_daily": build_relevant_etf_daily(as_of_date, core_industry_etf_daily),
        "fund_official_navs": fund_official_navs,
        "holding_valuation_snapshot": holding_valuation_snapshot,
        "holdings_change_vs_previous_report": holdings_change_vs_previous_report,
    }


def main():
    args = parse_args()
    payload = build_payload(as_of_date=args.date, holdings_file=args.holdings_file)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
        print(f"written: {output_path}")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
