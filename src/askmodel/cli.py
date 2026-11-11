from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import colorama
colorama.init()
class FakeConsole:
    def print(self, *args, **kwargs):
        # 把你原本用的标签替换成原生 ANSI 颜色码
        text = " ".join(str(a) for a in args)
        text = text.replace("[bold cyan]", "\033[1;36m")
        text = text.replace("[bold yellow]", "\033[1;33m")
        text = text.replace("[bold green]", "\033[1;32m")
        text = text.replace("[red]", "\033[91m")
        text = text.replace("[green]", "\033[92m")
        text = text.replace("[yellow]", "\033[93m")
        text = text.replace("[cyan]", "\033[96m")
        text = text.replace("[dim]", "\033[2m")
        text = text.replace("[bold]", "\033[1m")
        text = text.replace("[/]", "\033[0m")
        print(text, **kwargs)

console = FakeConsole()

from .client import ChatError, ModelClient, parse_ops
from .models import (
    CallRecord,
    ConversationRecord,
    FileOp,
    Mode,
    ModelConfig,
    OpResult,
    ProjectConfig,
    RecentEntry,
)
from .scanner import scan_tree
from .store import Store
from .writer import execute_op

app = typer.Typer(no_args_is_help=False, add_completion=False)
project_app = typer.Typer(no_args_is_help=False)
config_app = typer.Typer(no_args_is_help=False)

HELP_TREE = """askmodel - AI 辅助项目开发 CLI

项目：
  askmodel project                       查看当前项目
  askmodel project show                  列出所有项目
  askmodel project to <name>             切换/创建项目
  askmodel project del <name>            删除项目
  askmodel project flash                 清空当前项目的记忆（work和chat分开）
  askmodel project mode [work|chat]      查看/修改当前项目的模式
  askmodel project main  [--base_url --model_name --api_key]
  askmodel project asit  [--base_url --model_name --api_key]

目录与对话：
  askmodel to <dir>                      切换 askmodel 当前目录字段
  askmodel do <自然语言>                  对话（work 模式多轮确认 / chat 模式单轮）
  askmodel immersion                     沉浸式（%out 退出）
  askmodel history [-v] [-n 数量] [-m 模式] 查看历史输入输出记录

全局配置：
  askmodel config                        查看全局配置
  askmodel config mode [work|chat]       查看/修改全局默认模式
  askmodel config main  [--base_url --model_name --api_key] [--flash]
  askmodel config asit  [--base_url --model_name --api_key] [--flash]
  askmodel config max_times <n>          单次对话模型调用上限（默认 3）
"""


def get_store() -> Store:
    return Store()


def resolve_model(store: Store, which: str = "main", required: bool = True) -> Optional[ModelConfig]:
    project = store.get_current_project()
    pcfg = store.load_project_config(project)
    cfg = getattr(pcfg, which)
    if not cfg or not cfg.base_url or not cfg.model_name:
        if required:
            label = "主" if which == "main" else "辅"
            raise RuntimeError(
                f"项目 {project} 未配置{label}模型，请先执行："
                f"askmodel project {which} --base_url ... --model_name ... --api_key ..."
            )
        return None
    return cfg

def get_current_mode(store: Store) -> Mode:
    project = store.get_current_project()
    if project:
        pcfg = store.load_project_config(project)
        if pcfg.mode:
            return pcfg.mode
    return store.load_config().mode

