"""
Meta (Facebook) Ads API - 拉取 Meta 广告数据
环境变量:
  META_APP_ID          - Meta App ID
  META_APP_SECRET      - Meta App Secret
  META_ACCESS_TOKEN    - 长期 Access Token
  META_AD_ACCOUNT_ID   - 广告账户 ID (格式: act_123456)
"""
import json, os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import requests


def get_meta_ads_data(access_token, ad_account_id, start_date, end_date):
    base_url = f"https://graph.facebook.com/v19.0/{ad_account_id}/insights"

    params = {
        "access_token": access_token,
        "time_range": json.dumps({"since": start_date, "until": end_date}),
        "time_increment": 1,  # 按天
        "level": "campaign",
        "fields": ",".join([
            "campaign_name", "date_start",
            "spend", "impressions", "clicks", "cpc", "ctr",
            "actions", "cost_per_action_type",
        ]),
        "limit": 500,
    }

    resp = requests.get(base_url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    rows = []
    for item in data:
        # 提取 lead / email signup 动作
        leads = 0
        if "actions" in item:
            for action in item["actions"]:
                if action["action_type"] in ["lead", "offsite_conversion.fb_pixel_lead",
                                              "onsite_conversion.lead_grouped"]:
                    leads += int(action.get("value", 0))

        cpl = 0
        if "cost_per_action_type" in item:
            for cpa in item["cost_per_action_type"]:
                if cpa["action_type"] in ["lead", "offsite_conversion.fb_pixel_lead"]:
                    cpl = float(cpa.get("value", 0))

        rows.append({
            "date": item.get("date_start", ""),
            "campaign": item.get("campaign_name", ""),
            "spend": round(float(item.get("spend", 0)), 2),
            "impressions": int(item.get("impressions", 0)),
            "clicks": int(item.get("clicks", 0)),
            "cpc": round(float(item.get("cpc", 0)), 2),
            "ctr": round(float(item.get("ctr", 0)), 2),
            "emailSignups": leads,
            "cpl": round(cpl, 2),
        })

    total_spend = sum(r["spend"] for r in rows)
    total_clicks = sum(r["clicks"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)
    total_signups = sum(r["emailSignups"] for r in rows)

    return {
        "daily": rows,
        "summary": {
            "totalSpend": round(total_spend, 2),
            "totalClicks": total_clicks,
            "totalImpressions": total_impressions,
            "totalEmailSignups": total_signups,
            "avgCpc": round(total_spend / total_clicks, 2) if total_clicks else 0,
            "avgCtr": round(total_clicks / total_impressions * 100, 2) if total_impressions else 0,
            "avgCpl": round(total_spend / total_signups, 2) if total_signups else 0,
        }
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            access_token = os.environ.get("META_ACCESS_TOKEN", "")
            ad_account_id = os.environ.get("META_AD_ACCOUNT_ID", "")

            if not access_token or not ad_account_id:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "missing_config",
                    "message": "请配置 META_ACCESS_TOKEN 和 META_AD_ACCOUNT_ID 环境变量"
                }).encode())
                return

            start_date = "2026-04-16"
            end_date = "2026-04-30"

            result = get_meta_ads_data(access_token, ad_account_id, start_date, end_date)
            result["status"] = "ok"
            result["updatedAt"] = datetime.utcnow().isoformat() + "Z"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=60")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
