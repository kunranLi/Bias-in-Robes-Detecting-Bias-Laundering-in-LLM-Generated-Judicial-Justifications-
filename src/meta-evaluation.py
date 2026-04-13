import argparse
import csv
import glob
import json
import os
import random
from collections import Counter


def load_items_from_json_files(json_dir: str, pattern: str):
    """Load all items from JSON files matching pattern in the given directory (assuming list structure)."""
    items = []
    json_paths = glob.glob(os.path.join(json_dir, pattern), recursive=False)
    for path in json_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"读取 {path} 失败，跳过。错误：{e}")
            continue

        if isinstance(data, list):
            for idx, obj in enumerate(data):
                if isinstance(obj, dict):
                    items.append(
                        {
                            "file": os.path.basename(path),
                            "file_path": path,
                            "index_in_file": idx,
                            "item": obj,
                        }
                    )
        else:
            print(f"{path} 不是列表结构，当前脚本未处理，跳过。")

    return items


def choose_text_field_for_judgement(item: dict, score_field: str):
    """Build the text used for manual judgment.

    Explicit: prompt_explicit + two newlines + reason_explicit
    Implicit: prompt_implicit + two newlines + reason_implicit
    """
    field_prefix = score_field.replace("score_", "")

    if field_prefix == "explicit":
        prompt = item.get("prompt_explicit", "")
        reason = item.get("reason_explicit", "")
    elif field_prefix == "implicit":
        prompt = item.get("prompt_implicit", "")
        reason = item.get("reason_implicit", "")
    else:
        # Fallback logic: keep previous auto-matching behavior
        # Priority: analysis > reason > prompt
        for suffix in ["analysis", "reason", "prompt"]:
            key = f"{suffix}_{field_prefix}"
            if key in item and isinstance(item[key], str):
                return item[key]

        for key in ["analysis_explicit", "analysis_implicit", "reason_explicit",
                    "reason_implicit", "prompt_explicit", "prompt_implicit"]:
            if key in item and isinstance(item[key], str):
                return item[key]

        return ""

    # Concatenate prompt and reason; if one is empty, return the other
    if prompt and reason:
        return f"{prompt}\n\n{reason}"
    elif prompt:
        return str(prompt)
    elif reason:
        return str(reason)
    else:
        return ""


