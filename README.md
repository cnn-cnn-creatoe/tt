# AI News 推文监控与 AI 解析系统

版本：v1.0
作者：nan
邮箱：3236606446@qq.com

这是一个基于 Flask 的 X/Twitter 推文监控工具。系统会按配置抓取指定账号的新推文，并调用兼容 OpenAI 格式的大模型接口生成中文标题、翻译和解读，最后通过网页界面展示。

## 主要功能

- 监控多个 X/Twitter 账号
- 支持排除回复类推文
- 调用大模型生成标题、翻译和解读
- 推文数据按日期保存到本地 `data/`
- 提供首页、详情页、设置页和帮助页
- Windows 支持一键启动、后台运行、一键关闭

## 快速启动

在 Windows 电脑上双击：

```bat
start.bat
```

脚本会自动完成这些事：

- 检查 Python 环境
- 如果没有 Python，会尝试通过 `winget` 安装 Python 3.12
- 创建本项目专用虚拟环境 `.venv`
- 缺少依赖时自动安装 `requirements.txt`
- 如果没有 `config.json`，自动从 `config.example.json` 生成一份本地配置
- 后台启动网站服务
- 自动打开 `http://127.0.0.1:5000`
- 启动完成后关闭命令行窗口

停止服务时双击：

```bat
end.bat
```

`end.bat` 会关闭本项目启动的后台服务，并清理 PID 记录。

## 首次配置

打开网站后进入「设置」页面，填写：

- `Twitter API Key`：用于从 TwitterAPI.io 获取推文
- `大模型接口地址`：兼容 OpenAI 调用格式的 Base URL，例如 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `大模型名称`：例如 `qwen-plus`
- `大模型 API Key`：用于 AI 翻译、标题和解读
- `监控账号`：每行或每个输入框填写一个账号名，不需要 `@`
- `检查间隔`：建议 300 秒或更高
- `初始回溯`：首次启动时向前抓取多少小时内的推文

保存配置后点击「启动监控」即可开始抓取和分析。

## 迁移到其他电脑

推荐使用项目根目录里的：

```bat
package.bat
```

它会生成：

```text
dist/AI-News-v1.0.zip
```

迁移包不会包含真实密钥、虚拟环境、日志、运行缓存和本地推文数据。迁移到另一台 Windows 电脑后，解压项目并双击 `start.bat` 即可自动配置并启动。

## 配置和密钥说明

真实配置文件是：

```text
config.json
```

这个文件只保存在本机，不会提交到 GitHub。仓库中只保留：

```text
config.example.json
```

如果换电脑运行，第一次启动会自动生成新的 `config.json`，然后在网页设置页重新填写密钥即可。

## 常用文件

```text
app.py                    Flask 主应用
twitter_ai_monitor.py     推文抓取与 AI 处理逻辑
tweets.py                 推文接口辅助模块
llm.py                    大模型调用辅助模块
templates/                页面模板
static/                   前端样式和脚本
requirements.txt          Python 依赖
start.bat                 Windows 一键配置并后台启动
end.bat                   Windows 一键关闭后台服务
package.bat               生成迁移压缩包
config.example.json       配置模板，不含密钥
data/                     本地推文数据目录
logs/                     本地运行日志目录
```

## 故障排查

如果 `start.bat` 启动失败，请查看：

```text
logs/install.log
logs/server.err.log
logs/server.out.log
```

常见原因：

- Python 未安装且当前系统没有 `winget`
- 网络无法下载依赖
- 5000 端口被其他程序占用
- API Key、Base URL 或模型名称填写错误

端口被占用时，先运行 `end.bat`。如果仍然占用，请关闭其他使用 5000 端口的程序，或修改 `start.bat` 中的 `PORT`。

## 发布记录

### v1.0

- 增加 Windows 一键配置和后台启动
- 增加 `end.bat` 一键停止后台服务
- 增加迁移包生成脚本
- 将真实密钥配置排除出 GitHub
- 补充完整使用教程和项目说明
