import requests
import time
import json
import os
import sys
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from openai import OpenAI

AI_FAILURE_MESSAGE = "AI处理失败：大模型调用失败，请检查 API Key、接口地址、模型名称和额度。"


def mask_sensitive_text(value) -> str:
    text = str(value)
    text = re.sub(r"(sk-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+", r"\1***", text)
    text = re.sub(r"(new1_[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+", r"\1***", text)
    return text


def log(*args, sep=" ", end="\n"):
    text = sep.join(mask_sensitive_text(arg) for arg in args) + end
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        sys.stdout.write(safe_text)
        sys.stdout.flush()


class TwitterAIMonitor:
    """Twitter推文监控和AI处理器"""
    
    def __init__(self, twitter_api_key: str, llm_url: str, llm_api_key: str, llm_model: str = "", data_dir: str = "data"):
        """
        初始化监控器
        
        :param twitter_api_key: TwitterAPI.io API Key
        :param llm_url: 大模型接口URL
        :param llm_api_key: 大模型API Key
        :param data_dir: 数据存储目录
        """
        self.twitter_api_key = twitter_api_key
        self.llm_client = None
        if llm_url and llm_api_key:
            self.llm_client = OpenAI(
                api_key=llm_api_key,
                base_url=llm_url,
            )
        self.llm_model = llm_model
        self.data_dir = data_dir
        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)

    @staticmethod
    def _normalize_account(account: str) -> str:
        account = str(account or "").strip()
        if account.startswith(("https://x.com/", "https://twitter.com/")):
            account = account.rstrip("/").split("/")[-1]
        return account.lstrip("@")

    @staticmethod
    def _to_unix_seconds(dt: datetime) -> int:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp())

    @staticmethod
    def _tweet_created_at_seconds(tweet: dict):
        created_at = tweet.get("createdAt") or tweet.get("created_at")
        if not created_at:
            return None
        try:
            return int(parsedate_to_datetime(created_at).timestamp())
        except (TypeError, ValueError):
            try:
                return int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _looks_like_chinese(text: str) -> bool:
        value = str(text or "")
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", value)
        letters = re.findall(r"[A-Za-z]", value)
        return bool(chinese_chars) and len(chinese_chars) >= max(2, len(letters) // 2)

    @staticmethod
    def _media_items(value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            if isinstance(value.get("media"), list):
                return value["media"]
            if isinstance(value.get("photos"), list):
                return value["photos"]
            if isinstance(value.get("images"), list):
                return value["images"]
            return [value]
        return []

    @classmethod
    def extract_image_urls(cls, tweet: dict) -> list:
        """Extract image URLs from common TwitterAPI.io response shapes."""
        candidates = []
        media_sources = [
            tweet.get("media"),
            tweet.get("entities"),
            tweet.get("extendedEntities"),
            tweet.get("extended_entities"),
            tweet.get("attachments"),
            tweet.get("photos"),
            tweet.get("images"),
        ]

        for source in media_sources:
            for item in cls._media_items(source):
                if not isinstance(item, dict):
                    continue
                media_type = str(item.get("type") or item.get("media_type") or item.get("content_type") or "").lower()
                if media_type and media_type not in {"photo", "image", "animated_gif", "video"}:
                    continue
                for key in ("media_url_https", "media_url", "url", "image_url", "preview_image_url", "thumbnail_url"):
                    url = item.get(key)
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        candidates.append(url)
                if isinstance(item.get("variants"), list):
                    for variant in item["variants"]:
                        url = variant.get("url") if isinstance(variant, dict) else None
                        if isinstance(url, str) and url.startswith(("http://", "https://")) and any(ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                            candidates.append(url)

        seen = set()
        urls = []
        for url in candidates:
            clean_url = url.strip()
            key = clean_url.split("?")[0]
            if clean_url and key not in seen:
                seen.add(key)
                urls.append(clean_url)
        return urls[:4]

    @staticmethod
    def _json_from_text(text: str) -> dict:
        value = str(text or "").strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*", "", value)
            value = re.sub(r"\s*```$", "", value)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", value, flags=re.S)
            if match:
                return json.loads(match.group(0))
            raise

    def get_ai_response(self, prompt: str, image_urls: list = None) -> str:
        """
        调用AI模型获取响应
        
        :param prompt: 输入提示词
        :param image_urls: 可选图片 URL，用于视觉模型读取图片内容
        :return: AI响应内容
        """
        if not self.llm_client or not self.llm_model:
            return AI_FAILURE_MESSAGE

        image_urls = image_urls or []
        user_content = prompt
        if image_urls:
            user_content = [{"type": "text", "text": prompt}]
            user_content.extend(
                {"type": "image_url", "image_url": {"url": image_url}}
                for image_url in image_urls
            )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "你是一个中文推文解析助手。只输出用户要求的内容，不要编造事实。"},
                    {"role": "user", "content": user_content},
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            if image_urls:
                log(f"视觉模型调用失败，尝试改用纯文本调用: {e}")
                text_prompt = prompt + "\n\n图片 URL（如果模型不能直接读取图片，请只按文本内容解析）：\n" + "\n".join(image_urls)
                try:
                    completion = self.llm_client.chat.completions.create(
                        model=self.llm_model,
                        messages=[
                            {"role": "system", "content": "你是一个中文推文解析助手。只输出用户要求的内容，不要编造事实。"},
                            {"role": "user", "content": text_prompt},
                        ]
                    )
                    return completion.choices[0].message.content
                except Exception as fallback_error:
                    log(f"AI调用出错: {fallback_error}")
                    return AI_FAILURE_MESSAGE

            log(f"AI调用出错: {e}")
            return AI_FAILURE_MESSAGE

    def process_tweet_with_ai(self, tweet_text: str, image_urls: list = None) -> dict:
        """
        使用AI处理推文：翻译、解读、生成标题
        
        :param tweet_text: 推文内容
        :param image_urls: 推文图片 URL
        :return: 包含AI处理结果的字典
        """
        image_urls = image_urls or []
        chinese_hint = "这条推文主要是中文，translation 字段直接保留中文原文，可轻微修正明显错别字。" if self._looks_like_chinese(tweet_text) else "如果原文不是中文，请把 translation 字段翻译成自然中文。"
        image_hint = "推文包含图片。请读取图片中的文字和画面信息，并把有价值的信息纳入标题、翻译和解读。" if image_urls else "推文没有可用图片。"
        prompt = f"""请处理下面这条 X/Twitter 推文，并只返回一个 JSON 对象。

要求：
1. title：中文标题，10-25 个字，概括核心信息。
2. translation：中文内容。{chinese_hint}
3. analysis：中文解读，80-180 字。内容短时就简短解释，不要编造钱包地址、空投规则、项目背景等原文没有的信息。
4. {image_hint}
5. 只返回 JSON，不要 Markdown，不要额外说明。

JSON 格式：
{{"title":"...","translation":"...","analysis":"..."}}

推文原文：
{tweet_text or "(无文本内容)"}
"""

        response = self.get_ai_response(prompt, image_urls=image_urls)
        if response.startswith("AI处理失败"):
            return {
                'title': "AI处理失败",
                'translation': response,
                'analysis': response
            }

        try:
            data = self._json_from_text(response)
        except Exception as e:
            log(f"AI返回内容不是有效JSON，使用原始响应兜底: {e}")
            data = {}

        title = str(data.get("title") or "").strip()
        translation = str(data.get("translation") or "").strip()
        analysis = str(data.get("analysis") or "").strip()

        if not translation:
            translation = tweet_text if self._looks_like_chinese(tweet_text) else response.strip()
        if not title:
            title = translation[:24] or "推文解析"
        if not analysis:
            analysis = response.strip()

        return {
            'title': title.strip(),
            'translation': translation.strip(),
            'analysis': analysis.strip()
        }
    
    def get_tweets_from_account(self, account: str, since_time: datetime, until_time: datetime, exclude_replies: bool = False) -> list:
        """
        获取指定账号在指定时间范围内的推文
        
        :param account: Twitter账号
        :param since_time: 开始时间
        :param until_time: 结束时间
        :param exclude_replies: 是否排除回复推文
        :return: 推文列表
        """
        url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
        headers = {"X-API-Key": self.twitter_api_key}

        account_handle = self._normalize_account(account)
        since_ts = self._to_unix_seconds(since_time)
        until_ts = self._to_unix_seconds(until_time)
        current_until = until_ts
        query_filters = ["-filter:replies"] if exclude_replies else []

        all_tweets = []
        seen_ids = set()
        api_calls = 0
        max_api_calls = 200

        while current_until > since_ts and api_calls < max_api_calls:
            query_parts = [
                f"from:{account_handle}",
                f"since_time:{since_ts}",
                f"until_time:{current_until}",
                *query_filters,
                "include:nativeretweets",
            ]
            query = " ".join(part for part in query_parts if part)
            params = {"query": query, "queryType": "Latest"}

            response = requests.get(url, headers=headers, params=params, timeout=30)
            api_calls += 1
            
            if response.status_code == 200:
                data = response.json()
                tweets = data.get("tweets", [])
                
                if tweets:
                    for t in tweets:
                        t['author'] = account_handle  # 添加作者信息
                        tweet_id = t.get("id") or t.get("id_str")
                        if tweet_id and tweet_id not in seen_ids:
                            seen_ids.add(tweet_id)
                            all_tweets.append(t)

                if len(tweets) < 20:
                    break

                created_times = [
                    created_ts for created_ts in
                    (self._tweet_created_at_seconds(tweet) for tweet in tweets)
                    if created_ts is not None
                ]
                if not created_times:
                    break

                next_until = min(created_times) - 1
                if next_until >= current_until:
                    break
                current_until = max(next_until, since_ts)
            else:
                log(f"获取推文出错: {response.status_code} - {response.text}")
                break

        if api_calls >= max_api_calls:
            log(f"@{account_handle} 查询达到安全上限 {max_api_calls} 次，已停止继续翻页")
        
        return all_tweets
    
    def save_tweet_data(self, tweet_data: dict):
        """
        保存推文数据到JSON文件，按天存储
        
        :param tweet_data: 推文数据
        """
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = os.path.join(self.data_dir, f"tweets_{today}.json")
        
        # 读取现有数据
        existing_data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []
        
        # 检查是否重复 - 根据推文ID去重
        tweet_id = tweet_data.get('id')
        existing_ids = {item.get('id') for item in existing_data if item.get('id')}
        
        if tweet_id not in existing_ids:
            # 添加新数据（仅当ID不重复时）
            existing_data.append(tweet_data)
            log(f"保存新推文: {tweet_id} - {tweet_data.get('author', 'Unknown')}")
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
        else:
            log(f"跳过重复推文: {tweet_id} - {tweet_data.get('author', 'Unknown')}")
    
    def load_tweets_by_date(self, date_str: str = None) -> list:
        """
        根据日期加载推文数据
        
        :param date_str: 日期字符串 (YYYY-MM-DD)，默认为今天
        :return: 推文数据列表
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        file_path = os.path.join(self.data_dir, f"tweets_{date_str}.json")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []
    
    def get_all_tweets(self) -> list:
        """
        获取所有存储的推文数据
        
        :return: 所有推文数据列表
        """
        all_tweets = []
        
        # 遍历数据目录中的所有JSON文件
        if os.path.exists(self.data_dir):
            for filename in os.listdir(self.data_dir):
                if filename.startswith("tweets_") and filename.endswith(".json"):
                    file_path = os.path.join(self.data_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            tweets = json.load(f)
                            all_tweets.extend(tweets)
                    except json.JSONDecodeError:
                        continue
        
        # 按时间排序（最新的在前）
        all_tweets.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return all_tweets
    
    def monitor_and_process(self, target_accounts: list, check_interval: int = 300, hours: int = 1, exclude_replies: bool = False):
        """
        监控Twitter账号并使用AI处理新推文
        
        :param target_accounts: 要监控的账号列表
        :param check_interval: 检查间隔（秒）
        :param hours: 初始回溯时间（小时）
        :param exclude_replies: 是否排除回复推文
        """
        last_checked_time = datetime.utcnow() - timedelta(hours=hours)
        
        def check_and_process_tweets():
            nonlocal last_checked_time
            until_time = datetime.utcnow()
            since_time = last_checked_time
            
            all_tweets = []
            
            for account in target_accounts:
                tweets = self.get_tweets_from_account(account, since_time, until_time, exclude_replies)
                all_tweets.extend(tweets)
                
                # 添加5秒延迟，避免API限制
                if account != target_accounts[-1]:  # 如果不是最后一个账号，添加延迟
                    log("等待5秒，避免API请求限制...")
                    time.sleep(5)
            
            if all_tweets:
                log(f"发现 {len(all_tweets)} 条新推文，开始AI处理...\n")
                
                for idx, tweet in enumerate(all_tweets, start=1):
                    log(f"{'='*60}")
                    log(f"处理推文 {idx}/{len(all_tweets)}")
                    log(f"{'='*60}")
                    
                    # 基本信息
                    tweet_id = tweet.get('id') or tweet.get('id_str')
                    tweet_url = f"https://twitter.com/{tweet['author']}/status/{tweet_id}"
                    original_text = tweet.get('text', '')
                    image_urls = self.extract_image_urls(tweet)
                    
                    log(f"作者：{tweet['author']}")
                    log(f"发布时间：{tweet.get('createdAt')}")
                    log(f"原文：{original_text}")
                    if image_urls:
                        log(f"图片：{', '.join(image_urls)}")
                    log(f"链接：{tweet_url}")
                    log()
                    
                    # AI处理
                    log("AI处理中...")
                    ai_result = self.process_tweet_with_ai(original_text, image_urls=image_urls)
                    
                    log(f"AI标题：{ai_result['title']}")
                    log(f"AI翻译：{ai_result['translation']}")
                    log(f"AI解读：{ai_result['analysis']}")
                    log(f"{'='*60}\n")
                    
                    # 保存数据到JSON
                    tweet_data = {
                        'id': tweet_id,
                        'author': tweet['author'],
                        'created_at': tweet.get('createdAt'),
                        'original_text': original_text,
                        'tweet_url': tweet_url,
                        'media_urls': image_urls,
                        'ai_title': ai_result['title'],
                        'ai_translation': ai_result['translation'],
                        'ai_analysis': ai_result['analysis'],
                        'timestamp': datetime.utcnow().isoformat(),
                        'processed_date': datetime.now().strftime("%Y-%m-%d")
                    }
                    self.save_tweet_data(tweet_data)
                    
                    # 添加延迟避免API频率限制
                    time.sleep(2)
            else:
                log(f"{datetime.utcnow()} - 没有发现新推文。")
            
            last_checked_time = until_time
        
        log(f"开始监控账号: {', '.join(target_accounts)}")
        log(f"检查间隔: {check_interval} 秒")
        log(f"AI处理功能已启用\n")
        
        try:
            while True:
                check_and_process_tweets()
                log(f"等待 {check_interval} 秒后进行下次检查...")
                time.sleep(check_interval)
        except KeyboardInterrupt:
            log("监控已停止。")
    
    def monitor_and_process_with_status(self, target_accounts: list, check_interval: int = 300, hours: int = 1, status_dict: dict = None, exclude_replies: bool = False):
        """
        带状态更新的监控功能
        
        :param target_accounts: 要监控的账号列表
        :param check_interval: 检查间隔（秒）
        :param hours: 初始回溯时间（小时）
        :param status_dict: 状态字典，用于更新前端显示
        :param exclude_replies: 是否排除回复推文
        """
        last_checked_time = datetime.utcnow() - timedelta(hours=hours)
        
        def update_status(status, account="", result=""):
            if status_dict:
                status_dict["current_status"] = status
                status_dict["current_account"] = account
                status_dict["last_update"] = datetime.now().isoformat()
                if result:
                    status_dict["last_result"] = result
                # 计算下次检查时间
                next_time = datetime.now() + timedelta(seconds=check_interval)
                status_dict["next_check_time"] = next_time.isoformat()
        
        def check_and_process_tweets():
            nonlocal last_checked_time
            until_time = datetime.utcnow()
            since_time = last_checked_time
            
            all_tweets = []
            
            try:
                # 更新状态：开始抓取
                update_status("扫描中", f"{', '.join(target_accounts)}")

                for account in target_accounts:
                    try:
                        update_status(f"正在抓取 @{account} 的推文...")
                        tweets = self.get_tweets_from_account(account, since_time, until_time, exclude_replies)
                        all_tweets.extend(tweets)
                        log(f"成功获取 @{account} 的 {len(tweets)} 条推文")
                        
                        # 添加5秒延迟，避免API限制
                        if account != target_accounts[-1]:  # 如果不是最后一个账号，添加延迟
                            log("等待5秒，避免API请求限制...")
                            time.sleep(5)
                            
                    except Exception as e:
                        log(f"获取 @{account} 推文失败: {str(e)}")
                        update_status(f"@{account} 数据获取异常", result=f"错误: {str(e)}")
                        continue
            except Exception as e:
                log(f"推文扫描过程出错: {str(e)}")
                update_status("扫描过程异常", result=f"错误: {str(e)}")
                return
            
            if all_tweets:
                update_status(f"发现 {len(all_tweets)} 条新推文，AI分析中...", result=f"找到 {len(all_tweets)} 条新推文")
                
                for idx, tweet in enumerate(all_tweets, start=1):
                    # 基本信息
                    tweet_id = tweet.get('id') or tweet.get('id_str')
                    tweet_url = f"https://twitter.com/{tweet['author']}/status/{tweet_id}"
                    original_text = tweet.get('text', '')
                    image_urls = self.extract_image_urls(tweet)
                    
                    # 更新状态：AI处理中
                    update_status(f"AI处理中... ({idx}/{len(all_tweets)})", f"@{tweet['author']}")
                    
                    # AI处理
                    try:
                        ai_result = self.process_tweet_with_ai(original_text, image_urls=image_urls)
                    except Exception as e:
                        log(f"AI处理推文失败: {str(e)}")
                        ai_result = {
                            'title': f"处理失败: {str(e)[:50]}",
                            'translation': original_text,
                            'analysis': f"AI处理失败: {str(e)}"
                        }
                    
                    # 保存数据到JSON
                    tweet_data = {
                        'id': tweet_id,
                        'author': tweet['author'],
                        'created_at': tweet.get('createdAt'),
                        'original_text': original_text,
                        'tweet_url': tweet_url,
                        'media_urls': image_urls,
                        'ai_title': ai_result['title'],
                        'ai_translation': ai_result['translation'],
                        'ai_analysis': ai_result['analysis'],
                        'timestamp': datetime.utcnow().isoformat(),
                        'processed_date': datetime.now().strftime("%Y-%m-%d")
                    }
                    self.save_tweet_data(tweet_data)
                    
                    # 更新处理计数
                    if status_dict:
                        status_dict["processed_tweets"] = status_dict.get("processed_tweets", 0) + 1
                    
                    # 添加延迟避免API频率限制
                    time.sleep(2)
                
                update_status("处理完成", result=f"成功处理 {len(all_tweets)} 条推文")
            else:
                update_status("智能待机中", result="未发现新推文，继续监控中...")
            
            last_checked_time = until_time
        
        update_status("监控已启动", f"监控 {len(target_accounts)} 个账号")
        log(f"监控启动成功，目标账号: {target_accounts}")
        
        try:
            while status_dict and status_dict.get("running", False):
                log("开始新一轮检查循环...")
                check_and_process_tweets()
                
                # 倒计时等待
                for remaining in range(check_interval, 0, -10):
                    if not status_dict.get("running", False):
                        log("收到停止信号，退出监控")
                        break
                    update_status(f"下次扫描倒计时 {remaining}s", result=status_dict.get("last_result", ""))
                    time.sleep(10)
                    
        except KeyboardInterrupt:
            log("监控被中断")
            update_status("监控已停止")
        except Exception as e:
            log(f"监控过程出现异常: {str(e)}")
            update_status("监控异常停止", result=f"错误: {str(e)}")
            if status_dict:
                status_dict["running"] = False


# 主程序
if __name__ == "__main__":
    # 从配置文件加载配置
    config_file = "config.json"
    
    # 默认配置
    default_config = {
        "TWITTER_API_KEY": "",
        "LLM_URL": "",
        "LLM_MODEL": "",
        "LLM_API_KEY": "",
        "TARGET_ACCOUNTS": ["OpenAI"],
        "CHECK_INTERVAL": 300,
        "INITIAL_HOURS": 64,
        "EXCLUDE_REPLIES": False # 新增配置项
    }
    
    # 读取配置文件
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
        except Exception as e:
            log(f"读取配置文件失败，使用默认配置: {e}")
            config = default_config
    else:
        log("配置文件不存在，使用默认配置")
        config = default_config
    
    # 提取配置参数
    TWITTER_API_KEY = config["TWITTER_API_KEY"]
    LLM_URL = config["LLM_URL"]
    LLM_MODEL = config.get("LLM_MODEL", "")
    LLM_API_KEY = config["LLM_API_KEY"]
    TARGET_ACCOUNTS = config["TARGET_ACCOUNTS"]
    CHECK_INTERVAL = config["CHECK_INTERVAL"]
    INITIAL_HOURS = config["INITIAL_HOURS"]
    EXCLUDE_REPLIES = config["EXCLUDE_REPLIES"] # 从配置加载
    
    log(f"开始监控账号: {', '.join(TARGET_ACCOUNTS)}")
    log(f"检查间隔: {CHECK_INTERVAL}秒")
    log(f"初始回溯: {INITIAL_HOURS}小时")
    log(f"是否排除回复: {EXCLUDE_REPLIES}") # 打印配置
    
    # 创建监控器并开始监控
    monitor = TwitterAIMonitor(TWITTER_API_KEY, LLM_URL, LLM_API_KEY, LLM_MODEL)
    monitor.monitor_and_process(TARGET_ACCOUNTS, CHECK_INTERVAL, INITIAL_HOURS, EXCLUDE_REPLIES)
