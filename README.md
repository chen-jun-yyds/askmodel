# askmodel

一个代码完全由 AI 编写，让 AI 直接在项目里生成/修改文件的命令行工具。

> [!CAUTION]
> **askmodel 没有撤回功能。**
> 模型写入或覆盖文件后，askmodel 不会保存历史版本，也无法撤销。
> **请自行用 Git 或其他版本管理工具管理项目**，例如每次 `to` 之前 `git commit`，
> 不满意时用 `git checkout` 或 `git reset` 恢复。

## 特性

- 扫描项目结构，生成上下文供模型理解
- 支持多项目隔离，每个项目独立的对话记忆
- 主模型写代码 + 小模型生成摘要，成本可控
- 路径安全：模型只能操作指定目录内的文件，无法越界
- 依赖提示：模型自动识别需要新增的包
- 无自动执行：只生成文件，运行交给你

## 安装

需要 Python 3.9+。

### 1. 安装 pipx

如果还没装 pipx：

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

`ensurepath` 会把 pipx 的命令目录加入 PATH。**运行后必须重开终端**，让 PATH 生效。

验证：

```bash
pipx --version
```

能看到版本号就说明装好了。

### 2. 安装 askmodel

```bash
cd 到项目目录
pipx install .
```

或者用 pip（这样askmodel文件夹不能移动）：

```bash
pip install -e .
```

### 3. 验证

重开终端后：

```bash
askmodel
```

看到用法提示就说明安装成功。如果提示"不是内部或外部命令"，说明 PATH 没生效，重开终端再试。

## 首次配置

askmodel 默认没有配置任何模型。首次使用前，先选一个 provider：

```bash
# 查看所有预设
askmodel providers

# 用预设配置主模型（以 DeepSeek 为例）
askmodel main deepseek --key sk-你的key
```

可选：配置小模型（以智谱 GLM-4-Flash 为例）用于生成项目摘要：

```bash
askmodel small zhipu --key 你的智谱key
```

**如果不配小模型**，askmodel 会回退使用主模型做摘要。

## 用法

### 项目管理

```bash
askmodel project                      # 查看当前项目
askmodel project myproject            # 切换到/创建 myproject
askmodel project show                 # 列出所有项目
askmodel project out myproject        # 移除项目，切回默认
```

### 扫描项目

```bash
askmodel scan                         # 标准扫描当前目录（限制字符数和文件数）
askmodel scan --deep                  # 全量扫描（不限字符数和文件数）
askmodel here "src" here "README.md" scan   # 扫描多个路径
askmodel flash                        # 清空当前项目的记忆
```

### 让模型生成文件

```bash
askmodel to 创建一个 test.py 输出 hello world
askmodel here "myproj" to 加一个日志模块
```

### 模型配置

```bash
askmodel main                         # 查看主模型配置
askmodel main deepseek --key sk-xxx   # 用预设切换
askmodel main --model deepseek-reasoner    # 只改模型，保留 key 和 base
askmodel main --key k --base b --model m   # 完全自定义
askmodel small                        # 查看小模型配置
askmodel providers                    # 列出所有预设 provider
```

## 配置文件

所有配置和记忆都保存在 `~/.askmodel/`，不会污染项目目录，也不会提交到 Git：

```
~/.askmodel/
  config.json           # 主模型配置
  small.json            # 小模型配置
  current_project       # 当前项目名
  projects/
    default/            # 默认项目
      scan_context.json # 扫描文本
      summary.md        # 项目理解摘要
      history.json      # 对话历史
    myproject/          # 自定义项目
```

## 工作流程

```
scan        → 扫描项目，结果写入当前项目的 scan_context.json
首次 to     → 扫描文本 ≥ 1000 字符时，用小模型生成摘要
            → 摘要 + 最近对话 + 你的需求 → 主模型 → 返回 JSON
            → 写入文件
            → 自动重扫并更新摘要
flash       → 清空当前项目的所有记忆
```

## 设计边界

- **不做自动执行**：模型生成代码后不自动运行，避免路径逃逸和其他安全风险
- **不做撤回**：版本管理交给 Git，askmodel 只负责生成
- **不做沙箱**：依赖你自己审查代码

## License

MIT