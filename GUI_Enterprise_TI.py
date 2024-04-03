import argparse
import requests
import json
import pandas as pd
import os
import sqlite3
from prettytable import PrettyTable
import dns.resolver
from geopy.geocoders import Nominatim

# 定义常量列表，包含常见的CDN服务商名称
COMMON_CDN_NAMES = ["cloudflare", "akamai", "fastly", "maxcdn", "cloudfront", "azure cdn", "google cloud cdn", "stackpath", "limelight", "incapsula"]  # 根据需要添加更多CDN服务商名称

class QuakeQuery:
    def __init__(self, api_key):
        self.api_key = api_key
        self.conn = None
        self.geolocator = Nominatim(user_agent="GUI_Enterprise_TI")

    def check_cdn_usage(self, hostname):
        ipv4_addresses = []
        resolver = dns.resolver.Resolver()
        answers = resolver.resolve(hostname, 'A')

        for answer in answers:
            ipv4_addresses.append(answer.address)

        return len(ipv4_addresses) >= 2

    def connect_to_database(self, db_name="quake_results.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS quake_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL
            )
        """)
        self.conn.commit()

    def store_to_database(self, results):
        insert_query = """
            INSERT INTO quake_results (hostname, ip, port) VALUES (?, ?, ?)
        """
        rows_to_insert = [(item["service"]["http"]["host"], item["ip"], item["port"]) for item in results]

        self.cursor.executemany(insert_query, rows_to_insert)
        self.conn.commit()

    def perform_search(self, query, result_count, start_page):
        headers = {"X-QuakeToken": self.api_key}
        payload = {
            "query": query,
            "start": start_page,
            "size": str(result_count),
        }

        try:
            response = requests.post(
                url="https://quake.360.cn/api/v3/search/quake_service",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return json.loads(response.text)
        except requests.RequestException as e:
            print(f"API请求过程中发生错误: {e}")
            raise

    def identify_cdn_provider(self, hostname):
            url = f"http://{hostname}"
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()

                server_header = response.headers.get("Server", "").lower()
                for cdn_name in COMMON_CDN_NAMES:
                    if cdn_name.lower() in server_header:
                        return cdn_name

            except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
                pass
            return None

    def display_results(self, api_response, start_page, result_count, query_term):
            print("\n")
            print(f"页码：第{api_response['meta']['pagination']['page_index']}页 共"
                f"{api_response['meta']['pagination']['page_size']}页 总数量："
                f"{api_response['meta']['pagination']['total']}个")
            print(f"查询内容：{query_term}")

            table = PrettyTable(["序号", "地址", "IP",  "端口","IP位置", "CDN服务商"])

            for index, item in enumerate(api_response["data"], start=1):
                if "http" in item["service"]:
                    hostname = item["service"]["http"]["host"]

                    if self.check_cdn_usage(hostname):
                        cdn_provider = self.identify_cdn_provider(hostname)
                    else:
                        cdn_provider = "未知"

                    ip_address = item["ip"]
                    location = self.get_ip_location(ip_address)  # 获取IP位置信息

                    table.add_row([
                        index,
                        hostname,
                        ip_address,
                        item["port"],
                        location or "未知",
                        cdn_provider,
                    ])
                else:
                    print(f"警告：第{index}条结果的'service'结构中缺少'http'子项，跳过该条记录。")

            print(table)

    def get_ip_location(self, ip_address):
        print("查询中...", end="\r")
        location = self._get_ip_location_with_ip_api(ip_address)
        if location is None:
            location = self._get_ip_location_with_geopy(ip_address)
        print(" " * 20, end="\r")  # 清除“查询中...”并回车
        return location

    def _get_ip_location_with_geopy(self, ip_address):
        try:
            location = self.geolocator.reverse(ip_address, language="zh-CN")
            return location.address
        except Exception as e:
            print(f"使用geopy获取IP {ip_address} 位置信息时发生错误: {e}")
            return None

    def _get_ip_location_with_ip_api(self, ip_address):
        try:
            response = requests.get(f"http://ip-api.com/json/{ip_address}?lang=zh-CN")
            response.raise_for_status()
            data = response.json()
            if data["status"] == "success":
                return data["city"]
        except Exception as e:
            print(f"使用ip-api.com获取IP {ip_address} 位置信息时发生错误: {e}")
        return None

    def identify_cdn_provider(self, hostname):
        url = f"http://{hostname}"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            server_header = response.headers.get("Server", "").lower()

            for cdn_name in COMMON_CDN_NAMES:
                if cdn_name.lower() in server_header:
                    return cdn_name

        except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
            pass

        return None

    def parse_command_line_arguments(self):
        parser = argparse.ArgumentParser(
            description="例如：python GUI_Enterprise_TI.py --search domain:xx.com\t ",
            prog="GUI_Enterprise_TI.py",
        )

        group = parser.add_mutually_exclusive_group()
        group.add_argument("--version", "-V", action="version",
                           version=f"| %(prog)s Ver1.2|")

        parser.add_argument("--search", "-S", help="搜索关键词", type=str)
        parser.add_argument("--size", help="显示结果数量（默认为100）", default=100)
        parser.add_argument("--page", help="显示结果页码（默认为1）", default=1)

        return parser.parse_args()
    def check_domain_for_cdn(self, domain):
        ipv4_addresses = []
        resolver = dns.resolver.Resolver()
        answers = resolver.resolve(domain, 'A')

        for answer in answers:
            ipv4_addresses.append(answer.address)

        return len(ipv4_addresses) > 1
    def main(self):
        args = self.parse_command_line_arguments()

        if args.search:
            search_results = self.perform_search(args.search, args.size, args.page)
            self.display_results(search_results, args.page, args.size, args.search)
            self.connect_to_database()
            self.store_to_database(search_results["data"])
            self.export_to_excel(search_results, args.search)
            print(f"结果已成功导出至当前目录下的quake_results_{args.search.replace(' ', '_').replace(':', '').replace('"', '')}.xlsx文件。")
        else:
            print("\nUsage: GUI_Enterprise_TI.py -h, --help 查看帮助信息并退出")

    def export_to_excel(self, api_response, query_term):
        data = [
            (
                index + 1,
                item["service"]["http"]["host"],
                item["ip"],
                item["port"],
                self.get_ip_location(item["ip"]),
                self.identify_cdn_provider(item["service"]["http"]["host"])
            )
            for index, item in enumerate(api_response["data"])
        ]

        df = pd.DataFrame(data, columns=["序号", "地址", "IP", "端口", "IP位置", "CDN服务商"])
        current_dir = os.getcwd()
        query_filename = query_term.replace(" ", "_").replace(":", "").replace('"', "")
        file_name = f"quake_results_{query_filename}.xlsx"
        file_path = os.path.join(current_dir, file_name)

        df.to_excel(file_path, index=False, engine="openpyxl")
        print(f"结果已成功导出至当前目录下的{file_name}文件。")

if __name__ == "__main__":
    print(r"""
________                                 ___ ___    _____  ____  ___
\______ \_______   ____ _____    _____  /   |   \  /  _  \ \   \/  /
 |    |  \_  __ \_/ __ \\__  \  /     \/    ~    \/  /_\  \ \     / 
 |    `   \  | \/\  ___/ / __ \|  Y Y  \    Y    /    |    \/     \ 
/_______  /__|    \___  >____  /__|_|  /\___|_  /\____|__  /___/\  \
        \/            \/     \/      \/       \/         \/      \_/
GUI_Enterprise_TI Ver1.2
Copyright © dreamhax
All rights reserved.
""")

    quake_query = QuakeQuery("")    #API Key
    quake_query.main()