import argparse
import sys


def count(text):
    return len(text.splitlines()), len(text.split()), len(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cuenta líneas, palabras y caracteres")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        lines, words, chars = count(f.read())
    print(f"{lines} {words} {chars} {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