def build_system_prompt(mode: Mode, cwd: Path) -> str:
    if mode == Mode.CHAT:
        return (
            "你是askmodel，处于chat状态的一个闲聊助手。请用自然语言直接回答用户。\n"
        )
    return (
        "你是 askmodel，处于work状态的一个 AI 编程助手。\n"
        f"当前工作目录：{cwd}\n"
        "你必须只输出一个 JSON 数组，不要输出任何其他内容。\n"
        "可用 action：\n"
        '- read: {"action":"read","path":"相对路径","reason":"为什么读"}\n'
        '- write: {"action":"write","path":"相对路径","content":"文件内容","reason":"为什么写"}（如果要创建文件、空文件、或修改文件，必须用 write！write 会自动创建不存在的目录和文件！）\n'
        '- part_modify: {"action":"part_modify","path":"相对路径","original":"要替换的原文","current":"新内容","near_line":行号可选,"reason":"为什么改"}\n'
        '- delete: {"action":"delete","path":"相对路径","reason":"为什么删"}\n'
        '- chat: {"action":"chat","content":"自然语言说明"}（用于解释、感想、对话）\n'
        "【如果你需要创建一个空文件夹或文件，可使用write动作在目标路径写空白内容】\n"
        "【路径必须相对当前工作目录，不能越界】\n"
        "【严正警告】\n"
        "1. 你只能生成代码和文件，绝对无法执行代码！禁止假装自己要运行文件。\n"
        "2. 你的输出只是指令，需要用户按回车确认后才会生效。所以你绝对不能在一轮里刚写完文件，就立刻去 read 这个文件！\n"
        "【执行策略：先全面阅读，后批量操作】\n"
        "1. 请先查看'当前目录文件树'，自行判断哪些文件与用户的需求相关。\n"
        "2. 如果需要读取多个文件，请在【同一轮】输出包含多个 read 动作的 JSON 数组，一次性读完。\n"
        "3. 在你认为获取了所有必要的文件内容之前，绝对不要发起 write 或 part_modify。\n"
        "4. 确认阅读完毕后，请在【同一轮】输出包含所有修改动作的 JSON 数组，一次性完成所有修改。\n"
        "5. 【极其重要】请仔细阅读'当前 read 结果'。如果该文件已经出现在那里，绝对不要再次发起 read！直接进入修改阶段！\n"
        "6. 【如何回答与结束】\n"
        "   - 如果用户要求解释、说明感想或提问，请使用 chat 动作。\n"
        "   - 如果你需要同时修改文件并说话，请把它们放在同一个数组里。\n"
        "   - 如果你已经完成了所有修改，且还有话要说（比如感言），请在【下一轮】单独输出一个 chat 动作。\n"
        "   - 如果你彻底没活了，请输出 [] 结束对话。"
    )


def format_recent(recent: list[RecentEntry]) -> str:
    if not recent:
        return ""
    parts = []
    for i, e in enumerate(recent, 1):
        parts.append(f"[{i}] ({e.mode.value})\n用户：{e.user_input}\n模型：{e.model_output}")
    return "\n\n".join(parts)


def build_user_message(
    summary: str,
    recent: list[RecentEntry],
    tree: str,
    user_input: str,
    read_results: dict[str, str],
    other_results: list[str],
) -> str:
    parts = []
    if summary:
        parts.append(f"## 历史摘要\n{summary}")
    r = format_recent(recent)
    if r:
        parts.append(f"## 最近对话\n{r}")
    
    if tree:
        parts.append(f"## 当前目录文件树\n{tree}")
        
    read_block = ["## 当前 read 结果"]
    if not read_results:
        read_block.append("（暂无）")
    else:
        for path, content in read_results.items():
            read_block.append(f"=== {path} 的完整内容如下 ===")
            read_block.append(content)
            read_block.append(f"=== {path} 内容结束 ===")
    parts.append("\n".join(read_block))
    
    if other_results:
        parts.append("## 上一轮执行结果\n" + "\n".join(other_results))
        
    parts.append(f"## 用户输入\n{user_input}")
    return "\n\n".join(parts)


def show_content(op: FileOp) -> None:
    if op.action == "write":
        console.print("[bold]content:[/]")
        console.print(op.content or "(空)")
    elif op.action == "part_modify":
        console.print("[bold]original:[/]")
        console.print(op.original or "(空)")
        console.print("[bold]current:[/]")
        console.print(op.current or "(空)")


def confirm_op(op: FileOp) -> tuple[bool, Optional[int]]:
    if op.action == "chat":
        console.print(op.content or "")
        return True, None

    header = f"[bold cyan]{op.action}[/] {op.path or ''}"
    if op.reason:
        header += f"  [dim]{op.reason}[/]"
    console.print(header)
    if op.action in ("write", "part_modify"):
        console.print("[dim]输入 s 查看内容[/]")

    hints = ["回车/y=执行", "n=拒绝"]
    if op.action == "read":
        hints.append("数字=限制读行数")
    console.print("[dim]" + "  ".join(hints) + "[/]")

    while True:
        try:
            ans = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return False, None

        if ans == "" or ans.lower() == "y":
            return True, None
        if ans.lower() == "n":
            return False, None
        if ans.lower() == "s" and op.action in ("write", "part_modify"):
            show_content(op)
            continue
        if ans.isdigit() and op.action == "read":
            return True, int(ans)
        console.print("[red]无效输入[/]")


