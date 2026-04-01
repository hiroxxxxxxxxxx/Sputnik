COCKPIT_BOT_COMMANDS_MESSAGE = (
    "Sputnik Cockpit Bot\n"
    "/ping … 接続・設定確認\n"
    "/cockpit または /status … 現在の計器（IB から取得）\n"
    "/daily … Daily Flight Log（市場・資本・各層）\n"
    "/position … ポジション明細 + target 差分\n"
    "/breakdown … 各因子の計算内訳（Layer 2 シグナル）\n"
    "/health … IB 接続と whatIf のヘルスチェック\n"
    "/schedule … 取引時間スキャン（夏冬・短縮・休場の事前通知）\n"
    "/altitude … 現在の高度設定を表示\n"
    "/setaltitude <high|mid|low> … 高度設定を更新（要管理者 user_id）\n"
    "/sbaseline … 現在の S baseline（NQ/GC）を表示\n"
    "/setsbaseline <nq|gc|mnq|mgc> <mm_per_lot> … S baseline を更新（要管理者 user_id）\n"
    "/mode … 現在の ap_mode / execution_lock を表示\n"
    "/setmode <Manual|SemiAuto|Auto> … ap_mode を更新（要管理者 user_id）\n"
    "/setlock <on|off> … execution_lock を更新（要管理者 user_id）\n"
    "/target … target_base_futures（MNQ/MGC 相当 + 現在高度の有効legs）\n"
    "/settarget <mnq|mgc|nq|gc> <base> … 該当側のみ更新（要管理者 user_id）"
)

COCKPIT_FETCH_TIMEOUT = 90
