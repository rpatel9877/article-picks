"""Command-line helpers.

  python manage.py report            Build this week's Word report now (no email)
  python manage.py report --send     Build and email it
  python manage.py reminder          Send the Monday reminder now
  python manage.py tick              Run the scheduler check once
  python manage.py demo              Load sample data (offline) and build a sample report
"""
import argparse

import cycle as cyc
import db
import jobs
import scorer


def main():
    parser = argparse.ArgumentParser(description="Weekly reading picks")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--week", help="Deadline date YYYY-MM-DD (default: the open week)")
    r.add_argument("--send", action="store_true")
    sub.add_parser("reminder")
    sub.add_parser("tick")
    sub.add_parser("demo")
    args = parser.parse_args()
    db.init_db()

    if args.cmd == "report":
        week = args.week or cyc.open_cycle()
        if args.send:
            print(jobs.send_report(week)[1])
        else:
            path, items = jobs.build_report_file(week)
            print(f"Built {path} with {len(items)} links.")
    elif args.cmd == "reminder":
        print(jobs.send_reminder(cyc.open_cycle())[1])
    elif args.cmd == "tick":
        print(jobs.tick() or "Nothing due.")
    elif args.cmd == "demo":
        run_demo()


# Fictional sample data so the layout can be previewed without internet access or an API key.
DEMO = [
    ("Priya Shah", "https://example.org/insights/why-dividend-growth-outlasts-yield",
     "Why dividend growth has outlasted high yield over five decades", "Example Research", 2350, "free",
     {"worldview_fit": 5, "originality": 4, "relevance": 5, "readability": 5, "nonpartisan": 5}, {},
     "Long-horizon evidence that fits our quality bias, written for non-specialists.",
     "Most income investors reach for the highest yield. This piece looks at fifty years of data and "
     "finds that companies steadily growing their dividends delivered better results with less drama."),
    ("Priya Shah", "https://example.com/markets/stocks-rally-on-jobs-report",
     "Stocks rally after jobs report beats forecasts", "Example Wire", 420, "free",
     {"worldview_fit": 2, "originality": 1, "relevance": 5, "readability": 3, "nonpartisan": 5},
     {"too_short": True}, "A same-day market wrap that every outlet ran; little lasting insight.", ""),
    ("Marcus Lee", "https://example.net/essays/the-hidden-cost-of-private-credit-marks",
     "The hidden cost of stale marks in private credit", "Example Quarterly", 3100, "free",
     {"worldview_fit": 5, "originality": 5, "relevance": 5, "readability": 4, "nonpartisan": 5}, {},
     "An under-covered angle on private credit valuations that clients keep asking about.",
     "Private credit has grown quickly, but how often are those loans actually valued? This essay explains "
     "why smooth reported returns can hide real risk, in plain language."),
    ("Marcus Lee", "https://www.wsj.com/finance/example-article",
     "Example subscription article on bank earnings", "The Wall Street Journal", 0, "likely",
     {"worldview_fit": 3, "originality": 2, "relevance": 5, "readability": 4, "nonpartisan": 5}, {},
     "Solid reporting, but clients would hit a paywall.", ""),
    ("Elena Ruiz", "https://example.org/papers/term-premium-estimation",
     "Estimating the term premium with an affine model", "Example Fed Working Paper", 9800, "free",
     {"worldview_fit": 3, "originality": 4, "relevance": 5, "readability": 1, "nonpartisan": 5},
     {"too_technical": True}, "Interesting topic, but the math makes it unsuitable for clients.", ""),
    ("Elena Ruiz", "https://example.com/blog/what-japan-teaches-about-demographics-and-returns",
     "What Japan teaches about demographics and market returns", "Example Blog", 1900, "free",
     {"worldview_fit": 4, "originality": 4, "relevance": 5, "readability": 5, "nonpartisan": 5}, {},
     "A long-view comparison that helps clients think past next quarter.",
     "Ageing populations are often blamed for weak markets. Japan's experience suggests the story is "
     "more nuanced, and the piece draws practical lessons for long-term investors."),
    ("Tom Becker", "https://example.net/analysis/tariffs-and-the-consumer",
     "Who actually pays for tariffs? A look at price data", "Example Analysis", 1600, "free",
     {"worldview_fit": 4, "originality": 3, "relevance": 5, "readability": 5, "nonpartisan": 4}, {},
     "Data-driven and even-handed on a topic clients care about.",
     "Tariffs are debated loudly, but the price data tells a quieter story. This article walks through "
     "who absorbs the cost and what it means for company margins."),
    ("Tom Becker", "https://example.org/opinion/why-the-other-party-is-ruining-the-economy",
     "Why the other party is ruining the economy", "Example Opinion", 1200, "free",
     {"worldview_fit": 2, "originality": 2, "relevance": 3, "readability": 5, "nonpartisan": 1},
     {"partisan": True}, "Clearly partisan; would distract from our message.", ""),
    ("Marcus Lee", "https://example.com/blog/what-japan-teaches-about-demographics-and-returns",
     None, None, None, None, None, None, None, None),
    ("Priya Shah", "https://example.com/research/cash-drag-in-rising-rate-regimes",
     "The quiet drag of holding too much cash", "Example Research", 1400, "free",
     {"worldview_fit": 4, "originality": 3, "relevance": 5, "readability": 5, "nonpartisan": 5}, {},
     "Useful reminder for clients sitting on large cash balances.",
     "Cash feels safe, especially after a volatile stretch. This piece shows how holding too much of it "
     "for too long has quietly cost investors over time."),
]


def seed_demo_analyses(settings):
    """Stores pre-written sample scores so the demo works offline without an API key."""
    for (_, url, title, site, words, paywall, scores, flags, why, intro) in DEMO:
        if title is None:
            continue
        article = {"url": url, "domain": url.split("/")[2].removeprefix("www."), "title": title, "site": site,
                   "author": "", "word_count": words, "is_pdf": False, "paywall": paywall,
                   "paywall_reason": "Subscription site (wsj.com)" if paywall == "likely" else "",
                   "fetched": True, "error": ""}
        result = {"title": title, "summary": why, "topic": "", "scores": scores,
                  "flags": {"too_technical": False, "too_short": False, "partisan": False, "off_topic": False, **flags},
                  "why": why, "draft_intro": intro, "method": "ai"}
        db.save_analysis(scorer.cache_key(url, settings), url, scorer._finalize(article, result))


def run_demo():
    db.save_settings({"team_members": "Priya Shah, priya@example.com\nMarcus Lee, marcus@example.com\n"
                                      "Elena Ruiz, elena@example.com\nTom Becker, tom@example.com",
                      "report_recipients": "adam@example.com"})
    settings = db.get_settings()
    week = cyc.open_cycle()
    for (who, url, *_rest) in DEMO:
        db.add_submission(week, who, url, "Great long-term perspective." if "dividend" in url else "")
    seed_demo_analyses(settings)
    path, items = jobs.build_report_file(week)
    print(f"Sample report: {path} ({len(items)} unique links)")


if __name__ == "__main__":
    main()
