import json
import sys
from pathlib import Path

from . import config, scanner, api, executor, memory


def print_help():
    print("用法：")
    print("  askmodel                                     显示本提示")
    print()
    print("【项目】")
    print("  askmodel project                             显示当前项目")
    print("  askmodel project <name>                      切换到/创建项目")
    print("  askmodel project show                        列出所有项目")
    print("  askmodel project out <name>                  移除项目，切回默认")
    print()
    print("【扫描】")
    print("  askmodel scan                                标准扫描当前目录")
    print("  askmodel scan --deep                         全量扫描当前目录")
    print('  askmodel here "a" here "b" scan              标准扫描多个路径')
    print('  askmodel here "a" --deep here "b" scan       a 全量，b 标准')
    print('  askmodel here "a" here "b" scan --deep       所有路径全量')
    print("  askmodel flash                               清空当前项目记忆")
    print()
    print("【对话】")
    print("  askmodel to <需求>                           读摘要+记忆+对话 + 调模型")
    print('  askmodel here "dir" to <需求>                指定文件夹操作')
    print()
    print("【模型】")
    print("  askmodel main                                显示主模型配置")
    print("  askmodel main <provider> --key <k>           用预设切换主模型")
    print("  askmodel main --key <k> --base <b> --model <m>   自定义主模型")
    print("  askmodel small                               显示小模型配置")
    print("  askmodel small <provider> --key <k>          用预设切换小模型")
    print("  askmodel small --key <k> --base <b> --model <m>  自定义小模型")
    print("  askmodel providers                           列出所有预设 provider")
    print()
    print("说明：--deep 紧跟某个 here 路径时，只对该路径生效；")
    print("      出现在 scan 后面时，对所有路径生效。")


def parse_argv(argv: list):
    if not argv:
        return ("help", None, None, [], False)

    if argv[0] == "project":
        return ("project", None, None, argv[1:], False)

    if argv[0] == "main":
        return ("main", None, None, argv[1:], False)

    if argv[0] == "small":
        return ("small", None, None, argv[1:], False)

    if argv[0] == "providers":
        return ("providers", None, None, [], False)

    if argv[0] == "flash":
        return ("flash", None, None, [], False)

    if argv[0] == "scan":
        rest = argv[1:]
        deep = "--deep" in rest
        rest = [a for a in rest if a != "--deep"]
        if rest:
            print(f"错误：scan 后面不支持其他参数：{' '.join(rest)}")
            sys.exit(1)
        return ("scan", None, None, [(".", deep)], deep)

    if argv[0] == "to":
        return ("to", ".", " ".join(argv[1:]), [], False)

    if argv[0] == "here":
        paths = []
        i = 0
        action = None
        rest = []
        while i < len(argv):
            tok = argv[i]
            if tok == "here":
                if i + 1 >= len(argv):
                    print("错误：here 后面需要跟路径")
                    sys.exit(1)
                p = argv[i + 1]
                i += 2
                deep = False
                if i < len(argv) and argv[i] == "--deep":
                    deep = True
                    i += 1
                paths.append((p, deep))
            elif tok in ("scan", "to"):
                action = tok
                rest = argv[i + 1:]
                break
            else:
                print(f"错误：here 序列中出现未知 token：{tok}")
                sys.exit(1)

        if action is None:
            print("错误：here 序列后面需要跟 scan 或 to")
            sys.exit(1)

        if action == "scan":
            global_deep = "--deep" in rest
            rest = [a for a in rest if a != "--deep"]
            if rest:
                print(f"错误：scan 后面不支持其他参数：{' '.join(rest)}")
                sys.exit(1)
            if global_deep:
                paths = [(p, d or True) for (p, d) in paths]
            return ("scan", None, None, paths, global_deep)

        if action == "to":
            if len(paths) != 1:
                print("错误：to 时只能指定一个文件夹")
                sys.exit(1)
            return ("to", paths[0][0], " ".join(rest), [], False)

    print(f"错误：无法识别的语法：{' '.join(argv)}")
    print_help()
    sys.exit(1)


def resolve(directory: str) -> Path:
    p = Path(directory).expanduser()
    return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()


def parse_flags(args: list) -> dict:
    result = {}
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("--") and "=" in tok:
            name, val = tok[2:].split("=", 1)
            result[name] = val
            i += 1
        elif tok.startswith("--"):
            name = tok[2:]
            if i + 1 >= len(args):
                print(f"错误：{tok} 后面需要跟值")
                sys.exit(1)
            result[name] = args[i + 1]
            i += 2
        else:
            print(f"错误：无法识别的参数：{tok}")
            sys.exit(1)
    return result


# ---------- project ----------

