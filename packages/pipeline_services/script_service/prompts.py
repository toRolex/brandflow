from __future__ import annotations

DEFAULT_BRAND = "滋元堂"
DEFAULT_SCENE = "云南山野鲜菌、家庭餐桌、朋友尝鲜、送礼分享"
DEFAULT_MATERIAL = "菌子近景、清洗切片、热锅翻炒、端上餐桌"

_SYSTEM_PROMPT = (
    "你是一位短视频文案专家，专门为食用菌产品撰写抖音口播文案。\n"
    "要求：口语化、节奏感强、每句话不超过20字、不使用emoji。\n"
    "必须在文案中恰当地提到「充分烹熟」这个食品安全提示。\n"
    "品名只能出现1次，品牌只能出现1次。"
)


def build_first_half_messages(
    product: str,
    brand: str,
    scene: str = DEFAULT_SCENE,
    material: str = DEFAULT_MATERIAL,
    custom_prompt: str = "",
) -> list[dict[str, str]]:
    """构建前半段（4句）的 LLM messages。"""
    user_content = (
        f"请为「{product}」（品牌：{brand}）撰写短视频口播文案的前半段（前4句）。\n"
        f"场景：{scene}\n"
        f"素材画面：{material}\n"
        f"要求：\n"
        f"1. 恰好4句话\n"
        f"2. 口语化，适合抖音口播\n"
        f"3. 品名「{product}」在前半段出现1次\n"
        f"4. 品牌「{brand}」不在前半段出现（留给后半段）\n"
        f"5. 每句话不超过20个字\n"
        f"6. 不使用任何emoji\n"
        f"7. 不提及医疗功效\n"
    )
    if custom_prompt:
        user_content += f"\n额外要求：{custom_prompt}\n"
    user_content += (
        "\n请以 JSON 格式返回，格式如下：\n"
        '{"sentence_1": "...", "sentence_2": "...", "sentence_3": "...", "sentence_4": "..."}'
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_second_half_messages(
    product: str,
    brand: str,
    scene: str = DEFAULT_SCENE,
    material: str = DEFAULT_MATERIAL,
    first_half: str = "",
    first_length: int = 0,
    custom_prompt: str = "",
) -> list[dict[str, str]]:
    """构建后半段（4句）的 LLM messages。"""
    user_content = (
        f"这是「{product}」短视频口播文案的前半段（{first_length}字）：\n"
        f"{first_half}\n\n"
        f"请续写后半段（后4句），要求：\n"
        f"1. 恰好4句话\n"
        f"2. 与前半段自然衔接\n"
        f"3. 品牌「{brand}」在后半段出现恰好1次\n"
        f"4. 品名「{product}」不在后半段重复\n"
        f"5. 必须包含「充分烹熟」\n"
        f"6. 每句话不超过20个字\n"
        f"7. 不使用任何emoji\n"
        f"8. 不提及医疗功效\n"
    )
    if custom_prompt:
        user_content += f"\n额外要求：{custom_prompt}\n"
    user_content += (
        "\n请以 JSON 格式返回，格式如下：\n"
        '{"sentence_5": "...", "sentence_6": "...", "sentence_7": "...", "sentence_8": "..."}'
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


_CANTONESE_SYSTEM_PROMPT = (
    "你是一位粤语短视频文案专家，专门将普通话口播文案转换为地道的口语化粤语。\n"
    "要求：\n"
    "1. 使用地道粤语口语表达（如「嘅」「咗」「嚟」「緊」「喺」「冇」「啲」「㗎」等粤语常用字）\n"
    "2. 保持原文案的信息完整性和结构\n"
    "3. 将「充分烹熟」转换为粤语同义表达（如「徹底煮熟」或「煮到熟透」）\n"
    "4. 不使用emoji\n"
    "5. 不提及医疗功效\n"
    "6. 直接返回转换后的粤语全文，不要加任何解释或前缀"
)


def build_cantonese_conversion_messages(
    mandarin_text: str,
    product: str,
    brand: str,
) -> list[dict[str, str]]:
    """构建普通话→粤语转换的 LLM messages。"""
    user_content = (
        f"请将以下普通话短视频口播文案转换为口语化粤语：\n\n"
        f"{mandarin_text}\n\n"
        f"注意：\n"
        f"- 品名「{product}」保持原样\n"
        f"- 品牌「{brand}」保持原样\n"
        f"- 食品安全提示需用粤语同义表达（如「徹底煮熟」）\n"
        f"- 保持原文案的结构和节奏\n"
        f"- 直接返回粤语全文，不要加任何解释"
    )
    return [
        {"role": "system", "content": _CANTONESE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
