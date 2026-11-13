#!/usr/bin/env python3
"""Remplace un bloc de site précis dans un Caddyfile sans toucher aux autres domaines."""

from pathlib import Path
import sys


def replace_site(config: str, snippet: str, domain: str) -> str:
    marker = f"{domain} {{"
    start = config.find(marker)
    if start < 0:
        raise ValueError(f"Bloc introuvable : {domain}")

    depth = 0
    end = None
    for index in range(start, len(config)):
        character = config[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise ValueError(f"Bloc Caddy incomplet : {domain}")

    while end < len(config) and config[end] in "\r\n":
        end += 1
    return config[:start] + snippet.strip() + "\n" + config[end:]


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: replace-caddy-site.py CONFIG SNIPPET DOMAIN OUTPUT")
    config_path, snippet_path, domain, output_path = map(Path, sys.argv[1:])
    updated = replace_site(
        config_path.read_text(encoding="utf-8"),
        snippet_path.read_text(encoding="utf-8"),
        str(domain),
    )
    output_path.write_text(updated, encoding="utf-8")
