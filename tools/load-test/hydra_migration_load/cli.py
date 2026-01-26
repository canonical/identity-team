import argparse
import asyncio

from load_flows import run_load
from setup_identities import run_setup


def main():
    parser = argparse.ArgumentParser(prog="hydra-migration-load")
    sub = parser.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup")
    setup_p.add_argument("--num-users", type=int, default=1000)
    setup_p.add_argument("--num-clients", type=int, default=50)
    setup_p.add_argument("--output", type=str, default="setup.json")

    run_p = sub.add_parser("run")
    run_p.add_argument("--setup-file", type=str, default="setup.json")
    run_p.add_argument("--logins-per-user", type=int, default=10)
    run_p.add_argument("--concurrency", type=int, default=50)
    run_p.add_argument("--enable-refresh", action="store_true")

    args = parser.parse_args()

    if args.command == "setup":
        asyncio.run(run_setup(args.num_users, args.num_clients, args.output))
    elif args.command == "run":
        asyncio.run(
            run_load(
                setup_path=args.setup_file,
                logins_per_user=args.logins_per_user,
                concurrency=args.concurrency,
                enable_refresh=args.enable_refresh,
            )
        )


if __name__ == "__main__":
    main()
