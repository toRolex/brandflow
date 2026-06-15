"""Tests for LLM sentence classification factory."""

import json
from unittest.mock import patch, Mock
from packages.pipeline_services.asset_library.classify import create_classify_fn


def _mock_llm_response(content: str):
    """创建模拟的 LLM API 响应。"""
    resp = Mock()
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode("utf-8")
    return resp


class TestClassifyFn:
    def test_classify_returns_category_name(self):
        """分类函数应返回合法的中文分类名。"""
        mock_resp = _mock_llm_response('{"category": "烹饪翻炒"}')

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
            )
            result = fn("翻炒均匀后出锅装盘。")

        assert result == "烹饪翻炒"

    def test_classify_returns_none_on_parse_failure(self):
        """LLM 返回无效 JSON 时应返回 None。"""
        mock_resp = _mock_llm_response("not json at all")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
            )
            result = fn("随便一句话。")

        assert result is None

    def test_classify_prompt_includes_sentence(self):
        """Prompt 应包含待分类的句子。"""
        sentence = "今天上山采菌子。"
        mock_resp = _mock_llm_response('{"category": "产地溯源"}')

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
            )
            result = fn(sentence)

        assert result == "产地溯源"
        call_args = mock_urlopen.call_args[0][0]
        req_body = json.loads(call_args.data)
        messages = req_body["messages"]
        assert any(sentence in msg["content"] for msg in messages)

    def test_classify_returns_none_on_http_error(self):
        """HTTP 请求失败时应返回 None。"""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("connection refused")
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
            )
            result = fn("测试句子就是这样的。")

        assert result is None
