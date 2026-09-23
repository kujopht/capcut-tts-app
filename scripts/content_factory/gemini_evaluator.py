"""Gemini 3.8 Flash Evaluator, Metadata Generator, and Translator.

Uses Google Antigravity (agy CLI) with gemini-3.8-flash-high to perform:
1. Quality evaluation & filtering (quality score >= 7.5 threshold)
2. Fanfic.world production metadata packaging (SEO Vietnamese title, description, tags)
3. High-quality narrative translation (ZH/EN -> VI)
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")

USAGE_FILE = PROJECT_ROOT / "raw_spool" / "agy_accounts_usage.json"

DEFAULT_MODEL = "gemini-3.8-flash-high"
FALLBACK_MODEL = "gemini-3.8-flash-high"
CLAUDE_MODEL = "claude-sonnet-4-6"
GPT_MODEL = "gpt-oss-120b-medium"
QUALITY_THRESHOLD = 7.5
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


_SWITCH_LOCK = threading.Lock()
_POOL_LOCK = threading.Lock()
_BUSY_ACCOUNTS: Set[str] = set()


PROFILES_DIR = Path(r"C:\Users\nguye\agy-profiles\saved_profiles")
SERVER_LIMITS_FILE = PROJECT_ROOT / "raw_spool" / "agy_server_limits.json"


def get_all_available_accounts(include_ineligible: bool = False) -> List[str]:
    """Returns naturally sorted list of all accounts found in saved_profiles."""
    if not PROFILES_DIR.exists():
        return [f"acc{i}" for i in range(1, 13)]
    bins = [p.stem for p in PROFILES_DIR.glob("*.bin")]
    def _sort_key(s: str):
        m = re.search(r"\d+", s)
        return (int(m.group(0)) if m else 999, s)
    accs = sorted(bins, key=_sort_key)
    if not include_ineligible and SERVER_LIMITS_FILE.exists():
        try:
            lims = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
            ineligible = {a for a, info in lims.items() if info.get("status") == "INELIGIBLE"}
            accs = [a for a in accs if a not in ineligible]
        except Exception:
            pass
    return accs or [f"acc{i}" for i in range(1, 13)]


def load_account_usage() -> Dict[str, Any]:
    """Loads real-time metrics for all accounts from disk or initializes defaults."""
    all_accs = get_all_available_accounts(include_ineligible=True)
    data: Dict[str, Any] = {
        "accounts": {
            acc: {
                "name": acc,
                "calls_total": 0,
                "calls_success": 0,
                "quota_errors": 0,
                "last_used": None,
                "last_latency_s": 0.0,
                "status": "READY",
                "last_error": "",
            }
            for acc in all_accs
        },
        "current_active": "acc1",
        "active_accounts": [],
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if USAGE_FILE.exists():
        try:
            stored = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict) and "accounts" in stored:
                for acc, info in stored["accounts"].items():
                    if acc in data["accounts"]:
                        data["accounts"][acc].update(info)
                    else:
                        data["accounts"][acc] = info
                data["current_active"] = stored.get("current_active", "acc1")
                data["active_accounts"] = stored.get("active_accounts", [])
        except Exception:
            pass
    return data


def save_account_usage(data: Dict[str, Any]) -> None:
    """Safely saves updated usage metrics to disk."""
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tmp = str(USAGE_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(USAGE_FILE))
    except Exception:
        pass


def record_account_call(acc: str, success: bool, latency_s: float = 0.0, error_msg: str = "") -> None:
    """Records an attempt, latency, and result for an Antigravity account."""
    data = load_account_usage()
    if acc not in data["accounts"]:
        data["accounts"][acc] = {
            "name": acc, "calls_total": 0, "calls_success": 0,
            "quota_errors": 0, "last_used": None, "last_latency_s": 0.0,
            "status": "READY", "last_error": "",
        }
    entry = data["accounts"][acc]
    entry["calls_total"] += 1
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    entry["last_used"] = now_str
    entry["last_latency_s"] = round(latency_s, 2)
    data["current_active"] = acc
    data["active_accounts"] = list(_BUSY_ACCOUNTS)

    if success:
        entry["calls_success"] += 1
        entry["status"] = "ACTIVE"
        entry["last_error"] = ""
    else:
        is_quota = any(w in error_msg.lower() for w in ("quota", "limit", "429", "resource_exhausted"))
        if is_quota:
            entry["quota_errors"] += 1
            entry["status"] = "RATE_LIMITED"
        else:
            entry["status"] = "ERROR"
        entry["last_error"] = error_msg[:100]

    save_account_usage(data)


class AgyAccountPool:
    """Manages multi-account leasing, concurrent distribution & automatic failover across all accounts.
    
    Implements Quota-Aware Weighted Round-Robin Load Balancing:
    - Dynamically inspects 5-Hour & Weekly limits from Google Antigravity servers.
    - Prioritizes accounts with highest remaining quota and fewest total calls.
    - Automatically rests and protects low-quota accounts when <40% until reset.
    - Rotates evenly across healthy accounts so no single account is overburdened.
    """
    def __init__(self):
        self.profiles_dir = PROFILES_DIR
        self.sessions_dir = Path(r"C:\Users\nguye\.agy-sessions")
        self.accounts = self._load_accounts()
        self._current_idx = 0

    def _load_accounts(self) -> List[str]:
        return get_all_available_accounts(include_ineligible=False)

    def _get_account_scores(self, model: str = DEFAULT_MODEL) -> Dict[str, float]:
        self.accounts = self._load_accounts()
        limits = {}
        if SERVER_LIMITS_FILE.exists():
            try:
                limits = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        usage = load_account_usage().get("accounts", {})

        is_claude_or_gpt = any(k in model.lower() for k in ("claude", "gpt", "3p"))

        scores = {}
        for acc in self.accounts:
            lim = limits.get(acc, {})
            u = usage.get(acc, {})
            calls = int(u.get("calls_total", 0))
            status = u.get("status", "READY")

            if is_claude_or_gpt:
                cld_wk = float(lim.get("claude_weekly_remaining", 100.0))
                cld_disabled = bool(lim.get("claude_5h_disabled", False)) and cld_wk <= 0
                if status == "RATE_LIMITED" or cld_disabled or cld_wk <= 0:
                    score = -10000.0
                elif cld_wk < 15.0:
                    score = -5000.0 + cld_wk
                else:
                    # High Claude quota prioritized and evenly spread across calls
                    score = (cld_wk * 3.0) - (calls * 0.5)
            else:
                h5 = float(lim.get("five_hour_remaining", 100.0))
                wk = float(lim.get("weekly_remaining", 100.0))

                # Severe penalty for rate-limited or critically depleted accounts (<10%)
                if status == "RATE_LIMITED" or h5 < 10.0 or wk < 5.0:
                    score = -10000.0 + h5
                elif h5 < 25.0:
                    # Rest mode for low accounts (<25%) so healthy accounts handle workload until reset
                    score = -5000.0 + h5
                else:
                    # Score emphasizes 5h limit preservation (weight 2.5), weekly limit (weight 1.0),
                    # and penalizes call count to ensure even distribution across identical-quota accounts
                    score = (h5 * 2.5) + wk - (calls * 0.5)

            scores[acc] = score
        return scores

    def get_current_account(self) -> str:
        with _POOL_LOCK:
            if not self.accounts:
                return "acc1"
            return self.accounts[self._current_idx % len(self.accounts)]

    def rotate_to_next(self) -> str:
        with _POOL_LOCK:
            if not self.accounts:
                return "acc1"
            self._current_idx = (self._current_idx + 1) % len(self.accounts)
            return self.accounts[self._current_idx % len(self.accounts)]

    def acquire_account(self, exclude: Optional[Set[str]] = None, model: str = DEFAULT_MODEL) -> str:
        """Acquires the optimal healthy account from the 8-account pool for the specific model."""
        with _POOL_LOCK:
            excluded = exclude or set()
            scores = self._get_account_scores(model=model)

            # Filter out excluded accounts
            available = [acc for acc in self.accounts if acc not in excluded]
            if not available:
                available = self.accounts

            # Prefer accounts not currently busy
            idle_candidates = [acc for acc in available if acc not in _BUSY_ACCOUNTS]
            pool_to_pick = idle_candidates if idle_candidates else available

            # Sort by health score descending (highest quota first!)
            pool_to_pick.sort(key=lambda acc: scores.get(acc, 0.0), reverse=True)

            # Group the top-tier healthy accounts (within 20 points of best score)
            best_score = scores.get(pool_to_pick[0], 0.0)
            top_group = [acc for acc in pool_to_pick if (best_score - scores.get(acc, 0.0)) <= 20.0]

            # Round-robin across the top-tier group to distribute load perfectly
            chosen = None
            for i in range(len(top_group)):
                candidate = top_group[(self._current_idx + i) % len(top_group)]
                chosen = candidate
                self._current_idx = (self._current_idx + i + 1) % len(top_group)
                break

            if not chosen:
                chosen = pool_to_pick[0]

            _BUSY_ACCOUNTS.add(chosen)
            self._sync_active_state()
            return chosen

    def release_account(self, acc: str) -> None:
        """Releases an account back to idle pool."""
        with _POOL_LOCK:
            _BUSY_ACCOUNTS.discard(acc)
            self._sync_active_state()

    def _sync_active_state(self) -> None:
        """Syncs active accounts to disk for UI visualization."""
        try:
            data = load_account_usage()
            data["active_accounts"] = list(_BUSY_ACCOUNTS)
            save_account_usage(data)
        except Exception:
            pass

    def switch_to(self, acc: str, with_lock: bool = True) -> bool:
        try:
            sys.path.insert(0, r"C:\Users\nguye\agy-profiles")
            import agy_profile
            return agy_profile.switch_profile(acc, with_lock=with_lock)
        except Exception:
            cmd = ["python", r"C:\Users\nguye\agy-profiles\agy_profile.py", "switch", acc]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
            return res.returncode == 0


GLOBAL_POOL = AgyAccountPool()


def find_agy_binary() -> str:
    """Finds the agy CLI binary executable."""
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    if candidate.is_file():
        return str(candidate)
    which = shutil.which("agy")
    if which:
        return which
    raise FileNotFoundError("Could not find agy.exe. Ensure Google Antigravity CLI is installed.")


def call_gemini(
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 120,
    system_instruction: Optional[str] = None,
    allow_fallback: bool = True,
) -> str:
    """Executes prompt via agy CLI with safe thread concurrency, multi-account pool,
    and automatic failover to Claude Sonnet 4.6 & GPT-OSS when Gemini quota is exhausted."""
    agy_bin = find_agy_binary()
    full_prompt = prompt
    if system_instruction:
        full_prompt = f"[SYSTEM INSTRUCTION]:\n{system_instruction}\n\n[USER PROMPT]:\n{prompt}"

    # Determine model failover sequence
    models_to_try = [model]
    if allow_fallback and "gemini" in model.lower():
        models_to_try.append(CLAUDE_MODEL)  # "claude-sonnet-4-6"
        models_to_try.append(GPT_MODEL)     # "gpt-oss-120b-medium"

    last_error = ""

    for active_model in models_to_try:
        if active_model != model:
            print(f"[Multi-Account Pool] ⚡ TỰ ĐỘNG CHUYỂN MODEL DỰ PHÒNG: Sang '{active_model}' do Gemini cạn quota...")

        num_accounts = max(1, len(GLOBAL_POOL.accounts))
        tried_accounts: Set[str] = set()
        model_exhausted = False

        for attempt in range(num_accounts):
            acc = GLOBAL_POOL.acquire_account(exclude=tried_accounts, model=active_model)
            tried_accounts.add(acc)
            t_start = time.time()

            # Fast check: If the acquired account has score < -2000 on attempt 0, all accounts are out of quota for this model
            scores = GLOBAL_POOL._get_account_scores(model=active_model)
            if scores.get(acc, 0.0) < -2000 and attempt == 0:
                GLOBAL_POOL.release_account(acc)
                print(f"[Multi-Account Pool] Toàn bộ {len(GLOBAL_POOL.accounts)} tài khoản đều cạn hạn mức cho '{active_model}'. Đổi sang model tiếp theo...")
                model_exhausted = True
                break

            env = os.environ.copy()
            session_dir = GLOBAL_POOL.sessions_dir / acc
            if session_dir.exists():
                env["USERPROFILE"] = str(session_dir)
                env["HOME"] = str(session_dir)

            cmd = [
                agy_bin,
                "--model", active_model,
                "--output-format", "text",
                "--print-timeout", f"{timeout_seconds}s",
            ]

            try:
                # Stagger credential switch & process spawn using system-wide Named Mutex
                sys.path.insert(0, r"C:\Users\nguye\agy-profiles")
                try:
                    from agy_profile import profile_switch_lock
                except ImportError:
                    profile_switch_lock = None

                if profile_switch_lock:
                    with profile_switch_lock(timeout_ms=30000):
                        GLOBAL_POOL.switch_to(acc, with_lock=False)
                        proc = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            env=env,
                            creationflags=NO_WINDOW,
                        )
                        time.sleep(0.8)  # Allow agy.exe to read Windows Credential on startup
                else:
                    with _SWITCH_LOCK:
                        GLOBAL_POOL.switch_to(acc)
                        proc = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            env=env,
                            creationflags=NO_WINDOW,
                        )
                        time.sleep(0.8)

                # Execute communication in parallel outside the switch lock!
                out, err = proc.communicate(input=full_prompt, timeout=timeout_seconds + 30)
                latency = time.time() - t_start

                if proc.returncode != 0:
                    err_msg = (err or "").strip()
                    last_error = err_msg
                    record_account_call(acc, success=False, latency_s=latency, error_msg=err_msg)
                    if any(w in err_msg.lower() for w in ("quota", "limit", "429", "resource_exhausted")):
                        print(f"[Multi-Account Pool] Tài khoản {acc} chạm quota '{active_model}'. Thử tài khoản khác...")
                        try:
                            if SERVER_LIMITS_FILE.exists():
                                s_data = json.loads(SERVER_LIMITS_FILE.read_text(encoding="utf-8"))
                                if acc in s_data:
                                    s_data[acc]["five_hour_remaining"] = 0.0
                                    s_data[acc]["updated_at"] = datetime.datetime.now().strftime("%H:%M:%S %d/%m")
                                    SERVER_LIMITS_FILE.write_text(json.dumps(s_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                        continue
                    print(f"[Multi-Account Pool] Lỗi gọi '{active_model}' trên {acc}: {err_msg[:100]}. Thử tiếp...")
                    continue

                out = (out or "").strip()
                if not out:
                    last_error = f"agy trả về output rỗng với model {active_model}"
                    record_account_call(acc, success=False, latency_s=latency, error_msg="output rỗng")
                    print(f"[Multi-Account Pool] agy trả về output rỗng trên {acc} ({active_model}). Thử tiếp...")
                    continue

                record_account_call(acc, success=True, latency_s=latency)
                return out

            finally:
                GLOBAL_POOL.release_account(acc)

        if model_exhausted:
            continue

    raise RuntimeError(f"Tất cả tài khoản và model dự phòng (Gemini/Claude/GPT) đều cạn quota hoặc lỗi: {last_error}")


def call_gemini_parallel(
    prompts: List[str],
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 120,
    system_instruction: Optional[str] = None,
) -> List[str]:
    """Executes multiple prompts concurrently across the 8-account pool."""
    if not prompts:
        return []
    max_workers = min(len(prompts), len(GLOBAL_POOL.accounts))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(call_gemini, p, model, timeout_seconds, system_instruction)
            for p in prompts
        ]
        return [f.result() for f in futures]


def extract_json(raw_text: str) -> Any:
    """Extracts JSON object or array from LLM response text."""
    text = raw_text.strip()
    # Match ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass

    # Match first { to last } or [ to ]
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = text[brace_start:brace_end + 1]
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass

    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidate = text[bracket_start:bracket_end + 1]
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass

    return json.loads(text, strict=False)


@dataclass
class EvaluationResult:
    approved: bool
    score: float
    fandom: str
    summary: str
    reasoning: str
    suggested_tags: List[str] = field(default_factory=list)
    content_safety: str = "PASS"


def evaluate_content(
    title: str,
    description_or_snippet: str,
    source_type: str = "general",
    threshold: float = QUALITY_THRESHOLD,
) -> EvaluationResult:
    """Evaluates whether content meets quality standards for fanfic.world."""
    prompt = f"""Bạn là chuyên gia thẩm định nội dung cho nền tảng fanfic.world.
