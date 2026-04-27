# 技术报告（供后续 Agent 接手）

生成时间：2026-04-26  
项目目录：`C:\Users\44156\Desktop\单词本`

## 1. 项目目标

这是一个本地网页版托福填词记单词工具。用户输入一个或多个英文单词后，系统调用大模型生成：

- 中文含义
- 10 条新托福风格填词例句
- 每条例句对应的正确答案 `answer`
- 每条例句用于显示的前缀 `visible_prefix`

随后用户可在网页中进行填词练习，系统会维护每个单词的“熟练度”。

## 2. 当前目录结构

- `app.py`：服务入口，启动 `ThreadingHTTPServer`
- `toefl_vocab/config.py`：默认模型配置、数据库路径、静态目录路径
- `toefl_vocab/server.py`：HTTP 路由与错误处理
- `toefl_vocab/llm.py`：大模型调用、提示词、并发生成、模型返回解析
- `toefl_vocab/store.py`：SQLite 持久化、词本 CRUD、练习抽题、熟练度更新
- `toefl_vocab/utils.py`：输入解析、遮词逻辑、前缀归一化、答案校验
- `static/index.html`：页面结构
- `static/app.js`：前端交互
- `static/styles.css`：样式
- `data/vocab.sqlite3`：本地数据库
- `requirements.txt`：第三方依赖
- `.gitignore`：已忽略 `data/`、虚拟环境、缓存文件

## 3. 启动方式

```powershell
cd C:\Users\44156\Desktop\单词本
python app.py --host 127.0.0.1 --port 8765
```

浏览器地址：

```text
http://127.0.0.1:8765
```

`app.py` 启动时会先调用 `init_db()`，因此数据库迁移逻辑是自动执行的。

## 4. 当前默认配置

定义于 `toefl_vocab/config.py`：

- 默认协议：`genai`
- 默认模型：`gemini-3-flash-preview-free`
- 默认 Base URL：`https://aihubmix.com/v1`
- 默认 API Key 环境变量：`AIHUBMIX_API_KEY`

前端会通过 `/api/status` 读取这些默认值并预填到表单。

## 5. 前后端整体流程

### 5.1 录词与生成

1. 用户在左侧输入多个单词，前端按回车换行或标点分隔。
2. 前端提交 `protocol / model / base_url / api_key / words` 到 `/api/generate`。
3. `server.py` 调用 `build_request_config()` 和 `generate_words()`。
4. `llm.py` 会把每个单词拆成独立请求，用 `ThreadPoolExecutor` 并发发送。
5. 每个词成功后返回结构化结果；失败的词只进入 `skipped`，不会拖垮整批。
6. `store.py/save_generated_items()` 将词、中文释义、例句、答案、前缀落库。

### 5.2 练习

1. 前端调用 `/api/practice/start`，传 `mode` 和 `n`。
2. 后端从数据库选出对应的 `n` 个单词，每个单词随机取 1 条例句。
3. `mask_sentence()` 根据 `answer + visible_prefix` 生成遮词题面。
4. 用户作答后调用 `/api/practice/check`。
5. 后端检查答案，并更新该单词的熟练度。

## 6. 已实现的核心规则

### 6.1 例句和答案

- 每个词要求生成 10 条可用例句。
- 每条例句单独存 `answer`，不再假设答案一定等于原始单词。
- 允许时态、单复数、三单、分词等屈折变化。
- `answer` 必须真实出现在 `sentence` 中。

### 6.2 字母提示规则

最新规则（2026-04-24 之后）：

- `visible_prefix` 必须是 `answer` 从首字母开始的连续前缀。
- 被遮挡的字母数必须 `>= answer 总字母数的一半`。
- 若总字母数为奇数，则按向上取整计算。

注意：这个约束不只写在提示词里，后端也强制执行。

- 提示词约束在 `toefl_vocab/llm.py`
- 兜底归一化逻辑在 `toefl_vocab/utils.py`

也就是说，即使模型返回了过长前缀，保存前也会被裁剪到合法长度。

### 6.3 熟练度

- 范围：`0` 到 `10`
- 新单词默认熟练度：`0`
- 答对：`+1`
- 答错：`-5`
- 超界时会被钳制回 `0-10`

### 6.4 练习模式

当前支持三种模式：

- `recent`：最近 `n` 个单词
- `random`：全词本随机 `n` 个单词
- `weak`：按熟练度从低到高选最不熟悉的 `n` 个单词

每个被选中的单词只抽一条例句参与当轮练习，最终再整体打乱。

