from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import threading
import time
from twitter_ai_monitor import TwitterAIMonitor

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", "dev-secret-key-change-me")

APP_NAME = "ai推文解析追踪"
BEIJING_TZ = timezone(timedelta(hours=8))

# 全局变量
monitor_instance = None
monitor_thread = None
monitoring_status = {
    "running": False, 
    "last_update": None,
    "current_status": "待机中",
    "processed_tweets": 0,
    "current_account": "",
    "next_check_time": None,
    "last_result": "暂无结果"
}

def parse_datetime_value(time_str):
    """解析 Twitter 时间或 ISO 时间。"""
    if not time_str:
        return None

    value = str(time_str).strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def to_beijing_datetime(time_str):
    dt = parse_datetime_value(time_str)
    if not dt:
        return None
    return dt.astimezone(BEIJING_TZ)

def utc_to_beijing(utc_time_str):
    """将UTC时间字符串转换为北京时间字符串。"""
    beijing_time = to_beijing_datetime(utc_time_str)
    if not beijing_time:
        return utc_time_str or ""
    return beijing_time.strftime("%Y-%m-%d %H:%M:%S")

def format_publish_time(time_str):
    """用于卡片和详情页的发布时间，例如 2026.5.3 12:00。"""
    beijing_time = to_beijing_datetime(time_str)
    if not beijing_time:
        return ""
    return f"{beijing_time.year}.{beijing_time.month}.{beijing_time.day} {beijing_time:%H:%M}"

def publish_date_key(tweet):
    beijing_time = to_beijing_datetime(tweet.get("created_at") or tweet.get("createdAt"))
    if not beijing_time:
        return tweet.get("processed_date", "")
    return beijing_time.strftime("%Y-%m-%d")

def enrich_tweet_times(tweet):
    """补充模板需要的发布时间和处理时间字段。"""
    tweet["published_time"] = format_publish_time(tweet.get("created_at") or tweet.get("createdAt"))
    tweet["published_date"] = publish_date_key(tweet)
    tweet["processed_time"] = utc_to_beijing(tweet.get("timestamp"))
    ai_failed = any(
        str(tweet.get(field, "")).strip().startswith("AI处理失败")
        for field in ("ai_title", "ai_translation", "ai_analysis")
    )
    tweet["ai_failed"] = ai_failed
    tweet["display_title"] = "AI解析未完成" if ai_failed else (tweet.get("ai_title") or "未生成标题")
    tweet["display_summary"] = tweet.get("original_text", "") if ai_failed else (tweet.get("ai_translation") or tweet.get("original_text", ""))
    tweet["display_translation"] = (
        "AI解析未完成。请检查设置里的大模型 API Key、接口地址、模型名称和调用额度。"
        if ai_failed else (tweet.get("ai_translation") or "暂无翻译")
    )
    tweet["display_analysis"] = (
        "AI解析未完成。推文已成功抓取，但大模型调用失败。"
        if ai_failed else (tweet.get("ai_analysis") or "暂无解读")
    )
    return tweet