Hãy phân tích và đánh giá chất lượng của tác phẩm/nội dung dưới đây:

[Nguồn]: {source_type}
[Tiêu đề]: {title}
[Mô tả / Đoạn trích]:
{description_or_snippet[:3000]}

Tiêu chuẩn đánh giá:
1. Thang điểm 0.0 đến 10.0 (chất lượng cốt truyện, độ hấp dẫn, độ mượt mà, tính giải trí).
2. Kiểm tra an toàn nội dung (PASS hoặc FLAG nếu vi phạm đạo đức nghiêm trọng, chính trị nhạy cảm).
3. Xác định Fandom / Thể loại (ví dụ: Naruto, Harry Potter, Tiên Hiệp, Đô Thị, Re:Zero...).
4. Đề xuất danh sách thẻ (tags).
5. QUY TẮC CẤM TUYỆT ĐỐI: KHÔNG BAO GIỜ DUYỆT (gán approved = false, score = 0.0, content_safety = 'FLAG') đối với bất kỳ nội dung Đam Mỹ, Boy Love (BL), Yaoi, Danmei, đồng tính nam. Phải từ chối ngay lập tức!

BẮT BUỘC trả về ĐÚNG MỘT JSON OBJECT theo cấu trúc:
```json
{{
  "score": 8.2,
  "approved": true,
  "fandom": "Tên fandom hoặc thể loại",
  "summary": "Tóm tắt ngắn 2-3 câu về nội dung",
  "reasoning": "Giải thích chi tiết tại sao đạt hay không đạt",
  "suggested_tags": ["tag1", "tag2", "tag3"],
  "content_safety": "PASS"
}}
```
Chỉ trả về JSON, không kèm lời chào hay giải thích ngoài JSON.
"""
    raw = call_gemini(prompt, model=DEFAULT_MODEL, timeout_seconds=60)
    try:
        data = extract_json(raw)
        score = float(data.get("score", 0.0))
        approved = bool(score >= threshold and data.get("content_safety", "PASS") == "PASS")
        return EvaluationResult(
            approved=approved,
            score=score,
            fandom=str(data.get("fandom", "Đồng Nhân")),
            summary=str(data.get("summary", "")),
            reasoning=str(data.get("reasoning", "")),
            suggested_tags=list(data.get("suggested_tags", [])),
            content_safety=str(data.get("content_safety", "PASS")),
        )
    except Exception as exc:
        return EvaluationResult(
            approved=False,
            score=0.0,
            fandom="Không rõ",
            summary=title,
            reasoning=f"Lỗi parse thẩm định từ Gemini: {exc}. Nội dung thô: {raw[:200]}",
            suggested_tags=[],
            content_safety="UNKNOWN",
        )


def generate_fanfic_world_metadata(
    title: str,
    text_context: str,
    author: str = "Tác giả mạng",
    source_url: str = "",
    fandom_hint: str = "",
) -> Dict[str, Any]:
    """Generates production-ready Vietnamese title, SEO description, and metadata for fanfic.world."""
    prompt = f"""Bạn là biên tập viên trưởng của nền tảng truyện và audio fanfic.world.