def cmd_project(args: list):
    if not args:
        name = config.get_current_project()
        print(f"当前项目：{name}")
        return

    sub = args[0]

    if sub == "show":
        projects = config.list_projects()
        current = config.get_current_project()
        print("项目列表：")
        for p in projects:
            mark = "  * " if p == current else "    "
            suffix = "（默认）" if p == config.DEFAULT_PROJECT else ""
            print(f"{mark}{p}{suffix}")
        return

    if sub == "out":
        if len(args) < 2:
            print("错误：project out 后面需要跟项目名")
            return
        name = args[1]
        if name == config.DEFAULT_PROJECT:
            print("错误：默认项目不能移除")
            return
        if not config.project_exists(name):
            print(f"错误：项目 {name} 不存在")
            return
        was_current = (config.get_current_project() == name)
        config.remove_project(name)
        if was_current:
            config.set_current_project(config.DEFAULT_PROJECT)
            print(f"已移除项目 {name}，切换到默认项目")
        else:
            print(f"已移除项目 {name}")
        return

    name = sub
    if not config.project_exists(name):
        config.create_project(name)
        print(f"→ 已创建项目 {name}")
    config.set_current_project(name)
    print(f"→ 当前项目：{name}")


# ---------- main / small / providers ----------

def _show_model(cfg: dict, label: str):
    print(f"{label}：")
    print(f"  base_url: {cfg.get('base_url') or '(未配置)'}")
    print(f"  model:    {cfg.get('model') or '(未配置)'}")
    key = cfg.get("api_key", "")
    print(f"  api_key:  {'已设置' if key else '(未配置)'}")


def _apply_preset(cfg: dict, provider: str, key: str) -> bool:
    preset = config.PROVIDER_PRESETS.get(provider)
    if not preset:
        print(f"错误：未知 provider：{provider}")
        print(f"可用预设：{', '.join(config.PROVIDER_PRESETS.keys())}")
        return False
    cfg["api_key"] = key
    cfg["base_url"] = preset["base_url"]
    cfg["model"] = preset["model"]
    return True


def cmd_main(args: list):
    cfg = config.load()

    if not args:
        _show_model(cfg, "主模型配置")
        return

    if not args[0].startswith("--") and args[0] in config.PROVIDER_PRESETS:
        provider = args[0]
        flags = parse_flags(args[1:])
        if "key" not in flags:
            print(f"用法：askmodel main {provider} --key <api_key>")
            return
        if _apply_preset(cfg, provider, flags["key"]):
            config.save(cfg)
            preset = config.PROVIDER_PRESETS[provider]
            print(f"主模型已切换为 {provider}：{preset['base_url']} / {preset['model']}")
        return

    flags = parse_flags(args)
    changed = []
    if "key" in flags:
        cfg["api_key"] = flags["key"]
        changed.append("key")
    if "base" in flags:
        cfg["base_url"] = flags["base"]
        changed.append("base")
    if "model" in flags:
        cfg["model"] = flags["model"]
        changed.append("model")

    if not changed:
        print("用法：")
        print("  askmodel main --key <k> --base <b> --model <m>")
        print("  askmodel main <provider> --key <k>")
        return

    config.save(cfg)
    print(f"主模型已更新：{', '.join(changed)}")


def cmd_small(args: list):
    cfg = config.load_small_raw()

    if not args:
        _show_model(cfg, "小模型配置")
        # 提示是否回退到主模型
        if not config.is_configured(cfg):
            print("  （未配置完整时，将回退使用主模型）")
        return

    if not args[0].startswith("--") and args[0] in config.PROVIDER_PRESETS:
        provider = args[0]
        flags = parse_flags(args[1:])
        if "key" not in flags:
            print(f"用法：askmodel small {provider} --key <api_key>")
            return
        if _apply_preset(cfg, provider, flags["key"]):
            config.save_small(cfg)
            preset = config.PROVIDER_PRESETS[provider]
            print(f"小模型已切换为 {provider}：{preset['base_url']} / {preset['model']}")
        return

    flags = parse_flags(args)
    changed = []
    if "key" in flags:
        cfg["api_key"] = flags["key"]
        changed.append("key")
    if "base" in flags:
        cfg["base_url"] = flags["base"]
        changed.append("base")
    if "model" in flags:
        cfg["model"] = flags["model"]
        changed.append("model")

    if not changed:
        print("用法：")
        print("  askmodel small --key <k> --base <b> --model <m>")
        print("  askmodel small <provider> --key <k>")
        return

    config.save_small(cfg)
    print(f"小模型已更新：{', '.join(changed)}")


def cmd_providers():
    print("可用 provider 预设：\n")
    for name, preset in config.PROVIDER_PRESETS.items():
        print(f"  {name}")
        print(f"    base_url: {preset['base_url']}")
        print(f"    model:    {preset['model']}")
    print()
    print("自定义：")
    print("  askmodel main  --key <k> --base <b> --model <m>")
    print("  askmodel small --key <k> --base <b> --model <m>")


# ---------- scan / flash / to ----------

