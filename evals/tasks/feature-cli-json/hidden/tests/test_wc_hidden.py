import json

from wc import main


def test_json(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("hola mundo\nadios\n")
    assert main(["--json", str(f)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"lines": 2, "words": 3, "chars": 17, "path": str(f)}


def test_plain_unchanged(tmp_path, capsys):
    f = tmp_path / "b.txt"
    f.write_text("uno\n")
    main([str(f)])
    assert capsys.readouterr().out.strip() == f"1 1 4 {f}"
