from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import main_controller as mc


TARGET_MIN_CHARS = 150
TARGET_MAX_CHARS = 200
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_BRAND = "滋元堂"
DEFAULT_SCENE = "云南山野鲜菌、家庭餐桌、朋友尝鲜、送礼分享"
DEFAULT_MATERIAL = "菌子近景、清洗切片、热锅翻炒、端上餐桌"
FORBIDDEN_TERMS = ["治疗", "治愈", "疗效", "降血糖", "降血压", "抗癌", "药到病除"]
MAX_GENERATION_ATTEMPTS = mc.SCRIPT_GENERATION_MAX_ATTEMPTS
SPECIAL_BYPASS_TOKEN = mc.SCRIPT_SPECIAL_BYPASS_TOKEN


def compact_len(text: str) -> int:
    return mc.compact_text_length(text)


def normalize_text(text: str) -> str:
    text = mc.EMOJI_RE.sub("", str(text or ""))
    text = re.sub(r"\s+", "", text)
    text = text.replace("!", "。").replace("！", "。").replace("?", "。").replace("？", "。")
    text = re.sub(r"。+", "。", text)
    return text.strip("。 \t\r\n") + ("。" if text.strip("。 \t\r\n") else "")


def split_sentences(text: str) -> list[str]:
    return [item.strip("，,。！？!? \t\r\n") for item in re.split(r"[。！？!?]", text or "") if item.strip("，,。！？!? \t\r\n")]


def join_sentences(sentences: list[str]) -> str:
    cleaned = [item.strip("，,。！？!? \t\r\n") for item in sentences if item.strip("，,。！？!? \t\r\n")]
    return "。".join(cleaned) + ("。" if cleaned else "")


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回可解析的 JSON")
    return json.loads(text[start : end + 1])


def extract_half_text(payload: dict[str, Any], half_key: str, sentence_numbers: list[int]) -> str:
    sentence_values = []
    for number in sentence_numbers:
        for key in [f"sentence_{number}", f"s{number}", f"第{number}句"]:
            value = str(payload.get(key, "") or "").strip()
            if value:
                sentence_values.append(value)
                break
    if sentence_values:
        return normalize_text(join_sentences(sentence_values))
    return normalize_text(payload.get(half_key) or payload.get("video_script") or "")


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\s]+', "_", value.strip())
    return (cleaned or "product")[:40]


def validate_script(text: str, product: str, brand: str) -> dict[str, Any]:
    sentences = split_sentences(text)
    total = compact_len(text)
    first_sentence = sentences[0] if sentences else ""
    last_sentence = sentences[-1] if sentences else ""
    forbidden_hits = [term for term in FORBIDDEN_TERMS if term in text]
    check = {
        "total_chars": total,
        "sentence_count": len(sentences),
        "first_sentence_chars": compact_len(first_sentence),
        "last_sentence_chars": compact_len(last_sentence),
        "product_count": text.count(product),
        "brand_count": text.count(brand),
        "has_fully_cooked": "充分烹熟" in text,
        "has_emoji": bool(mc.EMOJI_RE.search(text)),
        "forbidden_hits": forbidden_hits,
    }
    check["pass_flag"] = (
        TARGET_MIN_CHARS <= total <= TARGET_MAX_CHARS
        and check["product_count"] == 1
        and check["brand_count"] == 1
        and check["has_fully_cooked"]
        and not check["has_emoji"]
        and not forbidden_hits
    )
    return check


