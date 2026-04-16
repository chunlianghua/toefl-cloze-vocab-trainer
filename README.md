# TOEFL Cloze Vocab Trainer

一个本地网页版托福填词记单词工具。输入单词后，程序会调用阿里云百炼生成中文含义和例句，并把词本保存在本地。

## Requirements

- Python 3.10+
- 阿里云百炼 API Key

本项目只使用 Python 标准库，不需要额外安装第三方 Python 包。

## Configure API Key

PowerShell 当前窗口临时设置：

```powershell
$env:ALIYUN_API_KEY="你的百炼 API Key"
```

也可以写入 Windows 用户环境变量：

```powershell
setx ALIYUN_API_KEY "你的百炼 API Key"
```

如果使用 `setx`，请重新打开 PowerShell 后再启动服务。

## Start

进入项目目录：

```powershell
cd C:\Users\44156\Desktop\单词本
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
2. 点击“生成并保存”，等待百炼返回中文含义和例句。
3. 在右侧选择“最近 n 词”或“随机 n 词”，点击“开始”练习。
4. 根据句子和已给出的单词开头字母，补全缺失部分。
