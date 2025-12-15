#!/usr/bin/env python3
"""
Regression tests for Telegram Markdown formatting in /llm_app output.

Production issue: Telegram rejected the /llm_app listing message with:
  BadRequest: Can't parse entities: can't find end of the entity ...

Root cause: app names like `ustc_preregister` contain underscores, which break
Telegram Markdown when not escaped.
"""

import sys
from pathlib import Path

import pytest


# Add parent directory to path for imports (consistent with other tests)
sys.path.insert(0, str(Path(__file__).parent.parent))


from commands.llm_app import _build_available_apps_message, get_llm_app_welcome_message


@pytest.mark.unit
class TestLLMAppMarkdownRegression:
    """Unit tests ensuring /llm_app messages are Markdown-safe."""

    def test_available_apps_message_does_not_include_raw_underscores(self) -> None:
        """App names with underscores must not appear unescaped in Markdown text."""
        apps = [
            {
                "name": "ustc_preregister",
                "description": "Deposit/withdraw USTC-cb for preregistration",
            },
            {"name": "swap", "description": "Swap tokens"},
        ]

        msg = _build_available_apps_message(apps)

        # Display name should be human-friendly (no underscore)
        assert "Ustc Preregister" in msg
        assert "Ustc_Preregister" not in msg

        # A raw underscore outside of code spans is what caused Telegram parsing failures.
        # We allow underscores inside inline code spans (backticks).
        def strip_inline_code_spans(text: str) -> str:
            in_code = False
            out = []
            for ch in text:
                if ch == "`":
                    in_code = not in_code
                    continue
                if not in_code:
                    out.append(ch)
            return "".join(out)

        assert "_" not in strip_inline_code_spans(msg)

    def test_welcome_message_is_markdown_safe_for_underscore_app_name(self) -> None:
        """Welcome header must not contain raw underscores when parse_mode=Markdown is used."""
        msg = get_llm_app_welcome_message(
            "ustc_preregister", "USTC+ Preregister - Deposit and withdraw USTC-cb"
        )
        assert "Ustc Preregister" in msg
        assert "_" not in msg


