import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from twitter_ai_monitor import TwitterAIMonitor, log


FAIL_PREFIXES = ("AI处理失败", "处理失败")


def is_failed(tweet: dict) -> bool:
    return any(
        str(tweet.get(field, "")).strip().startswith(FAIL_PREFIXES)
        for field in ("ai_title", "ai_translation", "ai_analysis")
    )


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Reprocess failed tweet AI results.")
    parser.add_argument("--all", action="store_true", help="Reprocess every stored tweet instead of failed ones only.")
    parser.add_argument("--data-dir", default="data", help="Tweet data directory.")
    parser.add_argument("--config", default="config.json", help="Local config path.")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    monitor = TwitterAIMonitor(
        config.get("TWITTER_API_KEY", ""),
        config.get("LLM_URL", ""),
        config.get("LLM_API_KEY", ""),
        config.get("LLM_MODEL", ""),
        data_dir=args.data_dir,
    )

    data_dir = Path(args.data_dir)
    files = sorted(data_dir.glob("tweets_*.json"))
    total = 0
    updated = 0
    still_failed = 0

    for path in files:
        with path.open("r", encoding="utf-8") as f:
            tweets = json.load(f)

        changed = False
        for tweet in tweets:
            if not args.all and not is_failed(tweet):
                continue

            total += 1
            text = tweet.get("original_text") or tweet.get("text") or ""
            image_urls = tweet.get("media_urls") or []
            log(f"重新解析推文 {tweet.get('id', '')}: {text[:60]}")
            result = monitor.process_tweet_with_ai(text, image_urls=image_urls)
            tweet["ai_title"] = result["title"]
            tweet["ai_translation"] = result["translation"]
            tweet["ai_analysis"] = result["analysis"]
            changed = True

            if is_failed(tweet):
                still_failed += 1
            else:
                updated += 1

        if changed:
            with path.open("w", encoding="utf-8") as f:
                json.dump(tweets, f, ensure_ascii=False, indent=2)

    log(f"待处理: {total}，成功更新: {updated}，仍失败: {still_failed}")
    if still_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
