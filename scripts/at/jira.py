"""接口自动化缺陷提 Jira（半自动）：草稿 → 用户确认 → 提交。我们的 Jira 是 6.3.6，只有 REST v2 + 用户名密码（Basic）。

凭据：~/.config/jira/account.json {"user": ..., "password": ...}（用户本人写入，600 权限，不进仓库、不发群）。
草稿：qa-notes/jira-drafts/*.json，字段 summary / description / component / priority / assignee / round。

用法（check/show/submit/find/transition/comment）：
  python3 -I jira.py check                 # 登录核对 + 列出 LIKOLIKO 的问题类型、模块、优先级
  python3 -I jira.py show <草稿.json>      # 只打印将要提交的内容，不提交
  python3 -I jira.py submit <草稿.json>    # 提交；成功后把 issue key 写回草稿
"""
import base64
import gzip
import json
import os
import http.client
import ipaddress
import socket
import ssl
import time
import sys
import tempfile
import shutil
import subprocess
import urllib.error
import urllib.request

BASE = "http://jira.example.com:18082"
PROJECT = "LIKOLIKO"
ISSUE_TYPE = "缺陷"
ASSIGNEE = {"java": "研发B", "go": "kingzhang"}  # Jira 显示名。用户名：研发B = w.guo，研发C = j.zhang（显示名 kingzhang）
COMPONENT_SERVER = "后端任务"  # 接口缺陷默认模块
# Jira 6.3.6 按中文名建单会报「无效的优先级」（显示名是翻译，内部名是英文），一律传 id（11-10 从 createmeta 取）
PRIORITY_ID = {"紧急": "1", "严重": "2", "重要": "3", "次要": "4", "微小": "5"}
COMPONENT_ID = {"app-2026-027": "11902", "前端任务Android": "11800", "前端任务iOS": "11801", "前端任务双端": "11900",
                "后端任务": "11802", "推送": "11901"}


def auth():
    acc = json.load(open(os.path.expanduser("~/.config/jira/account.json")))
    return "Basic " + base64.b64encode(f"{acc['user']}:{acc['password']}".encode()).decode()


_DNS_CACHE = {"until": 0, "addresses": []}
IP_CACHE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../runs/jira_ip.json"))
DOH_ENDPOINTS = ("https://dns.alidns.com/resolve", "https://doh.pub/dns-query",
                 "https://dns.google/resolve", "https://cloudflare-dns.com/dns-query")
CACHE_MAX_AGE = 900  # 动态地址只在15分钟内兜底，不长期固定IP。