def apply_read_limit(content: str, limit: Optional[int]) -> str:
    if not limit:
        return content
    lines = content.split("\n")
    if len(lines) <= limit:
        return content
    return "\n".join(lines[:limit]) + f"\n... (已截断，只读前 {limit} 行，原文共 {len(lines)} 行)"


def next_summary_index(summary_text: str) -> int:
    n = 0
    for line in summary_text.split("\n"):
        if line.startswith("第") and "次对话：" in line:
            n += 1
    return n + 1


def maybe_summarize(store: Store, old_entry: RecentEntry, mode: Mode) -> None:
    try:
        asit_cfg = resolve_model(store, "asit", required=False)
        if not asit_cfg:
            return
        client = ModelClient(asit_cfg)
        
        # 1. 为刚被挤出去的对话生成单条摘要
        text = f"用户输入：{old_entry.user_input}\n模型输出：{old_entry.model_output}"
        system = "你是一个摘要助手。用一段简洁的中文概括这次对话的主要内容、涉及的文件和关键决策。"
        result = client.chat(system, text)
        
        # 2. 读取现有摘要内容，判断当前行数
        summary_text = store.load_summary(mode)
        lines = [line for line in summary_text.split("\n") if line.strip()]
        idx = len(lines) + 1
        new_line = f"第{idx}次对话：{result.content.strip()}"
        
        # 3. 如果加上新的一条没超过 10 条，直接正常追加（原汁原味）
        if len(lines) + 1 <= 10:
            store.append_summary(new_line, mode)
            return
            
        # 4. 如果超过 10 条了，触发压缩
        console.print("[cyan]>>> 历史摘要过长，正在自动压缩旧摘要以节省上下文 <<<[/]")
        
        # 把现有的前 6 条加上新产生的这条（或者只拿前 6 条压缩）
        to_compress = "\n".join(lines[:6])
        rest = lines[6:]
        
        compress_system = "你是一个摘要压缩助手。请把以下多段历史摘要，极简地合并概括成一段话。只保留核心的架构决策和文件变动。"
        compressed_result = client.chat(compress_system, to_compress)
        
        # 5. 重组摘要内容：1条综合 + 后面的几条 + 刚生成的最新一条
        new_lines = [f"【前期综合摘要】：{compressed_result.content.strip()}"] + rest + [new_line]
        
        # 6. 此时必须覆写整个文件
        p = store.summary_path(mode)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        
    except Exception as e:
        console.print(f"[yellow]摘要或压缩失败（忽略）：{e}[/]")


def save_recent_with_summary(store: Store, entry: RecentEntry, mode: Mode) -> None:
    old = store.load_recent(mode)
    if len(old) >= 5:
        maybe_summarize(store, old[0], mode)
    store.push_recent(entry, mode)


