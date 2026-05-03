import os
from openai import OpenAI

def get_model_response(url: str, api_key: str, prompt: str, model: str) -> str:
    """
    调用 Qwen 模型返回文字内容

    :param url: 模型 base_url
    :param api_key: API Key
    :param prompt: 用户输入的文本
    :return: 模型返回的文字内容
    """
    client = OpenAI(
        api_key=api_key,
        base_url=url,
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        # 如果需要，可启用或禁用思考过程
        # extra_body={"enable_thinking": False},
    )

    # 只返回文字内容
    return completion.choices[0].message.content

if __name__ == "__main__":
    url = os.getenv("LLM_URL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    prompt = "你是谁？"

    if not all([url, api_key, model]):
        raise SystemExit("请先设置 LLM_URL、LLM_API_KEY 和 LLM_MODEL 环境变量")

    text = get_model_response(url, api_key, prompt, model)
    print(text)
