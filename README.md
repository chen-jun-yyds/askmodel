# askmodel

一个轻量、纯粹、可定制的终端 AI 编程助手。把你的想法和代码库直接交给大模型，让它帮你读代码、写代码、改代码。

askmodel 是一个基于命令行的 AI 助手。它通过与大模型（兼容 OpenAI 接口，如智谱 GLM、DeepSeek 等）进行交互，能够一次性读取多份文件、批量生成修改指令，并在你的确认下安全地执行文件操作。

## 核心特性

- 批量并发操作：大模型可以一次性输出多个 read 或 write 指令，无需来回确认，极大降低 Token 成本和等待时间。
- 绝对安全：所有文件操作（覆盖、修改、删除）在执行前都会交由用户二次确认；所有路径被严格限制在当前工作目录下，防止路径逃逸。
- 自动备份：在覆盖或删除文件前，自动将原文件备份到 ~/.askmodel/projects/<项目>/backups/，杜绝“AI 删库跑路”。
- 渐进式记忆：自动记录最近 5 轮对话和历史摘要；当摘要过长时，会自动调用辅模型进行“摘要压缩”，防止上下文爆炸。
- 双模式设计：work 模式专注代码生成与文件修改；chat 模式用于自然语言闲聊，两套记忆完全物理隔离。
- 多项目隔离：全局默认配置 + 项目独立配置，互不污染，不同项目拥有独立的记忆和模型配置。

## 安装

推荐使用 pipx 进行全局安装，保持系统环境干净。

如果你还没安装 pipx：
    py -m pip install --user pipx
    py -m pipx ensurepath

进入项目目录，进行全局安装：
    cd /d D:\venv-python\askmodel
    pipx install --editable .

开发者提示：使用 --editable 模式安装后，修改源码无需重新安装即可生效。如果后续不想修改了，可以使用 pipx install --force . 切换为普通模式。

## 快速开始

### 1. 配置模型
askmodel 兼容 OpenAI 格式的 API。你可以配置全局默认的主模型（用于干活）和辅模型（用于生成摘要）。
使用示例：
    askmodel config main --base_url "你的base_url" --model_name "你的model" --api_key "你的key"
    askmodel config asit --base_url "你的base_url" --model_name "你的model" --api_key "你的key"

### 2. 切换目录与项目
    :: 切换到你要操作的代码目录
    askmodel to "D:\my_project"

    :: 创建一个专属项目（会继承全局模型配置）
    askmodel project to my_agent

### 3. 开始对话
    askmodel do "帮我看看这个项目是做什么的"

此时，模型会输出 read 指令请求查看文件内容，你按回车确认后，它会在下一次回答中给出分析。

### 4. 沉浸式对话
如果你不想每次都敲 askmodel do，可以直接进入沉浸模式（输入 %out 退出）：
    askmodel immersion
    [work]D:\my_project> 帮我在 main.py 里加一个 print("Hello") 的测试
    [work]D:\my_project> %out

## 命令清单

- askmodel project：查看当前所在项目
- askmodel project show：列出所有项目
- askmodel project to <name>：切换/创建项目
- askmodel project del <name>：删除项目（default 为兜底项目，不可删除）
- askmodel project flash：清空当前项目的记忆（包括 work 和 chat 的记忆）
- askmodel project mode [work|chat]：查看/切换当前项目的运行模式
- askmodel to <dir>：切换 askmodel 的工作目录
- askmodel do <需求>：与模型对话并执行代码操作
- askmodel immersion：进入沉浸式对话（可输入 %out 退出）
- askmodel history [-v]：查看历史记录，加 -v 查看完整的 Prompt 和 Raw 响应
- askmodel config：查看全局默认配置
- askmodel config max_times <n>：修改单次对话中允许模型思考/调用指令的最大轮数

## 工作原理与数据存储

所有配置和历史数据均保存在 ~/.askmodel/ 目录下，卸载软件不会删除你的数据。

目录结构如下：
    ~/.askmodel/
    ├── config.json          # 全局默认模型配置与模式
    ├── current_project      # 记录当前所在项目
    ├── current_dir          # 记录当前所在目录
    └── projects/
        ├── default/         # 出厂兜底项目（永不可删）
        ├── my_agent/
        │   ├── project.json # 当前项目的独立模型配置
        │   ├── work/        # 工作模式的记忆
        │   │   ├── summary.md
        │   │   ├── recent.json
        │   │   └── history/ # 每日对话完整日志
        │   ├── chat/        # 闲聊模式的记忆
        │   └── backups/     # 文件被修改/删除前的备份

## JSON 指令协议

在 work 模式下，大模型会严格按照以下 JSON 数组格式返回指令，由 askmodel 解析并在用户确认后执行：

- 读取：{"action":"read","path":"相对路径","reason":"为什么读"}
- 全量写入：{"action":"write","path":"相对路径","content":"文件内容"}
- 局部替换：{"action":"part_modify","path":"相对路径","original":"原文","current":"新内容","near_line":行号}
- 创建文件夹：{"action":"create","path":"相对路径/","reason":"为什么创建"}
- 删除：{"action":"delete","path":"相对路径","reason":"为什么删"}
- 纯文本对话：{"action":"chat","content":"自然语言输出"}

## 进阶与开发

- 防幻觉机制：如果模型试图重复读取已读过的文件，或者在同一轮刚写完就立刻去读，程序会直接拦截并警告模型，强迫其推进任务。
- 摘要压缩机制：当 summary.md 超过 10 条记录时，会自动触发压缩，将最老的 6 条合并为 1 条【前期综合摘要】，在保留长期记忆的同时确保 Token 消耗可控。

构建你自己的 AI 工作流：
去修改 src/askmodel/cli.py 里的 build_system_prompt 函数，你可以完全定制 AI 的提示词，让它变成前端专家、爬虫专家，或者诗人。

---
Powered by Python & 你的想象力.