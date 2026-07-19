"""Tests for the shared Script Sentence parser.

Covers the parser contract from issue #175 / ADR 0005:
- sentence-ending punctuation (。！？!?) and line breaks end a sentence
- clause punctuation does not split sentences
- empty lines are ignored
- punctuation is preserved as part of the sentence text
"""

from __future__ import annotations

from packages.pipeline_services.script_sentence import parse_script_sentences


class TestParseScriptSentences:
    def test_splits_on_sentence_end_punctuation(self) -> None:
        text = "第一句。第二句！第三句？"
        assert parse_script_sentences(text) == ["第一句。", "第二句！", "第三句？"]

    def test_preserves_punctuation(self) -> None:
        text = "今天真好。"
        assert parse_script_sentences(text) == ["今天真好。"]

    def test_ignores_empty_lines(self) -> None:
        text = "第一句。\n\n第二句。"
        assert parse_script_sentences(text) == ["第一句。", "第二句。"]

    def test_ignores_whitespace_only_lines(self) -> None:
        text = "第一句。\n   \n第二句。"
        assert parse_script_sentences(text) == ["第一句。", "第二句。"]

    def test_does_not_split_on_clause_punctuation(self) -> None:
        text = "你好，世界；今天天气，晴朗。"
        assert parse_script_sentences(text) == ["你好，世界；今天天气，晴朗。"]

    def test_line_break_ends_sentence(self) -> None:
        text = "第一行\n第二行"
        assert parse_script_sentences(text) == ["第一行", "第二行"]

    def test_line_break_after_punctuation_does_not_duplicate(self) -> None:
        text = "第一句。\n第二句。"
        assert parse_script_sentences(text) == ["第一句。", "第二句。"]

    def test_mixed_clause_and_sentence_punctuation(self) -> None:
        text = "今天，天气很好；我们出去玩！回来再吃饭。"
        assert parse_script_sentences(text) == [
            "今天，天气很好；我们出去玩！",
            "回来再吃饭。",
        ]

    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_script_sentences("") == []

    def test_only_whitespace_returns_empty_list(self) -> None:
        assert parse_script_sentences("   \n\t  ") == []

    def test_western_sentence_end_punctuation(self) -> None:
        text = "Hello world! How are you? I am fine."
        assert parse_script_sentences(text) == [
            "Hello world!",
            "How are you?",
            "I am fine.",
        ]

    def test_mixed_western_and_chinese_punctuation(self) -> None:
        text = "Hello! 你好。How are you?"
        assert parse_script_sentences(text) == [
            "Hello!",
            "你好。",
            "How are you?",
        ]