def throttle_before_call(throttle_path: Path, interval_seconds: float, label: str) -> float:
    throttle_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = throttle_path.with_suffix(".lock")
    lock_fd: int | None = None
    deadline = time.time() + 60
    while lock_fd is None:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError:
            if time.time() > deadline:
                raise TimeoutError(f"等待 LLM 节流锁超时：{lock_path}")
            if time.time() - lock_path.stat().st_mtime > 120:
                lock_path.unlink(missing_ok=True)
                continue
            time.sleep(0.2)

    try:
        last_started_at = 0.0
        if throttle_path.exists():
            try:
                last_started_at = float(json.loads(throttle_path.read_text(encoding="utf-8")).get("last_started_at", 0.0))
            except (ValueError, json.JSONDecodeError):
                last_started_at = 0.0
        wait_seconds = max(0.0, interval_seconds - (time.time() - last_started_at))
        if wait_seconds > 0:
            print(f"[{label}] LLM 节流等待 {wait_seconds:.1f} 秒...")
            time.sleep(wait_seconds)
        throttle_path.write_text(
            json.dumps({"last_started_at": time.time(), "label": label}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return wait_seconds
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def post_llm(payload: dict[str, Any], throttle_path: Path, interval_seconds: float, label: str) -> dict[str, Any]:
    mc.require_dependency("requests", mc.requests)
    provider = (os.getenv("LLM_PROVIDER", "deepseek").strip() or "deepseek").lower()
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        api_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    elif provider == "kimi":
        api_key = os.getenv("KIMI_API_KEY", "").strip()
        api_url = os.getenv("KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions")
        model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
    else:
        raise RuntimeError(f"暂不支持的 LLM_PROVIDER: {provider}")
    if not api_key:
        raise RuntimeError(f"缺少 {provider.upper()} API Key，请先在 .env 中配置。")
    throttle_before_call(throttle_path, interval_seconds, label)
    request_payload = dict(payload)
    request_payload["model"] = request_payload.get("model") or model
    if provider == "deepseek" and "thinking" not in request_payload:
        request_payload["thinking"] = {"type": "disabled"}
    response = mc.requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=request_payload,
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    return extract_json_object(body["choices"][0]["message"]["content"])


def first_half_payload(product: str, brand: str, scene: str, material: str, custom_prompt: str = "") -> dict[str, Any]:
    user_content = (
        f"产品：{product}。\n"
        f"场景：{scene}。\n"
        f"素材想象：{material}。\n"
        "前半段任务：写开场、品名、山野鲜菌画面、家庭餐桌期待感。\n"
        "输出字段：sentence_1, sentence_2, sentence_3, sentence_4, first_half, structure_check, pass_flag。"
    )
    if custom_prompt:
        user_content += f"\n\n额外要求：{custom_prompt}"

    return {
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    '你是"滋元堂脚本文案库"的前半段生成器。\n'
                    "你只生成 video_script 的前半段，不写标题、简介、标签，不写完整结尾，不写品牌 CTA。\n"
                    "目标：按爆款矩阵写到 90+ 分标准；下面的红线是你生成前的自检约束，不要输出红线解释。\n"
                    "硬规则：\n"
                    "1. 只输出 JSON。\n"
                    "2. 必须分别填写 sentence_1、sentence_2、sentence_3、sentence_4，再把四句合并为 first_half。\n"
                    '3. sentence_1 用自然短句；精准锁定爱吃菌、家常做饭或山野食材爱好者；必须给强认知反差或情绪共鸣；不用疑问句，直接给确定性钩子；禁止平铺直叙、自我介绍式、泛泛无指向，否则视为"开头无有效钩子"。\n'
                    f'4. sentence_2 18-24 字；严格承接 sentence_1；全文唯一一次出现"{product}"；同步带出核心价值或核心场景；禁止重复品名、脱离钩子跑题、提前植入品牌。\n'
                    '5. sentence_3 24-32 字；必须和菌子近景、清洗、切片画面 100% 同步；写清洗或切片动作细节；植入 1 个轻量绝对化记忆点，例如"别使劲搓揉"或"顺纹路轻刷"；口语化；禁止口画脱节、无关内容、长难句。\n'
                    "6. sentence_4 24-32 字；用具象化感官描述构建家庭餐桌真实食用场景；带出鲜、香、全家适配的期待感；禁止空泛表述，禁止任何功效类表述，只能写口感、场景、食用体验。\n"
                    f'7. 不出现"{brand}"，不出现"充分烹熟"，这两个留给后半段。\n'
                    "8. 禁 emoji，禁医疗功效，禁疾病治疗，禁夸大承诺。\n"
                    "9. 口语化，像真实短视频口播，不要文艺腔过重。"
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }


def second_half_payload(product: str, brand: str, scene: str, material: str, first_half: str, first_length: int, custom_prompt: str = "") -> dict[str, Any]:
    min_needed = max(90, TARGET_MIN_CHARS - first_length + 10)
    max_allowed = max(min_needed, min(115, TARGET_MAX_CHARS - first_length))

    user_content = (
        f"前半段全文：{first_half}\n"
        f"前半段本地统计：{first_length} 字。\n"
        f"产品：{product}。\n"
        f"场景：{scene}。\n"
        f"素材想象：{material}。\n"
        "后半段任务：继续写烹饪提醒、朋友/家庭分享、品牌轻收束。\n"
        "输出字段：sentence_5, sentence_6, sentence_7, sentence_8, second_half, structure_check, pass_flag。"
    )
    if custom_prompt:
        user_content += f"\n\n额外要求：{custom_prompt}"

    return {
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    '你是"滋元堂脚本文案库"的后半段生成器。\n'
                    "你没有记忆，下面会给你前半段全文。你只生成后半段，不要改写前半段，不要重复前半段。\n"
                    "目标：按爆款矩阵写到 90+ 分标准；下面的红线是你生成前的自检约束，不要输出红线解释。\n"
                    "硬规则：\n"
                    "1. 只输出 JSON。\n"
                    "2. 必须分别填写 sentence_5、sentence_6、sentence_7、sentence_8，再把四句合并为 second_half。\n"
                    f"3. second_half 合计目标 {min_needed}-{max_allowed} 个中文字符，宁可接近上限，不要缩水。\n"
                    f'4. sentence_5 26-34 字；必须自然包含"充分烹熟"；同步明确安全操作要求，给用户可落地的安全指引；强化安全记忆点；禁止省略安全提示，禁止"未炒熟也能吃"一类违规表达，禁止弱化安全要求。\n'
                    '5. sentence_6 24-32 字；构建具象家庭或朋友分享场景；明确指定转发/分享对象；给用户一个明确分享理由，例如帮到亲友或适合一起尝鲜；禁止"觉得有用就转发"这种模糊引导。\n'
                    '6. sentence_7 18-28 字；明确带出季节限定、原生态山野鲜或应季尝鲜价值；强化错过难寻的稀缺感；禁止使用"最、第一"等绝对化用语，禁止虚假宣传。\n'
                    f'7. sentence_8 简短自然；必须自然包含"{brand}"；搭配低门槛轻行动指令，例如认准、尝鲜、关注；禁止复杂高门槛指令，禁止引导私下交易，禁止生硬品牌植入。\n'
                    f'8. 不得再次出现"{product}"，用"这种菌子/这口山野鲜/这一盘"代称。\n'
                    "9. 禁 emoji，禁医疗功效，禁疾病治疗，禁夸大承诺。\n"
                    "10. 口语化承接前半段，不要写标题、简介、标签。"
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }


def mock_outputs(product: str, brand: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "first_half": f"大家好，今天要介绍的是来自山野的美味。{product}，这个名字听起来就让人充满期待。想象一下，新鲜的菌子在山林间生长，它们在雨后破土而出，带着泥土的芬芳。",
            "pass_flag": True,
        },
        {
            "second_half": f"在烹饪这一盘时，记得要充分烹熟，以确保食用安全。邀上三两好友，围坐一桌，分享这来自大自然的馈赠，入口鲜香，也能增进彼此情谊。想要更多山野鲜，不妨来{brand}看看。",
            "pass_flag": True,
        },
    )


def generate_script(args: argparse.Namespace) -> dict[str, Any]:
    root_dir = Path(__file__).resolve().parent
    mc.load_environment(root_dir)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    throttle_path = root_dir / "logs" / "llm_call_throttle.json"

    product = mc.project_product_name(args.product.strip())
    brand = args.brand.strip() or DEFAULT_BRAND
    custom_prompt = getattr(args, "custom_prompt", "") or ""
    attempts: list[dict[str, Any]] = []
    selected_attempt: dict[str, Any] | None = None
    for attempt_no in range(1, MAX_GENERATION_ATTEMPTS + 1):
        attempt: dict[str, Any] = {"attempt_no": attempt_no}
        try:
            if args.mock:
                first_raw, second_raw = mock_outputs(product, brand)
            else:
                first_raw = post_llm(
                    first_half_payload(product, brand, args.scene, args.material, custom_prompt),
                    throttle_path,
                    args.interval_seconds,
                    f"first_half_attempt_{attempt_no}",
                )
            first_half = extract_half_text(first_raw, "first_half", [1, 2, 3, 4])
            if not args.mock:
                second_raw = post_llm(
                    second_half_payload(product, brand, args.scene, args.material, first_half, compact_len(first_half), custom_prompt),
                    throttle_path,
                    args.interval_seconds,
                    f"second_half_attempt_{attempt_no}",
                )
            second_half = extract_half_text(second_raw, "second_half", [5, 6, 7, 8])
            combined = normalize_text(first_half.rstrip("。") + "。" + second_half.lstrip("。"))
            final_check = validate_script(combined, product, brand)
            attempt.update(
                {
                    "first_raw": first_raw,
                    "second_raw": second_raw,
                    "first_half": first_half,
                    "second_half": second_half,
                    "combined": combined,
                    "final_check": final_check,
                }
            )
            attempts.append(attempt)
            if final_check["pass_flag"]:
                selected_attempt = attempt
                break
            print(f"[attempt {attempt_no}/{MAX_GENERATION_ATTEMPTS}] 未通过本地质检，准备让 LLM 重新生成：{final_check}")
        except Exception as exc:  # noqa: BLE001
            attempt["error"] = str(exc)
            attempts.append(attempt)
            print(f"[attempt {attempt_no}/{MAX_GENERATION_ATTEMPTS}] 调用或解析失败：{exc}")

    script_special_bypass = False
    if selected_attempt is None:
        usable_attempts = [attempt for attempt in attempts if attempt.get("combined")]
        if not usable_attempts:
            raise RuntimeError(f"LLM 连续 {MAX_GENERATION_ATTEMPTS} 次失败，且没有可用正文。")
        selected_attempt = min(usable_attempts, key=lambda item: compact_len(item["combined"]))
        script_special_bypass = True

    first_raw = selected_attempt.get("first_raw", {})
    second_raw = selected_attempt.get("second_raw", {})
    first_half = selected_attempt.get("first_half", "")
    second_half = selected_attempt.get("second_half", "")
    combined = selected_attempt["combined"]
    initial_check = selected_attempt["final_check"]
    stabilization_actions: list[str] = []
    final_script = combined
    final_check = selected_attempt["final_check"]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{stamp}_{safe_filename(product)}_tts口播文案"
    txt_path = output_dir / f"{base_name}.txt"
    json_path = output_dir / f"{base_name}.json"
    txt_path.write_text(final_script + "\n", encoding="utf-8")
    audit_payload = {
        "product": product,
        "brand": brand,
        "scene": args.scene,
        "material": args.material,
        "mode": "mock" if args.mock else f"{os.getenv('LLM_PROVIDER', 'deepseek')}_two_stage",
        "target_chars": [TARGET_MIN_CHARS, TARGET_MAX_CHARS],
        "selected_attempt": selected_attempt.get("attempt_no"),
        "attempts": attempts,
        "script_special_bypass": script_special_bypass,
        "script_special_bypass_token": SPECIAL_BYPASS_TOKEN if script_special_bypass else "",
        "script_special_reason": "llm_three_attempts_failed_use_shortest" if script_special_bypass else "",
        "first_raw": first_raw,
        "second_raw": second_raw,
        "first_half": first_half,
        "second_half": second_half,
        "combined_before_stabilize": combined,
        "initial_check": initial_check,
        "stabilization_actions": stabilization_actions,
        "final_script": final_script,
        "final_check": final_check,
        "txt_path": str(txt_path),
    }
    json_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_payload["json_path"] = str(json_path)
    return audit_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="两段式 LLM 口播文案生成器，只输出给 TTS 使用的最终正文。")
    parser.add_argument("product", nargs="?", help="菌菇/品名，例如：荔枝菌、羊肚菌、松茸")
    parser.add_argument("--brand", default=DEFAULT_BRAND, help=f"品牌名，默认：{DEFAULT_BRAND}")
    parser.add_argument("--scene", default=DEFAULT_SCENE, help=f"场景描述，默认：{DEFAULT_SCENE}")
    parser.add_argument("--material", default=DEFAULT_MATERIAL, help=f"素材想象，默认：{DEFAULT_MATERIAL}")
    parser.add_argument("--output-dir", default="待配音文案", help="输出目录，默认：待配音文案")
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS, help="LLM 调用最小间隔秒数，默认 10")
    parser.add_argument("--mock", action="store_true", help="离线模拟，不调用 LLM，用于检查脚本流程")
    args = parser.parse_args()
    if not args.product:
        args.product = input("请输入菌菇/品名（默认：荔枝菌）：").strip() or "荔枝菌"
    return args


def main() -> int:
    try:
        result = generate_script(parse_args())
    except Exception as exc:  # noqa: BLE001
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1

    print("\n=== TTS 可用口播正文 ===")
    print(result["final_script"])
    print("\n=== 本地验收 ===")
    print(json.dumps(result["final_check"], ensure_ascii=False, indent=2))
    if result.get("script_special_bypass"):
        print(f"\n特殊放行：{SPECIAL_BYPASS_TOKEN}，三次未过时已选择 LLM 最短稿。")
    print(f"\n文案文件：{result['txt_path']}")
    print(f"审计文件：{result['json_path']}")
    return 0 if result["final_check"]["pass_flag"] or result.get("script_special_bypass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
