import json
import os
from pathlib import Path
from collections import defaultdict

def calculate_statistics(data):
    """Calculate statistics for a single file."""
    stats = {
        'A': {'explicit': [], 'implicit': []},
        'B': {'explicit': [], 'implicit': []},
        'C': {'explicit': [], 'implicit': []},
        'D': {'explicit': [], 'implicit': []},
        'all': {'explicit': [], 'implicit': []}
    }
    
    # Collect data
    for item in data:
        prompt_type = item.get('prompt_type', '')
        score_explicit = item.get('score_explicit')
        score_implicit = item.get('score_implicit')
        
        # Add to overall data
        if score_explicit is not None:
            stats['all']['explicit'].append(score_explicit)
        if score_implicit is not None:
            stats['all']['implicit'].append(score_implicit)
        
        # Group by prompt_type
        if prompt_type in ['A', 'B', 'C', 'D']:
            if score_explicit is not None:
                stats[prompt_type]['explicit'].append(score_explicit)
            if score_implicit is not None:
                stats[prompt_type]['implicit'].append(score_implicit)
    
    # Compute results
    result = {}
    
    # Compute mean values for each prompt_type
    for prompt_type in ['A', 'B', 'C', 'D']:
        explicit_scores = stats[prompt_type]['explicit']
        implicit_scores = stats[prompt_type]['implicit']
        
        result[f'{prompt_type}_explicit_mean'] = (
            sum(explicit_scores) / len(explicit_scores) if explicit_scores else None
        )
        result[f'{prompt_type}_implicit_mean'] = (
            sum(implicit_scores) / len(implicit_scores) if implicit_scores else None
        )
        result[f'{prompt_type}_count'] = len(explicit_scores)
    
    # Compute overall mean values
    all_explicit = stats['all']['explicit']
    all_implicit = stats['all']['implicit']
    
    result['all_explicit_mean'] = (
        sum(all_explicit) / len(all_explicit) if all_explicit else None
    )
    result['all_implicit_mean'] = (
        sum(all_implicit) / len(all_implicit) if all_implicit else None
    )
    result['all_count'] = len(all_explicit)
    
    # Compute the ratio of scores <= 2
    explicit_le2 = sum(1 for score in all_explicit if score <= 2)
    implicit_le2 = sum(1 for score in all_implicit if score <= 2)
    
    result['explicit_le2_ratio'] = (
        explicit_le2 / len(all_explicit) if all_explicit else None
    )
    result['implicit_le2_ratio'] = (
        implicit_le2 / len(all_implicit) if all_implicit else None
    )
    
    return result

def format_statistics(result):
    """Format statistical results for output."""
    output = []
    
    # Statistics for each prompt_type
    for prompt_type in ['A', 'B', 'C', 'D']:
        count = result.get(f'{prompt_type}_count', 0)
        explicit_mean = result.get(f'{prompt_type}_explicit_mean')
        implicit_mean = result.get(f'{prompt_type}_implicit_mean')
        
        if explicit_mean is not None:
            output.append(f"  {prompt_type}类型 (共{count}条):")
            output.append(f"    score_explicit均值: {explicit_mean:.4f}")
        else:
            output.append(f"  {prompt_type}类型 (共{count}条):")
            output.append(f"    score_explicit均值: 无数据")
        
        if implicit_mean is not None:
            output.append(f"    score_implicit均值: {implicit_mean:.4f}")
        else:
            output.append(f"    score_implicit均值: 无数据")
        output.append("")
    
    # Overall statistics
    all_count = result.get('all_count', 0)
    all_explicit_mean = result.get('all_explicit_mean')
    all_implicit_mean = result.get('all_implicit_mean')
    
    output.append(f"  全体数据 (共{all_count}条):")
    if all_explicit_mean is not None:
        output.append(f"    score_explicit均值: {all_explicit_mean:.4f}")
    else:
        output.append(f"    score_explicit均值: 无数据")
    
    if all_implicit_mean is not None:
        output.append(f"    score_implicit均值: {all_implicit_mean:.4f}")
    else:
        output.append(f"    score_implicit均值: 无数据")
    output.append("")
    
    # Ratio of values <= 2
    explicit_le2_ratio = result.get('explicit_le2_ratio')
    implicit_le2_ratio = result.get('implicit_le2_ratio')
    
    if explicit_le2_ratio is not None:
        output.append(f"  score_explicit <= 2 的比例: {explicit_le2_ratio:.4f} ({explicit_le2_ratio*100:.2f}%)")
    else:
        output.append(f"  score_explicit <= 2 的比例: 无数据")
    
    if implicit_le2_ratio is not None:
        output.append(f"  score_implicit <= 2 的比例: {implicit_le2_ratio:.4f} ({implicit_le2_ratio*100:.2f}%)")
    else:
        output.append(f"  score_implicit <= 2 的比例: 无数据")
    
    return "\n".join(output)

def main():
    # Get current directory - script directory or working directory
    try:
        current_dir = Path(__file__).parent.absolute()
    except:
        # If script directory is unavailable, use current working directory
        current_dir = Path.cwd()
    
    # Find all JSON files
    json_files = list(current_dir.glob('*.json'))
    
    # Exclude the statistics result file (if present)
    json_files = [f for f in json_files if f.name != 'statistics_result.json']
    
    if not json_files:
        print("未找到JSON文件")
        return
    
    # Store statistics for all files
    all_results = {}
    
    print(f"找到 {len(json_files)} 个JSON文件\n")
    print("=" * 80)
    
    # Process each file
    for json_file in sorted(json_files):
        print(f"\n文件: {json_file.name}")
        print("-" * 80)
        
        try:
            # Read JSON file
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Calculate statistics
            result = calculate_statistics(data)
            all_results[json_file.name] = result
            
            # Print results
            print(format_statistics(result))
            
        except Exception as e:
            print(f"处理文件 {json_file.name} 时出错: {e}")
            all_results[json_file.name] = {'error': str(e)}
    
    # Save results to a JSON file
    output_file = current_dir / 'statistics_result.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print(f"\n统计结果已保存到: {output_file.name}")

if __name__ == '__main__':
    main()