Hãy biên soạn gói thông tin xuất bản hoàn chỉnh, hấp dẫn cho tác phẩm sau:

[Tiêu đề gốc]: {title}
[Tác giả]: {author}
[Link nguồn]: {source_url}
[Gợi ý Fandom]: {fandom_hint}
[Nội dung tham khảo / Tóm tắt]:
{text_context[:4000]}

Yêu cầu xuất bản:
1. `title_vi`: ĐẶT TỰA ĐỀ MỚI ĐỘC QUYỀN CHO BỘ TRUYỆN:
   - Giữ trọn vẹn điểm cuốn hút, nhân vật chính, fandom và bối cảnh.
   - TUYỆT ĐỐI KHÔNG COPY y nguyên tiêu đề YouTube gốc (để bảo vệ bản quyền và phong cách xuất bản độc quyền, không để lộ nguồn gốc video).
   - Đặt tên theo phong cách tiểu thuyết / web novel đỉnh cao, hào hùng, cuốn hút (ví dụ: thay vì "Tôi Có Thể Biến Thành Super Saiyan Ở Thời Đại Rocks - One Piece Fanfic", hãy viết lại thành: "Kỷ Nguyên Rocks: Ta Thức Tỉnh Huyết Mạch Siêu Saiyan").
2. `description_vi`: Đoạn mô tả chi tiết khoảng 150-250 chữ gồm:
   - Dẫn nhập cốt truyện kích thích trí tò mò
   - Điểm độc đáo của nhân vật chính hoặc tình huống biến cố
   - Lời kêu gọi độc giả/người nghe cùng trải nghiệm