def cmd_sample(args):
    json_dir = args.json_dir
    pattern = args.pattern
    n = args.n
    score_field = args.score_field
    out_csv = args.out_csv
    seed = args.seed

    random.seed(seed)

    items = load_items_from_json_files(json_dir, pattern)
    if not items:
        print("未在指定目录下找到可用 JSON 数据。")
        return

    # Support half explicit / half implicit sampling when score_field == "both"
    if score_field == "both":
        explicit_key = "score_explicit"
        implicit_key = "score_implicit"

        explicit_items = [
            it for it in items
            if isinstance(it["item"], dict)
            and explicit_key in it["item"]
            and it["item"][explicit_key] is not None
        ]
        implicit_items = [
            it for it in items
            if isinstance(it["item"], dict)
            and implicit_key in it["item"]
            and it["item"][implicit_key] is not None
        ]

        if not explicit_items and not implicit_items:
            print("在 JSON 中未找到包含 score_explicit 或 score_implicit 的样本。")
            return

        # Target: half explicit and half implicit; fill shortage from the other side
        target_exp = n // 2
        target_imp = n - target_exp

        available_exp = len(explicit_items)
        available_imp = len(implicit_items)

        take_exp = min(target_exp, available_exp)
        take_imp = min(target_imp, available_imp)

        remaining = n - (take_exp + take_imp)
        if remaining > 0:
            extra_exp = min(remaining, available_exp - take_exp)
            take_exp += extra_exp
            remaining -= extra_exp
        if remaining > 0:
            extra_imp = min(remaining, available_imp - take_imp)
            take_imp += extra_imp
            remaining -= extra_imp

        sampled = []
        if take_exp > 0:
            chosen_exp = random.sample(explicit_items, take_exp)
            for it in chosen_exp:
                it_with_field = dict(it)
                it_with_field["__score_field__"] = explicit_key
                sampled.append(it_with_field)
        if take_imp > 0:
            chosen_imp = random.sample(implicit_items, take_imp)
            for it in chosen_imp:
                it_with_field = dict(it)
                it_with_field["__score_field__"] = implicit_key
                sampled.append(it_with_field)

        random.shuffle(sampled)

        print(
            f"总样本数 {len(explicit_items) + len(implicit_items)}，"
            f"本次实际抽取 显性 {take_exp} 条，隐性 {take_imp} 条，共 {len(sampled)} 条。"
        )
    else:
        # Filter samples containing the specified score field (and score is not None)
        items_with_score = [
            it for it in items
            if isinstance(it["item"], dict)
            and score_field in it["item"]
            and it["item"][score_field] is not None
        ]
        if not items_with_score:
            print(f"在 JSON 中未找到包含有效字段 {score_field} 的样本。")
            print(f"提示：可用的打分字段可能包括：score_explicit, score_implicit 等")
            return

        if len(items_with_score) <= n:
            sampled = items_with_score
            print(f"可用样本数 {len(items_with_score)} 少于或等于 {n}，将全部导出。")
        else:
            sampled = random.sample(items_with_score, n)
            print(f"从 {len(items_with_score)} 条样本中随机抽取 {n} 条。")

    # Write CSV for manual scoring
    fieldnames = [
        "sample_id",      # Global sample ID
        "file",           # Source filename
        "item_index",     # Index in the original JSON list
        "ID",             # ID field in item (if present)
        "score_field",    # Score field for this sample (explicit/implicit)
        "llm_score",      # Original LLM score
        "human_score",    # Manually assigned score (initially empty)
        "text_for_judgement",  # Text provided for reading and judgment
    ]

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, it in enumerate(sampled, start=1):
            obj = it["item"]
            # Each sample's own score field (may be explicit/implicit)
            this_score_field = it.get("__score_field__", score_field)
            llm_score = obj.get(this_score_field, "")
            text_for_judgement = choose_text_field_for_judgement(obj, this_score_field)
            row = {
                "sample_id": i,
                "file": it["file"],
                "item_index": it["index_in_file"],
                "ID": obj.get("ID", ""),
                "score_field": this_score_field,
                "llm_score": llm_score,
                "human_score": "",  # Fill later in Excel/table or via interactive input
                "text_for_judgement": text_for_judgement,
            }
            writer.writerow(row)

    print(f"已生成样本文件：{out_csv}")
    
    # If interactive mode is enabled, start interactive scoring immediately
    if args.interactive:
        cmd_interactive_simple(sampled, out_csv, score_field)
    else:
        print("请在该 CSV 中为每一行的 human_score 列填写你的人工打分（数字）。")
        print("或者使用 --interactive 选项进行交互式打分。")


def pearson_correlation(xs, ys):
    """Pure Python implementation of Pearson correlation."""
    n = len(xs)
    if n == 0:
        return float("nan")

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)

    if var_x == 0 or var_y == 0:
        return float("nan")

    return cov / (var_x ** 0.5 * var_y ** 0.5)


def cohens_kappa(xs, ys):
    """Pure Python implementation of Cohen's kappa (unweighted)."""
    if len(xs) != len(ys) or len(xs) == 0:
        return float("nan")

    # Map labels to indices
    labels = sorted(set(xs) | set(ys))
    label_to_idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    N = len(xs)

    # Build confusion matrix
    conf = [[0] * k for _ in range(k)]
    for x, y in zip(xs, ys):
        i = label_to_idx[x]
        j = label_to_idx[y]
        conf[i][j] += 1

    # Observed agreement Po
    agree = sum(conf[i][i] for i in range(k))
    Po = agree / N

    # Expected agreement Pe
    row_sums = [sum(conf[i][j] for j in range(k)) for i in range(k)]
    col_sums = [sum(conf[i][j] for i in range(k)) for j in range(k)]

    Pe = 0.0
    for i in range(k):
        Pe += (row_sums[i] / N) * (col_sums[i] / N)

    if Pe == 1.0:
        return 1.0
    if Pe == 0.0:
        return (Po - Pe)  # Avoid divide-by-zero; degraded fallback

    kappa = (Po - Pe) / (1 - Pe)
    return kappa


