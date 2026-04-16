"""
Shopify Admin API - 拉取销售转化数据
环境变量:
  SHOPIFY_STORE_NA       - 北美店铺域名 (例: store-na.myshopify.com)
  SHOPIFY_TOKEN_NA       - 北美店铺 Admin API Access Token
  SHOPIFY_STORE_EU       - 欧洲店铺域名 (例: store-eu.myshopify.com)
  SHOPIFY_TOKEN_EU       - 欧洲店铺 Admin API Access Token
"""
import json, os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import requests


# 活动相关产品 SKU / handle 映射
PRODUCT_MAP = {
    "x2d-ii-100c": "X2D II 100C",
    "xcd-2-8-4-35-100e": "XCD 35-100E",
    "xcd-35-100e": "XCD 35-100E",
    "907x-cfv-100c": "907X & CFV 100C",
}

LENS_HANDLES = ["xcd-55v", "xcd-28p", "xcd-38v", "xcd-90v", "xcd-25v", "xcd-20-35e"]


def fetch_shopify_orders(store_domain, access_token, start_date, end_date):
    """拉取指定日期范围内的订单"""
    url = f"https://{store_domain}/admin/api/2024-01/orders.json"
    headers = {"X-Shopify-Access-Token": access_token}

    all_orders = []
    params = {
        "created_at_min": f"{start_date}T00:00:00Z",
        "created_at_max": f"{end_date}T23:59:59Z",
        "status": "any",
        "limit": 250,
        "fields": "id,created_at,total_price,currency,line_items,financial_status",
    }

    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        orders = resp.json().get("orders", [])
        all_orders.extend(orders)

        # 分页
        link = resp.headers.get("Link", "")
        if 'rel="next"' in link:
            next_url = link.split(";")[0].strip("<>")
            url = next_url
            params = {}
        else:
            break

    return all_orders


def process_orders(orders):
    """处理订单数据,按日期和产品分类"""
    daily = {}
    product_summary = {}

    for order in orders:
        if order.get("financial_status") == "voided":
            continue

        date = order["created_at"][:10]
        total = float(order.get("total_price", 0))
        currency = order.get("currency", "USD")

        if date not in daily:
            daily[date] = {"orders": 0, "revenue": 0, "units": 0, "x2d_sold": 0, "100e_sold": 0}

        daily[date]["orders"] += 1
        daily[date]["revenue"] += total

        for item in order.get("line_items", []):
            qty = item.get("quantity", 1)
            handle = item.get("product_id", "")
            title = item.get("title", "").lower()
            line_price = float(item.get("price", 0)) * qty

            daily[date]["units"] += qty

            # 识别产品类型
            product_type = "其他"
            if "x2d" in title and "100c" in title:
                product_type = "X2D II 100C"
                daily[date]["x2d_sold"] += qty
            elif "35-100" in title or "35100" in title:
                product_type = "XCD 35-100E"
                daily[date]["100e_sold"] += qty
            elif "907" in title:
                product_type = "907X & CFV 100C"
            elif any(lens in title for lens in ["55v", "28p", "38v", "90v", "25v", "20-35"]):
                product_type = "镜头"
            elif "xcd" in title:
                product_type = "镜头"

            if product_type not in product_summary:
                product_summary[product_type] = {"units": 0, "revenue": 0, "orders": 0}
            product_summary[product_type]["units"] += qty
            product_summary[product_type]["revenue"] += line_price
            product_summary[product_type]["orders"] += 1

    # 转为列表并排序
    daily_list = [{"date": k, **v} for k, v in sorted(daily.items())]

    total_orders = sum(d["orders"] for d in daily_list)
    total_revenue = sum(d["revenue"] for d in daily_list)
    total_units = sum(d["units"] for d in daily_list)

    return {
        "daily": daily_list,
        "byProduct": product_summary,
        "summary": {
            "totalOrders": total_orders,
            "totalRevenue": round(total_revenue, 2),
            "totalUnits": total_units,
            "aov": round(total_revenue / total_orders, 2) if total_orders else 0,
            "totalX2dSold": sum(d["x2d_sold"] for d in daily_list),
            "total100eSold": sum(d["100e_sold"] for d in daily_list),
        }
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            stores = {}
            na_store = os.environ.get("SHOPIFY_STORE_NA", "")
            na_token = os.environ.get("SHOPIFY_TOKEN_NA", "")
            eu_store = os.environ.get("SHOPIFY_STORE_EU", "")
            eu_token = os.environ.get("SHOPIFY_TOKEN_EU", "")

            if not (na_store and na_token) and not (eu_store and eu_token):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "missing_config",
                    "message": "请配置 SHOPIFY_STORE_NA/EU 和 SHOPIFY_TOKEN_NA/EU 环境变量"
                }).encode())
                return

            start_date = "2026-04-16"
            end_date = "2026-04-30"
            result = {"status": "ok", "regions": {}}

            if na_store and na_token:
                na_orders = fetch_shopify_orders(na_store, na_token, start_date, end_date)
                result["regions"]["NA"] = process_orders(na_orders)

            if eu_store and eu_token:
                eu_orders = fetch_shopify_orders(eu_store, eu_token, start_date, end_date)
                result["regions"]["EU"] = process_orders(eu_orders)

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
