import requests
import time
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

def to_unix_seconds(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())

def tweet_created_at_seconds(tweet: dict):
    created_at = tweet.get("createdAt")
    if not created_at:
        return None
    try:
        return int(parsedate_to_datetime(created_at).timestamp())
    except (TypeError, ValueError):
        return None

def monitor_tweets(api_key: str, target_accounts: list, check_interval: int = 300, hours: int = 1):
    """
    监控指定 Twitter 账号的新推文，并以中文格式输出信息
    
    :param api_key: TwitterAPI.io API Key
    :param target_accounts: 要监控的账号列表
    :param check_interval: 检查间隔（秒）
    :param hours: 初始回溯时间（小时）
    """
    last_checked_time = datetime.utcnow() - timedelta(hours=hours)
    
    def check_for_new_tweets():
        nonlocal last_checked_time
        until_time = datetime.utcnow()
        since_time = last_checked_time
        
        since_ts = to_unix_seconds(since_time)
        until_ts = to_unix_seconds(until_time)
        
        all_tweets = []
        
        for account in target_accounts:
            url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
            headers = {"X-API-Key": api_key}
            current_until = until_ts
            seen_ids = set()

            while current_until > since_ts:
                query = f"from:{account} since_time:{since_ts} until_time:{current_until} include:nativeretweets"
                params = {"query": query, "queryType": "Latest"}
                response = requests.get(url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    tweets = data.get("tweets", [])
                    if tweets:
                        for t in tweets:
                            t['author'] = account  # 添加作者信息
                            tweet_id = t.get("id") or t.get("id_str")
                            if tweet_id and tweet_id not in seen_ids:
                                seen_ids.add(tweet_id)
                                all_tweets.append(t)
                    if len(tweets) < 20:
                        break

                    created_times = [
                        created_ts for created_ts in
                        (tweet_created_at_seconds(tweet) for tweet in tweets)
                        if created_ts is not None
                    ]
                    if not created_times:
                        break
                    next_until = min(created_times) - 1
                    if next_until >= current_until:
                        break
                    current_until = max(next_until, since_ts)
                else:
                    print(f"错误: {response.status_code} - {response.text}")
                    break
        
        if all_tweets:
            for idx, tweet in enumerate(all_tweets, start=1):
                tweet_id = tweet.get('id') or tweet.get('id_str')
                tweet_url = f"https://twitter.com/{tweet['author']}/status/{tweet_id}"
                print(f"信息{idx}：")
                print(f"作者：{tweet['author']}")
                print(f"发布时间：{tweet.get('createdAt')}")
                print(f"内容：{tweet.get('text')}")
                print(f"链接：{tweet_url}\n")
        else:
            print(f"{datetime.utcnow()} - 没有新的推文。")
        
        last_checked_time = until_time
    
    print(f"开始监控账号: {', '.join(target_accounts)}")
    print(f"检查间隔: {check_interval} 秒\n")
    
    try:
        while True:
            check_for_new_tweets()
            time.sleep(check_interval)
    except KeyboardInterrupt:
        print("监控已停止。")

# 示例调用
if __name__ == "__main__":
    API_KEY = os.getenv("TWITTER_API_KEY", "")
    if not API_KEY:
        raise SystemExit("请先设置 TWITTER_API_KEY 环境变量")
    TARGET_ACCOUNT = ["OpenAI"]
    CHECK_INTERVAL = 300  # 5 分钟
    HOURS = 70  # 初始回溯 70 小时
    
    monitor_tweets(API_KEY, TARGET_ACCOUNT, CHECK_INTERVAL, HOURS)