def cmd_interactive_simple(sampled_items, csv_file, score_field):
    """Interactive scoring: show samples one by one in terminal and collect user scores."""
    print("\n" + "=" * 80)
    print("开始交互式打分")
    print("=" * 80)
    print("提示：")
    print("  - 输入数字分数后按回车确认")
    print("  - 输入 'q' 或 'quit' 退出并保存已完成的打分")
    print("  - 输入 's' 或 'skip' 跳过当前样本（不保存分数）")
    print("  - 输入 'b' 或 'back' 返回上一题（如果已保存）")
    print("-" * 80)
    
    # Load existing CSV (if there are already saved scores)
    existing_scores = {}
    if os.path.exists(csv_file):
        with open(csv_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sample_id = int(row["sample_id"])
                if row.get("human_score", "").strip():
                    try:
                        existing_scores[sample_id] = float(row["human_score"])
                    except ValueError:
                        pass
    
    # Prepare data
    samples_data = []
    for i, it in enumerate(sampled_items, start=1):
        obj = it["item"]
        this_score_field = it.get("__score_field__", score_field)
        text_for_judgement = choose_text_field_for_judgement(obj, this_score_field)
        samples_data.append({
            "sample_id": i,
            "file": it["file"],
            "item_index": it["index_in_file"],
            "ID": obj.get("ID", ""),
            "score_field": this_score_field,
            "llm_score": obj.get(this_score_field, ""),
            "text_for_judgement": text_for_judgement,
            "human_score": existing_scores.get(i, ""),
        })
    
    current_idx = 0
    total = len(samples_data)
    
    # Find the first unrated sample
    for idx, sample in enumerate(samples_data):
        if not sample["human_score"]:
            current_idx = idx
            break
    
    while current_idx < total:
        sample = samples_data[current_idx]
        sample_id = sample["sample_id"]
        
        # Clear screen (optional; supports both Windows and Unix)
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("\n" + "=" * 80)
        print(f"样本 {sample_id}/{total} (进度: {current_idx + 1}/{total})")
        print("=" * 80)
        print(f"\n文件: {sample['file']}")
        print(f"ID: {sample['ID']}")
        print(f"LLM 打分: {sample['llm_score']}")
        if sample["human_score"]:
            print(f"当前已保存分数: {sample['human_score']}")
        print("\n" + "-" * 80)
        print("待判断文本：")
        print("-" * 80)
        
        # Display text; truncate if too long
        text = sample["text_for_judgement"]
        if len(text) > 2000:
            print(text[:2000] + "\n... (文本较长，已截断)")
        else:
            print(text)
        
        print("\n" + "-" * 80)
        user_input = input(f"请输入你的打分 (1-5，或 q退出/s跳过/b返回): ").strip()
        
        if user_input.lower() in ['q', 'quit']:
            print("\n退出并保存已完成的打分...")
            break
        elif user_input.lower() in ['s', 'skip']:
            print("跳过当前样本")
            current_idx += 1
            continue
        elif user_input.lower() in ['b', 'back']:
            if current_idx > 0:
                current_idx -= 1
                print("返回上一题")
                continue
            else:
                print("已经是第一题，无法返回")
                continue
        else:
            try:
                score = float(user_input)
                # Additional score range checks can be added here
                if score < 1 or score > 5:
                    print(f"警告：分数 {score} 超出常见范围 (1-5)，但仍会保存")
                
                sample["human_score"] = score
                print(f"已保存分数: {score}")
                current_idx += 1
            except ValueError:
                print("输入无效，请输入数字、'q'、's' 或 'b'")
                input("按回车继续...")
                continue
        
        # Save after each sample to avoid data loss on unexpected exit
        save_scores_to_csv(samples_data, csv_file, score_field)
    
    # Final save
    save_scores_to_csv(samples_data, csv_file, score_field)
    print(f"\n打分完成！结果已保存到: {csv_file}")
    print(f"已完成打分: {sum(1 for s in samples_data if s['human_score'])}/{total}")


def save_scores_to_csv(samples_data, csv_file, score_field):
    """Save scoring results to a CSV file."""
    fieldnames = [
        "sample_id",
        "file",
        "item_index",
        "ID",
        "score_field",
        "llm_score",
        "human_score",
        "text_for_judgement",
    ]
    
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples_data:
            row = {
                "sample_id": sample["sample_id"],
                "file": sample["file"],
                "item_index": sample["item_index"],
                "ID": sample["ID"],
                "score_field": sample.get("score_field", score_field),
                "llm_score": sample["llm_score"],
                "human_score": sample["human_score"] if sample["human_score"] else "",
                "text_for_judgement": sample["text_for_judgement"],
            }
            writer.writerow(row)


def cmd_interactive(args):
    """Interactive scoring command for scoring an existing CSV file."""
    csv_file = args.sample_file
    
    if not os.path.exists(csv_file):
        print(f"错误：文件 {csv_file} 不存在。")
        print("请先运行 'sample' 命令生成样本文件。")
        return
    
    # Read CSV file
    samples_data = []
    with open(csv_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples_data.append({
                "sample_id": int(row["sample_id"]),
                "file": row["file"],
                "item_index": row["item_index"],
                "ID": row.get("ID", ""),
                "score_field": row.get("score_field", score_field),
                "llm_score": row.get("llm_score", ""),
                "text_for_judgement": row.get("text_for_judgement", ""),
                "human_score": float(row["human_score"]) if row.get("human_score", "").strip() else "",
            })
    
    if not samples_data:
        print("CSV文件中没有数据。")
        return
    
    # Determine score field (infer from llm_score column name, or use argument)
    score_field = args.score_field if hasattr(args, 'score_field') else "score_explicit"
    
    # Convert to the format required by interactive function
    # Ideally we would reload original data for full context
    # For simplicity, we directly use data from CSV
    print("\n" + "=" * 80)
    print("开始交互式打分")
    print("=" * 80)
    
    total = len(samples_data)
    current_idx = 0
    
    # Find the first unrated sample
    for idx, sample in enumerate(samples_data):
        if not sample["human_score"]:
            current_idx = idx
            break
    
    while current_idx < total:
        sample = samples_data[current_idx]
        sample_id = sample["sample_id"]
        
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("\n" + "=" * 80)
        print(f"样本 {sample_id}/{total} (进度: {current_idx + 1}/{total})")
        print("=" * 80)
        print(f"\n文件: {sample['file']}")
        print(f"ID: {sample['ID']}")
        print(f"LLM 打分: {sample['llm_score']}")
        if sample["human_score"]:
            print(f"当前已保存分数: {sample['human_score']}")
        print("\n" + "-" * 80)
        print("待判断文本：")
        print("-" * 80)
        
        text = sample["text_for_judgement"]
        if len(text) > 2000:
            print(text[:2000] + "\n... (文本较长，已截断)")
        else:
            print(text)
        
        print("\n" + "-" * 80)
        user_input = input(f"请输入你的打分 (1-5，或 q退出/s跳过/b返回): ").strip()
        
        if user_input.lower() in ['q', 'quit']:
            print("\n退出并保存已完成的打分...")
            break
        elif user_input.lower() in ['s', 'skip']:
            print("跳过当前样本")
            current_idx += 1
            continue
        elif user_input.lower() in ['b', 'back']:
            if current_idx > 0:
                current_idx -= 1
                print("返回上一题")
                continue
            else:
                print("已经是第一题，无法返回")
                continue
        else:
            try:
                score = float(user_input)
                if score < 1 or score > 5:
                    print(f"警告：分数 {score} 超出常见范围 (1-5)，但仍会保存")
                
                sample["human_score"] = score
                print(f"已保存分数: {score}")
                current_idx += 1
            except ValueError:
                print("输入无效，请输入数字、'q'、's' 或 'b'")
                input("按回车继续...")
                continue
        
        # Save after each completed sample
        save_scores_to_csv(samples_data, csv_file, score_field)
    
    # Final save
    save_scores_to_csv(samples_data, csv_file, score_field)
    print(f"\n打分完成！结果已保存到: {csv_file}")
    print(f"已完成打分: {sum(1 for s in samples_data if s['human_score'])}/{total}")


def cmd_eval(args):
    sample_file = args.sample_file
    llm_col = args.llm_col
    human_col = args.human_col

    llm_scores = []
    human_scores = []

    with open(sample_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            llm_val = row.get(llm_col, "").strip()
            human_val = row.get(human_col, "").strip()

            if llm_val == "" or human_val == "":
                # Skip samples missing either side's score
                continue

            try:
                llm_score = float(llm_val)
                human_score = float(human_val)
            except ValueError:
                # Non-numeric value, skip
                continue

            llm_scores.append(llm_score)
            human_scores.append(human_score)

    if not llm_scores:
        print("未在 CSV 中找到同时具有 LLM 和人工打分的有效样本。")
        return

    # Pearson correlation (treat scores as continuous variables)
    pearson = pearson_correlation(llm_scores, human_scores)

    # Cohen's kappa (treat scores as categories)
    # If you want integer bins as categories, round first:
    llm_cats = [int(round(x)) for x in llm_scores]
    human_cats = [int(round(y)) for y in human_scores]
    kappa = cohens_kappa(llm_cats, human_cats)

    print(f"有效样本数：{len(llm_scores)}")
    print(f"Pearson 相关系数：{pearson:.4f}")
    print(f"Cohen's kappa 系数：{kappa:.4f}")

    # Also print score distributions to inspect consistency
    print("\nLLM 分布：", dict(Counter(llm_cats)))
    print("人工 分布：", dict(Counter(human_cats)))


def main():
    parser = argparse.ArgumentParser(
        description="从 JSON 中抽样做人类打分，并与 LLM 打分比较（Pearson + Cohen's kappa）"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand: sample
    p_sample = subparsers.add_parser("sample", help="从 JSON 中随机抽样，生成待人工打分的 CSV")
    p_sample.add_argument(
        "--json-dir",
        type=str,
        default=".",
        help="JSON 文件所在目录（默认当前目录）",
    )
    p_sample.add_argument(
        "--pattern",
        type=str,
        default="*.json",
        help="匹配 JSON 文件的模式（默认 *.json）",
    )
    p_sample.add_argument(
        "--score-field",
        type=str,
        default="score_explicit",
        help="要对比的 LLM 打分字段名（默认 score_explicit，也可以是 score_implicit 或其他字段）",
    )
    p_sample.add_argument(
        "--n",
        type=int,
        default=100,
        help="抽样数量（默认 100）",
    )
    p_sample.add_argument(
        "--out-csv",
        type=str,
        default="sample_for_human.csv",
        help="输出的 CSV 文件名（默认 sample_for_human.csv）",
    )
    p_sample.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机数种子（保证可复现，默认 42）",
    )
    p_sample.add_argument(
        "--interactive",
        action="store_true",
        help="抽样后立即进入交互式打分模式",
    )
    p_sample.set_defaults(func=cmd_sample)

    # Subcommand: interactive
    p_interactive = subparsers.add_parser("interactive", help="对已有的CSV文件进行交互式打分")
    p_interactive.add_argument(
        "--sample-file",
        type=str,
        default="sample_for_human.csv",
        help="要打分的CSV文件（默认 sample_for_human.csv）",
    )
    p_interactive.add_argument(
        "--score-field",
        type=str,
        default="score_explicit",
        help="打分字段名（用于显示，默认 score_explicit）",
    )
    p_interactive.set_defaults(func=cmd_interactive)

    # Subcommand: eval
    p_eval = subparsers.add_parser("eval", help="读取人工打分后的 CSV，计算相关和 kappa")
    p_eval.add_argument(
        "--sample-file",
        type=str,
        default="sample_for_human.csv",
        help="包含 llm_score 和 human_score 的 CSV 文件（默认 sample_for_human.csv）",
    )
    p_eval.add_argument(
        "--llm-col",
        type=str,
        default="llm_score",
        help="CSV 中 LLM 打分所在列名（默认 llm_score）",
    )
    p_eval.add_argument(
        "--human-col",
        type=str,
        default="human_score",
        help="CSV 中人工打分所在列名（默认 human_score）",
    )
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()