def _save_ip_cache(host, addresses, ttl, endpoint):
    directory = os.path.dirname(IP_CACHE)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".jira-ip-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"host": host, "addresses": addresses, "resolved_at": time.time(),
                       "ttl": ttl, "resolver": endpoint}, f, ensure_ascii=False)
        os.replace(tmp, IP_CACHE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _cached_addresses(host):
    try:
        with open(IP_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
        age = time.time() - float(cached["resolved_at"])
        if cached.get("host") != host or not 0 <= age <= CACHE_MAX_AGE:
            return []
        return sorted({str(ipaddress.IPv4Address(x)) for x in cached["addresses"]})
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _fallback_addresses():
    """系统解析失败后优先国内加密DNS；都失败再用短期缓存，不改系统配置。"""
    if _DNS_CACHE["until"] > time.monotonic():
        return _DNS_CACHE["addresses"]
    host = urllib.parse.urlsplit(BASE).hostname
    ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if os.path.exists("/etc/ssl/cert.pem") else ssl.create_default_context()
    for endpoint in DOH_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint + "?" + urllib.parse.urlencode({"name": host, "type": "A"}),
                                         headers={"Accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
                data = json.load(r)
            if data.get("Status") != 0:
                continue
            answers = [x for x in data.get("Answer", []) if x.get("type") == 1 and str(x.get("name", "")).rstrip(".").lower() == host.lower()]
            addresses = sorted({str(ipaddress.IPv4Address(x["data"])) for x in answers})
            if not addresses:
                continue
            ttl = max(0, min([int(x.get("TTL", 0)) for x in answers] + [60]))
            _DNS_CACHE.update(until=time.monotonic() + ttl, addresses=addresses)
            _save_ip_cache(host, addresses, ttl, endpoint)
            return addresses
        except (OSError, ValueError, KeyError, TypeError):
            continue
    addresses = _cached_addresses(host)
    if addresses:
        return addresses
    raise OSError("Jira备用域名解析失败，且没有15分钟内的可用地址缓存")


def open_url(req, timeout=30):
    """仅系统域名解析失败才重试；HTTP/超时/写入结果未知时不自动重试。"""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as ex:
        if not isinstance(ex.reason, socket.gaierror):
            raise
        target = urllib.parse.urlsplit(req.full_url if isinstance(req, urllib.request.Request) else req)
        original = urllib.parse.urlsplit(BASE)
        if (target.scheme, target.hostname, target.port) != (original.scheme, original.hostname, original.port):
            raise
        addresses = _fallback_addresses()

        class JiraConnection(http.client.HTTPConnection):
            def connect(self):
                # 原URL/Host/认证目的地保持不变，仅连接到加密DNS解析或短期缓存的A记录。
                self.sock = socket.create_connection((addresses[0], self.port), self.timeout, self.source_address)

        class JiraHandler(urllib.request.HTTPHandler):
            def http_open(self, request):
                return self.do_open(JiraConnection, request)

        return urllib.request.build_opener(JiraHandler()).open(req, timeout=timeout)


def _curl_get(req, timeout=30):
    """只读查询用本机curl：有总时限、压缩响应；认证仅经stdin传递。"""
    target = urllib.parse.urlsplit(req.full_url)
    args = [shutil.which("curl"), "--silent", "--show-error", "--compressed", "--ipv4",
            "--connect-timeout", "8", "--max-time", str(timeout), "--config", "-",
            "--write-out", "\n%{http_code}"]
    try:
        socket.gethostbyname(target.hostname)
    except socket.gaierror:
        ip = _fallback_addresses()[0]
        args += ["--resolve", f"{target.hostname}:{target.port or 80}:{ip}"]
    args.append(req.full_url)
    # curl配置中的引号和反斜线按其语法转义；不写临时认证文件、不放命令行。
    def quote(value):
        return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
    config = "".join('header = "' + quote(k + ": " + v) + '"\n' for k, v in req.header_items())
    for attempt in range(2):
        try:
            result = subprocess.run(args, input=config.encode(), capture_output=True, timeout=timeout + 5)
        except subprocess.TimeoutExpired as ex:
            if attempt == 0:
                continue
            raise TimeoutError("Jira只读查询超过总时限") from ex
        if result.returncode == 0:
            break
        if attempt == 0 and result.returncode in (5, 6, 7, 18, 28, 52, 56):
            continue  # 只读GET最多重试一次，写入绝不经过此路径。
        raise OSError(f"Jira只读查询失败，curl退出码{result.returncode}；未进行写入")
    payload, status = result.stdout.rsplit(b"\n", 1)
    if int(status) >= 400:
        raise SystemExit(f"GET {target.path} → HTTP {status.decode()}: {payload.decode(errors='replace')[:800]}")
    return json.loads(payload) if payload else {}


def call(method, path, data=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": auth(), "Content-Type": "application/json", "Accept-Encoding": "gzip"})
    if method.upper() == "GET" and shutil.which("curl"):
        return _curl_get(req)
    try:
        with open_url(req, timeout=30) as r:
            payload = r.read()
            if r.headers.get("Content-Encoding", "").lower() == "gzip":
                payload = gzip.decompress(payload)
            body = payload.decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → HTTP {e.code}: {e.read().decode(errors='replace')[:800]}")


def meta():
    m = call("GET", f"/rest/api/2/issue/createmeta?projectKeys={PROJECT}&expand=projects.issuetypes.fields")
    proj = (m.get("projects") or [None])[0]
    if not proj:
        raise SystemExit(f"看不到项目 {PROJECT}（账号没有建单权限？）")
    return proj


def check():
    me = call("GET", "/rest/api/2/myself")
    print("登录成功：", me.get("displayName"), f"({me.get('name')})")
    proj = meta()
    for it in proj["issuetypes"]:
        req = [f.get("name") for f in it["fields"].values() if f.get("required")]
        print(f"问题类型 {it['name']}（id {it['id']}）必填：{req}")
    comps = call("GET", f"/rest/api/2/project/{PROJECT}/components")
    print("模块：", [c["name"] for c in comps])
    print("优先级：", [p["name"] for p in call("GET", "/rest/api/2/priority")])
    for k, name in ASSIGNEE.items():
        users = call("GET", f"/rest/api/2/user/assignable/search?project={PROJECT}&username={urllib.request.quote(name)}")
        print(f"{k} 默认指派 {name} →", [(u['name'], u['displayName']) for u in users][:3])


def build(d):
    fields = {"project": {"key": PROJECT}, "issuetype": {"name": ISSUE_TYPE},
              "summary": d["summary"], "description": d["description"],
              "components": [{"id": COMPONENT_ID[d["component"]]}], "priority": {"id": PRIORITY_ID[d["priority"]]}}
    if d.get("assignee"):
        fields["assignee"] = {"name": d["assignee"]}
    return {"fields": fields}


def find_existing(summary):
    """按标题找同一问题的已有单（任何状态）。用户 11-11 定：同样的问题再出现要重新打开旧单，不写新单。"""
    jql = f'project = {PROJECT} AND summary ~ "\\"{summary}\\"" ORDER BY created DESC'
    res = call("GET", "/rest/api/2/search?jql=" + urllib.request.quote(jql) + "&fields=summary,status,resolution&maxResults=5")
    return [(i["key"], i["fields"]["summary"], i["fields"]["status"]["name"]) for i in res.get("issues", [])
            if i["fields"]["summary"].strip() == summary.strip()]


def transition(key, to_name, comment=None):
    """把单子流转到目标状态（按 transitions 里 to.name 匹配，如 关闭 / 完成 / 进行中 / 重新打开）。"""
    ts = call("GET", f"/rest/api/2/issue/{key}/transitions")["transitions"]
    hit = [t for t in ts if t["to"]["name"] == to_name or t["name"] == to_name]
    if not hit:
        raise SystemExit(f"{key} 没有到「{to_name}」的流转，可选：{[(t['name'], t['to']['name']) for t in ts]}")
    body = {"transition": {"id": hit[0]["id"]}}
    if comment:
        body["update"] = {"comment": [{"add": {"body": comment}}]}
    call("POST", f"/rest/api/2/issue/{key}/transitions", body)
    st = call("GET", f"/rest/api/2/issue/{key}?fields=status")["fields"]["status"]["name"]
    print(f"{key} → {st}")
    return st


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "show", "submit", "find", "transition", "comment"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "check":
        return check()
    if sys.argv[1] == "find":      # jira.py find "<标题>"
        return print(find_existing(sys.argv[2]))
    if sys.argv[1] == "transition":  # jira.py transition BUG-766 关闭 ["评论"]
        return transition(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    if sys.argv[1] == "comment":   # jira.py comment BUG-766 "评论"
        call("POST", f"/rest/api/2/issue/{sys.argv[2]}/comment", {"body": sys.argv[3]})
        return print("已评论", sys.argv[2])
    path = sys.argv[2]
    d = json.load(open(path, encoding="utf-8"))
    payload = build(d)
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    if sys.argv[1] == "show":
        return
    if d.get("key"):
        raise SystemExit(f"草稿已提交过：{d['key']}，不重复提交")
    dup = find_existing(d["summary"])
    if dup:
        raise SystemExit(f"已有同标题的单 {dup}：同样的问题要用 `jira.py transition <key> 重新打开 \"评论\"` 重开旧单，不新建")
    res = call("POST", "/rest/api/2/issue", payload)
    d["key"] = res["key"]
    d["url"] = f"{BASE}/browse/{res['key']}"
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已提交：", d["url"])


if __name__ == "__main__":
    main()
