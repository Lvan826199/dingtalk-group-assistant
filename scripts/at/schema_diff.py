"""对照合同（OpenAPI 3.1 子集）的 JSON Schema 和真实返回，列出全部差异（不只第一处）。

差异类型：
  type      类型不符（合同 integer，实际 string 等）
  missing   合同 required 里有、实际没返回
  extra     实际返回了、合同 properties 里没写
  null      实际为 null，合同类型不允许 null
"""


def _types(schema):
    t = schema.get("type")
    if t is None:
        return None
    return set(t) if isinstance(t, list) else {t}


def _actual_type(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def diff(schema, value, path="$", out=None, max_items=500):
    """返回 [(path, kind, detail)]。数组最多检查前 max_items 个元素（11-10 从 3 改成 500：只比前 3 条漏掉了列表深处的 null / 缺字段，平台 jsonschema 是全量比）。collapse() 会把下标合并。"""
    if out is None:
        out = []
    if not isinstance(schema, dict):
        return out
    want = _types(schema)
    got = _actual_type(value)
    if want is not None:
        ok = got in want or (got == "integer" and "number" in want)
        if not ok:
            out.append((path, "null" if got == "null" else "type", f"合同 {'/'.join(sorted(want))}，实际 {got}"))
            return out
    if got == "object":
        props = schema.get("properties") or {}
        for k in schema.get("required") or []:
            if k not in value:
                out.append((f"{path}.{k}", "missing", "合同必有，实际没返回"))
        if props:
            for k in value:
                if k not in props:
                    out.append((f"{path}.{k}", "extra", f"合同没写，实际 {_actual_type(value[k])}"))
        for k, sub in props.items():
            if k in value:
                diff(sub, value[k], f"{path}.{k}", out, max_items)
    elif got == "array" and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value[:max_items]):
            diff(schema["items"], item, f"{path}[{i}]", out, max_items)
    return out


def collapse(items):
    """把 $.data.datas[0].x / [1].x / [2].x 合并成 $.data.datas[*].x，去重。"""
    import re
    seen, res = set(), []
    for p, k, d in items:
        key = (re.sub(r"\[\d+\]", "[*]", p), k, d)
        if key not in seen:
            seen.add(key)
            res.append(key)
    return res
