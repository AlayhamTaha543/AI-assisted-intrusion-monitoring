from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_make_users_and_demo_use_compose():
    makefile = (ROOT / 'Makefile').read_text()
    users_block = makefile.split('users:')[1].split('\n\n')[0]
    demo_block = makefile.split('demo:')[1].split('\n\n')[0]
    assert 'docker compose exec' in users_block
    assert 'docker compose exec' in demo_block
    for line in users_block.splitlines()[1:]:
        assert not line.strip().startswith('python')
    for line in demo_block.splitlines()[1:]:
        assert not line.strip().startswith('python')


def test_readme_documents_demo_flow():
    readme = (ROOT / 'README.md').read_text()
    assert 'INGEST_TOKEN=' in readme
    assert 'make users' in readme