def cmd_scan(paths_with_deep: list):
    desc = "，".join(
        f'{p}({"全量" if d else "标准"})' for p, d in paths_with_deep
    )
    print(f"→ 扫描 {desc}...")
    context = scanner.scan_paths(paths_with_deep)

    paths = [p for p, _ in paths_with_deep]
    config.save_scan(context, paths)

    size_chars = len(context)
    size_kb = len(context.encode("utf-8")) / 1024
    print("→ 已将文件内容写入扫描文件")
    print(f"  路径：{config.scan_file()}")
    print(f"  大小：{size_chars} 字符（约 {size_kb:.1f} KB）")

    if size_chars > config.SCAN_SIZE_WARN:
        print()
        print(f"  ⚠ 扫描文件较大，生成摘要时可能较慢")
        print(f"    建议用更精确的路径重新扫描：")
        print(f'    askmodel here "具体路径" scan')


def cmd_flash():
    name = config.get_current_project()
    memory.clear_project()
    print(f"已清空项目 {name} 的记忆")


def _print_config_guide():
    print("主模型未配置。请先运行以下命令之一：")
    print()
    print("  用预设（推荐）：")
    print("    askmodel main deepseek --key sk-xxx")
    print("    askmodel main zhipu --key sk-xxx")
    print("    askmodel main siliconflow --key sk-xxx")
    print("    askmodel main moonshot --key sk-xxx")
    print("    askmodel main openai --key sk-xxx")
    print()
    print("  自定义：")
    print("    askmodel main --key <api_key> --base <base_url> --model <model>")
    print()
    print("  查看所有预设：askmodel providers")


def cmd_to(directory: str, prompt: str):
    root = resolve(directory)
    if not root.is_dir():
        print(f"错误：{root} 不是文件夹")
        return

    cfg = config.load()
    if not config.is_configured(cfg):
        _print_config_guide()
        return

    small_cfg = config.load_small()

    if not memory.load_summary():
        context = config.load_scan_context()
        if not context:
            print("→ 无扫描文件，直接对话")
        elif len(context) < memory.SUMMARY_MIN_CHARS:
            print(f"→ 扫描文本较短（{len(context)} 字符），跳过摘要生成")
        else:
            print("→ 首次对话，生成项目摘要...")
            try:
                summary = memory.generate_summary(context, small_cfg)
                memory.save_summary(summary)
                print(f"→ 摘要已生成（{len(summary)} 字符）")
            except Exception as e:
                print(f"✗ 生成摘要失败: {e}")
                return

    if not prompt:
        print("检测到空需求。")
        if input("确认以空命令运行？(Y/N): ").strip().upper() != "Y":
            print("已取消")
            return

    print(f"→ 工作目录: {root}")
    print(f"→ 当前项目: {config.get_current_project()}")
    print("→ 请求模型...")

    messages = memory.build_messages(prompt, api.SYSTEM_PROMPT)
    try:
        result = api.ask(messages, cfg)
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        return

    memory.record_turn(prompt, json.dumps(result, ensure_ascii=False))

    if not result.get("filename"):
        print(f"\n[模型回答]")
        print(result.get("reason", ""))
    else:
        target = executor.safe_path(root, result["filename"])
        print(f"\n──── 执行报告 ────")
        print(f"[AI 决策] 写入 {result['filename']}")
        print(f"  理由: {result.get('reason', '(无)')}")

        if target.exists():
            if input(f"{target} 已存在，覆盖？(y/n): ").lower() != "y":
                print("已取消")
                return

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result["content"], encoding="utf-8")
        print(f"[文件操作] ✓ 已写入 {result['filename']} ({len(result['content'])} 字符)")

        deps = result.get("dependencies", [])
        if deps:
            print(f"[依赖提示]")
            executor.show_dependencies(deps)

        data = config.load_scan_data()
        paths = data.get("paths", ["."])
        if paths:
            print(f"\n→ 项目已变化，重新扫描...")
            new_context = scanner.scan_paths([(p, False) for p in paths])
            config.save_scan(new_context, paths)
            if len(new_context) >= memory.SUMMARY_MIN_CHARS:
                print("→ 更新摘要...")
                try:
                    new_summary = memory.generate_summary(new_context, small_cfg)
                    memory.save_summary(new_summary)
                    print(f"→ 摘要已更新（{len(new_summary)} 字符）")
                except Exception as e:
                    print(f"  ✗ 摘要更新失败: {e}")
            else:
                memory.save_summary("")

    try:
        if memory.maybe_compress(small_cfg):
            print("→ 历史对话已压缩")
    except Exception as e:
        print(f"  ✗ 历史压缩失败: {e}")

    print("──────────────────")


def main():
    config.ensure_default_project()

    argv = sys.argv[1:]
    action, directory, prompt, args, deep = parse_argv(argv)

    if action == "help":
        print_help()
    elif action == "project":
        cmd_project(args)
    elif action == "main":
        cmd_main(args)
    elif action == "small":
        cmd_small(args)
    elif action == "providers":
        cmd_providers()
    elif action == "flash":
        cmd_flash()
    elif action == "scan":
        cmd_scan(args)
    elif action == "to":
        cmd_to(directory, prompt)


if __name__ == "__main__":
    main()