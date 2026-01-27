"""Pure functions for building strings and objects.

文字列の組み立てや選択肢の生成を行う純粋関数群。
UI やロジックで使う値を生成するが、副作用は持たない。
"""

# チャンネル名のデフォルトテンプレート。{name} がオーナー名に置き換わる
DEFAULT_CHANNEL_TEMPLATE = "{name}'s Channel"


def build_channel_name(
    owner_name: str, template: str = DEFAULT_CHANNEL_TEMPLATE
) -> str:
    """オーナー名からチャンネル名を生成する。

    Args:
        owner_name: チャンネルオーナーの表示名 (display_name)
        template: テンプレート文字列。{name} がオーナー名に置換される

    Returns:
        生成されたチャンネル名 (例: "太郎's Channel")
    """
    return template.replace("{name}", owner_name)


def build_user_limit_options() -> list[tuple[str, int]]:
    """人数制限セレクトメニューの選択肢を生成する。

    Returns:
        (表示ラベル, 値) のタプルのリスト。
        例: [("No Limit", 0), ("2 Users", 2), ...]
    """
    return [
        ("No Limit", 0),
        ("2 Users", 2),
        ("5 Users", 5),
        ("10 Users", 10),
        ("15 Users", 15),
        ("25 Users", 25),
        ("50 Users", 50),
    ]


def truncate_name(name: str, max_length: int = 100) -> str:
    """チャンネル名を Discord の制限に収まるように切り詰める。

    100 文字を超える場合、末尾を "..." に置き換える。

    Args:
        name: 切り詰め対象の文字列
        max_length: 最大文字数 (デフォルト: 100 = Discord の上限)

    Returns:
        切り詰め後の文字列。制限内ならそのまま返す
    """
    if len(name) <= max_length:
        return name
    return name[: max_length - 3] + "..."
