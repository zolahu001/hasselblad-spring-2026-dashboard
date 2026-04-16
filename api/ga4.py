"""
GA4 Data API - 拉取网站流量数据
环境变量:
  GA4_PROPERTY_ID        - GA4 属性 ID (例: 123456789)
  GA4_SERVICE_ACCOUNT    - Service Account JSON 密钥 (整个JSON字符串)
"""
import json, os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler

def get_ga4_data(property_id, credentials_json, start_date, end_date, region=None):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, FilterExpression,
        Filter, OrderBy
    )
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=creds)

    dimensions = [Dimension(name="date")]
    dim_filter = None

    # 如果指定区域,按国家过滤
    if region:
        country_codes = {
            "NA": ["US", "CA"],
            "EU": ["DE", "FR", "GB", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "DK", "NO", "FI", "IE", "PT"]
        }
        codes = country_codes.get(region, [])
        if codes:
            dim_filter = FilterExpression(
                filter=Filter(
                    field_name="country",
                    in_list_filter=Filter.InListFilter(values=codes)
                )
            )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=dimensions,
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="screenPageViews"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="screenPageViewsPerSession"),
        ],
        dimension_filter=dim_filter,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    response = client.run_report(request)

    rows = []
    for row in response.rows:
        rows.append({
            "date": row.dimension_values[0].value,
            "sessions": int(row.metric_values[0].value),
            "users": int(row.metric_values[1].value),
            "newUsers": int(row.metric_values[2].value),
            "pageViews": int(row.metric_values[3].value),
            "bounceRate": round(float(row.metric_values[4].value) * 100, 2),
            "avgSessionDuration": round(float(row.metric_values[5].value), 1),
            "pagesPerSession": round(float(row.metric_values[6].value), 2),
        })
    return rows


def get_landing_page_data(property_id, credentials_json, start_date, end_date):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, FilterExpression,
        Filter, OrderBy
    )
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=creds)

    target_pages = ["/featured", "/products/x2d-ii-100c", "/products/xcd-35-100e",
                    "/products/907x-cfv-100c", "/"]

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="averageSessionDuration"),
        ],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="pagePath",
                in_list_filter=Filter.InListFilter(values=target_pages)
            )
        ),
    )
    response = client.run_report(request)

    pages = []
    for row in response.rows:
        pages.append({
            "page": row.dimension_values[0].value,
            "pageViews": int(row.metric_values[0].value),
            "avgTime": round(float(row.metric_values[1].value), 1),
        })
    return pages


def get_source_medium_data(property_id, credentials_json, start_date, end_date):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, OrderBy
    )
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=creds)

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="sessionSourceMedium")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="newUsers"),
            Metric(name="conversions"),
        ],
        order_bys=[OrderBy(
            metric=OrderBy.MetricOrderBy(metric_name="sessions"),
            desc=True
        )],
        limit=10,
    )
    response = client.run_report(request)

    sources = []
    for row in response.rows:
        sessions = int(row.metric_values[0].value)
        sources.append({
            "sourceMedium": row.dimension_values[0].value,
            "sessions": sessions,
            "newUsers": int(row.metric_values[1].value),
            "conversions": int(row.metric_values[2].value),
        })
    return sources


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            property_id = os.environ.get("GA4_PROPERTY_ID", "")
            credentials = os.environ.get("GA4_SERVICE_ACCOUNT", "")

            if not property_id or not credentials:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "missing_config",
                    "message": "请配置 GA4_PROPERTY_ID 和 GA4_SERVICE_ACCOUNT 环境变量"
                }).encode())
                return

            # 活动日期范围
            start_date = "2026-04-16"
            end_date = "2026-04-30"

            # 拉取各区域每日数据
            na_daily = get_ga4_data(property_id, credentials, start_date, end_date, "NA")
            eu_daily = get_ga4_data(property_id, credentials, start_date, end_date, "EU")

            # 拉取流量来源
            sources = get_source_medium_data(property_id, credentials, start_date, end_date)

            # 拉取关键页面
            pages = get_landing_page_data(property_id, credentials, start_date, end_date)

            result = {
                "status": "ok",
                "dateRange": {"start": start_date, "end": end_date},
                "daily": {"NA": na_daily, "EU": eu_daily},
                "sources": sources,
                "pages": pages,
                "updatedAt": datetime.utcnow().isoformat() + "Z"
            }

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