def date_filter_from_request():
    date_filter = request.args.get('date', '').strip()
    year = request.args.get('year', '').strip()
    month = request.args.get('month', '').strip()
    day = request.args.get('day', '').strip()

    if date_filter and not year:
        parts = date_filter.split("-")
        year = parts[0] if len(parts) > 0 else ""
        month = str(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else ""
        day = str(int(parts[2])) if len(parts) > 2 and parts[2].isdigit() else ""

    if not date_filter and year:
        date_parts = [year.zfill(4)]
        if month:
            date_parts.append(month.zfill(2))
        if day:
            date_parts.append(day.zfill(2))
        date_filter = "-".join(date_parts)

    return date_filter, year, month, day

def available_date_parts(tweets):
    dates = [tweet.get("published_date") or publish_date_key(tweet) for tweet in tweets]
    years = sorted({date[:4] for date in dates if len(date) >= 4}, reverse=True)
    if not years:
        years = [str(datetime.now().year)]
    return {
        "years": years,
        "months": [str(month) for month in range(1, 13)],
        "days": [str(day) for day in range(1, 32)],
    }

# 配置文件路径
CONFIG_FILE = "config.json"

@app.context_processor
def inject_app_name():
    return {"app_name": APP_NAME}

def load_config():
    """加载配置文件"""
    default_config = {
        "TWITTER_API_KEY": "",
        "LLM_URL": "",
        "LLM_MODEL": "",
        "LLM_API_KEY": "",
        "TARGET_ACCOUNTS": ["OpenAI"],
        "CHECK_INTERVAL": 300,
        "INITIAL_HOURS": 2,
        "EXCLUDE_REPLIES": False
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置以确保所有键都存在
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except json.JSONDecodeError:
            return default_config
    return default_config

def save_config(config):
    """保存配置文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def normalize_account_name(account):
    """统一账号格式，支持 @handle 和个人主页 URL。"""
    account = str(account or "").strip()
    if account.startswith(("https://x.com/", "https://twitter.com/")):
        account = account.rstrip("/").split("/")[-1]
    return account.lstrip("@").lower()

def get_configured_accounts():
    """返回当前配置的监控账号列表。"""
    accounts = load_config().get("TARGET_ACCOUNTS", [])
    if isinstance(accounts, str):
        accounts = [account.strip() for account in accounts.split(",") if account.strip()]
    return accounts

def filter_tweets_for_config(tweets):
    """只展示当前配置账号的推文，避免旧样例数据混入首页。"""
    accounts = get_configured_accounts()
    if not accounts:
        return tweets

    account_names = {normalize_account_name(account) for account in accounts}
    return [
        tweet for tweet in tweets
        if normalize_account_name(tweet.get("author", "")) in account_names
    ]

def get_stored_tweets():
    """读取本地已保存的推文。"""
    if monitor_instance:
        return monitor_instance.get_all_tweets()

    temp_monitor = TwitterAIMonitor("", "", "", "")
    return temp_monitor.get_all_tweets()

def get_visible_tweets():
    """读取当前配置账号对应的本地推文。"""
    return filter_tweets_for_config(get_stored_tweets())

def sync_processed_tweets_count(tweets=None):
    """让状态面板的处理总数和本地持久化数据保持一致。"""
    if tweets is None:
        tweets = get_visible_tweets()

    stored_count = len(tweets)
    current_count = monitoring_status.get("processed_tweets") or 0
    if monitoring_status.get("running"):
        monitoring_status["processed_tweets"] = max(current_count, stored_count)
    else:
        monitoring_status["processed_tweets"] = stored_count
    return monitoring_status["processed_tweets"]

def start_monitoring():
    """启动监控"""
    global monitor_instance, monitoring_status
    
    config = load_config()
    
    required_fields = ["TWITTER_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        return False, f"请先配置: {', '.join(missing_fields)}"

    if monitoring_status.get("running"):
        return False, "监控已经在运行中"
    
    try:
        monitor_instance = TwitterAIMonitor(
            config["TWITTER_API_KEY"],
            config["LLM_URL"],
            config["LLM_API_KEY"],
            config["LLM_MODEL"]
        )
        initial_processed_tweets = len(get_visible_tweets())

        monitoring_status.update({
            "running": True,
            "last_update": datetime.now().isoformat(),
            "current_status": "正在初始化...",
            "processed_tweets": initial_processed_tweets,
            "current_account": "",
            "next_check_time": None,
            "last_result": "等待首次扫描"
        })
        
        # 在新线程中启动监控
        def monitor_worker():
            try:
                # 获取是否排除回复的配置，默认为False
                exclude_replies = config.get("EXCLUDE_REPLIES", False)

                monitor_instance.monitor_and_process_with_status(
                    config["TARGET_ACCOUNTS"],
                    config["CHECK_INTERVAL"],
                    config["INITIAL_HOURS"],
                    monitoring_status,
                    exclude_replies
                )
            except Exception as e:
                monitoring_status.update({
                    "running": False,
                    "last_update": datetime.now().isoformat(),
                    "current_status": "监控线程异常停止",
                    "last_result": f"错误: {str(e)}"
                })
        
        global monitor_thread
        monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        monitor_thread.start()

        return True, "监控已启动"
        
    except Exception as e:
        return False, f"监控启动失败: {str(e)}"

def stop_monitoring():
    """停止监控"""
    global monitoring_status, monitor_instance, monitor_thread
    
    # 设置状态为停止
    monitoring_status["running"] = False
    monitoring_status["current_status"] = "已停止"
    monitoring_status["current_account"] = ""
    monitoring_status["next_check_time"] = None
    
    # 等待线程结束（最多等待3秒）
    if monitor_thread and monitor_thread.is_alive():
        try:
            monitor_thread.join(timeout=3)
        except Exception as e:
            print(f"停止监控线程时出错: {str(e)}")
    
    # 重置监控实例
    monitor_instance = None
    monitor_thread = None
    
    return True, "监控已停止"

@app.route('/')
def index():
    """首页"""
    # 获取筛选参数
    author_filter = request.args.get('author', '')
    date_filter, current_year, current_month, current_day = date_filter_from_request()
    
    # 获取当前配置账号对应的推文数据
    all_tweets = [enrich_tweet_times(tweet) for tweet in get_visible_tweets()]
    sync_processed_tweets_count(all_tweets)
    filtered_tweets = all_tweets
    
    if author_filter:
        filtered_tweets = [
            t for t in filtered_tweets
            if normalize_account_name(t.get('author', '')) == normalize_account_name(author_filter)
        ]
    
    if date_filter:
        filtered_tweets = [t for t in filtered_tweets if t.get('published_date', '').startswith(date_filter)]
    
    # 作者筛选项优先来自当前配置，即使首次扫描没有新推文也能看到目标账号
    configured_accounts = get_configured_accounts()
    authors = sorted(set(configured_accounts + [t.get('author', '') for t in all_tweets if t.get('author')]))
    date_parts = available_date_parts(all_tweets)
    
    # 更新监控状态中的时间为北京时间
    if monitoring_status.get('last_update'):
        monitoring_status['beijing_last_update'] = utc_to_beijing(monitoring_status['last_update'])
    
    if monitoring_status.get('next_check_time'):
        monitoring_status['beijing_next_check_time'] = utc_to_beijing(monitoring_status['next_check_time'])
    
    return render_template('index.html', 
                         tweets=filtered_tweets, 
                         authors=authors,
                         current_author=author_filter,
                         current_date=date_filter,
                         current_year=current_year,
                         current_month=current_month,
                         current_day=current_day,
                         date_parts=date_parts,
                         monitoring_status=monitoring_status)

@app.route('/tweet/<tweet_id>')
def tweet_detail(tweet_id):
    """推文详情页"""
    # 获取所有推文数据
    if monitor_instance:
        all_tweets = monitor_instance.get_all_tweets()
    else:
        temp_monitor = TwitterAIMonitor("", "", "")
        all_tweets = temp_monitor.get_all_tweets()
    
    # 查找指定ID的推文
    tweet = None
    for t in all_tweets:
        if t.get('id') == tweet_id:
            tweet = t
            break
    
    if not tweet:
        return "推文未找到", 404
    enrich_tweet_times(tweet)
    return render_template('tweet_detail.html', tweet=tweet, monitoring_status=monitoring_status)

@app.route('/settings')
def settings():
    """个人中心/设置页面"""
    config = load_config()
    sync_processed_tweets_count()
    return render_template('settings.html', config=config, monitoring_status=monitoring_status)

@app.route('/help')
def help_page():
    """使用说明页面"""
    return render_template('help.html', monitoring_status=monitoring_status)

@app.route('/api/save_config', methods=['POST'])
def save_config_api():
    """保存配置API"""
    try:
        if request.content_type == 'application/json':
            config = request.json
        else:
            # 处理表单数据
            config = request.form.to_dict()
        
        if not config:
            return jsonify({"success": False, "message": "未接收到配置数据"})
        
        # 验证必要字段
        required_fields = ['TWITTER_API_KEY', 'LLM_URL', 'LLM_MODEL', 'LLM_API_KEY']
        for field in required_fields:
            if not config.get(field):
                return jsonify({"success": False, "message": f"{field} 不能为空"})
        
        # 确保TARGET_ACCOUNTS是列表
        if isinstance(config.get('TARGET_ACCOUNTS'), str):
            config['TARGET_ACCOUNTS'] = [acc.strip() for acc in config['TARGET_ACCOUNTS'].split(',') if acc.strip()]
        
        # 转换数字字段
        if 'CHECK_INTERVAL' in config:
            config['CHECK_INTERVAL'] = int(config['CHECK_INTERVAL']) if config['CHECK_INTERVAL'] else 300
        if 'INITIAL_HOURS' in config:
            config['INITIAL_HOURS'] = int(config['INITIAL_HOURS']) if config['INITIAL_HOURS'] else 2
        config['EXCLUDE_REPLIES'] = bool(config.get('EXCLUDE_REPLIES'))
        
        save_config(config)
        return jsonify({"success": True, "message": "配置已保存"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"配置保存失败: {str(e)}"})

@app.route('/api/start_monitoring', methods=['POST'])
def start_monitoring_api():
    """启动监控API"""
    success, message = start_monitoring()
    return jsonify({"success": success, "message": message})

@app.route('/api/stop_monitoring', methods=['POST'])
def stop_monitoring_api():
    """停止监控API"""
    success, message = stop_monitoring()
    return jsonify({"success": success, "message": message})

@app.route('/api/monitoring_status')
def monitoring_status_api():
    """获取监控状态API"""
    sync_processed_tweets_count()
    return jsonify(monitoring_status)

@app.route('/api/tweets')
def tweets_api():
    """获取推文数据API"""
    author = request.args.get('author', '')
    date, _, _, _ = date_filter_from_request()
    
    # 只返回当前配置账号的数据，避免首页轮询继续看到旧样例数据
    all_tweets = [enrich_tweet_times(tweet) for tweet in get_visible_tweets()]
    sync_processed_tweets_count(all_tweets)
    filtered_tweets = all_tweets
    
    if author:
        filtered_tweets = [
            t for t in filtered_tweets
            if normalize_account_name(t.get('author', '')) == normalize_account_name(author)
        ]
    
    if date:
        filtered_tweets = [t for t in filtered_tweets if t.get('published_date', '').startswith(date)]
    
    return jsonify(filtered_tweets)

if __name__ == '__main__':
    # 确保必要的目录存在
    os.makedirs('data', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)

    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')

    app.run(debug=debug, host=host, port=port, use_reloader=False)
