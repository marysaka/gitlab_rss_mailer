from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
from pathlib import Path
import smtplib
from typing import Dict, List, Any, Optional

import yaml
import feedparser


class FeedEntry(object):
    id: str
    title: str
    author: str
    url: str

    def __init__(self, id: str, title: str, author: str, url: str) -> None:
        self.id = id
        self.title = title
        self.author = author
        self.url = url

    @staticmethod
    def from_raw_feed_entry(feed_entry: Any) -> "FeedEntry":
        id = feed_entry["id"]
        title = feed_entry["title"]
        author = feed_entry["author"]
        url = feed_entry["link"]

        return FeedEntry(id, title, author, url)

    def __str__(self) -> str:
        return f'FeedEntry {{ id: "{self.id}", title: "{self.title}", author: "{self.author}", url: "{self.url}"}}'

    def __repr__(self) -> str:
        return str(self)


class Feed(object):
    name: str
    title: str
    urls: List[str]

    def __init__(self, name: str, title: str, urls: List[str]) -> None:
        self.name = name
        self.title = title
        self.urls = urls

    @staticmethod
    def from_config(name: str, raw_config: Any) -> "Feed":
        return Feed(name, raw_config["title"], raw_config["urls"])

    def fetch_raw(self) -> List[Any]:
        entries = list()

        for url in self.urls:
            entries.extend(feedparser.parse(url)["entries"])

        return entries

    def fetch(self, known_ids: List[str]) -> List[FeedEntry]:
        entries = list()
        for raw_entry in self.fetch_raw():
            entry = FeedEntry.from_raw_feed_entry(raw_entry)
            if not entry.id in known_ids:
                entries.append(entry)

        return entries


class MailConfig(object):
    smtp_host: str
    smtp_port: str
    smtp_protocol: str
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str

    def __init__(
        self,
        smtp_host: str,
        smtp_port: str,
        smtp_protocol: str,
        smtp_username: str,
        smtp_password: str,
        email_from: str,
        email_to: str,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_protocol = smtp_protocol
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.email_from = email_from
        self.email_to = email_to

    @staticmethod
    def from_config(raw_config: Any) -> "MailConfig":
        return MailConfig(
            raw_config["host"],
            raw_config["port"],
            raw_config["protocol"],
            raw_config["username"],
            raw_config["password"],
            raw_config["email_from"],
            raw_config["email_to"],
        )


class Runner(object):
    mail_config: MailConfig
    feeds: List[Feed]
    feeds_cache: Dict[str, List[str]]
    feeds_cache_path: Path

    def __init__(self, config_path: Path, feeds_cache_path: Path) -> None:
        with config_path.open() as f:
            yaml_config = yaml.safe_load(f)

        self.mail_config = MailConfig.from_config(yaml_config["smtp"])
        self.feeds = list()

        for feed_name, raw_feed in yaml_config["feeds"].items():
            self.feeds.append(Feed.from_config(feed_name, raw_feed))
        self.feeds_cache_path = feeds_cache_path
        self.feeds_cache = json.loads(self.feeds_cache_path.read_text())

    def fetch_all(self, dry_run: bool) -> Dict[str, List[FeedEntry]]:
        result = dict()

        for feed in self.feeds:
            feed_cache = self.feeds_cache.get(feed.name, [])
            entries = feed.fetch(feed_cache)

            result[feed.name] = entries

            if not dry_run:
                for entry in entries:
                    feed_cache.append(entry.id)

                self.feeds_cache[feed.name] = feed_cache

        if not dry_run:
            self.feeds_cache_path.write_text(json.dumps(self.feeds_cache))

        return result

    def get_feed_by_name(self, feed_name: str) -> Optional[Feed]:
        for feed in self.feeds:
            if feed.name == feed_name:
                return feed

        return None

    def create_mail_text(self, feed_name: str, entries: List[FeedEntry]) -> str:
        feed = self.get_feed_by_name(feed_name)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[RSS Mailer] New entries for feed {feed.title}"
        msg["Reply-To"] = self.mail_config.email_from
        msg["From"] = self.mail_config.email_from
        msg["To"] = self.mail_config.email_to

        # Indicate that it's automated and that we don't want replies
        msg["Auto-Submitted"] = "auto-generated"
        msg["X-Auto-Response-Suppress"] = "All"

        plain_text = ""
        html_text = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">'
        html_text += '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n<body>\n'
        html_text += "<head>\n"
        html_text += (
            '<meta content="text/html; charset=UTF-8" http-equiv="Content-Type" />'
        )
        html_text += "</head>\n"

        html_text += "<body>\n"
        plain_text += f"New entries for feed {feed.title}\n"
        html_text += f"<p>New entries for feed {feed.title}</p>\n"

        html_text += "<ul>\n"
        for entry in entries:
            plain_text += f'- "{entry.title}" by {entry.author} ({entry.url})\n'
            html_text += f'<li>"<a href="{entry.url}">{entry.title}</a>" by {entry.author} ({entry.url})</li>\n'
        html_text += "</ul>\n"

        html_text += "\n</body>\n</html>\n"

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_text, "html"))

        return msg.as_string()

    def send_mails(self, mails: List[str]):
        if len(mails) == 0:
            return

        if self.mail_config.smtp_protocol == "ssl":
            conn = smtplib.SMTP_SSL(
                self.mail_config.smtp_host, int(self.mail_config.smtp_port)
            )
        else:
            conn = smtplib.SMTP(
                self.mail_config.smtp_host, int(self.mail_config.smtp_port)
            )

        conn.ehlo()

        if self.mail_config.smtp_protocol == "tls":
            conn.starttls()

        conn.login(self.mail_config.smtp_username, self.mail_config.smtp_password)

        for mail in mails:
            conn.sendmail(self.mail_config.email_from, self.mail_config.email_to, mail)

        conn.quit()
