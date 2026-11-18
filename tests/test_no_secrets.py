"""仓库里不能出现真实凭据：钉钉机器人 access_token / 加签 secret、GitHub 令牌、私钥。每次提交 CI 都跑。"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = {"钉钉机器人 access_token": r"access_token=[0-9a-f]{40,}", "钉钉加签 secret": r"\bSEC[0-9a-f]{40,}\b",
            "GitHub 令牌": r"\bgh[pousr]_[A-Za-z0-9]{30,}", "私钥": r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"}


def test_no_real_credentials():
    hits = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".pytest_cache")]
        for n in files:
            if n.endswith((".js", ".jpg", ".png", ".gif")):
                continue
            p = os.path.join(root, n)
            try:
                s = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            hits += [f"{os.path.relpath(p, ROOT)}：{k}" for k, pat in PATTERNS.items() if re.search(pat, s)]
    assert not hits, "\n".join(hits)
