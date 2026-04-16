"""
Google Ads API - 拉取广告数据
环境变量:
  GOOGLE_ADS_DEVELOPER_TOKEN  - Google Ads Developer Token
  GOOGLE_ADS_CLIENT_ID        - OAuth Client ID
  GOOGLE_ADS_CLIENT_SECRET    - OAuth Client Secret
  GOOGLE_ADS_REFRESH_TOKEN    - OAuth Refresh Token
  GOOGLE_ADS_CUSTOMER_ID      - Google Ads Customer ID (不含横线)
  GOOGLE_ADS_LOGIN_CUSTOMER_ID - MCC 账户 ID (如适用)
"""
import json, os
from datetime import datetime
from http.server import BaseHTTPRequestHandler


def get_ads_data(config, start_date, end_date):
    from google.ads.googleads.client import GoogleAdsClient

    client = GoogleAdsClient.load_from_dict({
        "developer_token": config["developer_token"],
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": config["refresh_token"],
        "login_customer_id": config.get("login_customer_id", ""),
        "use_proto_plus": True,
    })

    ga_service = client.get_service("GoogleAdsService")
    customer_id = config["customer_id"]

    # 按 campaign + 日期 拉取数据
    query = f"""
        SELECT
            campaign.name,
            campaign.advertising_channel_type,
            segments.date,
            segments.device,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.conversions_value,
            metrics.average_cpc
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            AND campaign.status = 'ENABLED'
        ORDER BY segments.date, campaign.name
    """

    rows = []
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            rows.append({
                "date": row.segments.date,
                "campaign": row.campaign.name,
                "channelType": row.campaign.advertising_channel_type.name,
                "device": row.segments.device.name,
                "spend": round(row.metrics.cost_micros / 1_000_000, 2),
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "conversions": round(row.metrics.conversions, 2),
                "conversionValue": round(row.metrics.conversions_value, 2),
                "avgCpc": round(row.metrics.average_cpc / 1_000_000, 2) if row.metrics.average_cpc else 0,
            })

    # 汇总
    total_spend = sum(r["spend"] for r in rows)
    total_clicks = sum(r["clicks"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)
    total_conversions = sum(r["conversions"] for r in rows)
    total_conv_value = sum(r["conversionValue"] for r in rows)

    return {
        "daily": rows,
        "summary": {
            "totalSpend": round(total_spend, 2),
            "totalClicks": total_clicks,
            "totalImpressions": total_impressions,
            "totalConversions": round(total_conversions, 2),
            "totalConversionValue": round(total_conv_value, 2),
            "avgCpc": round(total_spend / total_clicks, 2) if total_clicks else 0,
            "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions else 0,
            "roas": round(total_conv_value / total_spend, 2) if total_spend else 0,
        }
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            config = {
                "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
                "client_id": os.environ.get("GOOGLE_ADS_CLIENT_ID", ""),
                "client_secret": os.environ.get("GOOGLE_ADS_CLIENT_SECRET", ""),
                "refresh_token": os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", ""),
                "customer_id": os.environ.get("GOOGLE_ADS_CUSTOMER_ID", ""),
                "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
            }

            if not config["developer_token"] or not config["customer_id"]:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "missing_config",
                    "message": "请配置 Google Ads API 环境变量"
                }).encode())
                return

            start_date = "2026-04-16"
            end_date = "2026-04-30"

            result = get_ads_data(config, start_date, end_date)
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
