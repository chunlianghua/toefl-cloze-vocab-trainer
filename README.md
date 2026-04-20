# TOEFL Cloze Vocab Trainer

一个本地网页版托福填词记单词工具。输入单词后，程序会调用大模型生成中文含义和例句，并把词本保存在本地。

## Requirements

- Python 3.10+
- `openai`、`anthropic`、`google-genai` 这三个 Python SDK

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## Start

进入项目目录：

```powershell
cd path\to\toefl-cloze-vocab-trainer
```

启动本地服务：

```powershell
python app.py --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

## Usage

1. 在左侧输入单词。多个单词用回车换行分隔。
2. 选择协议类型，并填写模型名称、Base URL、API Key。
3. 点击“生成并保存”，等待模型返回中文含义和例句。
4. 在右侧选择练习模式，点击“开始”练习。支持最近单词、随机单词和最不熟悉单词三种模式。
5. 根据句子和已给出的单词开头字母，补全缺失部分。
6. 每个单词有 0 到 10 的熟练度；答对加 1，答错减 5，最不熟悉模式会优先选择低熟练度单词。

默认配置：

- 协议：`genai`
- 模型：`gemini-3-flash-preview-free`
- Base URL：`https://aihubmix.com/v1`
- API Key：优先读取系统变量 `AIHUBMIX_API_KEY`
