import argparse
import json
import sys


def count(text):
    return len(text.splitlines()), len(text.split()), len(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cuenta líneas, palabras y caracteres")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", help="Salida en JSON")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        lines, words, chars = count(f.read())
    if args.json:
        print(json.dumps({"lines": lines, "words": words, "chars": chars, "path": args.path}))
    else:
        print(f"{lines} {words} {chars} {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
