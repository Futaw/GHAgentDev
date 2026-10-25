from __future__ import annotations

from typing import Final

DOCUMENT_TYPES: Final = {
    "functional_spec": {
        "label": "機能仕様",
        "description": "目的、入出力、状態、例外と制約を説明します。",
    },
    "technical_guide": {
        "label": "技術ガイド",
        "description": "構成要素、実装の流れ、主要な判断と拡張点を説明します。",
    },
    "process_flow": {
        "label": "処理フロー",
        "description": "開始条件、手順、分岐、終了条件と失敗経路を説明します。",
    },
}
DETAIL_LEVELS: Final = {
    "overview": {"label": "概要", "description": "要点に絞って説明します。"},
    "standard": {"label": "標準", "description": "主要な根拠と流れを説明します。"},
    "detailed": {"label": "詳細", "description": "例外や制約も含めて詳しく説明します。"},
}
TARGET_AUDIENCES: Final = {
    "engineer": {"label": "エンジニア", "description": "実装と技術的な根拠を重視します。"},
    "beginner": {"label": "初学者", "description": "用語をかみ砕いて説明します。"},
    "product_manager": {
        "label": "プロダクトマネージャー",
        "description": "責務、フロー、制約を重視します。",
    },
}
THEMES: Final = {
    "technical-light": {
        "label": "Technical Light",
        "description": "明るく技術文書向けの表示です。",
    },
    "editorial": {"label": "Editorial", "description": "長文を読みやすいエディトリアル表示です。"},
}
DENSITIES: Final = {
    "comfortable": {"label": "ゆったり", "description": "余白を広く取ります。"},
    "compact": {"label": "コンパクト", "description": "情報を密に表示します。"},
}


def viewer_options() -> dict[str, object]:
    def items(values: dict[str, dict[str, str]]) -> list[dict[str, str]]:
        return [{"value": key, **value} for key, value in values.items()]

    return {
        "document_types": items(DOCUMENT_TYPES),
        "detail_levels": items(DETAIL_LEVELS),
        "target_audiences": items(TARGET_AUDIENCES),
        "themes": items(THEMES),
        "densities": items(DENSITIES),
        "defaults": {
            "document_type": "functional_spec",
            "detail_level": "standard",
            "target_audience": "engineer",
            "theme_slug": "technical-light",
            "density": "comfortable",
        },
    }
