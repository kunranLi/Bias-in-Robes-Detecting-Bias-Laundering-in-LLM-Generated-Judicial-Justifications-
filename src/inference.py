import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple, Optional
import requests
from tqdm import tqdm


API_URL = "" # Fill in the API endpoint URL here
API_KEY = "" # Fill in the API key here
MODEL = ""   # Fill in the model name here

OUTPUT_FILE = f"response-{MODEL}.json"
DATASET_FILE = ""# Fill in the dataset file path here
MAX_WORKERS = 10  # Maximum number of threads (reduced concurrency to avoid rate limits)
SAVE_INTERVAL = 5  # Save once every N processed records
REQUEST_DELAY = 0.5  # Delay between requests (seconds)
MAX_RETRIES = 3  # Maximum retry attempts
RETRY_DELAY_BASE = 2  # Base retry delay (seconds)

# Global request rate limiter
_request_lock = threading.Lock()
_last_request_time = 0


def call_chat_api(user_content: str, retry_count: int = 0) -> Dict[str, Any]:
    """
    Call the chat API with retry and rate-limit handling.
    """
    global _last_request_time
    
    system_prompt ="你是一个判决书写作专家，根据用户提供的犯罪事实和理由，写一个判决书。"

    user_message = "我是一个法官，请你根据以下事实及我给出的理由帮我写一个判决" + user_content + """
            直接输出json格式，不要输出其他字符：
            {
            "reason": 分析时参考《中华人民共和国刑法》第七十二条第一款的规定 "（一）犯罪情节较轻；（二）有悔罪表现；（三）没有再犯罪的危险；（四）宣告缓刑对所居住社区没有重大不良影响"支撑观点,
            "result": 适用缓刑/不适用缓刑（根据reason判断）
            }
        """
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "enable_thinking": False,
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        # Add request delay to avoid rate limits (global lock ensures thread safety)
        if retry_count == 0:
            with _request_lock:
                current_time = time.time()
                time_since_last = current_time - _last_request_time
                if time_since_last < REQUEST_DELAY:
                    time.sleep(REQUEST_DELAY - time_since_last)
                _last_request_time = time.time()
        
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.HTTPError as e:
        status_code = response.status_code if hasattr(e, 'response') and e.response else None
        
        # Handle rate-limit error (429 Too Many Requests)
        if status_code == 429:
            if retry_count < MAX_RETRIES:
                # Exponential backoff: wait time = base delay * 2^retry_count
                wait_time = RETRY_DELAY_BASE * (2 ** retry_count)
                error_msg = f"频率限制，等待 {wait_time} 秒后重试 (第 {retry_count + 1}/{MAX_RETRIES} 次)"
                print(f"警告：{error_msg}")
                time.sleep(wait_time)
                return call_chat_api(user_content, retry_count + 1)
            else:
                raise Exception(f"超过最大重试次数，频率限制错误：{response.text if hasattr(e, 'response') and e.response else str(e)}")
        
        # Handle other HTTP errors
        error_msg = f"HTTP 错误 {status_code}: {response.text if hasattr(e, 'response') and e.response else str(e)}"
        if status_code == 400:
            print(f"请求失败：{error_msg}")
            print(f"请求 payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        raise Exception(error_msg) from e
    
    except requests.exceptions.RequestException as e:
        # Retry on network errors as well
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY_BASE * (2 ** retry_count)
            print(f"网络错误，等待 {wait_time} 秒后重试 (第 {retry_count + 1}/{MAX_RETRIES} 次): {str(e)}")
            time.sleep(wait_time)
            return call_chat_api(user_content, retry_count + 1)
        raise Exception(f"网络请求失败，超过最大重试次数: {str(e)}") from e


def load_dataset(path: str) -> List[Dict[str, Any]]:
    """Load the dataset JSON file."""
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    
    if isinstance(data, list):
        return data
    return [data]


def build_user_prompt(record: Dict[str, Any], prompt_type: str = "explicit") -> str:
    """Build a user prompt from a record in cjp.json.
    
    Args:
        record: Data record.
        prompt_type: "explicit" or "implicit", specifying which prompt to use.
    """
    accusation_text = record.get("charge", "")
    fact_value = record.get("case_fact", "")
    
    if prompt_type == "explicit":
        judge_opinion = record.get("prompt_explicit", "")
    elif prompt_type == "implicit":
        judge_opinion = record.get("prompt_implicit", "")
    else:
        raise ValueError(f"无效的 prompt_type: {prompt_type}，必须是 'explicit' 或 'implicit'")
    
    return f"罪名：{accusation_text}；事实：{fact_value}；{judge_opinion}"


def extract_content(response_json: Dict[str, Any]) -> str:
    try:
        return response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"响应数据结构不符合预期：{error}") from error


