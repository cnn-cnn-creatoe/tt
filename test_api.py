import requests
import json
import os
from datetime import datetime, timedelta, timezone

# 从配置文件加载API密钥
config_file = "config.json"
with open(config_file, 'r', encoding='utf-8') as f:
    config = json.load(f)

TWITTER_API_KEY = config["TWITTER_API_KEY"]

# 设置时间范围
since_time = datetime.now(timezone.utc) - timedelta(days=2)
until_time = datetime.now(timezone.utc)
since_ts = int(since_time.timestamp())
until_ts = int(until_time.timestamp())

# 测试不同的查询参数
test_queries = [
    # 原始查询（包含回复）
    f"from:Google since_time:{since_ts} until_time:{until_ts} include:nativeretweets",
    
    # 排除回复的查询
    f"from:Google since_time:{since_ts} until_time:{until_ts} -filter:replies include:nativeretweets",
    
    # 只获取原创推文（不包括转发和回复）
    f"from:Google since_time:{since_ts} until_time:{until_ts} -filter:replies -filter:retweets",
    
    # 只获取原创推文和转发（不包括回复）
    f"from:Google since_time:{since_ts} until_time:{until_ts} -filter:replies"
]

# 测试每个查询
for i, query in enumerate(test_queries):
    print(f"\n测试查询 {i+1}: {query}")
    
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    params = {"query": query, "queryType": "Latest"}
    headers = {"X-API-Key": TWITTER_API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            tweets = data.get("tweets", [])
            print(f"获取到 {len(tweets)} 条推文")
            
            # 显示前3条推文的内容
            for j, tweet in enumerate(tweets[:3]):
                print(f"  推文 {j+1}: {tweet.get('text', '')[:100]}...")
        else:
            print(f"API请求失败: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"发生错误: {str(e)}")