3. `summary`: Tóm tắt cốt lõi trong 2-3 câu ngắn.
4. `fandom`: Xác định chính xác vũ trụ/thể loại (ví dụ: "Naruto", "Harry Potter", "Genshin Impact", "Tiên Hiệp").
5. `tags`: 5 đến 8 từ khóa hot (ví dụ: ["xuyên không", "hệ thống", "đồng nhân", "hắc hóa", "naruto"]).
6. `rating`: "General", "Teen", hoặc "Mature".

BẮT BUỘC trả về ĐÚNG MỘT JSON OBJECT:
```json
{{
  "title_vi": "...",
  "description_vi": "...",
  "summary": "...",
  "fandom": "...",
  "tags": ["..."],
  "rating": "General"
}}
```
Chỉ trả về JSON, không kèm bất kỳ giải thích nào khác.
"""
    raw = call_gemini(prompt, model=DEFAULT_MODEL, timeout_seconds=90)
    try:
        data = extract_json(raw)
        return {
            "title_vi": data.get("title_vi", title),
            "description_vi": data.get("description_vi", text_context[:200]),
            "summary": data.get("summary", ""),
            "fandom": data.get("fandom", fandom_hint or "Đồng Nhân"),
            "tags": list(data.get("tags", ["fanfic", "audiobook"])),
            "rating": data.get("rating", "General"),
            "author": author,
            "source_url": source_url,
        }
    except Exception as exc:
        return {
            "title_vi": title,
            "description_vi": text_context[:300],
            "summary": title,
            "fandom": fandom_hint or "Đồng Nhân",
            "tags": ["fanfic"],
            "rating": "General",
            "author": author,
            "source_url": source_url,
            "_error": str(exc),
        }


def translate_text(
    text: str,
    source_lang: str = "auto",
    target_lang: str = "vi",
    context_notes: str = "",
) -> str:
    """Translates text to natural, fluent Vietnamese novel style."""
    prompt = f"""Hãy dịch đoạn văn bản sau sang tiếng Việt mượt mà, đậm chất văn học tiểu thuyết / truyện fanfic.
Giữ chuẩn danh xưng nhân vật, các thuật ngữ võ thuật/phép thuật phù hợp phong cách đọc truyện.
Không cắt xén nội dung, không thêm lời bình luận.

[Ghi chú bối cảnh]: {context_notes or 'Truyện novel / fanfic'}
[Văn bản cần dịch]:
{text}
"""
    return call_gemini(prompt, model=DEFAULT_MODEL, timeout_seconds=120)
