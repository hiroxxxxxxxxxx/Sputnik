"""
レポート用 Jinja2 テンプレートの共通レンダリング。

責務境界:
- Python（format_*_report.py）: データ取得・ビジネスルール・値のフォーマット（数値→文字列、単位、桁など）。
  context には「フォーマット済みの値」のみ渡す（例: level="0", date_iso="2026-03-09", rows=[{factor, lv, value}]）。
  表示文言（見出し・ラベル・「|」の並びなど）は組み立てない。
- テンプレート: 表示文言とレイアウトを記載。見出し・表の形式・区切り線・「どこにどの変数を置くか」をテンプレート側で書く。
  {{ section.level }} のようにフォーマット済みの値を挿入する。
"""

from pathlib import Path
from typing import Any

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render(template_name: str, context: dict[str, Any]) -> str:
    """
    templates/ 直下のテンプレートをレンダリングする。
    context は表示用に整えた値のみ渡すこと（責務境界はモジュール docstring 参照）。

    :param template_name: ファイル名（例: daily_report.txt）。
    :param context: テンプレート変数（表示用文字列 or そのリスト）。
    :return: レンダリング済みテキスト。
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(template_name).render(**context)
