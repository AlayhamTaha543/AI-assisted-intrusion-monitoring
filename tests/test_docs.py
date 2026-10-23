from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_decisions_documents_key_choices():
    decisions = (ROOT / 'docs' / 'DECISIONS.md').read_text()
    assert 'tool_name' in decisions
    assert 'ignore_conflicts' in decisions
    assert 'llm_unavailable' in decisions
    assert 'queue_unavailable' in decisions
    assert '## Step 0 results' in decisions


def test_readme_documents_limitations():
    readme = (ROOT / 'README.md').read_text()
    assert 'Limitations' in readme