## 7. 数据库结构

数据库文件：`data/vocab.sqlite3`

### `words`

- `id`
- `word_key`：小写唯一键
- `display_word`
- `chinese_meaning`
- `proficiency`
- `model`
- `created_at`
- `updated_at`

### `examples`

- `id`
- `word_id`
- `sentence`
- `answer`
- `visible_prefix`
- `created_at`

说明：

- `examples.word_id` 外键指向 `words.id`
- 删除单词会级联删除例句
- `init_db()` 里包含历史数据库的自动补列逻辑

## 8. API 概览

### `GET /api/status`

返回默认模型配置、支持的协议列表、词数与例句数。

### `GET /api/words`

返回当前词本列表。

### `POST /api/generate`

请求体核心字段：

- `words`
- `protocol`
- `model`
- `base_url`
- `api_key`

返回：

- `saved`
- `skipped`
- `word_count`
- `example_count`

### `POST /api/practice/start`

请求：

- `mode`
- `n`

返回本轮题目列表。

### `POST /api/practice/check`

请求：

- `example_id`
- `answer`
- `visible_prefix`

返回判题结果、标准答案、熟练度更新结果等。

### `DELETE /api/words/{id}`

删除单词及其例句。

## 9. 前端行为摘要

前端核心逻辑集中在 `static/app.js`：

- 页面加载时调用 `/api/status` 和 `/api/words`
- 支持三类协议：`openai / genai / anthropic`
- 输入答案时，下划线位置会实时显示字母
- 检查完成后可以按回车切到下一题
- 生成失败会在页面显示错误框，并把错误打印到浏览器控制台
- 部分单词生成失败时，会显示逐词失败原因，并把这些词保留在输入框里方便重试

## 10. LLM 调用层说明

`toefl_vocab/llm.py` 当前支持三种 SDK：

- `openai`
- `anthropic`
- `google-genai`

关键点：

- 每个单词是一个独立请求
- 默认并发数：`20`（环境变量 `LLM_MAX_WORKERS` 可改）
- 默认超时：`600` 秒（环境变量 `LLM_TIMEOUT_SECONDS` 可改）
- 如果某个词返回无法解析或请求失败，只跳过该词

## 11. 错误可观测性

当前错误链路已经打通：

- 后端：`server.py/send_error_json()` 会把错误摘要和 details 打印到控制台
- 前端：`static/app.js` 会把错误显示在页面上，并 `console.error(...)`
- 生成接口若仅部分失败，也会把逐词失败原因打印和展示

## 12. 当前 Git / 工作区状态

最近几次提交包括：

- `58a9800 更新`
- `92a71e6 Support multiple LLM providers`
- `17a4bdc 更新`
- `e2db220 Add proficiency-based practice`

截至 2026-04-26，工作区存在**未提交修改**：

- `toefl_vocab/llm.py`
- `toefl_vocab/utils.py`

这些未提交内容对应“被遮挡字母数至少为答案一半”的新规则。

## 13. 已知注意事项 / 风险

### 13.1 `/api/status` 当前会把默认 API Key 明文返回给前端

`server.py` 当前返回了：

- `default_api_key`
- `default_api_key_env`

这意味着只要浏览器打开页面，前端就能拿到当前默认 Key，并自动填进密码框。  
这是当前设计的一部分，但从安全角度看是一个明显的后续改进点。

### 13.2 本地数据库是持久化的

`data/vocab.sqlite3` 会长期保留词本。`data/` 已被 `.gitignore` 忽略，不会随仓库提交。

### 13.3 运行环境建议尽量独立

项目依赖是：

- `openai==2.32.0`
- `anthropic==0.96.0`
- `google-genai==1.73.1`

历史上在共享 Anaconda 环境中装这些库时，出现过 `pydantic` 相关警告。  
项目本身能运行，但如果未来环境问题变多，建议单独开虚拟环境。

## 14. 后续 Agent 接手建议

如果要继续开发，优先建议检查这几件事：

1. 是否要修正 `/api/status` 暴露默认 API Key 的问题
2. 是否要把技术报告里的最近未提交改动提交到 Git
3. 是否要补浏览器端或接口级自动化测试
4. 是否要继续强化前缀规则，例如加入词性、长度分层或更多托福题型约束

## 15. 一句话总结

这是一个“本地 Python + SQLite + 原生前端 + 多 LLM Provider”的托福填词词本工具；当前核心功能完整，可直接运行，后续维护重点在提示词演进、前缀规则、安全性和测试补齐。
