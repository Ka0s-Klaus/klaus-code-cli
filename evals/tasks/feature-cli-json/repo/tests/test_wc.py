from wc import main


def test_plain(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("hola mundo\nadios\n")
    assert main([str(f)]) == 0
    assert capsys.readouterr().out.strip() == f"2 3 17 {f}"
