"""发布文档保留字符串里的 Markdown 围栏，不截断程序，也不碰部署路径。"""
import importlib.util
from pathlib import Path


def test_render_preserves_embedded_backticks_and_json_boundary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('docs_builder_test', root / 'build_docs.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    template = tmp_path / 'template.md'
    template.write_text('版本：v1.0\n### agent\n```python\nold = True\n```\n### roles\n```json\n{\n}```\n### after\n保留\n', encoding='utf-8')
    source = {'agent.py': 'value = "```markdown\\n内容\\n```"', 'roles.json': '{}'}
    target = tmp_path / 'result.md'
    builder.render_doc(template, target, source, 'v3.1.2', {'agent.py': '### agent', 'roles.json': '### roles'})
    text = target.read_text(encoding='utf-8')
    assert source['agent.py'] + '\n```' in text
    assert '```json\n{}\n```' in text
    assert '### after\n保留' in text and '版本：v3.1.2' in text
    assert template.read_text(encoding='utf-8').startswith('版本：v1.0')
