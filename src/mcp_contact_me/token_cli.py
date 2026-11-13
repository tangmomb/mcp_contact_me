import argparse

from .config import get_settings
from .security import TokenRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Gère les jetons d'accès par projet.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "rotate", "revoke"):
        child = subparsers.add_parser(command)
        child.add_argument("project")
    subparsers.add_parser("list")
    args = parser.parse_args()

    registry = TokenRegistry(get_settings().token_registry_path)
    try:
        if args.command == "create":
            token = registry.create(args.project)
            print(f"Projet : {args.project}")
            print(f"Jeton (affiché une seule fois) : {token}")
        elif args.command == "rotate":
            token = registry.create(args.project, replace=True)
            print(f"Projet : {args.project}")
            print(f"Nouveau jeton (affiché une seule fois) : {token}")
        elif args.command == "revoke":
            registry.revoke(args.project)
            print(f"Jeton révoqué pour : {args.project}")
        else:
            for record in registry.list_projects():
                state = "actif" if record["enabled"] else "révoqué"
                print(f"{record['project']}\t{state}\t{record['created_at']}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