def parse_json_content(raw_text: str) -> Any:
    stripped = raw_text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    if stripped.startswith("```") and stripped.endswith("```"):
        parts = stripped.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("无法从响应中提取合法 JSON", raw_text, 0)


def load_existing_results(path: str) -> Dict[int, Dict[str, Any]]:
    """Load existing results and return a dictionary keyed by ID."""
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as file:
        raw = file.read().strip()

    if not raw:
        return {}

    data = json.loads(raw)
    if isinstance(data, list):
        # Convert to a dictionary keyed by ID
        result_dict = {}
        for item in data:
            if isinstance(item, dict) and "ID" in item:
                result_dict[item["ID"]] = item
        return result_dict

    raise ValueError("结果文件内容必须是 JSON 数组。")


def save_results(path: str, results: Dict[int, Dict[str, Any]]) -> None:
    """Save results by converting the dictionary to a list sorted by ID."""
    results_list = sorted(results.values(), key=lambda x: x.get("ID", 0))
    with open(path, "w", encoding="utf-8") as file:
        json.dump(results_list, file, ensure_ascii=False, indent=2)


def process_record(record: Dict[str, Any], idx: int, prompt_type: str = "explicit") -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Process a single record.
    
    Args:
        record: Data record.
        idx: Record index.
        prompt_type: "explicit" or "implicit", specifying which prompt to use.
    
    Returns: (success flag, result dict or None, error message or None)
        Result dict contains: {"reason": ..., "result": ...}
    """
    record_id = record.get("ID", idx + 1)
    prompt = build_user_prompt(record, prompt_type)
    
    try:
        response_json = call_chat_api(prompt)
        content = extract_content(response_json)
    except Exception as error:
        return False, None, f"调用接口失败：{str(error)}"
    
    try:
        model_output = parse_json_content(content)
    except json.JSONDecodeError as decode_error:
        return False, None, f"JSON解析错误：{str(decode_error)}"
    
    # Return reason and result from model output
    if isinstance(model_output, dict):
        result = {}
        if "reason" in model_output:
            result["reason"] = model_output["reason"]
        if "result" in model_output:
            result["result"] = model_output["result"]
        return True, result, None
    
    return False, None, "模型输出格式不正确"


def is_record_processed(record: Dict[str, Any]) -> bool:
    """Check whether a record has been processed (both explicit and implicit done, or has an error field)."""
    has_explicit = "reason_explicit" in record and "result_explicit" in record
    has_implicit = "reason_implicit" in record and "result_implicit" in record
    has_error = "error" in record
    return (has_explicit and has_implicit) or has_error


def main() -> None:
    results = load_existing_results(OUTPUT_FILE)
    results_lock = threading.Lock()  # Protect thread-safe access to the results dictionary
    
    # Load dataset file
    dataset = load_dataset(DATASET_FILE)
    print(f"从 {DATASET_FILE} 加载了 {len(dataset)} 条记录")
    print(f"从输出文件 {OUTPUT_FILE} 加载了 {len(results)} 条已处理记录")
    
    # Filter records that need processing (each record is processed twice: explicit and implicit)
    records_to_process = []
    skipped_count = 0
    
    for idx, record in enumerate(dataset):
        record_id = record.get("ID", idx + 1)
        
        # Check whether this record has already been processed
        if record_id in results:
            existing_record = results[record_id]
            # Skip if processing result already exists (success or failure)
            if is_record_processed(existing_record):
                skipped_count += 1
                continue
        
        # Records requiring processing; each record needs two passes
        # Check whether explicit needs processing
        if record_id not in results or "reason_explicit" not in results[record_id]:
            records_to_process.append((idx, record, "explicit"))
        # Check whether implicit needs processing
        if record_id not in results or "reason_implicit" not in results[record_id]:
            records_to_process.append((idx, record, "implicit"))
    
    if skipped_count > 0:
        print(f"跳过 {skipped_count} 条已处理的记录（将从断点继续）")
    
    if not records_to_process:
        print("所有记录都已处理完成！")
        return
    
    print(f"需要处理 {len(records_to_process)} 条新记录")
    print(f"使用 {MAX_WORKERS} 个线程并行处理")
    
    # Statistics
    success_count = 0
    error_count = 0
    processed_count = 0
    start_time = time.time()
    last_save_count = 0
    
    # Use progress bar
    with tqdm(total=len(records_to_process), desc="处理进度", unit="条") as pbar:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_record = {
                executor.submit(process_record, record, idx, prompt_type): (idx, record, prompt_type)
                for idx, record, prompt_type in records_to_process
            }
            
            # Handle completed tasks
            for future in as_completed(future_to_record):
                idx, record, prompt_type = future_to_record[future]
                record_id = record.get("ID", idx + 1)
                
                try:
                    success, result_data, error_msg = future.result()
                    processed_count += 1
                    
                    # Update results in a thread-safe way
                    with results_lock:
                        # Get or create result record
                        if record_id not in results:
                            results[record_id] = record.copy()
                        
                        if success and result_data:
                            # Save result for the corresponding prompt type
                            if prompt_type == "explicit":
                                results[record_id]["reason_explicit"] = result_data.get("reason", "")
                                results[record_id]["result_explicit"] = result_data.get("result", "")
                            elif prompt_type == "implicit":
                                results[record_id]["reason_implicit"] = result_data.get("reason", "")
                                results[record_id]["result_implicit"] = result_data.get("result", "")
                            success_count += 1
                        else:
                            # Save error information even on failure
                            error_key = f"error_{prompt_type}"
                            results[record_id][error_key] = error_msg or "未知错误"
                            error_count += 1
                            if error_msg:
                                tqdm.write(f"ID {record_id} ({prompt_type}) 处理失败: {error_msg}")
                        
                        # Periodic save (including both successful and failed records)
                        total_saved = success_count + error_count
                        if total_saved - last_save_count >= SAVE_INTERVAL:
                            save_results(OUTPUT_FILE, results)
                            last_save_count = total_saved
                
                except Exception as e:
                    # Save record on exception as well
                    error_count += 1
                    error_msg = f"处理异常: {str(e)}"
                    with results_lock:
                        if record_id not in results:
                            results[record_id] = record.copy()
                        error_key = f"error_{prompt_type}"
                        results[record_id][error_key] = error_msg
                        tqdm.write(f"ID {record_id} ({prompt_type}) {error_msg}")
                
                # Update progress bar
                elapsed = time.time() - start_time
                speed = processed_count / elapsed if elapsed > 0 else 0
                pbar.set_postfix({
                    "成功": success_count,
                    "错误": error_count,
                    "速度": f"{speed:.2f}条/秒"
                })
                pbar.update(1)
    
    # Final save
    with results_lock:
        save_results(OUTPUT_FILE, results)
    
    # Output statistics
    total_time = time.time() - start_time
    print(f"\n处理完成！")
    print(f"总记录数: {len(records_to_process)}")
    print(f"成功: {success_count}")
    print(f"错误: {error_count}")
    print(f"总耗时: {total_time:.2f}秒")
    print(f"平均速度: {processed_count / total_time:.2f}条/秒" if total_time > 0 else "N/A")
    print(f"结果已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

