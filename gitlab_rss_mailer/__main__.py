from argparse import ArgumentParser, Namespace
from pathlib import Path
import sys

from gitlab_rss_mailer import Runner


def parse_arguments() -> Namespace:
    parser = ArgumentParser(
        prog="gitlab_rss_mailer",
        description="A service that transform RSS feeds from GitLab issues and MRs into mail notifications",
    )

    parser.add_argument("config_file_path")
    parser.add_argument("cache_file_path")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    runner = Runner(Path(args.config_file_path), Path(args.cache_file_path))

    new_entries = runner.fetch_all(args.dry_run)

    mail_reports = list()

    for feed_name, entries in new_entries.items():
        if len(entries) == 0:
            continue

        mail_report = runner.create_mail_text(feed_name, entries)

        if not args.dry_run:
            mail_reports.append(mail_report)
        else:
            print(f'New mail report for "{feed_name}":')
            print(mail_report)

    runner.send_mails(mail_reports)

    return 0


if __name__ == "__main__":
    sys.exit(main())