def run_work_conversation(store: Store, user_input: str, mode: Mode) -> bool:
    project = store.get_current_project()
    cwd = store.get_current_dir()
    project_dir = store.ensure_project(project)
    backup_dir = project_dir / "backups"

    main_cfg = resolve_model(store, "main", required=True)
    assert main_cfg is not None
    client = ModelClient(main_cfg)

    gcfg = store.load_config()
    max_times = gcfg.max_times

    summary = store.load_summary(mode)
    recent = store.load_recent(mode)
    tree = scan_tree(cwd)
    system = build_system_prompt(mode, cwd)

    record = ConversationRecord(
        conversation_id=datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
        timestamp=datetime.now(),
        mode=mode,
        user_input=user_input,
        project=project,
        cwd=str(cwd),
    )

    read_results: dict[str, str] = {}
    other_results: list[str] = []
    finished = False
    api_failed = False
    read_history: set[str] = set()

    for round_idx in range(1, max_times + 1):
        user_msg = build_user_message(summary, recent, tree, user_input, read_results, other_results)
        
        try:
            result = client.chat(system, user_msg)
        except ChatError as e:
            console.print(f"[red]模型调用失败：{e}[/]")
            api_failed = True
            break

        try:
            ops = parse_ops(result.content)
        except ChatError as e:
            console.print(f"[yellow]JSON 解析失败，已反馈给模型重试：{e}[/]")
            other_results.append(f"上一轮你的输出 JSON 解析失败：{e}\n请重新输出合法 JSON 数组。")
            record.calls.append(CallRecord(
                round=round_idx, system_prompt=system, input_text=user_msg, thinking=result.thinking,
                output=[], op_results=[],
                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                cache_hit_tokens=result.cache_hit_tokens, elapsed=result.elapsed, raw=result.raw,
            ))
            continue

        op_results: list[OpResult] = []
        has_read = False
        
        written_paths_in_this_round = set()
        valid_ops = []
        for op in ops:
            if op.action in ("write", "part_modify") and op.path:
                written_paths_in_this_round.add(op.path)
                
            if op.action == "read" and op.path in written_paths_in_this_round:
                console.print(f"[yellow]提示：模型试图在同一轮读取刚修改的文件 {op.path}，已被自动拦截。[/]")
                other_results.append(f"[read {op.path}] 失败：你刚修改过该文件，禁止在此轮读取。")
                continue
            valid_ops.append(op)
            
        ops = valid_ops

        if len(ops) > 1:
            console.print(f"[cyan]>>> 模型一次返回了 {len(ops)} 个有效操作，请依次确认 <<<[/]")
            
        for op in ops:
            if op.action == "read":
                has_read = True
                if op.path in read_history:
                    console.print(f"[yellow]提示：模型试图重复读取 {op.path}，已被拦截。[/]")
                    op_results.append(OpResult(action="read", path=op.path, ok=False, message="你已读过该文件，禁止重复读取。"))
                    other_results.append(f"[read {op.path}] 失败：你已经在之前读过了该文件，禁止重复读取。请直接修改或结束对话。")
                    continue
                read_history.add(op.path)

            ok, limit = confirm_op(op)
            if not ok:
                r = OpResult(action=op.action, path=op.path, ok=False, message="用户拒绝")
                op_results.append(r)
                other_results.append(f"[{op.action} {op.path or ''}] 用户拒绝")
                continue

            r = execute_op(op, cwd, backup_dir)
            
            if op.action == "read" and r.ok and r.content is not None:
                r.content = apply_read_limit(r.content, limit)
                read_results[op.path] = r.content
                lines_count = len(r.content.split("\n"))
                console.print(f"[green]✓ 已读取 {op.path}（共 {lines_count} 行，已加入上下文）[/]")
            
            elif op.action == "chat":
                pass
                
            else:
                if r.ok:
                    other_results.append(f"[{op.action} {op.path or ''}] 执行成功")
                else:
                    other_results.append(f"[{op.action} {op.path or ''}] 失败：{r.message}")
                    console.print(f"[red]{op.action} {op.path or ''} 失败：{r.message}[/]")

            op_results.append(r)

        record.calls.append(CallRecord(
            round=round_idx, system_prompt=system, input_text=user_msg, thinking=result.thinking,
            output=ops, op_results=op_results,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            cache_hit_tokens=result.cache_hit_tokens, elapsed=result.elapsed, raw=result.raw,
        ))

        if not has_read:
            finished = True
            break

    if not finished:
        if api_failed:
            console.print("[yellow]因模型 API 错误，本次对话提前中断[/]")
        else:
            console.print(f"[yellow]达到最大调用次数 {max_times} 仍未结束，本次对话失败[/]")

    store.append_conversation(record)
    
    valid_outputs = [op.model_dump(exclude_none=True) for c in record.calls for op in c.output]
    if valid_outputs:
        model_output_text = json.dumps(valid_outputs, ensure_ascii=False)
        save_recent_with_summary(
            store,
            RecentEntry(mode=mode, user_input=user_input, model_output=model_output_text),
            mode
        )
    return finished


def run_chat_conversation(store: Store, user_input: str) -> None:
    project = store.get_current_project()
    main_cfg = resolve_model(store, "main", required=True)
    assert main_cfg is not None
    client = ModelClient(main_cfg)

    cwd = store.get_current_dir()
    system = build_system_prompt(Mode.CHAT, cwd)
    
    user_msg = build_user_message(
        store.load_summary(Mode.CHAT), 
        store.load_recent(Mode.CHAT), 
        "", 
        user_input, {}, []
    )

    record = ConversationRecord(
        conversation_id=datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
        timestamp=datetime.now(), mode=Mode.CHAT,
        user_input=user_input, project=project, cwd=str(cwd),
    )

    try:
        result = client.chat(system, user_msg)
    except ChatError as e:
        console.print(f"[red]模型调用失败：{e}[/]")
        return

    console.print(result.content)

    record.calls.append(CallRecord(
        round=1, system_prompt=system, input_text=user_msg, thinking=result.thinking,
        output=[], op_results=[],
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        cache_hit_tokens=result.cache_hit_tokens, elapsed=result.elapsed, raw=result.raw,
    ))
    store.append_conversation(record)
    save_recent_with_summary(
        store,
        RecentEntry(mode=Mode.CHAT, user_input=user_input, model_output=result.content),
        Mode.CHAT
    )


@app.callback(invoke_without_command=True)
def main_cb(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print(HELP_TREE)
        raise typer.Exit()


@app.command("to")
def to_cmd(directory: str = typer.Argument(..., help="目标目录（相对当前 cwd 或绝对路径）")) -> None:
    store = get_store()
    p = Path(directory).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if not p.exists() or not p.is_dir():
        console.print(f"[red]目录不存在：{p}[/]")
        raise typer.Exit(1)
    store.set_current_dir(p)
    console.print(f"当前目录已切换为：{p}")


@app.command("do")
def do_cmd(requirement: str = typer.Argument(..., help="用户需求")) -> None:
    store = get_store()
    text = requirement.strip()
    if not text:
        console.print("[red]需求不能为空[/]")
        raise typer.Exit(1)
    
    if len(text) == 1:
        console.print("[red]单字符输入可能为误触，已取消[/]")
        raise typer.Exit(1)

    mode = get_current_mode(store)
    try:
        if mode == Mode.CHAT:
            run_chat_conversation(store, text)
        else:
            run_work_conversation(store, text, mode)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command("immersion")
def immersion_cmd() -> None:
    store = get_store()
    mode = get_current_mode(store)
    try:
        resolve_model(store, "main", required=True)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    console.print(f"[green]进入沉浸式（{mode.value}），输入 %out 退出[/]")
    while True:
        cwd = store.get_current_dir()
        try:
            line = input(f"[{mode.value}]{cwd}> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        s = line.strip()
        if s == "%out":
            break
        if not s:
            continue
        try:
            if mode == Mode.CHAT:
                run_chat_conversation(store, s)
            else:
                run_work_conversation(store, s, mode)
        except RuntimeError as e:
            console.print(f"[red]{e}[/]")


@app.command("history")
def history_cmd(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示完整输入输出"),
    limit: int = typer.Option(1, "--limit", "-n", help="显示最近几次对话"),
    mode_str: str = typer.Option("work", "--mode", "-m", help="查看 work 还是 chat 的历史")
) -> None:
    store = get_store()
    project = store.get_current_project()
    
    if mode_str not in ("work", "chat"):
        console.print("[red]mode 只能是 work 或 chat[/]")
        return
    mode = Mode(mode_str)

    hdir = store.history_dir(mode, project)
    if not hdir.exists():
        console.print(f"[yellow]暂无 {mode_str} 历史记录[/]")
        return
    
    files = sorted(hdir.glob("*.json"), reverse=True)
    records = []
    for f in files:
        arr = json.loads(f.read_text(encoding="utf-8"))
        for item in reversed(arr):
            records.append(item)
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break
    
    if not records:
        console.print("[yellow]暂无历史记录[/]")
        return

    for rec in reversed(records):
        console.print(f"[bold cyan]时间:[/] {rec['timestamp']}  [bold cyan]模式:[/] {rec['mode']}  [bold cyan]ID:[/] {rec['conversation_id']}")
        console.print(f"[bold green]用户输入:[/] {rec['user_input']}")
        for i, call in enumerate(rec.get('calls', []), 1):
            console.print(f"\n  [bold yellow]--- 第 {i} 次调用 ---[/]")
            console.print(f"  [dim]耗时: {call.get('elapsed', 0):.2f}s | 输入 Token: {call.get('input_tokens')} | 输出 Token: {call.get('output_tokens')}[/]")
            if verbose:
                console.print("  [bold]System Prompt:[/]")
                console.print(f"  {call.get('system_prompt', '')}")
                console.print("  [bold]User Message (发给模型的内容):[/]")
                console.print(f"  {call.get('input_text', '')}")
                console.print("  [bold]Raw Output (模型的原始返回):[/]")
                console.print(f"  {json.dumps(call.get('raw'), ensure_ascii=False, indent=2) if call.get('raw') else '无'}")
            else:
                outputs = call.get('output', [])
                if outputs:
                    console.print(f"  [bold]返回指令:[/] {[op['action'] for op in outputs]}")
                else:
                    console.print(f"  [bold]返回指令:[/] 无（可能解析失败或chat模式）")
        console.print("\n" + "="*50 + "\n")


app.add_typer(project_app, name="project")

@project_app.callback(invoke_without_command=True)
def project_cb(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print(f"当前项目：{get_store().get_current_project()}")


@project_app.command("to")
def project_to(name: str = typer.Argument(...)) -> None:
    store = get_store()
    
    if not store.project_dir(name).exists():
        store.ensure_project(name)
        gcfg = store.load_config()
        new_main = gcfg.main.model_copy(deep=True) if gcfg.main else None
        new_asit = gcfg.asit.model_copy(deep=True) if gcfg.asit else None
        
        # 保存项目配置
        store.save_project_config(ProjectConfig(main=new_main, asit=new_asit, mode=gcfg.mode), name)
        
        # 【新增这一行】强行把当前项目指针拨过去
        store.set_current_project(name)
        
        console.print(f"已创建并切换到项目：{name}（已自动继承全局配置副本）")
    else:
        store.set_current_project(name)
        console.print(f"已切换到项目：{name}")


@project_app.command("show")
def project_show() -> None:
    store = get_store()
    current = store.get_current_project()
    for n in store.list_projects():
        console.print(f"{n}{' *' if n == current else ''}")


@project_app.command("del")
def project_del(name: str = typer.Argument(...)) -> None:
    store = get_store()
    try:
        store.delete_project(name)  # store 里已经拦截了删除 default 的操作
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)
        
    if store.get_current_project() == name:
        # 【新增】如果删的是当前项目，自动切回 default
        store.set_current_project("default")
        console.print(f"已删除项目：{name}，当前项目已自动回退至 default")
    else:
        console.print(f"已删除项目：{name}")


@project_app.command("flash")
def project_flash() -> None:
    store = get_store()
    name = store.get_current_project()
    for mode in (Mode.WORK, Mode.CHAT):
        sp = store.summary_path(mode, name)
        rp = store.recent_path(mode, name)
        if sp.exists():
            sp.unlink()
        if rp.exists():
            rp.unlink()
    console.print(f"已清空项目 {name} 的记忆（work 和 chat 均已清空）")

@project_app.command("mode")
def project_mode(value: Optional[str] = typer.Argument(None)) -> None:
    store = get_store()
    project = store.get_current_project()
    
    if not project:
        console.print("[red]当前没有选择项目，请先使用 askmodel project to <name>[/]")
        raise typer.Exit(1)
        
    pcfg = store.load_project_config(project)
    
    if value is None:
        # 如果没有独立配置，就显示从全局继承来的模式
        current_mode = pcfg.mode or store.load_config().mode
        source = "项目配置" if pcfg.mode else "全局继承"
        console.print(f"项目 {project} 的当前模式：{current_mode.value}（来自{source}）")
        return
        
    if value not in ("work", "chat"):
        console.print("[red]模式只能是 work 或 chat[/]")
        raise typer.Exit(1)
        
    pcfg.mode = Mode(value)
    store.save_project_config(pcfg, project)
    console.print(f"项目 {project} 的模式已切换为：{value}")


def _project_model_cmd(which: str, base_url, model_name, api_key) -> None:
    store = get_store()
    name = store.get_current_project()
    pcfg = store.load_project_config(name)
    label = "主" if which == "main" else "辅"

    if base_url is None and model_name is None and api_key is None:
        cfg: Optional[ModelConfig] = getattr(pcfg, which)
        if not cfg:
            console.print(f"项目 {name} 的{label}模型：未配置")
            return
        console.print(f"项目 {name} 的{label}模型：")
        for k, v in cfg.masked().items():
            console.print(f"  {k}: {v}")
        return

    old_cfg = getattr(pcfg, which)
    new_base = base_url if base_url is not None else (old_cfg.base_url if old_cfg else None)
    new_name = model_name if model_name is not None else (old_cfg.model_name if old_cfg else None)
    new_key = api_key if api_key is not None else (old_cfg.api_key if old_cfg else "")

    if not new_base or not new_name:
        console.print("[yellow]提示：配置不完整，此时执行 do 会报错。[/]")

    setattr(pcfg, which, ModelConfig(base_url=new_base or "", model_name=new_name or "", api_key=new_key or ""))
    store.save_project_config(pcfg, name)
    console.print(f"已更新项目 {name} 的{label}模型")


@project_app.command("main")
def project_main(
    base_url: Optional[str] = typer.Option(None, "--base_url"),
    model_name: Optional[str] = typer.Option(None, "--model_name"),
    api_key: Optional[str] = typer.Option(None, "--api_key"),
) -> None:
    _project_model_cmd("main", base_url, model_name, api_key)


@project_app.command("asit")
def project_asit(
    base_url: Optional[str] = typer.Option(None, "--base_url"),
    model_name: Optional[str] = typer.Option(None, "--model_name"),
    api_key: Optional[str] = typer.Option(None, "--api_key"),
) -> None:
    _project_model_cmd("asit", base_url, model_name, api_key)


app.add_typer(config_app, name="config")

@config_app.callback(invoke_without_command=True)
def config_cb(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        store = get_store()
        gcfg = store.load_config()
        console.print("全局默认配置：")
        console.print(f"  max_times: {gcfg.max_times}")
        console.print(f"  mode: {gcfg.mode.value}")
        console.print("  main: " + (json.dumps(gcfg.main.masked(), ensure_ascii=False) if gcfg.main else "未配置"))
        console.print("  asit: " + (json.dumps(gcfg.asit.masked(), ensure_ascii=False) if gcfg.asit else "未配置"))


def _config_model_cmd(which: str, base_url, model_name, api_key, flash) -> None:
    store = get_store()
    gcfg = store.load_config()
    label = "主" if which == "main" else "辅"
    cfg = getattr(gcfg, which)

    if flash:
        setattr(gcfg, which, None)
        store.save_config(gcfg)
        console.print(f"已清空默认{label}模型配置")
        return

    if base_url is None and model_name is None and api_key is None:
        if not cfg:
            console.print(f"默认{label}模型：未配置")
            return
        console.print(f"默认{label}模型：")
        for k, v in cfg.masked().items():
            console.print(f"  {k}: {v}")
        return

    new_base = base_url if base_url is not None else (cfg.base_url if cfg else None)
    new_name = model_name if model_name is not None else (cfg.model_name if cfg else None)
    new_key = api_key if api_key is not None else (cfg.api_key if cfg else "")

    if not new_base or not new_name:
        console.print("[red]首次配置必须同时提供 --base_url 和 --model_name[/]")
        raise typer.Exit(1)

    setattr(gcfg, which, ModelConfig(base_url=new_base, model_name=new_name, api_key=new_key or ""))
    store.save_config(gcfg)
    console.print(f"已更新默认{label}模型")


@config_app.command("main")
def config_main(
    base_url: Optional[str] = typer.Option(None, "--base_url"),
    model_name: Optional[str] = typer.Option(None, "--model_name"),
    api_key: Optional[str] = typer.Option(None, "--api_key"),
    flash: bool = typer.Option(False, "--flash"),
) -> None:
    _config_model_cmd("main", base_url, model_name, api_key, flash)


@config_app.command("asit")
def config_asit(
    base_url: Optional[str] = typer.Option(None, "--base_url"),
    model_name: Optional[str] = typer.Option(None, "--model_name"),
    api_key: Optional[str] = typer.Option(None, "--api_key"),
    flash: bool = typer.Option(False, "--flash"),
) -> None:
    _config_model_cmd("asit", base_url, model_name, api_key, flash)


@config_app.command("max_times")
def config_max_times(value: int = typer.Argument(...)) -> None:
    if value < 1:
        console.print("[red]max_times 必须 >= 1[/]")
        raise typer.Exit(1)
    store = get_store()
    gcfg = store.load_config()
    gcfg.max_times = value
    store.save_config(gcfg)
    console.print(f"max_times 已设为：{value}")

@config_app.command("mode")
def config_mode(value: Optional[str] = typer.Argument(None)) -> None:
    store = get_store()
    gcfg = store.load_config()
    
    if value is None:
        console.print(f"全局默认模式：{gcfg.mode.value}")
        return
        
    if value not in ("work", "chat"):
        console.print("[red]模式只能是 work 或 chat[/]")
        raise typer.Exit(1)
        
    gcfg.mode = Mode(value)
    store.save_config(gcfg)
    console.print(f"全局默认模式已切换为：{value}")